"""Composite the brand's uploaded logo onto generated ad images."""

from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

LIGHT_BACKGROUND_THRESHOLD = 165
CAROUSEL_HEADER_RATIO = 0.11
VERTICAL_HEADER_RATIO = 0.13
# Runway image_to_video requires width/height >= 0.5 on promptImage.
RUNWAY_MIN_WH_RATIO = 0.501


def file_url_to_local_path(file_url: str | None) -> Path | None:
    if not file_url:
        return None
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    rel: Path | None = None
    if file_url.startswith("/files/"):
        rel = Path(file_url.removeprefix("/files/"))
    elif file_url.startswith("files/"):
        rel = Path(file_url.removeprefix("files/"))
    elif file_url.startswith("http://") or file_url.startswith("https://"):
        return None
    if rel is None:
        return None
    path = (upload_root / rel).resolve()
    try:
        path.relative_to(upload_root)
    except ValueError:
        return None
    return path if path.is_file() else None


def _uses_header_band(format_type: str | None, width: int, height: int) -> bool:
    ft = (format_type or "").lower()
    # Reels/video: full-bleed portrait; brand logo is burned onto the video file.
    if ft in {"reel", "video", "stories"}:
        return False
    if ft == "carousel":
        return True
    return width > int(height * 1.25)


def _region_is_light(img: Image.Image, left: int, top: int, width: int, height: int) -> bool:
    right = min(img.width, left + width)
    bottom = min(img.height, top + height)
    if right <= left or bottom <= top:
        return True
    region = img.crop((left, top, right, bottom)).convert("RGB")
    pixels = list(region.getdata())
    if not pixels:
        return True
    avg = sum(r + g + b for r, g, b in pixels) / (3 * len(pixels))
    return avg >= LIGHT_BACKGROUND_THRESHOLD


def _is_orange_brand_pixel(r: int, g: int, b: int) -> bool:
    return r > 140 and r > g + 25 and r > b + 15 and g < 210 and b < 180


def _recolor_white_text_to_dark(logo: Image.Image) -> Image.Image:
    out = logo.copy()
    px = out.load()
    w, h = out.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 40:
                continue
            if _is_orange_brand_pixel(r, g, b):
                continue
            luminance = 0.299 * r + 0.587 * g + 0.114 * b
            if luminance >= 200:
                px[x, y] = (22, 22, 22, a)
            elif luminance >= 155:
                px[x, y] = (38, 38, 38, a)
    return out


def _prepare_logo_for_background(
    logo: Image.Image,
    *,
    light_background: bool,
    use_uploaded_light_variant: bool,
) -> Image.Image:
    if not light_background:
        return logo
    if use_uploaded_light_variant:
        return logo
    return _recolor_white_text_to_dark(logo)


def _pad_to_runway_min_aspect_ratio(img: Image.Image, min_ratio: float = RUNWAY_MIN_WH_RATIO) -> Image.Image:
    """Pad sides so width/height meets Runway video promptImage validation."""
    w, h = img.size
    if h <= 0 or w / h >= min_ratio:
        return img
    new_w = int(h * min_ratio) + 2
    canvas = Image.new("RGBA", (new_w, h), (245, 245, 245, 255))
    if img.mode == "RGBA":
        canvas.paste(img, ((new_w - w) // 2, 0), img.split()[3])
    else:
        canvas.paste(img, ((new_w - w) // 2, 0))
    return canvas


def _add_carousel_header_band(
    base: Image.Image,
    logo_height: int,
    pad: int,
    *,
    format_type: str | None = None,
) -> tuple[Image.Image, int]:
    """Shift creative down and add a clean header band for the logo."""
    ft = (format_type or "").lower()
    ratio = VERTICAL_HEADER_RATIO if ft in {"reel", "video"} else CAROUSEL_HEADER_RATIO
    header_h = max(int(base.height * ratio), logo_height + pad * 3)
    canvas = Image.new("RGBA", (base.width, base.height + header_h), (245, 245, 245, 255))
    canvas.paste(base, (0, header_h))
    return canvas, header_h


def _crop_center_to_aspect(img: Image.Image, target_w_over_h: float) -> Image.Image:
    """Center-crop to target aspect ratio (e.g. 9/16 for portrait)."""
    w, h = img.size
    if w <= 0 or h <= 0:
        return img
    current = w / h
    if abs(current - target_w_over_h) < 0.02:
        return img
    if current > target_w_over_h:
        new_w = max(1, int(h * target_w_over_h))
        left = (w - new_w) // 2
        return img.crop((left, 0, left + new_w, h))
    new_h = max(1, int(w / target_w_over_h))
    top = (h - new_h) // 2
    return img.crop((0, top, w, top + new_h))


def _resize_portrait_seed(img: Image.Image, *, width: int = 1080, height: int = 1920) -> Image.Image:
    cropped = _crop_center_to_aspect(img, width / height)
    return cropped.resize((width, height), Image.Resampling.LANCZOS)


def pad_image_bytes_for_runway_video(image_bytes: bytes) -> bytes:
    """Prepare image_to_video seed: true 9:16 portrait, no side letterbox padding."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    portrait = _resize_portrait_seed(img)
    out = io.BytesIO()
    flat = Image.new("RGB", portrait.size, (255, 255, 255))
    flat.paste(portrait, mask=portrait.split()[3])
    flat.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _pick_logo_rgba_for_placement(
    *,
    logo_path: Path,
    logo_on_light_path: Path | None,
    light_background: bool,
    max_width: int,
) -> Image.Image:
    """One Brand Kit mark: primary (light) on dark areas, on_light (dark) on bright areas."""
    if light_background and logo_on_light_path and logo_on_light_path.is_file():
        logo_src = Image.open(logo_on_light_path).convert("RGBA")
        use_light_variant = True
    else:
        logo_src = Image.open(logo_path).convert("RGBA")
        use_light_variant = False

    if logo_src.width > max_width:
        scale = max_width / logo_src.width
        logo_src = logo_src.resize(
            (max_width, max(1, int(logo_src.height * scale))),
            Image.Resampling.LANCZOS,
        )

    return _prepare_logo_for_background(
        logo_src,
        light_background=light_background,
        use_uploaded_light_variant=use_light_variant,
    )


def apply_logo_overlay_bytes(
    image_bytes: bytes,
    logo_path: Path,
    *,
    logo_on_light_path: Path | None = None,
    format_type: str | None = None,
    max_width_ratio: float = 0.18,
    padding_ratio: float = 0.04,
) -> bytes:
    """Paste logo in the top margin; carousel layouts get a dedicated header band."""
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    pad = max(8, int(base.width * padding_ratio))
    header_band = _uses_header_band(format_type, base.width, base.height)
    max_w_ratio = 0.12 if header_band else max_width_ratio
    max_w = max(32, int(base.width * max_w_ratio))

    header_h = 0
    probe_h = max(32, int(max_w * 0.35))
    if header_band:
        base, header_h = _add_carousel_header_band(
            base, probe_h, pad, format_type=format_type
        )
        logo_x = pad
        logo_y = max(pad, (header_h - probe_h) // 2)
    else:
        logo_x = pad
        logo_y = pad

    light_bg = _region_is_light(base, logo_x, logo_y, max_w, probe_h)
    logo = _pick_logo_rgba_for_placement(
        logo_path=logo_path,
        logo_on_light_path=logo_on_light_path,
        light_background=light_bg,
        max_width=max_w,
    )
    if header_band:
        logo_y = max(pad, (header_h - logo.height) // 2)

    base.paste(logo, (logo_x, logo_y), logo)

    out = io.BytesIO()
    flat = Image.new("RGB", base.size, (255, 255, 255))
    flat.paste(base, mask=base.split()[3])
    flat.save(out, format="PNG", optimize=True)
    return out.getvalue()


def apply_logo_overlay_to_file(
    image_file_url: str,
    logo_url: str | None,
    *,
    tenant_id: str,
    logo_on_light_url: str | None = None,
    format_type: str | None = None,
) -> str | None:
    from app.services.file_service import file_service
    from app.services.media_content import image_suffix_and_type

    logo_path = file_url_to_local_path(logo_url)
    image_path = file_url_to_local_path(image_file_url)
    if not logo_path or not image_path:
        return image_file_url

    logo_on_light_path = file_url_to_local_path(logo_on_light_url)

    try:
        image_bytes = image_path.read_bytes()
        merged = apply_logo_overlay_bytes(
            image_bytes,
            logo_path,
            logo_on_light_path=logo_on_light_path,
            format_type=format_type,
        )
        suffix, content_type = image_suffix_and_type(merged)
        saved = file_service.save_bytes(
            content=merged,
            tenant_id=tenant_id,
            subfolder="generated",
            suffix=suffix,
            content_type=content_type,
        )
        try:
            image_path.unlink(missing_ok=True)
        except OSError:
            pass
        return saved["file_url"]
    except Exception:
        logger.exception("Logo overlay failed for %s", image_file_url)
        return image_file_url
