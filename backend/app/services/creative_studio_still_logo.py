"""Put the brand logo inside a drawn still, in a corner the user picks.

The image model is told to leave that corner empty (corner_prompt_rule), then the real logo file is
placed there, so the logo is never redrawn or misspelled and never covers the text. The light or dark
version of the logo is chosen from how bright the picture actually is under it: a dark mark on a light
background, a light mark on a dark one. The clean picture is never changed; a new copy is saved, so
the corner can be changed later without drawing again.
"""

from __future__ import annotations

import io
import logging
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

CORNERS = ("top_left", "top_right", "bottom_left", "bottom_right")
# Positions along the middle, for banner-style layouts that keep a clear strip at the top or bottom edge,
# and (rarely) the very centre. Auto never uses "center"; it may use a centre strip when every corner is busy.
CENTRE_POSITIONS = ("top_center", "bottom_center", "center")
POSITIONS = CORNERS + CENTRE_POSITIONS
CORNER_LABELS = {
    "top_left": "top-left",
    "top_right": "top-right",
    "bottom_left": "bottom-left",
    "bottom_right": "bottom-right",
    "top_center": "top-centre",
    "bottom_center": "bottom-centre",
    "center": "centre",
}
AUTO_ORDER = ("top_right", "top_left", "bottom_right", "bottom_left")  # tie-break order in Auto mode
LOGO_WIDTH_RATIO = 0.2 # of the picture's width
LOGO_MAX_HEIGHT_RATIO = 0.1  # of the picture's height, so a tall mark stays small
MARGIN_RATIO = 0.045  # gap from the picture edge (also keeps it inside phone safe areas)


def normalize_corner(value: str | None) -> str:
    """'top-right', 'Top Right' and 'top_right' all mean the same. Empty or 'none' means no logo."""
    text = (value or "").strip().lower().replace("-", "_").replace(" ", "_").replace("centre", "center")
    if text in {"", "none", "off", "no_logo"}:
        return ""
    if text not in POSITIONS:
        raise ValueError(
            "Choose top-left, top-right, bottom-left, bottom-right, top-centre, bottom-centre or centre for the logo."
        )
    return text


def corner_prompt_rule(corner: str | None) -> str:
    """Words added to the picture prompt so the model keeps that corner calm and empty."""
    key = normalize_corner(corner)
    if not key:
        return ""
    if key in CENTRE_POSITIONS:
        where = {
            "top_center": "the middle third of the width and the top sixth of the height (along the top edge)",
            "bottom_center": "the middle third of the width and the bottom sixth of the height (along the bottom edge)",
            "center": "the middle quarter of the width and the middle sixth of the height (the centre of the picture)",
        }[key]
        return (
            f" Keep the {CORNER_LABELS[key]} area of the picture clear: plain, calm background with no text, numbers, "
            f"icons, faces or busy detail in {where}, so the headline and every other line sit clear of it. "
            "This is a firm layout rule even for a busy infographic: shrink the artwork a little and leave that "
            "area empty rather than filling the edge. "
            "Do not draw any logo, brand mark or watermark anywhere; the real logo is added afterwards."
        )
    return (
        f" Keep the {CORNER_LABELS[key]} corner of the picture clear: plain, calm background with no text, "
        "numbers, icons, faces or busy detail in the outer quarter of the width and the outer sixth of the height "
        "there, so the headline and every other line start clear of that corner (to its side or below it). "
        "This is a firm layout rule even for a busy infographic: shrink the artwork a little and leave that margin "
        "empty rather than filling the edge. "
        "Do not draw any logo, brand mark or watermark anywhere; the real logo is added afterwards."
    )


def _trim(mark: Image.Image, fallback) -> Image.Image:
    """Cut empty margins so the mark sits right at the corner. A white mark is judged by its
    transparency (the shared trimmer treats near-white pixels as margin); an opaque file (a JPG
    with a white background) falls back to that shared trimmer."""
    box = mark.getchannel("A").point(lambda a: 255 if a > 25 else 0).getbbox()
    if box and box != (0, 0, mark.width, mark.height):
        return mark.crop(box)
    return fallback(mark)


def extract_logo(mark: Image.Image, tolerance: int = 34) -> Image.Image:
    """Take a logo off its backdrop so it sits directly on the picture, not in a white box.

    Many uploaded logos are a JPG or a PNG with a solid white (or other plain) background. If the four
    corners agree on one opaque colour, everything of that colour that is connected to the border is
    made transparent, plus a one-pixel fringe of its anti-aliasing so no halo is left. A logo that
    already has transparency, or whose corners are not one plain colour, is returned as it was. If
    removing the backdrop would leave almost nothing (a white mark on white), the original is kept.
    """
    from PIL import ImageChops, ImageDraw, ImageFilter

    rgba = mark.convert("RGBA")
    width, height = rgba.size
    if width < 4 or height < 4:
        return rgba
    px = rgba.load()
    corners = [px[0, 0], px[width - 1, 0], px[0, height - 1], px[width - 1, height - 1]]
    if any(c[3] < 250 for c in corners):
        return rgba  # already has a transparent background
    ref = tuple(sum(c[i] for c in corners) // 4 for i in range(3))
    if any(max(abs(c[i] - ref[i]) for i in range(3)) > 24 for c in corners):
        return rgba  # not a plain backdrop

    def distance(x: int, y: int) -> int:
        r, g, b, _ = px[x, y]
        return max(abs(r - ref[0]), abs(g - ref[1]), abs(b - ref[2]))

    backdrop = Image.new("L", (width, height), 0)  # 255 where a pixel is backdrop-coloured
    bp = backdrop.load()
    near = Image.new("L", (width, height), 0)  # 255 where it is almost backdrop-coloured (edge fringe)
    npx = near.load()
    for y in range(height):
        for x in range(width):
            d = distance(x, y)
            if d <= tolerance:
                bp[x, y] = 255
            if d <= tolerance * 2.5:
                npx[x, y] = 255
    # keep only the backdrop that touches the border (a white letter inside the mark stays)
    border = [(x, 0) for x in range(width)] + [(x, height - 1) for x in range(width)]
    border += [(0, y) for y in range(height)] + [(width - 1, y) for y in range(height)]
    for point in border:
        if bp[point] == 255:
            ImageDraw.floodfill(backdrop, point, 128)
    outside = backdrop.point(lambda v: 255 if v == 128 else 0)
    # the backdrop plus one pixel of its near-backdrop edge (anti-aliasing); a superset of `outside`
    removed = ImageChops.multiply(outside.filter(ImageFilter.MaxFilter(3)), near)
    alpha = removed.point(lambda v: 0 if v else 255)
    if sum(1 for v in alpha.getdata() if v) < width * height * 0.03:
        return rgba  # nothing would be left
    out = rgba.copy()
    out.putalpha(ImageChops.multiply(out.getchannel("A"), alpha))
    return out


def _extracted_copy(path: Path, folder: Path, name: str) -> Path:
    """A PNG of the logo with its plain backdrop removed (the original when there is none to remove).
    Large files are reduced first: a logo is never drawn bigger than a fraction of the picture, and
    the backdrop search should stay fast."""
    try:
        with Image.open(path) as source:
            image = source.convert("RGBA")
        if image.width > 900:
            image = image.resize((900, max(1, round(image.height * 900 / image.width))), Image.Resampling.LANCZOS)
        extracted = extract_logo(image)
        out = folder / f"{name}.png"
        extracted.save(out, format="PNG")
        return out
    except Exception:  # noqa: BLE001 - never lose the logo over a backdrop problem
        logger.exception("Logo backdrop removal failed for %s; using the file as uploaded", path)
        return path


def _luma(r: int, g: int, b: int) -> float:
    return 0.299 * r + 0.587 * g + 0.114 * b


def _lighten_dark_text(mark: Image.Image) -> Image.Image:
    """For a dark picture when the brand has only a dark logo file: dark, near-grey strokes (the
    wordmark and tagline) become white; coloured parts (a green or blue symbol) are left alone."""
    visible = [_luma(r, g, b) for r, g, b, a in mark.getdata() if a > 40]
    if not visible or sum(visible) / len(visible) >= 110:
        return mark  # already light enough to read on a dark picture
    out = mark.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a > 0 and _luma(r, g, b) < 100 and max(r, g, b) - min(r, g, b) < 80:
                px[x, y] = (255, 255, 255, a)
    return out


def _corner_position(corner: str, width: int, height: int, logo_w: int, logo_h: int) -> tuple[int, int]:
    margin = max(8, round(width * MARGIN_RATIO))
    if corner.endswith("center"):
        x = (width - logo_w) // 2
    else:
        x = margin if corner.endswith("left") else width - logo_w - margin
    if corner == "center":
        y = (height - logo_h) // 2
    else:
        y = margin if corner.startswith("top") else height - logo_h - margin
    return max(0, x), max(0, y)


def place_logo_in_corner(
    *,
    image_url: str,
    corner: str,
    tenant_id: str,
    logo_url: str | None,
    logo_on_light_url: str | None = None,
    suggested: str | None = None,
    avoid_text: bool = False,
    backing: str = "",
) -> dict[str, Any]:
    """Place the logo. ``corner`` is one of CORNERS, or ``"auto"``: measure all four corners of the
    finished picture and use the cleanest, preferring ``suggested`` (where the prompt left room).
    With ``avoid_text`` a chosen corner is kept only while it is clear: if the model put text or detail
    there, the logo moves to the cleanest corner instead of sitting on it."""
    from app.services.brand_logo import resolve_overlay_logo_paths
    from app.services.file_service import file_service
    from app.services.logo_overlay import (
        _pick_logo_rgba_for_placement,
        _region_edge_density,
        _region_is_busy,
        _region_is_light,
        _trim_logo_to_content,
        file_url_to_local_path,
    )

    auto = (corner or "").strip().lower() == "auto"
    key = "" if auto else normalize_corner(corner)
    if not auto and not key:
        raise ValueError("Choose a corner for the logo.")
    image_path = file_url_to_local_path(str(image_url or "").strip())
    if not image_path:
        raise ValueError("The picture could not be found. Draw it again and retry.")
    logo_path, on_light_path = resolve_overlay_logo_paths(logo_url, logo_on_light_url, tenant_id=tenant_id)
    if not logo_path:
        raise ValueError("No usable brand logo was found. Upload a PNG or JPG logo in the Brand Kit.")

    base = Image.open(image_path).convert("RGBA")
    width, height = base.size
    max_w = max(48, round(width * LOGO_WIDTH_RATIO))
    max_h = max(24, round(height * LOGO_MAX_HEIGHT_RATIO))

    # Take each logo file off its plain backdrop BEFORE the shared picker sees it (the picker can
    # recolour a white backdrop dark on a light picture, which would turn a white box into a dark one).
    scratch = tempfile.TemporaryDirectory(prefix="logo_extract_")
    logo_path = _extracted_copy(logo_path, Path(scratch.name), "main")
    on_light_path = _extracted_copy(on_light_path, Path(scratch.name), "light") if on_light_path else None

    def build(light: bool) -> Image.Image:
        mark = _trim(
            _pick_logo_rgba_for_placement(
                logo_path=logo_path, logo_on_light_path=on_light_path, light_background=light, max_width=max_w
            ),
            _trim_logo_to_content,
        )
        if not light:
            mark = _lighten_dark_text(mark)
        scale = min(max_w / mark.width, max_h / mark.height, 2.0)  # fit the box; never blow a small file up past 2x
        if abs(scale - 1.0) > 1e-3:
            mark = mark.resize((max(1, round(mark.width * scale)), max(1, round(mark.height * scale))), Image.Resampling.LANCZOS)
        return mark

    # Judge the brightness where the logo will really sit, then take the matching version of the mark.
    probe = build(True)
    def bar_result(bar_key: str, note: str = "") -> dict[str, Any]:
        # Nothing on the picture is covered: a slim strip is added above or below it and the logo goes
        # there (the picture gets a little taller; its content is untouched).
        pad = max(8, round(probe.height * 0.3))
        bar_h = probe.height + 2 * pad
        top = bar_key.startswith("top")
        canvas = Image.new("RGBA", (width, height + bar_h), (255, 255, 255, 255))
        canvas.alpha_composite(base, (0, bar_h if top else 0))
        margin = max(8, round(width * MARGIN_RATIO))
        if bar_key.endswith("center") or bar_key == "center":
            bx = (width - probe.width) // 2
        else:
            bx = margin if bar_key.endswith("left") else width - probe.width - margin
        canvas.alpha_composite(probe, (max(0, bx), (0 if top else height) + pad))
        scratch.cleanup()
        flat = canvas.convert("RGB")
        out = io.BytesIO()
        flat.save(out, format="PNG", optimize=True)
        saved = file_service.save_bytes(
            content=out.getvalue(), tenant_id=tenant_id, subfolder="generated", suffix=".png", content_type="image/png"
        )
        return {
            "url": str(saved["file_url"]),
            "source_url": str(image_url),
            "corner": bar_key if bar_key != "center" else "bottom_center",
            "auto": auto,
            "background": "light",
            "logo_version": "dark logo",
            "warnings": [note] if note else [],
        }

    def frame_result(frame_key: str, note: str = "") -> dict[str, Any]:
        """Make room the way a designer does: the finished artwork is scaled down a little and a blank band is
        left along the logo's edge; the logo goes in that band. The picture keeps its exact size and shape."""
        edge_top = frame_key.startswith("top")
        pad = max(8, round(probe.height * 0.3))
        band_h = probe.height + 2 * pad
        scale = (height - band_h) / height
        sw, sh = max(1, round(width * scale)), max(1, height - band_h)
        rgb = base.convert("RGB")
        strip = rgb.crop((0, 0, width, 6)) if edge_top else rgb.crop((0, height - 6, width, height))
        fill = strip.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
        light_fill = _luma(*fill) >= 140
        mark = probe if light_fill else build(False)
        canvas = Image.new("RGBA", (width, height), (*fill, 255))
        canvas.alpha_composite(base.resize((sw, sh), Image.Resampling.LANCZOS), ((width - sw) // 2, band_h if edge_top else 0))
        margin = max(8, round(width * MARGIN_RATIO))
        if frame_key.endswith("center") or frame_key == "center":
            fx = (width - mark.width) // 2
        else:
            fx = margin if frame_key.endswith("left") else width - mark.width - margin
        canvas.alpha_composite(mark, (max(0, fx), pad if edge_top else height - band_h + pad))
        scratch.cleanup()
        out = io.BytesIO()
        canvas.convert("RGB").save(out, format="PNG", optimize=True)
        saved = file_service.save_bytes(
            content=out.getvalue(), tenant_id=tenant_id, subfolder="generated", suffix=".png", content_type="image/png"
        )
        return {
            "url": str(saved["file_url"]),
            "source_url": str(image_url),
            "corner": frame_key if frame_key != "center" else "bottom_center",
            "auto": auto,
            "background": "light" if light_fill else "dark",
            "logo_version": "dark logo" if light_fill else "light logo",
            "warnings": [note] if note else [],
        }

    if backing == "bar":
        return bar_result("bottom_right" if auto else key)
    moved_from = ""
    if avoid_text and not auto:
        cx, cy = _corner_position(key, width, height, probe.width, probe.height)
        if _region_is_busy(base, cx, cy, probe.width, probe.height):
            moved_from, suggested, auto = key, key, True  # the chosen corner has text: pick the cleanest one
    if auto:
        # Lower score = cleaner. Busy (text or detail) corners lose heavily; the suggested corner and
        # the usual order (top-right first) only break ties between equally clean ones.
        order = list(dict.fromkeys([c for c in [normalize_corner(suggested) if suggested else ""] if c] + list(AUTO_ORDER)))
        scored = []
        for rank, name in enumerate(order):
            cx, cy = _corner_position(name, width, height, probe.width, probe.height)
            busy = _region_is_busy(base, cx, cy, probe.width, probe.height)
            edges = _region_edge_density(base, cx, cy, probe.width, probe.height)
            scored.append(((10.0 if busy else 0.0) + edges * 5 + rank * 0.15, name))
        if min(scored)[0] >= 10.0:
            # Every corner has text or detail: a designer would look for a clear strip along the top or
            # bottom edge before settling for a busy corner. (Never the middle of the picture.)
            for rank, name in enumerate(("top_center", "bottom_center"), start=len(order)):
                cx, cy = _corner_position(name, width, height, probe.width, probe.height)
                busy = _region_is_busy(base, cx, cy, probe.width, probe.height)
                edges = _region_edge_density(base, cx, cy, probe.width, probe.height)
                scored.append(((10.0 if busy else 0.0) + edges * 5 + rank * 0.15, name))
        key = min(scored)[1]
    x, y = _corner_position(key, width, height, probe.width, probe.height)
    light_background = _region_is_light(base, x, y, probe.width, probe.height)
    logo = probe if light_background else build(False)
    x, y = _corner_position(key, width, height, logo.width, logo.height)

    if backing == "":
        # The logo's edge needs a clear band. If the model ran text or artwork into it (it often ignores the
        # instruction to leave room), make the room here instead of putting the logo over the text.
        frame_key = key if key != "center" else "bottom_center"
        pad_px = max(8, round(logo.height * 0.3))
        band_px = logo.height + 2 * pad_px
        band_y = 0 if frame_key.startswith("top") else height - band_px
        near_x = max(0, x - pad_px)
        near_w = min(width - near_x, logo.width + 2 * pad_px)
        if _region_is_busy(base, x, y, logo.width, logo.height) or _region_is_busy(base, near_x, band_y, near_w, band_px):
            edge = "top" if frame_key.startswith("top") else "bottom"
            return frame_result(
                frame_key,
                f"The {edge} of the picture had text or artwork in it, so the picture was made a little smaller to leave "
                f"a clear band for the logo ({CORNER_LABELS[key]}). Choose 'Plain over the image' in Logo style to override.",
            )

    warnings: list[str] = []
    if moved_from and key != moved_from:
        warnings.append(
            f"The {CORNER_LABELS[moved_from]} corner had text in it, so the logo was moved to the {CORNER_LABELS[key]} corner."
        )
    if backing != "plate" and _region_is_busy(base, x, y, logo.width, logo.height):
        warnings.append(
            (
                "Every corner of this picture has detail or text in it, so the logo may sit over some. "
                f"It was put in the least busy one ({CORNER_LABELS[key]}); pick a corner yourself or draw it again."
                if auto
                else f"The {CORNER_LABELS[key]} corner of this picture has detail or text in it, so the logo may sit over it. "
                "Pick another corner or draw the picture again."
            )
        )

    if backing == "plate":
        # A busy spot: a soft white rounded plate under the mark keeps it readable and hides little.
        from PIL import ImageDraw

        pad = max(6, round(logo.height * 0.28))
        plate_logo = build(True)  # dark-on-white version of the mark
        px0, py0 = max(0, x - pad), max(0, y - pad)
        px1, py1 = min(width, x + plate_logo.width + pad), min(height, y + plate_logo.height + pad)
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rounded_rectangle((px0, py0, px1, py1), radius=pad, fill=(255, 255, 255, 238))
        base = Image.alpha_composite(base, overlay)
        logo, light_background = plate_logo, True
    scratch.cleanup()
    base.alpha_composite(logo, (x, y))
    flat = Image.new("RGB", base.size, (255, 255, 255))
    flat.paste(base, mask=base.split()[3])
    out = io.BytesIO()
    flat.save(out, format="PNG", optimize=True)
    saved = file_service.save_bytes(
        content=out.getvalue(), tenant_id=tenant_id, subfolder="generated", suffix=".png", content_type="image/png"
    )
    return {
        "url": str(saved["file_url"]),
        "source_url": str(image_url),
        "corner": key,
        "auto": auto,
        "background": "light" if light_background else "dark",
        "logo_version": "dark logo" if light_background else "light logo",
        "warnings": warnings,
    }
