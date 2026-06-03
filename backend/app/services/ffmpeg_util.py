"""Locate ffmpeg/ffprobe for video post-processing (logo, subtitles, trim)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_FFMPEG_HINT = (
    "ffmpeg is required to burn logos and subtitles onto videos. "
    "Run: pip install imageio-ffmpeg  (or install ffmpeg and add it to PATH), then restart the backend."
)


@lru_cache(maxsize=1)
def ffmpeg_executable() -> str | None:
    """Bundled imageio-ffmpeg first, then PATH, then common Windows install locations."""
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            logger.info("Using bundled ffmpeg: %s", exe)
            return exe
    except Exception as exc:
        logger.debug("imageio-ffmpeg unavailable: %s", exc)

    for name in ("ffmpeg", "ffmpeg.exe"):
        found = shutil.which(name)
        if found:
            logger.info("Using PATH ffmpeg: %s", found)
            return found

    if os.name == "nt":
        for candidate in (
            Path(os.environ.get("ProgramFiles", "")) / "ffmpeg" / "bin" / "ffmpeg.exe",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "ffmpeg" / "bin" / "ffmpeg.exe",
            Path.home() / "scoop" / "shims" / "ffmpeg.exe",
            Path("C:/ffmpeg/bin/ffmpeg.exe"),
        ):
            if candidate.is_file():
                logger.info("Using Windows ffmpeg: %s", candidate)
                return str(candidate)

    logger.error(_FFMPEG_HINT)
    return None


def ffprobe_executable() -> str | None:
    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        return None
    for candidate in (
        ffmpeg.replace("ffmpeg.exe", "ffprobe.exe"),
        ffmpeg.replace("ffmpeg", "ffprobe"),
    ):
        if Path(candidate).is_file():
            return candidate
    return shutil.which("ffprobe") or shutil.which("ffprobe.exe")


def require_ffmpeg() -> str:
    exe = ffmpeg_executable()
    if not exe:
        raise RuntimeError(_FFMPEG_HINT)
    return exe


def probe_video_duration(video_path: Path) -> float | None:
    """Actual media length in seconds — use for caption sync (not brief request duration)."""
    ffprobe = ffprobe_executable()
    if not ffprobe or not video_path.is_file():
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
        val = float((proc.stdout or "").strip())
        return val if val > 0.5 else None
    except ValueError:
        return None


def drawtext_font_opts() -> str:
    """fontconfig name (bundled ffmpeg on Windows has libfontconfig)."""
    if os.name == "nt":
        for name in ("Arial", "Segoe UI", "Calibri"):
            return f"font={name}"
        windir = os.environ.get("WINDIR", r"C:\Windows")
        arial = Path(windir) / "Fonts" / "arial.ttf"
        if arial.is_file():
            # Inside drawtext filter, escape drive colon for ffmpeg on Windows.
            p = arial.resolve().as_posix().replace(":", "\\:")
            return f"fontfile='{p}'"
    return "font=Arial"
