"""Lay approved still images (screens, graphics) over a finished Creative Studio video.

The stills are drawn by an image model and reviewed by the user (creative_studio_still.py). Showing
them as pictures, with a short fade and a slow zoom, keeps their text exactly as approved: Seedance
never redraws it. The video's own audio (the voice) is copied through untouched, and the video keeps
its length. The original file is never changed; a new copy is saved.
"""

from __future__ import annotations

import logging
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_INSERTS = 8
MIN_INSERT_SECONDS, MAX_INSERT_SECONDS = 1.0, 10.0
FADE_SECONDS = 0.25
ZOOM_AMOUNT = 0.06  # a still grows 6% over its window: alive, but the text stays steady
FPS = 24


def clean_inserts(inserts: list[dict[str, Any]], video_seconds: float) -> list[dict[str, Any]]:
    """Validate the windows: whole picture inside the video, not overlapping, sorted by start."""
    if not inserts:
        raise ValueError("Add at least one picture to lay over the video.")
    if len(inserts) > MAX_INSERTS:
        raise ValueError(f"Use at most {MAX_INSERTS} pictures.")
    cleaned: list[dict[str, Any]] = []
    for position, item in enumerate(inserts, start=1):
        url = str((item or {}).get("image_url") or "").strip()
        try:
            start = float(item.get("start_seconds"))
            length = float(item.get("duration_seconds"))
        except (TypeError, ValueError, AttributeError):
            raise ValueError(f"Picture {position} needs a start time and a length.") from None
        if not url:
            raise ValueError(f"Picture {position} has no image.")
        if not (math.isfinite(start) and math.isfinite(length)) or start < 0:
            raise ValueError(f"Picture {position} has an invalid start time.")
        if start >= video_seconds - 0.5:
            raise ValueError(f"Picture {position} starts at {start:g}s, after the video ends ({video_seconds:.1f}s).")
        end = min(start + max(MIN_INSERT_SECONDS, min(length, MAX_INSERT_SECONDS)), video_seconds)
        cleaned.append({"image_url": url, "start": round(start, 3), "end": round(end, 3), "n": position})
    cleaned.sort(key=lambda i: i["start"])
    for previous, current in zip(cleaned, cleaned[1:]):
        if current["start"] < previous["end"] - 1e-6:
            raise ValueError(
                f"Pictures {previous['n']} and {current['n']} overlap "
                f"({previous['start']:g}-{previous['end']:g}s and {current['start']:g}-{current['end']:g}s). Change a start time."
            )
    return cleaned


def _local_image(url: str) -> Path:
    from app.services.logo_overlay import file_url_to_local_path

    path = file_url_to_local_path(url)
    if not path or not path.is_file():
        raise ValueError("A picture could not be found. Generate it again and retry.")
    return path


def add_image_inserts_to_video(
    *,
    video_url: str,
    tenant_id: str,
    inserts: list[dict[str, Any]],
    zoom: bool = True,
) -> dict[str, Any]:
    from app.services.creative_studio_caption_logo import _output_size
    from app.services.creative_studio_picture import media_dimensions
    from app.services.ffmpeg_util import probe_video_duration, require_ffmpeg
    from app.services.file_service import file_service
    from app.services.video_subtitles import _ensure_local_video

    video_path = _ensure_local_video(str(video_url or "").strip(), tenant_id=tenant_id)
    if not video_path or not video_path.is_file():
        raise ValueError("The video file could not be found. Generate or re-open the video and retry.")
    ffmpeg = require_ffmpeg()
    duration = float(probe_video_duration(video_path) or 0.0)
    if duration <= 0:
        raise ValueError("The video length could not be read.")
    windows = clean_inserts(inserts, duration)
    images = [_local_image(w["image_url"]) for w in windows]
    src_w, src_h = media_dimensions(video_path)
    out_w, out_h = _output_size(src_w, src_h)

    with tempfile.TemporaryDirectory(prefix="cs_inserts_") as tmp:
        work = Path(tmp)
        shutil.copy2(video_path, work / "input.mp4")
        command = [ffmpeg, "-y", "-i", "input.mp4"]
        parts = [f"[0:v]scale={out_w}:{out_h}:flags=lanczos,setsar=1[v0]"]
        for index, (window, image) in enumerate(zip(windows, images), start=1):
            local = f"still{index}{image.suffix.lower() or '.png'}"
            shutil.copy2(image, work / local)
            command += ["-i", local]
            length = window["end"] - window["start"]
            frames = max(2, int(round(length * FPS)))
            growth = f"1+{ZOOM_AMOUNT}*on/{frames}" if zoom else "1"
            fade = min(FADE_SECONDS, length / 3)
            parts.append(
                # work at double size so the slow zoom is smooth, then cut to the video's frame
                f"[{index}:v]scale={out_w * 2}:{out_h * 2}:force_original_aspect_ratio=increase,crop={out_w * 2}:{out_h * 2},"
                f"zoompan=z='{growth}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={out_w}x{out_h}:fps={FPS},"
                f"format=rgba,fade=t=in:st=0:d={fade:.3f}:alpha=1,fade=t=out:st={length - fade:.3f}:d={fade:.3f}:alpha=1,"
                f"setpts=PTS+{window['start']:.3f}/TB[s{index}]"
            )
            parts.append(f"[v{index - 1}][s{index}]overlay=0:0:eof_action=pass:format=auto[v{index}]")
        command += [
            "-filter_complex", ";".join(parts), "-map", f"[v{len(windows)}]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart", "output.mp4",
        ]
        proc = subprocess.run(command, capture_output=True, text=True, cwd=str(work))
        output = work / "output.mp4"
        if proc.returncode != 0 or not output.is_file() or output.stat().st_size < 1000:
            logger.error("Creative Studio inserts failed: %s", (proc.stderr or "")[-1500:])
            raise RuntimeError("The pictures could not be added to this video.")
        saved = file_service.save_bytes(
            content=output.read_bytes(), tenant_id=tenant_id, subfolder="generated", suffix=".mp4", content_type="video/mp4"
        )
    return {
        "url": str(saved["file_url"]),
        "source_url": str(video_url),
        "width": out_w,
        "height": out_h,
        "duration_seconds": round(duration, 2),
        "inserts": [{"start_seconds": w["start"], "end_seconds": w["end"]} for w in windows],
        "warnings": [],
    }
