"""Normalize reel/video to full-frame 1080x1920 — fix HeyGen letterboxing."""

from __future__ import annotations

import io
import logging
import re
import subprocess
import tempfile
from pathlib import Path

from app.core.config import settings
from app.services.logo_overlay import file_url_to_local_path
from app.services.media.voiceover import _ffmpeg_executable

logger = logging.getLogger(__name__)

PORTRAIT_W = 1080
PORTRAIT_H = 1920
_CROP_RE = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")
_TARGET_AR = PORTRAIT_W / PORTRAIT_H  # 9:16


def is_vertical_format(format_type: str | None) -> bool:
    """9:16 reel/stories only — NOT landscape `video` (16:9 must not be cropped to portrait)."""
    return (format_type or "").lower() in {"reel", "stories"}


def _portrait_normalize_enabled() -> bool:
    raw = getattr(settings, "VIDEO_PORTRAIT_NORMALIZE", True)
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw)


def _ffprobe_size(video_path: Path) -> tuple[int, int]:
    from app.services.video_logo_overlay import _ffprobe_executable

    ffprobe = _ffprobe_executable()
    if not ffprobe:
        return PORTRAIT_W, PORTRAIT_H
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and "x" in proc.stdout:
        w, h = proc.stdout.strip().split("x", 1)
        return max(1, int(w)), max(1, int(h))
    return PORTRAIT_W, PORTRAIT_H


def _extract_png_frame(ffmpeg: str, video_path: Path, seconds: float = 1.0) -> bytes | None:
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-ss",
        str(seconds),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or len(proc.stdout) < 100:
        return None
    return proc.stdout


def _row_is_border(img, y: int, *, w: int, threshold: int = 28) -> bool:
    from PIL import Image

    if not isinstance(img, Image.Image):
        return False
    samples = [img.getpixel((x, y))[:3] for x in range(0, w, max(1, w // 48))]
    if not samples:
        return True
    ref = samples[0]
    return all(
        abs(r - ref[0]) + abs(g - ref[1]) + abs(b - ref[2]) < threshold
        for r, g, b in samples
    )


def _col_is_border(img, x: int, *, h: int, threshold: int = 28) -> bool:
    from PIL import Image

    samples = [img.getpixel((x, y))[:3] for y in range(0, h, max(1, h // 48))]
    if not samples:
        return True
    ref = samples[0]
    return all(
        abs(r - ref[0]) + abs(g - ref[1]) + abs(b - ref[2]) < threshold
        for r, g, b in samples
    )


def _detect_bars_from_frame(video_path: Path, ffmpeg: str) -> str | None:
    """Detect uniform black/white bars via frame scan (fallback when cropdetect fails)."""
    from PIL import Image

    for t in (0.5, 1.0, 2.0, 4.0):
        raw = _extract_png_frame(ffmpeg, video_path, seconds=t)
        if not raw:
            continue
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size

        top = 0
        while top < h - 8 and _row_is_border(img, top, w=w):
            top += 2
        bottom = h - 1
        while bottom > top + 8 and _row_is_border(img, bottom, w=w):
            bottom -= 2

        left = 0
        while left < w - 8 and _col_is_border(img, left, h=h):
            left += 2
        right = w - 1
        while right > left + 8 and _col_is_border(img, right, h=h):
            right -= 2

        cw = right - left + 1
        ch = bottom - top + 1
        if cw < int(w * 0.96) or ch < int(h * 0.88):
            logger.info(
                "Portrait normalize: frame bar crop %sx%s at %s,%s (from %sx%s)",
                cw,
                ch,
                left,
                top,
                w,
                h,
            )
            return f"{cw}:{ch}:{left}:{top}"
    return None


def _detect_letterbox_crop_ffmpeg(ffmpeg: str, video_path: Path) -> str | None:
    best: tuple[int, str] | None = None
    full_w, full_h = _ffprobe_size(video_path)

    for limit in (8, 12, 18, 28):
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-i",
            str(video_path),
            "-vf",
            f"cropdetect=limit={limit}:round=2:reset=300",
            "-t",
            "8",
            "-f",
            "null",
            "-",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        text = (proc.stderr or "") + (proc.stdout or "")
        for match in _CROP_RE.findall(text):
            w, h, x, y = (int(v) for v in match)
            if w < 32 or h < 32:
                continue
            if w >= int(full_w * 0.99) and h >= int(full_h * 0.99):
                continue
            area = w * h
            if best is None or area < best[0]:
                best = (area, f"{w}:{h}:{x}:{y}")

    if best:
        logger.info("Portrait normalize: cropdetect %s", best[1])
        return best[1]
    return None


def _cover_scale_crop_vf() -> str:
    return (
        f"scale={PORTRAIT_W}:{PORTRAIT_H}:force_original_aspect_ratio=increase,"
        f"crop={PORTRAIT_W}:{PORTRAIT_H},setsar=1,setdar={PORTRAIT_W}/{PORTRAIT_H}"
    )


def _build_portrait_vf(video_path: Path, ffmpeg: str) -> str:
    width, height = _ffprobe_size(video_path)
    steps: list[str] = []

    # Pure landscape file → zoom to fill 9:16 (fixes black bars left/right in player)
    if width > int(height * 1.02):
        logger.info("Portrait normalize: landscape source %sx%s", width, height)
        return _cover_scale_crop_vf()

    crop = _detect_letterbox_crop_ffmpeg(ffmpeg, video_path)
    if not crop:
        crop = _detect_bars_from_frame(video_path, ffmpeg)

    if crop:
        cw, ch, _, _ = (int(v) for v in crop.split(":"))
        # Pillarbox inside portrait canvas (content narrower than frame)
        if cw < int(width * 0.96):
            steps.append(f"crop={crop}")
        # Letterbox (content shorter than frame)
        elif ch < int(height * 0.88):
            steps.append(f"crop={crop}")
        else:
            crop = None

    if not crop:
        ar = width / max(height, 1)
        # Still pillarboxed but detectors missed — center crop to 9:16 then fill
        if ar < _TARGET_AR * 0.85:
            crop_h = int(width / _TARGET_AR)
            if crop_h < height:
                y = (height - crop_h) // 2
                steps.append(f"crop={width}:{crop_h}:0:{y}")
                logger.info("Portrait normalize: pillarbox fallback crop h=%s", crop_h)

    steps.append(_cover_scale_crop_vf())
    return ",".join(steps)


def normalize_portrait_video_file(
    video_file_url: str,
    *,
    tenant_id: str,
    format_type: str | None = None,
) -> str | None:
    """Remove baked-in bars and force 1080x1920 portrait."""
    if not is_vertical_format(format_type):
        return None
    if not _portrait_normalize_enabled():
        return None

    video_path = file_url_to_local_path(video_file_url)
    if not video_path:
        logger.warning("Portrait normalize skipped: not local %s", video_file_url[:80])
        return None

    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        logger.warning("Portrait normalize skipped: ffmpeg not found")
        return None

    from app.services.file_service import file_service
    from app.services.media_content import video_suffix_and_type

    try:
        vf = _build_portrait_vf(video_path, ffmpeg)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / f"portrait{video_path.suffix or '.mp4'}"
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                str(video_path),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-colorspace",
                "bt709",
                "-color_primaries",
                "bt709",
                "-color_trc",
                "bt709",
                "-c:a",
                "copy",
                "-movflags",
                "+faststart",
                str(out),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                logger.warning(
                    "Portrait normalize ffmpeg failed: %s",
                    (proc.stderr or proc.stdout)[-800:],
                )
                return None

            out_w, out_h = _ffprobe_size(out)
            if abs(out_w / max(out_h, 1) - _TARGET_AR) > 0.03:
                logger.warning(
                    "Portrait normalize output aspect unexpected: %sx%s",
                    out_w,
                    out_h,
                )

            content = out.read_bytes()
            suffix, content_type = video_suffix_and_type(content)
            saved = file_service.save_bytes(
                content=content,
                tenant_id=tenant_id,
                subfolder="generated",
                suffix=suffix,
                content_type=content_type,
            )
            logger.info(
                "Portrait normalize OK %s → %s (%sx%s)",
                video_file_url[-40:],
                saved["file_url"],
                *_ffprobe_size(out),
            )
            return saved["file_url"]
    except Exception:
        logger.exception("Portrait normalize failed for %s", video_file_url)
        return None
