"""Prepare and verify exact narration before spending on video generation."""
from __future__ import annotations

import hashlib
import json
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


async def prepare_narration(events: list[tuple[float, float, str]], *, tenant_id: str,
                            brief: str = '') -> dict:
    if not settings.OPENAI_API_KEY:
        raise ValueError('OpenAI speech is not configured. Add OPENAI_API_KEY before generating a narrated video.')
    from app.services.usage_tracker import record_usage
    # Do not send camera directions or captions to the speech model.
    style = ('An adult female commercial narrator with a warm, confident, quick conversational delivery. '
             'Speak only the supplied words. No introductions, additional words, music or effects. ')
    if 'australian' in brief.lower():
        style += 'Use a natural Australian English accent, consistently for every line. '
    model, voice = 'gpt-4o-mini-tts', 'marin'
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
                        delivery = window * (0.82, 0.60, 0.45)[attempt]
                        response = await client.post(
                            settings.OPENAI_BASE_URL.rstrip('/') + '/audio/speech',
                            headers={'Authorization': f'Bearer {settings.OPENAI_API_KEY}'},
                            json={'model': model, 'voice': voice, 'input': text, 'response_format': 'wav',
                                  'instructions': style + f'Deliver this short phrase quickly, as a brief upbeat tag at the end of a commercial. Use a brisk, fluent delivery at about {max(3.5, len(text.split()) / delivery):.1f} words per second. Complete the entire line within {delivery:.2f} seconds. Begin immediately. No slow drawl, elongated vowels, or dramatic pauses. Speak the exact words in one fluid phrase.'},
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
            duration = probe_video_duration(target)
            if duration is None or duration > window + 0.02:
                raise ValueError('Prepared narration no longer matches the timing window')
            lines.append({'start': start, 'end': end, 'text': text, 'path': str(target), 'duration': duration})
    return {'provider': 'openai', 'model': model, 'voice': voice, 'lines': lines, 'ai_generated': True}
