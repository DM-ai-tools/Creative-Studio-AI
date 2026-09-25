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
    # imageio-ffmpeg ships only ffmpeg.exe — do not treat it as ffprobe
    for candidate in (
        str(Path(ffmpeg).with_name("ffprobe.exe")),
        str(Path(ffmpeg).with_name("ffprobe")),
        ffmpeg.replace("ffmpeg.exe", "ffprobe.exe"),
    ):
        p = Path(candidate)
        if p.is_file() and p.resolve() != Path(ffmpeg).resolve() and "ffprobe" in p.name.lower():
            return str(p)
    found = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if found and Path(found).resolve() != Path(ffmpeg).resolve():
        return found
    return None


def require_ffmpeg() -> str:
    exe = ffmpeg_executable()
    if not exe:
        raise RuntimeError(_FFMPEG_HINT)
    return exe


def probe_has_audio(video_path: Path | str) -> bool | None:
    """Check the actual stream, including installations with FFmpeg but no ffprobe."""
    path = Path(video_path)
    if not path.is_file():
        return None
    probe = ffprobe_executable()
    if probe:
        proc = subprocess.run(
            [probe, "-v", "error", "-select_streams", "a:0", "-show_entries",
             "stream=index", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0:
            return bool(proc.stdout.strip())
    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        return None
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    import re
    metadata = proc.stderr or ""
    if not re.search(r"Stream #.*Video:", metadata):
        return None
    return bool(re.search(r"Stream #.*Audio:", metadata))


def probe_video_duration(video_path: Path | str) -> float | None:
    """Actual media length in seconds (Path or str)."""
    path = Path(video_path)
    if not path.is_file():
        return None

    ffprobe = ffprobe_executable()
    if ffprobe:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            try:
                val = float((proc.stdout or "").strip())
                if val > 0.5:
                    return val
            except ValueError:
                pass

    # Fallback: parse `ffmpeg -i` Duration line (imageio bundle has no ffprobe)
    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        return None
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
    )
    import re

    text = (proc.stderr or "") + (proc.stdout or "")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not m:
        return None
    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    val = h * 3600 + mi * 60 + s
    return val if val > 0.5 else None


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
