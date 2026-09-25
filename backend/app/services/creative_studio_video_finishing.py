"""Reliable post-production for Creative Studio Seedance videos."""

from __future__ import annotations

import logging
import asyncio
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.ffmpeg_util import ffmpeg_executable, probe_has_audio, probe_video_duration
from app.services.file_service import file_service
from app.services.video_subtitles import _ensure_local_video, _video_dimensions

logger = logging.getLogger(__name__)

_RANGE = r"(\d+(?:\.\d+)?)\s*[–—-]\s*(\d+(?:\.\d+)?)"
_QUOTED = r"[“\"]([^”\"]+)[”\"]"


def voiceover_requested(brief: str) -> bool:
    label = r"(?:voice[ -]?over|narrat(?:ion|or))"
    # An explicit silence/no-narration instruction takes precedence over a mention.
    if re.search(rf"(?i)\b(?:no|without|omit|disable)\s+(?:any\s+)?{label}\b", brief):
        return False
    return bool(re.search(rf"(?i)\b{label}\b", brief))


async def plan_requested_voiceover(
    brief: str, *, duration_seconds: int
) -> list[tuple[float, float, str]]:
    """Write narration only when requested without a script; exact supplied words win."""
    exact = extract_voiceover_events(brief, duration_seconds=duration_seconds)
    if exact:
        return exact
    if not settings.OPENROUTER_API_KEY or not voiceover_requested(brief):
        return []
    from app.services.image_prompt_service import _get_openrouter_client
    from app.services.prompt_llm_catalog import default_prompt_llm_model

    client = _get_openrouter_client()
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=default_prompt_llm_model(),
        messages=[
            {"role": "system", "content": (
                "Write only the narrator's spoken copy requested by the brief. "
                "Return JSON: {\"lines\":[{\"start\":0,\"end\":5,\"text\":\"spoken words\"}]}. "
                f"The film is {duration_seconds}s. Use nonoverlapping windows within it, "
                "each at most 15s. Target at most two spoken words per second. "
                "Respect scene times, language, brand and claims. Never narrate camera "
                "directions, headings, timing, style instructions or JSON. No invented claims. "
                "If narration is explicitly prohibited, return an empty lines array."
            )},
            {"role": "user", "content": brief},
        ],
        max_tokens=4000,
        temperature=0.2,
    )
    raw = (response.choices[0].message.content or "").strip()
    raw = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", raw)
    lines = json.loads(raw).get("lines", [])
    result = []
    previous_end = 0.0
    for line in lines:
        a, b = float(line["start"]), float(line["end"])
        spoken = str(line["text"]).strip()
        if not (0 <= a < b <= duration_seconds and a >= previous_end and b - a <= 15):
            raise ValueError("Narration planner returned invalid scene timings")
        if not spoken or len(spoken) > 1000:
            raise ValueError("Narration planner returned an empty or excessive spoken line")
        result.append((a, b, spoken))
        previous_end = b
    return result


def extract_overlay_events(prompt: str) -> list[tuple[float, float, str]]:
    """Read the brief's authoritative `Use only these exact text moments` list."""
    text = prompt or ""
    match = re.search(
        r"(?is)Use only these exact text moments\s*:\s*(.*?)(?:\n\s*Use a restrained|\n\s*Voiceover performance)",
        text,
    )
    section = match.group(1) if match else ""
    events: list[tuple[float, float, str]] = []
    for row in section.splitlines():
        timing = re.search(_RANGE + r"\s*seconds?\s*:\s*(.*)", row, re.I)
        if not timing:
            continue
        start, end = float(timing.group(1)), float(timing.group(2))
        content = timing.group(3).strip()
        quote = re.search(_QUOTED, content)
        if quote:
            events.append((start, end, quote.group(1).strip()))
            continue
        if re.search(r"(?i)final\s+(?:brand(?:\s*card)?|end\s*card)", content):
            end_card = re.search(
                r"(?is)Reveal the complete end card.*?:\s*\n(.*?)(?:\n\s*Voiceover|\n\s*Use the supplied)",
                text,
            )
            if end_card:
                lines = [
                    line.strip()
                    for line in end_card.group(1).splitlines()
                    if line.strip() and len(line.strip()) <= 100
                ][:4]
                if lines:
                    events.append((start, end, r"\N".join(lines)))
    if events:
        return events[:12]

    # Generic timed-scene briefs often place copy in a dedicated section inside
    # each scene instead of repeating the timing on every text line.
    from app.services.creative_studio_timeline import SHOT_HEADER

    headers = list(SHOT_HEADER.finditer(text))
    for index, header in enumerate(headers):
        timing = re.search(_RANGE, header.group())
        if not timing:
            continue
        stop = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        body = text[header.end():stop]
        section_match = re.search(
            r"(?ims)^\s*(?:FINAL\s+)?ON-SCREEN\s+TEXT\s*:\s*(.*?)(?=^\s*[A-Z][A-Z /+-]{2,}\s*:\s*$|^\s*[-=]{4,}\s*$|\Z)",
            body,
        )
        if not section_match:
            continue
        section = section_match.group(1)
        lines = [item.strip() for item in re.findall(r"[“\"]([^”\"\n]+)[”\"]", section)]
        if not lines:
            lines = [
                row.strip()
                for row in section.splitlines()
                if row.strip()
                and not re.fullmatch(r"[-=_*\s]+", row.strip())
                and not re.search(r"(?i)^(?:no additional text|let the|keep the|text should)", row.strip())
                and len(row.strip()) <= 100
            ]
        if lines:
            events.append((float(timing.group(1)), float(timing.group(2)), r"\N".join(lines[:4])))
    if events:
        return events[:12]

    # Fallback for shorter prompts that only use `On-screen text, X-Y seconds`.
    for match in re.finditer(
        r"(?is)On-screen text[^\n]*?" + _RANGE + r"\s*seconds?\s*:\s*\n?\s*" + _QUOTED,
        text,
    ):
        events.append((float(match.group(1)), float(match.group(2)), match.group(3).strip()))
    return events[:12]


def extract_voiceover_events(prompt: str, *, duration_seconds: float = 15) -> list[tuple[float, float, str]]:
    """Extract exact narrator lines and their requested windows."""
    text = prompt or ""
    events: list[tuple[float, float, str]] = []
    for match in re.finditer(
        r"(?is)Voiceover\s*,?\s*" + _RANGE + r"\s*seconds?\s*:\s*\n?\s*" + _QUOTED,
        text,
    ):
        events.append((float(match.group(1)), float(match.group(2)), match.group(3).strip()))
    for match in re.finditer(
        r"(?is)Voiceover begins at\s*(\d+(?:\.\d+)?)\s*seconds?\s*:\s*\n?\s*" + _QUOTED,
        text,
    ):
        start = float(match.group(1))
        line = match.group(2).strip()
        end_hint = re.search(
            rf"(?is){re.escape(line)}.*?finishing by\s*(\d+(?:\.\d+)?)\s*seconds?",
            text,
        )
        events.append((start, float(end_hint.group(1)) if end_hint else start + 2.2, line))
    # Accept common labels, optional timings, straight/curly quotes, and plain script
    # lines. Never send unlabelled production directions to TTS.
    label = re.compile(
        r'(?im)^\s*(?:[-*]\s*)?(?:(\d+(?:\.\d+)?\s*[–—-]\s*\d+(?:\.\d+)?\s*s(?:econds?)?)\s*[:—-]?\s*)?'
        r'(?:voice[ -]?over|VO|narration|narrator|dialogue)'
        r'\s*(?:script\s*)?(?:[,([]\s*)?'
        r'(\d+(?:\.\d+)?\s*[–—-]\s*\d+(?:\.\d+)?\s*s(?:econds?)?)?'
        r'\s*[)\]]?\s*:\s*'
        r'(?:"([^"\n]+)"|“([^”\n]+)”|\x27([^\x27\n]+)\x27|([^\n]+))'
    )
    untimed: list[str] = []
    for match in label.finditer(text):
        line = next((g.strip() for g in match.groups()[2:] if g), "")
        if not line:
            continue
        timing_text = match.group(1) or match.group(2)
        timing = re.search(_RANGE, timing_text or "")
        if not timing:
            # A narration line inside a timed scene inherits that scene's window.
            headers = list(re.finditer(
                r"(?im)^\s*(?:#{1,6}\s*)?(?:Scene|CLIP)\s*\d+[^\n]*",
                text[:match.start()],
            ))
            if headers:
                heading = re.sub(
                    r"(?i)^\s*(?:#{1,6}\s*)?(?:Scene|CLIP)\s*\d+\b",
                    "", headers[-1].group(),
                )
                timing = re.search(_RANGE, heading)
        if timing:
            events.append((float(timing.group(1)), float(timing.group(2)), line))
        elif line not in untimed:
            untimed.append(line)
    # Untimed script uses the remaining runtime, with word-weighted windows.
    cursor = max((end for _, end, _ in events), default=0.0)
    available = max(0.0, float(duration_seconds) - cursor)
    words = sum(max(1, len(line.split())) for line in untimed)
    for line in untimed:
        end = cursor + available * max(1, len(line.split())) / words
        events.append((cursor, end, line))
        cursor = end
    return sorted({
        (max(0.0, a), min(float(duration_seconds), b), t)
        for a, b, t in events if t and b > a and a < duration_seconds
    }, key=lambda item: item[0])


_SECONDS_PER_WORD = 0.42
_MIN_LINE_SECONDS = 1.2
_GAP_SECONDS = 0.08


def normalize_voiceover_windows(
    events: list[tuple[float, float, str]],
    *,
    duration_seconds: float,
    seconds_per_word: float = _SECONDS_PER_WORD,
    min_line_seconds: float = _MIN_LINE_SECONDS,
    gap_seconds: float = _GAP_SECONDS,
) -> list[tuple[float, float, str]]:
    """Widen dialogue windows that are too tight for natural TTS delivery."""
    if not events:
        return []
    duration = float(duration_seconds)
    ordered = sorted(events, key=lambda item: item[0])
    normalized: list[tuple[float, float, str]] = []
    for index, (start, end, text) in enumerate(ordered):
        start = max(0.0, min(float(start), duration - gap_seconds))
        end = max(start + gap_seconds, min(float(end), duration))
        words = max(1, len(text.split()))
        needed = max(min_line_seconds, words * seconds_per_word)
        next_start = (
            float(ordered[index + 1][0])
            if index + 1 < len(ordered)
            else duration
        )
        max_end = min(duration, next_start - gap_seconds) if next_start > start else duration
        end = min(max_end, max(end, start + needed))
        if end > start:
            normalized.append((start, end, text))
    return normalized


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    return f"{int(seconds // 3600)}:{int((seconds % 3600) // 60):02d}:{seconds % 60:05.2f}"


def _clean_ass(text: str) -> str:
    return text.replace("\\N", r"\N").replace("{", r"\{").replace("}", r"\}")


def apply_timed_overlays(
    video_url: str,
    events: list[tuple[float, float, str]],
    *,
    tenant_id: str,
) -> tuple[str, bool]:
    if not events or not ffmpeg_executable():
        return video_url, False
    video = _ensure_local_video(video_url, tenant_id=tenant_id)
    if not video:
        return video_url, False
    width, height = _video_dimensions(video)
    font_size = max(34, int(height * 0.047))
    margin_v = max(42, int(height * 0.08))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: AdCopy,Arial,{font_size},&H00FFFFFF,&H000000FF,&H50000000,&H00000000,-1,0,0,0,100,100,0,0,1,2.2,1.2,2,70,70,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows = [
        f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},AdCopy,,0,0,0,,{_clean_ass(copy)}"
        for start, end, copy in events
        if copy and end > start
    ]
    with tempfile.TemporaryDirectory(prefix="cs_overlay_") as tmp:
        work = Path(tmp)
        source = work / "input.mp4"
        ass = work / "overlays.ass"
        output = work / "output.mp4"
        shutil.copy2(video, source)
        ass.write_text(header + "\n".join(rows) + "\n", encoding="utf-8-sig")
        cmd = [
            ffmpeg_executable() or "ffmpeg", "-y", "-i", source.name,
            "-vf", f"ass={ass.name}", "-c:v", "libx264", "-preset", "fast",
            "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy",
            "-movflags", "+faststart", output.name,
        ]
        proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
        if proc.returncode != 0 or not output.is_file():
            logger.error("Creative Studio overlay burn failed: %s", (proc.stderr or "")[-800:])
            return video_url, False
        saved = file_service.save_bytes(
            output.read_bytes(), tenant_id, "generated", ".mp4", "video/mp4"
        )
        return saved["file_url"], True


def _has_audio(path: Path) -> bool:
    return probe_has_audio(path) is True


async def apply_timed_voiceover(
    video_url: str,
    events: list[tuple[float, float, str]],
    *,
    tenant_id: str,
    allow_time_stretch: bool = True,
    prepared_narration: dict | None = None,
) -> tuple[str, dict]:
    if not events:
        return video_url, {"status": "skipped", "reason": "No exact voiceover lines found"}
    if not prepared_narration and (not settings.RUNWAYML_VOICEOVER_ENABLED or not settings.RUNWAYML_API_KEY):
        return video_url, {"status": "skipped", "reason": "Runway TTS is not configured"}
    ffmpeg = ffmpeg_executable()
    video = _ensure_local_video(video_url, tenant_id=tenant_id)
    if not ffmpeg or not video:
        return video_url, {"status": "failed", "error": "ffmpeg or local video unavailable"}

    from app.services.media.voiceover import generate_tts_audio

    with tempfile.TemporaryDirectory(prefix="cs_vo_") as tmp:
        work = Path(tmp)
        source = work / "input.mp4"
        output = work / "output.mp4"
        shutil.copy2(video, source)
        audio_paths: list[Path] = []
        if prepared_narration:
            prepared_lines = prepared_narration.get("lines", [])
            if [(item["start"], item["end"], item["text"]) for item in prepared_lines] != events:
                raise ValueError("Prepared narration does not match the approved script/timing")
            audio_paths = [Path(item["path"]).resolve() for item in prepared_lines]
            missing = [str(path) for path in audio_paths if not path.is_file()]
            if missing:
                raise FileNotFoundError(missing[0])
        else:
            async with httpx.AsyncClient(timeout=180.0) as client:
                for index, (_, _, line) in enumerate(events):
                    audio = await generate_tts_audio(client, script=line, voice_preset="Serene")
                    suffix = ".wav" if audio[:4] == b"RIFF" else ".m4a" if audio[4:8] == b"ftyp" else ".mp3"
                    path = work / f"line-{index}{suffix}"
                    path.write_bytes(audio)
                    audio_paths.append(path)

        cmd: list[str] = [ffmpeg, "-y", "-i", str(source)]
        for path in audio_paths:
            cmd.extend(["-i", str(path)])
        filters: list[str] = []
        mix_labels: list[str] = []
        source_audio = probe_has_audio(source)
        if source_audio is None:
            return video_url, {"status": "failed", "error": "Could not inspect the source audio"}
        if source_audio:
            # Duck only around spoken lines, with short ramps; keep sound in the pauses.
            envelopes = [
                f"min(1,max(0,(t-{max(0, a - 0.12):.6f})/0.12))"
                f"*min(1,max(0,({b + 0.12:.6f}-t)/0.12))"
                for a, b, _ in events
            ]
            filters.append(
                "[0:a]volume='1-0.72*min(1," + "+".join(envelopes) + ")':eval=frame[base]"
            )
            mix_labels.append("[base]")
        for index, ((start, end, _), audio_path) in enumerate(zip(events, audio_paths), start=1):
            delay = max(0, int(start * 1000))
            label = f"vo{index}"
            window = end - start
            spoken_duration = probe_video_duration(audio_path)
            if window <= 0 or spoken_duration is None:
                return video_url, {"status": "failed", "error": "Could not measure narration timing"}
            # Fit the complete spoken line into its allotted window before delaying it.
            speed = max(1.0, spoken_duration / window)
            if not allow_time_stretch and spoken_duration > window + 0.05:
                return video_url, {
                    "status": "failed",
                    "error": f"Narration at {start:g}s exceeds its window. The brief prohibits speeding up speech; record a shorter delivery.",
                }
            if speed > 1.5:
                return video_url, {
                    "status": "failed",
                    "error": f"Narration at {start:g}s is too long for its {window:g}s window; shorten the line or extend the scene.",
                }
            filters.append(
                f"[{index}:a]aresample=48000,atempo={speed:.6f},"
                f"apad,atrim=duration={window:.6f},adelay={delay}:all=1,volume=1.0[{label}]"
            )
            mix_labels.append(f"[{label}]")
        filters.append(
            "".join(mix_labels)
            + f"amix=inputs={len(mix_labels)}:duration=longest:dropout_transition=0:normalize=0,alimiter=limit=0.95[mix]"
        )
        duration = probe_video_duration(source) or max(end for _, end, _ in events)
        cmd.extend([
            "-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[mix]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.3f}",
            "-movflags", "+faststart", str(output),
        ])
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not output.is_file():
            return video_url, {"status": "failed", "error": (proc.stderr or "")[-500:]}
        saved = file_service.save_bytes(
            output.read_bytes(), tenant_id, "generated", ".mp4", "video/mp4"
        )
        return saved["file_url"], {
            "status": "done",
            "script": " ".join(line for _, _, line in events),
            "timed_lines": len(events),
            "voice": (prepared_narration or {}).get("voice", "Serene"),
            "provider": (prepared_narration or {}).get("provider", "runway"),
            "ai_generated": True,
        }
