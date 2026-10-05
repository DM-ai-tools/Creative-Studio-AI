"""Prepare and verify exact narration before spending on video generation."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.ffmpeg_util import require_ffmpeg, probe_video_duration
from app.services.file_service import file_service


_CACHE_VERSION = "fit-exact-v2"


def _atempo_filter(speed: float) -> str:
    """Build an ffmpeg atempo chain for any speed-up greater than 1x."""
    factors: list[float] = []
    remaining = max(1.0, float(speed))
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    factors.append(remaining)
    return ",".join(f"atempo={factor:.6f}" for factor in factors)


def _write_pcm_wav(path: Path, samples: array, *, sample_rate: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(samples.tobytes())


def _fit_audio_to_window(source: Path, target: Path, *, duration: float, window: float) -> None:
    """Preserve the full spoken line while fitting it into its approved time window."""
    if duration <= window:
        shutil.copyfile(source, target)
        return
    # atempo changes timing without changing pitch. A tiny guard prevents encoder
    # rounding from leaving the result a few milliseconds beyond the scene window.
    speed = (duration / max(window, 0.05)) * 1.015
    proc = subprocess.run(
        [
            require_ffmpeg(), "-v", "error", "-y", "-i", str(source),
            "-af", _atempo_filter(speed), "-ac", "1", "-ar", "24000",
            "-c:a", "pcm_s16le", str(target),
        ],
        capture_output=True,
    )
    if proc.returncode:
        raise RuntimeError("Cannot fit prepared narration to the requested timing")


def _normalise_voice_line(path: Path) -> None:
    """Give every cached line the same perceived loudness and microphone profile."""
    target = path.with_suffix(".normalised.wav")
    proc = subprocess.run(
        [
            require_ffmpeg(), "-v", "error", "-y", "-i", str(path),
            "-af", "highpass=f=70,lowpass=f=14000,loudnorm=I=-16:TP=-1.5:LRA=7",
            "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(target),
        ],
        capture_output=True,
    )
    if proc.returncode or not target.is_file():
        target.unlink(missing_ok=True)
        raise RuntimeError("Cannot normalise prepared narration")
    target.replace(path)


def slice_prepared_narration(
    prepared: dict | None, *, start: float, end: float
) -> tuple[list[tuple[float, float, str]], dict | None]:
    """Rebase one immutable master-voice plan for a chapter preview."""
    if not prepared:
        return [], None
    events: list[tuple[float, float, str]] = []
    lines: list[dict] = []
    for item in prepared.get("lines") or []:
        a, b = float(item["start"]), float(item["end"])
        if a < start - 0.01 or b > end + 0.01:
            if a < end and b > start:
                raise ValueError(
                    "A narration line crosses a Seedance chapter boundary. Adjust its timing "
                    "before generation so the same full line is never split between calls."
                )
            continue
        if a >= start and b <= end:
            local = (a - start, b - start, str(item["text"]))
            events.append(local)
            lines.append({**item, "start": local[0], "end": local[1]})
    sliced = {**prepared, "lines": lines, "chapter_start": start, "chapter_end": end}
    return events, sliced


async def prepare_narration(events: list[tuple[float, float, str]], *, tenant_id: str,
                            brief: str = '') -> dict:
    if not settings.OPENAI_API_KEY:
        raise ValueError('OpenAI speech is not configured. Add OPENAI_API_KEY before generating a narrated video.')
    from app.services.usage_tracker import record_usage
    # Do not send camera directions or captions to the speech model.
    lower_brief = brief.lower()
    female_requested = bool(re.search(r"\b(?:female voice|female presenter|woman presenter)\b", lower_brief))
    male_requested = bool(re.search(r"\b(?:male voice|male presenter|man presenter)\b", lower_brief))
    gender = "male" if male_requested and not female_requested else "female"
    style = (f'One adult {gender} commercial narrator with a warm, confident, natural conversational delivery. '
             'Keep the same pitch, pace, tone, energy, microphone distance and accent for the entire film. '
             'Speak only the supplied words. No introductions, additional words, music or effects. ')
    if 'australian' in brief.lower():
        style += 'Use a natural Australian English accent, consistently for every line. '
    pace_match = re.search(r"(\d{2,3})\s*(?:[–—-]\s*(\d{2,3})\s*)?(?:wpm|words per minute)", lower_brief)
    target_wpm = (
        (int(pace_match.group(1)) + int(pace_match.group(2) or pace_match.group(1))) / 2
        if pace_match else 155.0
    )
    target_wpm = max(115.0, min(180.0, target_wpm))
    style += f'Use a steady natural pace near {target_wpm:.0f} words per minute. '
    model, voice = 'gpt-4o-mini-tts', ('cedar' if gender == 'male' else 'marin')
    root = (Path(file_service.upload_dir) / tenant_id / 'narration').resolve()
    root.mkdir(parents=True, exist_ok=True)
    lines = []
    async with httpx.AsyncClient(timeout=180) as client:
        for start, end, text in events:
            window = end - start
            if window <= 0:
                raise ValueError('Invalid voiceover window')
            identity = json.dumps([_CACHE_VERSION, model, voice, style, text, window], ensure_ascii=False)
            # An 80-bit cache key is ample here and avoids MAX_PATH failures in
            # deeply nested Windows/OneDrive workspaces.
            target = (root / (hashlib.sha256(identity.encode()).hexdigest()[:20] + '.wav')).resolve()
            cached = probe_video_duration(target)
            prepared_now = False
            if cached is None or cached > window + 0.02:
                if target.exists():
                    target.unlink(missing_ok=True)
                # Ask for a natural fit first. If the provider still runs long, use the
                # shortest complete take and fit its tempo without cutting or changing pitch.
                shortest_path: Path | None = None
                shortest_duration: float | None = None
                temp_paths: list[Path] = []
                try:
                    for attempt in range(3):
                        delivery = window * (0.96, 0.88, 0.80)[attempt]
                        response = await client.post(
                            settings.OPENAI_BASE_URL.rstrip('/') + '/audio/speech',
                            headers={'Authorization': f'Bearer {settings.OPENAI_API_KEY}'},
                            json={'model': model, 'voice': voice, 'input': text, 'response_format': 'wav',
                                  'instructions': style + f'Deliver this line as part of one continuous commercial narration. Complete it naturally within {delivery:.2f} seconds. Begin immediately. No elongated vowels or dramatic pauses. Speak the exact words in one fluid phrase.'},
                        )
                        if response.status_code >= 400:
                            try:
                                message = str(response.json().get('error', {}).get('message', 'Speech request failed'))
                            except Exception:
                                message = 'Speech request failed'
                            raise RuntimeError(f'OpenAI speech failed ({response.status_code}): {message[:300]}')
                        record_usage(provider='openai', model=model, operation='creative_studio_tts',
                                     tenant_id=tenant_id, extra={'characters': len(text), 'cost_status': 'unavailable'})
                        # Decode to PCM; remove only boundary digital silence, keeping 60ms guards.
                        with tempfile.TemporaryDirectory(prefix='cs_speech_') as tmp:
                            raw = Path(tmp) / 'source.wav'
                            pcm = Path(tmp) / 'pcm.wav'
                            raw.write_bytes(response.content)
                            proc = subprocess.run([require_ffmpeg(), '-v', 'error', '-y', '-i', str(raw),
                                '-ac', '1', '-ar', '24000', '-c:a', 'pcm_s16le', str(pcm)], capture_output=True)
                            if proc.returncode:
                                raise RuntimeError('Cannot decode OpenAI narration')
                            with wave.open(str(pcm), 'rb') as stream:
                                frames = stream.readframes(stream.getnframes())
                            import sys
                            samples = array('h', frames)
                            if sys.byteorder != 'little':
                                samples.byteswap()
                            active = [i for i, sample in enumerate(samples) if abs(sample) > 20]
                            if not active:
                                raise RuntimeError('Speech provider returned silent narration')
                            first = max(0, int(active[0]) - 1440)
                            last = min(len(samples), int(active[-1]) + 1441)
                            spoken = samples[first:last]
                            duration = len(spoken) / 24000
                            candidate = root / f".{target.stem}-{attempt}.wav"
                            _write_pcm_wav(candidate, spoken)
                            temp_paths.append(candidate)

                            if duration <= window:
                                candidate.replace(target)
                                temp_paths.remove(candidate)
                                shortest_path = None
                                shortest_duration = None
                                break

                            if shortest_duration is None or duration < shortest_duration:
                                shortest_path = candidate
                                shortest_duration = duration

                    if not target.exists():
                        if not shortest_path or shortest_duration is None or not shortest_path.is_file():
                            raise RuntimeError("Speech provider returned no usable narration")
                        _fit_audio_to_window(
                            shortest_path,
                            target,
                            duration=shortest_duration,
                            window=window,
                        )
                finally:
                    for temp_path in temp_paths:
                        temp_path.unlink(missing_ok=True)
                prepared_now = True
            duration = probe_video_duration(target)
            if duration is None or duration > window + 0.02:
                raise ValueError('Prepared narration no longer matches the timing window')
            if prepared_now:
                _normalise_voice_line(target)
                duration = probe_video_duration(target)
            lines.append({'start': start, 'end': end, 'text': text, 'path': str(target), 'duration': duration})
    return {
        'provider': 'openai', 'model': model, 'voice': voice,
        'voice_profile_id': f'openai:{model}:{voice}:commercial-v1:-16lufs', 'target_lufs': -16.0,
        'lines': lines, 'ai_generated': True,
    }
