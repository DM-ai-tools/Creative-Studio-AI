"""Composite the brand's uploaded logo onto generated ad images."""

from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

LIGHT_BACKGROUND_THRESHOLD = 165
CAROUSEL_HEADER_RATIO = 0.09
VERTICAL_HEADER_RATIO = 0.10
# Runway image_to_video requires width/height >= 0.5 on promptImage.
RUNWAY_MIN_WH_RATIO = 0.501
# Logo width inside the white header strip (~18% of image width).
HEADER_LOGO_WIDTH_RATIO = 0.18


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
    """Still ads get a small white top strip for the brand logo (avoids covering copy)."""
    del width, height
    ft = (format_type or "").lower()
    # Video stills / motion seeds stay full-bleed — logo is burned on the video later.
    if ft in {"reel", "video", "stories"}:
        return False
    return True


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
    """Shift creative down and add a clean white header strip for the logo."""
    ft = (format_type or "").lower()
    ratio = VERTICAL_HEADER_RATIO if ft in {"reel", "video"} else CAROUSEL_HEADER_RATIO
    header_h = max(int(base.height * ratio), logo_height + pad * 2)
    # Cap so the strip stays a small bar, not a huge empty zone.
    header_h = min(header_h, max(56, int(base.height * 0.12)))
    canvas = Image.new("RGBA", (base.width, base.height + header_h), (255, 255, 255, 255))
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


def _region_luminance_stats(
    img: Image.Image, left: int, top: int, width: int, height: int
) -> tuple[float, float]:
    """Return (average luminance, luminance std-dev) for a region."""
    right = min(img.width, left + max(1, width))
    bottom = min(img.height, top + max(1, height))
    if right <= left or bottom <= top:
        return 128.0, 0.0
    region = img.crop((left, top, right, bottom)).convert("L")
    # Downsample for speed
    sample = region.resize(
        (min(48, region.width), min(32, region.height)),
        Image.Resampling.BILINEAR,
    )
    values = list(sample.getdata())
    if not values:
        return 128.0, 0.0
    n = float(len(values))
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    return mean, var ** 0.5


def _region_edge_density(
    img: Image.Image, left: int, top: int, width: int, height: int
) -> float:
    """Rough text/detail detector: fraction of strong horizontal/vertical edges."""
    right = min(img.width, left + max(1, width))
    bottom = min(img.height, top + max(1, height))
    if right <= left + 2 or bottom <= top + 2:
        return 0.0
    region = img.crop((left, top, right, bottom)).convert("L")
    small = region.resize(
        (min(64, region.width), min(40, region.height)),
        Image.Resampling.BILINEAR,
    )
    px = small.load()
    w, h = small.size
    edges = 0
    total = 0
    for y in range(h - 1):
        for x in range(w - 1):
            total += 1
            dx = abs(px[x + 1, y] - px[x, y])
            dy = abs(px[x, y + 1] - px[x, y])
            if dx > 28 or dy > 28:
                edges += 1
    return edges / total if total else 0.0


def _region_is_busy(
    img: Image.Image, left: int, top: int, width: int, height: int
) -> bool:
    """True when corner likely contains text or high-detail UI (avoid logo overlap)."""
    _mean, std = _region_luminance_stats(img, left, top, width, height)
    edges = _region_edge_density(img, left, top, width, height)
    # Text on dark banners: high edge density + moderate variance
    return edges >= 0.12 or std >= 42.0


def _estimate_top_dark_banner_height(img: Image.Image) -> int:
    """Height of a dark overlay strip at the top (headline bar), if present."""
    gray = img.convert("L")
    w, h = gray.size
    max_scan = max(1, int(h * 0.28))
    row_step = max(1, max_scan // 40)
    dark_rows = 0
    for y in range(0, max_scan, row_step):
        # Sample a horizontal band across the middle of the frame
        band = gray.crop((int(w * 0.15), y, int(w * 0.85), min(h, y + row_step)))
        pixels = list(band.getdata())
        if not pixels:
            break
        avg = sum(pixels) / len(pixels)
        if avg <= 95:
            dark_rows = y + row_step
        elif dark_rows > 0 and avg > 120:
            break
    if dark_rows < int(h * 0.06):
        return 0
    return min(dark_rows + int(h * 0.01), int(h * 0.32))


def _pick_logo_anchor(
    img: Image.Image,
    *,
    logo_w: int,
    logo_h: int,
    pad: int,
) -> tuple[int, int]:
    """Choose top-left or top-right (or below dark banner) so logo does not cover text."""
    banner_h = _estimate_top_dark_banner_height(img)
    # Prefer sitting just below a dark headline strip when present
    y_below = max(pad, banner_h + pad // 2) if banner_h else pad

    candidates: list[tuple[str, int, int]] = [
        ("top_left", pad, pad),
        ("top_right", max(pad, img.width - logo_w - pad), pad),
        ("below_banner_left", pad, y_below),
        ("below_banner_right", max(pad, img.width - logo_w - pad), y_below),
    ]
    # Prefer left side when clear
    preference = ("top_left", "below_banner_left", "top_right", "below_banner_right")

    scored: list[tuple[float, int, str, int, int]] = []
    for name, x, y in candidates:
        x = max(0, min(x, img.width - logo_w))
        y = max(0, min(y, img.height - logo_h))
        busy = _region_is_busy(img, x, y, logo_w, logo_h)
        edges = _region_edge_density(img, x, y, logo_w, logo_h)
        pref = preference.index(name) if name in preference else 9
        # Lower score is better
        score = (1.0 if busy else 0.0) * 10 + edges * 5 + pref * 0.1
        scored.append((score, pref, name, x, y))

    scored.sort(key=lambda t: (t[0], t[1]))
    _score, _pref, name, x, y = scored[0]
    logger.info(
        "Logo placement: %s at (%s,%s) banner_h=%s score=%.2f",
        name,
        x,
        y,
        banner_h,
        _score,
    )
    return x, y


def apply_logo_overlay_bytes(
    image_bytes: bytes,
    logo_path: Path,
    *,
    logo_on_light_path: Path | None = None,
    format_type: str | None = None,
    max_width_ratio: float = 0.22,
    padding_ratio: float = 0.03,
) -> bytes:
    """Paste brand logo — stills use a small white top strip so logo never covers ad text."""
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    pad = max(10, int(base.width * padding_ratio))
    header_band = _uses_header_band(format_type, base.width, base.height)

    if header_band:
        max_w = max(64, int(base.width * HEADER_LOGO_WIDTH_RATIO))
        probe_h = max(28, int(max_w * 0.35))
        base, header_h = _add_carousel_header_band(
            base, probe_h, pad, format_type=format_type
        )
        logo = _pick_logo_rgba_for_placement(
            logo_path=logo_path,
            logo_on_light_path=logo_on_light_path,
            light_background=True,
            max_width=max_w,
        )
        max_logo_h = max(20, header_h - pad * 2)
        if logo.height > max_logo_h:
            scale = max_logo_h / logo.height
            logo = logo.resize(
                (max(1, int(logo.width * scale)), max_logo_h),
                Image.Resampling.LANCZOS,
            )
        logo_x = pad
        logo_y = max(pad // 2, (header_h - logo.height) // 2)
        base.paste(logo, (logo_x, logo_y), logo)
        logger.info(
            "Logo on white header: canvas=%sx%s header_h=%s logo=%sx%s",
            base.width,
            base.height,
            header_h,
            logo.width,
            logo.height,
        )
    else:
        max_w = max(64, int(base.width * max_width_ratio))
        probe_h = max(40, int(max_w * 0.4))
        light_probe = _region_is_light(base, pad, pad, max_w, probe_h)
        logo = _pick_logo_rgba_for_placement(
            logo_path=logo_path,
            logo_on_light_path=logo_on_light_path,
            light_background=light_probe,
            max_width=max_w,
        )
        logo_x, logo_y = _pick_logo_anchor(
            base, logo_w=logo.width, logo_h=logo.height, pad=pad
        )
        light_bg = _region_is_light(base, logo_x, logo_y, logo.width, logo.height)
        if light_bg != light_probe:
            logo = _pick_logo_rgba_for_placement(
                logo_path=logo_path,
                logo_on_light_path=logo_on_light_path,
                light_background=light_bg,
                max_width=max_w,
            )
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
    from app.services.brand_logo import resolve_overlay_logo_paths
    from app.services.file_service import file_service
    from app.services.media_content import image_suffix_and_type

    logo_path, logo_on_light_path = resolve_overlay_logo_paths(logo_url, logo_on_light_url)
    image_path = file_url_to_local_path(image_file_url)
    if not logo_path or not image_path:
        if logo_url and not logo_path:
            logger.warning(
                "Logo overlay skipped — logo not readable (upload PNG/JPG on Brand Kit): %s",
                str(logo_url)[:120],
            )
        elif logo_url and not image_path:
            logger.warning(
                "Logo overlay skipped — generated image not readable: %s",
                str(image_file_url)[:120],
            )
        return image_file_url

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
