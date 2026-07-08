"""Normalize reel/landscape video to full-frame 1080x1920 or 1920x1080 — fix HeyGen letterboxing."""

from __future__ import annotations

import io
import logging
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from app.core.config import settings
from app.services.logo_overlay import file_url_to_local_path
from app.services.media.voiceover import _ffmpeg_executable

logger = logging.getLogger(__name__)

PORTRAIT_W = 1080
PORTRAIT_H = 1920
LANDSCAPE_W = 1920
LANDSCAPE_H = 1080
_CROP_RE = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")
_PORTRAIT_AR = PORTRAIT_W / PORTRAIT_H  # 9:16
_LANDSCAPE_AR = LANDSCAPE_W / LANDSCAPE_H  # 16:9


def is_vertical_format(format_type: str | None) -> bool:
    """9:16 reel/stories only — NOT landscape `video` (16:9 must not be cropped to portrait)."""
    return (format_type or "").lower() in {"reel", "stories"}


def is_landscape_format(format_type: str | None) -> bool:
    return (format_type or "").lower() == "video"


def should_normalize_format(format_type: str | None) -> bool:
    return is_vertical_format(format_type) or is_landscape_format(format_type)


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


def _ffprobe_duration(video_path: Path) -> float:
    from app.services.video_logo_overlay import _ffprobe_executable

    ffprobe = _ffprobe_executable()
    if not ffprobe:
        return 30.0
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
    if proc.returncode == 0 and proc.stdout.strip():
        try:
            return max(1.0, float(proc.stdout.strip()))
        except ValueError:
            pass
    return 30.0


def _sample_timestamps_for_bars(video_path: Path, ffmpeg: str) -> list[float]:
    """Sample early, mid, and late frames — B-roll letterboxing often appears after the hook."""
    duration = _ffprobe_duration(video_path)
    stamps = {0.5, 1.0, 2.0, 4.0}
    for ratio in (0.12, 0.25, 0.4, 0.55, 0.7, 0.85):
        stamps.add(max(0.5, min(duration - 0.5, duration * ratio)))
    return sorted(stamps)


def _scan_frame_borders(img) -> tuple[str, int, int, int, int]:
    """Return crop string and content dimensions for a single frame."""
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
    return f"{cw}:{ch}:{left}:{top}", cw, ch, w, h


def _detect_consensus_border_crop(
    video_path: Path,
    ffmpeg: str,
    *,
    label: str,
    accept,
) -> str | None:
    """Crop only when enough sampled frames agree (avoids wrong crop on mixed scenes)."""
    from PIL import Image

    crops: list[str] = []
    areas: dict[str, float] = {}
    for t in _sample_timestamps_for_bars(video_path, ffmpeg):
        raw = _extract_png_frame(ffmpeg, video_path, seconds=t)
        if not raw:
            continue
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        crop, cw, ch, w, h = _scan_frame_borders(img)
        if accept(cw, ch, w, h):
            crops.append(crop)
            areas[crop] = (cw * ch) / max(w * h, 1)

    if not crops:
        return None

    counts = Counter(crops)
    crop, hits = counts.most_common(1)[0]
    samples = len(_sample_timestamps_for_bars(video_path, ffmpeg))
    area_ratio = areas.get(crop, 1.0)
    # Severe windowbox (tiny clip on black canvas) — lower bar to fix HeyGen B-roll
    min_hits = max(2, int(samples * 0.25)) if area_ratio < 0.45 else max(3, int(samples * 0.4))
    if hits >= min_hits:
        logger.info(
            "%s: consensus border crop %s (%s/%s frames, area=%.0f%%)",
            label,
            crop,
            hits,
            samples,
            area_ratio * 100,
        )
        return crop
    return None


def _portrait_border_accept(cw: int, ch: int, w: int, h: int) -> bool:
    area_ratio = (cw * ch) / max(w * h, 1)
    # Letterbox: landscape band inside portrait
    if cw >= int(w * 0.94) and ch < int(h * 0.88):
        return True
    # Windowbox: small clip floating on black canvas
    if cw < int(w * 0.92) and ch < int(h * 0.92) and area_ratio < 0.72:
        return True
    return False


def _landscape_fit_vf() -> str:
    """Fit content inside 16:9 without cropping faces (letterbox if needed)."""
    return (
        f"scale={LANDSCAPE_W}:{LANDSCAPE_H}:force_original_aspect_ratio=decrease,"
        f"pad={LANDSCAPE_W}:{LANDSCAPE_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    )


def _landscape_border_accept(cw: int, ch: int, w: int, h: int) -> bool:
    area_ratio = (cw * ch) / max(w * h, 1)
    # Only true windowbox — small clip on large black canvas (not a normal talking head)
    return cw < int(w * 0.88) and ch < int(h * 0.88) and area_ratio < 0.55


def _build_landscape_vf(video_path: Path, ffmpeg: str) -> str:
    """Always produce a 1920×1080 output.

    Landscape/square source  → cover-scale (zoom to fill, crop edges slightly).
    Portrait source           → fit-scale  (letterbox sides; preserves face).

    Never returns None — we always re-encode so windowbox baked in by HeyGen
    is reliably removed regardless of whether bar-detection succeeds.
    """
    width, height = _ffprobe_size(video_path)
    logger.info("Landscape normalize: source %sx%s", width, height)

    # Clearly portrait (e.g. HeyGen ignores orientation field)
    # → fit inside 1920×1080 with black bars rather than zoom into face
    if height > int(width * 1.1):
        logger.info("Landscape normalize: portrait source → fit to 1920x1080")
        return _landscape_fit_vf()

    # Landscape or near-square → cover-scale to fill every pixel of 1920×1080.
    # This removes any windowbox (small clip on black canvas) HeyGen bakes in.
    return _landscape_cover_vf()


def _detect_bars_from_frame(video_path: Path, ffmpeg: str, *, portrait: bool) -> str | None:
    label = "Portrait normalize" if portrait else "Landscape normalize"
    accept = _portrait_border_accept if portrait else _landscape_border_accept
    return _detect_consensus_border_crop(video_path, ffmpeg, label=label, accept=accept)


def _detect_letterbox_crop_ffmpeg(ffmpeg: str, video_path: Path) -> str | None:
    best: tuple[int, str] | None = None
    full_w, full_h = _ffprobe_size(video_path)
    duration = _ffprobe_duration(video_path)
    scan_t = min(8.0, max(4.0, duration * 0.35))

    for limit in (8, 12, 18, 28):
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-ss",
            str(max(0.0, duration * 0.15)),
            "-i",
            str(video_path),
            "-vf",
            f"cropdetect=limit={limit}:round=2:reset=300",
            "-t",
            str(scan_t),
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


def _cover_scale_crop_vf(*, width: int, height: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,setdar={width}/{height}"
    )


def _portrait_cover_vf() -> str:
    return _cover_scale_crop_vf(width=PORTRAIT_W, height=PORTRAIT_H)


def _landscape_cover_vf() -> str:
    return _cover_scale_crop_vf(width=LANDSCAPE_W, height=LANDSCAPE_H)


def _build_portrait_vf(video_path: Path, ffmpeg: str) -> str:
    width, height = _ffprobe_size(video_path)
    steps: list[str] = []

    if width > int(height * 1.02):
        logger.info("Portrait normalize: landscape source %sx%s", width, height)
        return _portrait_cover_vf()

    crop = _detect_letterbox_crop_ffmpeg(ffmpeg, video_path)
    if not crop:
        crop = _detect_bars_from_frame(video_path, ffmpeg, portrait=True)

    if crop:
        cw, ch, _, _ = (int(v) for v in crop.split(":"))
        if cw < int(width * 0.96) or ch < int(height * 0.88):
            steps.append(f"crop={crop}")
        else:
            crop = None

    if not crop:
        ar = width / max(height, 1)
        if ar < _PORTRAIT_AR * 0.85:
            crop_h = int(width / _PORTRAIT_AR)
            if crop_h < height:
                y = (height - crop_h) // 2
                steps.append(f"crop={width}:{crop_h}:0:{y}")
                logger.info("Portrait normalize: pillarbox fallback crop h=%s", crop_h)

    steps.append(_portrait_cover_vf())
    return ",".join(steps)


def _encode_normalized_video(
    video_path: Path,
    vf: str,
    *,
    tenant_id: str,
    label: str,
    target_ar: float,
    suffix_tag: str,
) -> str | None:
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        logger.warning("%s skipped: ffmpeg not found", label)
        return None

    from app.services.file_service import file_service
    from app.services.media_content import video_suffix_and_type

    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / f"{suffix_tag}{video_path.suffix or '.mp4'}"
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
                    "%s ffmpeg failed: %s",
                    label,
                    (proc.stderr or proc.stdout)[-800:],
                )
                return None

            out_w, out_h = _ffprobe_size(out)
            if abs(out_w / max(out_h, 1) - target_ar) > 0.03:
                logger.warning("%s output aspect unexpected: %sx%s", label, out_w, out_h)

            content = out.read_bytes()
            suffix, content_type = video_suffix_and_type(content)
            saved = file_service.save_bytes(
                content=content,
                tenant_id=tenant_id,
                subfolder="generated",
                suffix=suffix,
                content_type=content_type,
            )
            logger.info("%s OK → %s (%sx%s)", label, saved["file_url"], out_w, out_h)
            return saved["file_url"]
    except Exception:
        logger.exception("%s failed for %s", label, video_path)
        return None


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
        return None

    vf = _build_portrait_vf(video_path, ffmpeg)
    return _encode_normalized_video(
        video_path,
        vf,
        tenant_id=tenant_id,
        label="Portrait normalize",
        target_ar=_PORTRAIT_AR,
        suffix_tag="portrait",
    )


def normalize_landscape_video_file(
    video_file_url: str,
    *,
    tenant_id: str,
    format_type: str | None = None,
) -> str | None:
    """Force 1920×1080 landscape — always re-encode so HeyGen windowbox is removed."""
    if not is_landscape_format(format_type):
        return None
    if not _portrait_normalize_enabled():
        return None

    video_path = file_url_to_local_path(video_file_url)
    if not video_path:
        logger.warning("Landscape normalize skipped: not local %s", video_file_url[:80])
        return None

    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        logger.warning("Landscape normalize skipped: ffmpeg not found")
        return None

    # _build_landscape_vf always returns a VF string (never None)
    vf = _build_landscape_vf(video_path, ffmpeg)
    return _encode_normalized_video(
        video_path,
        vf,
        tenant_id=tenant_id,
        label="Landscape normalize",
        target_ar=_LANDSCAPE_AR,
        suffix_tag="landscape",
    )


def normalize_video_file(
    video_file_url: str,
    *,
    tenant_id: str,
    format_type: str | None,
) -> str | None:
    """Full-frame normalize for reel/stories (9:16) or landscape video (16:9)."""
    if is_vertical_format(format_type):
        return normalize_portrait_video_file(
            video_file_url, tenant_id=tenant_id, format_type=format_type
        )
    if is_landscape_format(format_type):
        return normalize_landscape_video_file(
            video_file_url, tenant_id=tenant_id, format_type=format_type
        )
    return None
