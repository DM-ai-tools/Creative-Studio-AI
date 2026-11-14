"""Optional last step for a finished Creative Studio video: burn captions and the brand logo.

The raw film stays untouched. This produces a second, upscaled file with the
spoken lines as captions near the bottom and the brand logo in the top-left
corner, in one encode so the text and logo are rendered at output resolution.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_CAPTION_CHARS = 26
_MAX_CAPTION_WORDS = 5
_SPEECH_WORDS_PER_SECOND = 2.6
_TARGET_SHORT_SIDE = 1080


def _split_caption_chunks(text: str) -> list[str]:
    """Break one spoken line into short phone-readable caption chunks."""
    words = [word for word in re.split(r"\s+", (text or "").strip()) if word and word not in {"—", "–", "-"}]
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and (len(candidate) > _MAX_CAPTION_CHARS or len(current) >= _MAX_CAPTION_WORDS):
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
        # Prefer to break after sentence punctuation so chunks follow the speech rhythm.
        if current and re.search(r"[.!?…]$", word) and len(current) >= 2:
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    return chunks


def caption_events_from_script(
    script: str, *, duration_seconds: float
) -> list[tuple[float, float, str]]:
    """Timed caption chunks from the script's spoken lines and their scene windows."""
    from app.services.creative_studio_video_finishing import extract_voiceover_events

    duration = max(1.0, float(duration_seconds))
    lines = [
        (max(0.0, float(start)), min(duration, float(end)), str(text).strip())
        for start, end, text in extract_voiceover_events(script or "", duration_seconds=duration)
        if str(text).strip()
    ]
    events: list[tuple[float, float, str]] = []
    for start, end, text in sorted(lines):
        if end - start < 0.2:
            continue
        chunks = _split_caption_chunks(text)
        if not chunks:
            continue
        spoken_words = sum(len(chunk.split()) for chunk in chunks)
        # A line rarely fills its whole scene. Spread captions over the estimated
        # speaking time so they do not trail behind the voice.
        speaking = min(end - start, max(1.0, spoken_words / _SPEECH_WORDS_PER_SECOND + 0.3))
        weights = [max(1, len(chunk)) for chunk in chunks]
        total = float(sum(weights))
        cursor = start
        for chunk, weight in zip(chunks, weights):
            chunk_end = min(end, cursor + speaking * weight / total)
            events.append((round(cursor, 3), round(chunk_end, 3), chunk))
            cursor = chunk_end
    return events


def _ass_time(seconds: float) -> str:
    total = max(0.0, float(seconds))
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    return f"{hours}:{minutes:02d}:{total % 60:05.2f}"


def build_caption_ass(
    events: list[tuple[float, float, str]], *, width: int, height: int
) -> str:
    """Bold white captions with a dark outline, centred a little above the bottom edge."""
    portrait = height > width * 1.2
    font_size = round(width * (0.052 if portrait else 0.046))
    # Sit above the bottom edge: clear of phone UI on vertical video, tidy on square.
    margin_v = round(height * (0.15 if portrait else 0.09))
    margin_h = round(width * 0.08)
    outline = max(2, round(font_size * 0.07))
    header = (
        "[Script Info]\nTitle: CreativeStudio captions\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Caption,Arial,{font_size},&H00FFFFFF,&H000000FF,&H00101010,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,{outline},1,2,{margin_h},{margin_h},{margin_v},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    rows = [
        f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Caption,,0,0,0,,"
        + text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")
        for start, end, text in events
    ]
    return header + "\n".join(rows) + "\n"


def _output_size(width: int, height: int) -> tuple[int, int]:
    """Upscale small provider output so captions and logo render crisply."""
    short = min(width, height)
    scale = max(1.0, _TARGET_SHORT_SIDE / max(1, short))
    out_w = int(round(width * scale / 2) * 2)
    out_h = int(round(height * scale / 2) * 2)
    return out_w, out_h


def _prepare_logo(
    video_path: Path,
    *,
    logo_url: str | None,
    logo_on_light_url: str | None,
    brand: dict | None,
    tenant_id: str,
    src_size: tuple[int, int],
    out_size: tuple[int, int],
    work_dir: Path,
) -> tuple[Path, int, int, int] | None:
    """Return (logo_png, x, y, width) for a top-left logo, or None when no logo is available."""
    from app.services.logo_overlay import _pick_logo_rgba_for_placement
    from app.services.video_logo_overlay import (
        _video_corner_is_light,
        logo_local_path,
        resolve_video_logo_urls,
    )

    resolved, resolved_on_light = resolve_video_logo_urls(
        brand=brand, logo_url=logo_url, logo_on_light_url=logo_on_light_url, tenant_id=tenant_id
    )
    logo_path = logo_local_path(resolved)
    if not logo_path or not logo_path.is_file():
        return None
    on_light_path = logo_local_path(resolved_on_light) if resolved_on_light else None

    out_w, out_h = out_size
    portrait = out_h > out_w * 1.2
    logo_w = round(out_w * (0.22 if portrait else 0.17))
    pad_x = round(out_w * 0.04)
    pad_y = round(out_h * (0.035 if portrait else 0.04))

    # Sample the same corner on the source frame to choose the light or dark mark.
    ratio = src_size[0] / max(1, out_w)
    light = _video_corner_is_light(
        video_path,
        overlay_x=int(pad_x * ratio),
        overlay_y=int(pad_y * ratio),
        region_w=max(8, int(logo_w * ratio)),
        region_h=max(8, int(logo_w * ratio * 0.4)),
    )
    logo = _pick_logo_rgba_for_placement(
        logo_path=logo_path,
        logo_on_light_path=on_light_path,
        light_background=light,
        max_width=logo_w * 2,  # keep extra pixels; ffmpeg scales down cleanly
    )
    logo_png = work_dir / "logo.png"
    logo.save(logo_png, format="PNG")
    return logo_png, pad_x, pad_y, logo_w


def finish_video_with_captions_and_logo(
    *,
    video_url: str,
    script: str,
    tenant_id: str,
    logo_url: str | None = None,
    logo_on_light_url: str | None = None,
    brand: dict | None = None,
    add_captions: bool = True,
    add_logo: bool = True,
) -> dict[str, Any]:
    """Burn captions and logo onto a copy of the video and return the new file URL."""
    from app.services.ffmpeg_util import probe_video_duration, require_ffmpeg
    from app.services.file_service import file_service
    # Reads the real size through ffmpeg. The ffprobe-based helper silently returns
    # 1080x1920 when ffprobe is missing, which would stretch a square video.
    from app.services.creative_studio_picture import media_dimensions
    from app.services.video_subtitles import _ensure_local_video

    if not add_captions and not add_logo:
        raise ValueError("Choose captions, logo, or both.")
    video_path = _ensure_local_video(str(video_url or "").strip(), tenant_id=tenant_id)
    if not video_path or not video_path.is_file():
        raise ValueError("The video file could not be found. Generate or re-open the video and retry.")

    ffmpeg = require_ffmpeg()
    duration = float(probe_video_duration(video_path) or 0.0) or 30.0
    src_w, src_h = media_dimensions(video_path)
    out_w, out_h = _output_size(src_w, src_h)
    warnings: list[str] = []

    events = caption_events_from_script(script, duration_seconds=duration) if add_captions else []
    if add_captions and not events:
        warnings.append(
            "No spoken lines were found in the script, so captions were not added. Label each "
            "line with DIALOGUE:, VOICEOVER: or NARRATION: under a timed scene heading."
        )

    with tempfile.TemporaryDirectory(prefix="cs_finish_") as tmp:
        work = Path(tmp)
        shutil.copy2(video_path, work / "input.mp4")
        logo = None
        if add_logo:
            try:
                logo = _prepare_logo(
                    video_path,
                    logo_url=logo_url,
                    logo_on_light_url=logo_on_light_url,
                    brand=brand,
                    tenant_id=tenant_id,
                    src_size=(src_w, src_h),
                    out_size=(out_w, out_h),
                    work_dir=work,
                )
            except Exception:  # noqa: BLE001 - a bad logo file must not lose the captions
                logger.exception("Creative Studio finish: logo could not be prepared")
                logo = None
            if logo is None:
                warnings.append(
                    "No brand logo was available, so the logo was not added. Upload a logo to the "
                    "brand or attach one with the Logo role."
                )
        if not events and logo is None:
            raise ValueError(" ".join(warnings) or "Nothing could be added to this video.")

        chain = [f"[0:v]scale={out_w}:{out_h}:flags=lanczos,setsar=1[base]"]
        current = "base"
        command = [ffmpeg, "-y", "-i", "input.mp4"]
        if logo is not None:
            _, logo_x, logo_y, logo_w = logo
            command += ["-i", "logo.png"]
            chain.append(f"[1:v]format=rgba,scale={logo_w}:-1:flags=lanczos[logo]")
            chain.append(f"[{current}][logo]overlay={logo_x}:{logo_y}:format=auto[branded]")
            current = "branded"
        if events:
            (work / "captions.ass").write_text(
                build_caption_ass(events, width=out_w, height=out_h), encoding="utf-8-sig"
            )
            chain.append(f"[{current}]subtitles=captions.ass:charenc=UTF-8[captioned]")
            current = "captioned"
        command += [
            "-filter_complex", ";".join(chain), "-map", f"[{current}]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart", "output.mp4",
        ]
        # Relative paths with cwd avoid Windows drive-letter colons inside the filter.
        proc = subprocess.run(command, capture_output=True, text=True, cwd=str(work))
        output = work / "output.mp4"
        if proc.returncode != 0 or not output.is_file() or output.stat().st_size < 1000:
            logger.error("Creative Studio finish failed: %s", (proc.stderr or "")[-1200:])
            raise RuntimeError("Captions and logo could not be added to this video.")
        saved = file_service.save_bytes(
            content=output.read_bytes(),
            tenant_id=tenant_id,
            subfolder="generated",
            suffix=".mp4",
            content_type="video/mp4",
        )
    return {
        "url": str(saved["file_url"]),
        "source_url": str(video_url),
        "captions_applied": bool(events),
        "caption_count": len(events),
        "logo_applied": logo is not None,
        "width": out_w,
        "height": out_h,
        "duration_seconds": round(duration, 2),
        "warnings": warnings,
    }
