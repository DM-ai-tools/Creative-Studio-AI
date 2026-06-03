"""Trim generated videos to the brief's requested duration (HeyGen often runs long)."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from app.core.config import settings
from app.services.logo_overlay import file_url_to_local_path
from app.services.media.voiceover import _ffmpeg_executable
from app.services.video_logo_overlay import _ffprobe_executable

logger = logging.getLogger(__name__)


def _ffprobe_duration(video_path: Path) -> float | None:
    ffprobe = _ffprobe_executable()
    if not ffprobe:
        return None
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None


def _trim_enabled() -> bool:
    raw = getattr(settings, "VIDEO_TRIM_TO_REQUESTED_DURATION", True)
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw)


def trim_video_to_max_seconds(
    video_file_url: str,
    *,
    tenant_id: str,
    max_seconds: float,
    tolerance_sec: float = 1.5,
) -> tuple[str | None, float | None]:
    """
    If the file is longer than max_seconds + tolerance, cut to max_seconds.
    Returns (new_url, new_duration) or (None, None) if trim skipped/failed.
    """
    if not _trim_enabled() or max_seconds <= 0:
        return None, None

    video_path = file_url_to_local_path(video_file_url)
    if not video_path:
        return None, None

    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        logger.warning("Video trim skipped: ffmpeg not found")
        return None, None

    current = _ffprobe_duration(video_path)
    if current is None or current <= max_seconds + tolerance_sec:
        return None, None

    target = max(3.0, float(max_seconds))
    logger.info(
        "Trimming video %.1fs → %.1fs (requested cap)",
        current,
        target,
    )

    from app.services.file_service import file_service
    from app.services.media_content import video_suffix_and_type

    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / f"trim{video_path.suffix or '.mp4'}"
            attempts = [
                ["-c", "copy"],
                ["-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac"],
            ]
            proc = None
            for codec_args in attempts:
                cmd = [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(video_path),
                    "-t",
                    f"{target:.3f}",
                    *codec_args,
                    "-movflags",
                    "+faststart",
                    str(out),
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode == 0:
                    break
            if proc is None or proc.returncode != 0:
                logger.warning(
                    "Video trim ffmpeg failed: %s",
                    (proc.stderr or proc.stdout)[-600:] if proc else "",
                )
                return None, None

                content = out.read_bytes()
                if len(content) < 1000:
                    return None, None
                suffix, content_type = video_suffix_and_type(content)
                saved = file_service.save_bytes(
                    content=content,
                    tenant_id=tenant_id,
                    subfolder="generated",
                    suffix=suffix,
                    content_type=content_type,
                )
                new_dur = _ffprobe_duration(out) or target
                return saved["file_url"], float(new_dur)
    except Exception:
        logger.exception("Video trim failed for %s", video_file_url)
        return None, None

    return None, None
