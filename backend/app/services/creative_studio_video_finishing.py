"""Reliable post-production for Creative Studio Seedance videos."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.ffmpeg_util import ffmpeg_executable, ffprobe_executable, probe_video_duration
from app.services.file_service import file_service
from app.services.video_subtitles import _ensure_local_video, _video_dimensions

logger = logging.getLogger(__name__)

_RANGE = r"(\d+(?:\.\d+)?)\s*[–—-]\s*(\d+(?:\.\d+)?)"
_QUOTED = r"[“\"]([^”\"]+)[”\"]"


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

    # Fallback for shorter prompts that only use `On-screen text, X-Y seconds`.
    for match in re.finditer(
        r"(?is)On-screen text[^\n]*?" + _RANGE + r"\s*seconds?\s*:\s*\n?\s*" + _QUOTED,
        text,
    ):
        events.append((float(match.group(1)), float(match.group(2)), match.group(3).strip()))
    return events[:12]


def extract_voiceover_events(prompt: str) -> list[tuple[float, float, str]]:
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
    return sorted({(a, b, t) for a, b, t in events}, key=lambda item: item[0])[:12]


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
    probe = ffprobe_executable()
    if not probe:
        return False
    proc = subprocess.run(
        [probe, "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return proc.returncode == 0 and bool(proc.stdout.strip())


async def apply_timed_voiceover(
    video_url: str,
    events: list[tuple[float, float, str]],
    *,
    tenant_id: str,
) -> tuple[str, dict]:
    if not events:
        return video_url, {"status": "skipped", "reason": "No exact voiceover lines found"}
    if not settings.RUNWAYML_VOICEOVER_ENABLED or not settings.RUNWAYML_API_KEY:
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
        if _has_audio(source):
            filters.append("[0:a]volume=0.28[base]")
            mix_labels.append("[base]")
        for index, ((start, _, _), _) in enumerate(zip(events, audio_paths), start=1):
            delay = max(0, int(start * 1000))
            label = f"vo{index}"
            filters.append(f"[{index}:a]adelay={delay}|{delay},volume=1.0[{label}]")
            mix_labels.append(f"[{label}]")
        filters.append(
            "".join(mix_labels)
            + f"amix=inputs={len(mix_labels)}:duration=longest:dropout_transition=0[mix]"
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
            "voice": "Serene",
        }
