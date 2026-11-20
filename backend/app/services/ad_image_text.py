"""Draw an ad image's text in the brand's real fonts and colours.

"Exact brand fonts" mode: the image model is asked for a picture with no writing and a calm, empty area
for text; this module then draws the on-image lines itself:
  * the hook large, in the Brand Kit's heading font;
  * the headline smaller, in the body font;
  * a CTA pill filled with the brand's primary colour (its label picks black or white for contrast).
The words are exactly the words given (never misspelled), the fonts are the saved fonts (not imitations),
and the text colour is chosen from the picture under it so it is always readable. The image model never
draws text in this mode, so it cannot garble it.

Pure drawing lives in ``render``; ``apply_text_overlay`` loads and saves the files.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.services.ad_image_punch import parse_marked, payoff_indices

logger = logging.getLogger(__name__)

EXACT = "exact"
ZONE_SHARE = 0.42  # the lower (or upper) share of the frame kept for text
MARGIN_SHARE = 0.07
HOOK_LINE = 1.18  # line pitch of the hook, as a multiple of its size (room for the highlight block)
RAMP_SHARE = 0.17  # the backing behind the text eases out over this share of the height
_DARK, _LIGHT = (20, 20, 24), (255, 255, 255)


def requested(kb_models: dict | None, brief_dict: dict | None) -> bool:
    value = (kb_models or {}).get("image_text_mode") or (brief_dict or {}).get("image_text_mode") or ""
    return str(value).strip().lower() == EXACT


# (alignment, backing) pairs. Each creative gets a different one, so a campaign does not repeat one template:
# "fade" = soft panel easing into the picture, "band" = solid brand-colour band, "card" = rounded card on the picture.
LAYOUTS = (
    ("left", "fade"),
    ("center", "band"),
    ("left", "card"),
    ("center", "fade"),
    ("right", "band"),
    ("center", "card"),
    ("right", "fade"),
    ("left", "band"),
)


def layout_for(seed: str, index: int = 0) -> tuple[str, str]:
    """The (alignment, backing) for one creative: stable for the same campaign and position, different between
    creatives, and the same again when a single image is regenerated."""
    import hashlib

    start = int(hashlib.sha1(str(seed or "").encode("utf-8")).hexdigest()[:8], 16)
    return LAYOUTS[(start + int(index or 0)) % len(LAYOUTS)]


def zone_for_logo(logo_mode: str) -> str:
    """Text goes at the bottom unless the logo is in a bottom corner, then it goes at the top."""
    return "top" if str(logo_mode or "").startswith("bottom") else "bottom"


def _rgb(value: str | None) -> tuple[int, int, int] | None:
    text = (value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    if len(text) != 6:
        return None
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError:
        return None


def _luminance(rgb: tuple[int, int, int]) -> float:
    def channel(v: int) -> float:
        s = v / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _balanced(draw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap, and avoid a one-word last line ("...wear every / day") by narrowing the lines a little when
    that keeps the same number of lines."""
    lines = _wrap(draw, text, font, max_width)
    if len(lines) < 2 or len(lines[-1].split()) > 1:
        return lines
    for share in (0.92, 0.84, 0.76, 0.68, 0.6):
        trial = _wrap(draw, text, font, round(max_width * share))
        if len(trial) == len(lines) and len(trial[-1].split()) > 1:
            return trial
    return lines


def _fit(draw, text: str, font_path: Path, max_width: int, max_lines: int, start: int, minimum: int):
    """The largest size at which the text fits the width in at most ``max_lines`` lines."""
    size = start
    while size >= minimum:
        font = ImageFont.truetype(str(font_path), size)
        lines = _balanced(draw, text, font, max_width)
        if len(lines) <= max_lines and all(draw.textlength(line, font=font) <= max_width for line in lines):
            return font, lines
        size -= 2
    font = ImageFont.truetype(str(font_path), minimum)
    return font, _wrap(draw, text, font, max_width)[:max_lines]


def _mean_rgb(img: Image.Image, box: tuple[float, float, float, float]) -> tuple[int, int, int]:
    """The average colour of a region of the picture (as it is at this moment)."""
    left, top = max(0, round(box[0])), max(0, round(box[1]))
    right, bottom = min(img.width, round(box[2])), min(img.height, round(box[3]))
    if right <= left or bottom <= top:
        return (128, 128, 128)
    pixels = list(img.crop((left, top, right, bottom)).convert("RGB").resize((8, 8)).getdata())
    return tuple(round(sum(p[i] for p in pixels) / len(pixels)) for i in range(3))  # type: ignore[return-value]


def _smooth(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def _best_neutral(background: tuple[int, int, int]) -> tuple[int, int, int]:
    return max((_DARK, _LIGHT), key=lambda colour: _contrast(colour, background))


def render(
    base: Image.Image,
    *,
    hook: str = "",
    headline: str = "",
    cta: str = "",
    primary: str = "",
    secondary: str = "",
    heading_font: Path,
    body_font: Path,
    zone: str = "bottom",
    align: str = "left",
    backing: str = "fade",
) -> tuple[Image.Image, dict[str, Any]]:
    img = base.convert("RGBA")
    width, height = img.size
    margin = round(width * MARGIN_SHARE)
    max_w = width - 2 * margin
    zone_h = round(height * ZONE_SHARE)

    def x_for(item_w: float) -> float:
        if align == "left":
            return margin
        if align == "right":
            return width - margin - item_w
        return (width - item_w) / 2

    top_zone = zone == "top"
    y_start = 0 if top_zone else height - zone_h
    measure = ImageDraw.Draw(img)
    # **double asterisks** in the hook mark the words to highlight; otherwise its payoff words are used.
    # The asterisks are never printed.
    highlight_idx = payoff_indices(hook)  # read the marks BEFORE the asterisks are removed
    hook, _marked = parse_marked(hook)
    headline, cta = headline.replace("**", ""), cta.replace("**", "")

    # 1. Layout: the biggest sizes at which the lines fit the zone.
    block: list[tuple[str, Any, Any]] = []  # (kind, lines or label, font)
    for scale in (1.0, 0.88, 0.76, 0.64, 0.52):
        block = []
        used = 0.0
        if hook.strip():
            font, lines = _fit(measure, hook.strip(), heading_font, max_w, 3, round(height * 0.085 * scale), max(16, round(height * 0.035)))
            block.append(("hook", lines, font))
            used += len(lines) * font.size * HOOK_LINE
        if headline.strip():
            sub_size = max(14, round((block[0][2].size if block else height * 0.06) * 0.5))
            font, lines = _fit(measure, headline.strip(), body_font, max_w, 2, sub_size, max(13, round(height * 0.024)))
            block.append(("headline", lines, font))
            used += (font.size * 0.5 if block[:-1] else 0) + len(lines) * font.size * 1.3
        if cta.strip():
            font = ImageFont.truetype(str(body_font), max(14, round(height * 0.032 * scale)))
            block.append(("cta", cta.strip(), font))
            used += font.size * 0.9 + font.size * 2.4
        if used <= zone_h - margin * 1.2:
            break
    gap_hook = (block[0][2].size * 0.35) if block and block[0][0] == "hook" else 0
    total = gap_hook * (1 if len(block) > 1 else 0)
    for kind, content, font in block:
        total += font.size * 3.1 if kind == "cta" else len(content) * font.size * (HOOK_LINE if kind == "hook" else 1.3)
    y0 = (margin * 0.9) if top_zone else (height - margin * 0.9 - total)

    # 2. Where every line and the button sit.
    placed: list[dict[str, Any]] = []
    y = y0
    for kind, content, font in block:
        if kind == "cta":
            y += font.size * 0.9
            pad_x, pad_y = font.size * 1.3, font.size * 0.62
            pill_w, pill_h = measure.textlength(content, font=font) + 2 * pad_x, font.size + 2 * pad_y
            x = x_for(pill_w)
            placed.append({"kind": "cta", "text": content, "font": font, "x": x, "y": y, "w": pill_w, "h": pill_h, "pad": (pad_x, pad_y)})
            y += pill_h
            continue
        word_no = 0
        for line in content:
            line_w = measure.textlength(line, font=font)
            x = x_for(line_w)
            entry = {"kind": kind, "text": line, "font": font, "x": x, "y": y, "w": line_w, "h": font.size * 1.1}
            if kind == "hook":  # each word with whether it is a highlighted one
                words = line.split()
                entry["words"] = [(w, (word_no + i) in highlight_idx) for i, w in enumerate(words)]
                word_no += len(words)
            placed.append(entry)
            y += font.size * (HOOK_LINE if kind == "hook" else 1.3)
        if kind == "hook":
            y += gap_hook

    # 3. A backing for the text: solid behind the text block, easing into the picture, and never reaching
    #    above the zone. Light or dark is chosen from the picture where the text sits.
    text_top, text_bottom = y0, y0 + total
    mean = _mean_rgb(img, (0, text_top - margin * 0.5, width, text_bottom + margin * 0.5))
    bright = (0.299 * mean[0] + 0.587 * mean[1] + 0.114 * mean[2]) > 150
    scrim_rgb = _LIGHT if bright else (0, 0, 0)
    alpha_max = round(255 * (0.72 if bright else 0.64))
    ramp = max(8, round(height * RAMP_SHARE))  # how far the backing eases out into the picture
    primary_rgb, secondary_rgb = _rgb(primary), _rgb(secondary)
    band_fill: tuple[int, int, int] | None = None
    if backing == "band":
        # A solid band in the brand's primary colour (or a deep neutral), edge to edge behind the text.
        band_fill = primary_rgb or _DARK
        pad = margin * 0.7
        band_top = 0 if top_zone else max(0, round(text_top - pad))
        band_bottom = min(height, round(text_bottom + pad)) if top_zone else height
        img.alpha_composite(Image.new("RGBA", (width, max(1, band_bottom - band_top)), band_fill + (250,)), (0, band_top))
    elif backing == "card":
        # A rounded card inset from the edges, sitting on the picture.
        card = Image.new("RGBA", img.size, (0, 0, 0, 0))
        pad = margin * 0.6
        ImageDraw.Draw(card).rounded_rectangle(
            (margin * 0.55, text_top - pad, width - margin * 0.55, text_bottom + pad),
            radius=margin * 0.8,
            fill=(255, 255, 255, 238),
        )
        img = Image.alpha_composite(img, card)
    if backing in {"band", "card"}:
        pass
    elif top_zone:
        solid_end = text_bottom + margin * 0.5
        fade_end = min(height, solid_end + ramp)
        span_top, span_bottom = 0, round(fade_end)

        def alpha_at(row: float) -> float:
            return alpha_max if row <= solid_end else alpha_max * (1 - _smooth((row - solid_end) / max(1.0, fade_end - solid_end)))
    else:
        solid_start = text_top - margin * 0.5
        fade_start = max(0, solid_start - ramp)  # may reach above the zone: a soft edge beats a hard slab
        span_top, span_bottom = round(fade_start), height

        def alpha_at(row: float) -> float:
            return alpha_max if row >= solid_start else alpha_max * _smooth((row - fade_start) / max(1.0, solid_start - fade_start))
    if backing not in {"band", "card"}:
        span_h = max(1, span_bottom - span_top)
        strip = Image.new("L", (1, span_h))
        strip.putdata([round(alpha_at(span_top + i + 0.5)) for i in range(span_h)])
        scrim = Image.new("RGBA", (width, span_h), scrim_rgb + (0,))
        scrim.putalpha(strip.resize((width, span_h)))
        img.alpha_composite(scrim, (0, span_top))

    # 4. Colours chosen from the pixels actually under each part (after the backing), so text is readable
    #    even when the model painted a background in the brand colour itself.
    def backdrop(kind: str) -> tuple[int, int, int] | None:
        parts = [p for p in placed if p["kind"] == kind]
        if not parts:
            return None
        box = (min(p["x"] for p in parts), min(p["y"] for p in parts), max(p["x"] + p["w"] for p in parts), max(p["y"] + p["h"] for p in parts))
        return _mean_rgb(img, box)

    hook_bg = backdrop("hook") or mean
    sub_bg = backdrop("headline") or mean
    accent_rgb = primary_rgb or secondary_rgb
    use_highlight = bool(highlight_idx) and accent_rgb is not None
    if use_highlight:
        # punchy look: the hook in the plain readable colour, its payoff words on a block of the brand accent
        hook_rgb = _best_neutral(hook_bg)
        mark_text = _DARK if _contrast(accent_rgb, _DARK) >= _contrast(accent_rgb, _LIGHT) else _LIGHT
    else:
        hook_rgb = primary_rgb if primary_rgb and _contrast(primary_rgb, hook_bg) >= 3.0 else _best_neutral(hook_bg)
        mark_text = hook_rgb
    sub_rgb = secondary_rgb if secondary_rgb and _contrast(secondary_rgb, sub_bg) >= 4.5 else _best_neutral(sub_bg)
    cta_bg = backdrop("cta") or mean
    pill_fill = primary_rgb or _best_neutral(cta_bg)
    if band_fill is not None:
        # On a band in the brand colour the highlight block and the button must not be that same colour.
        light_band = _luminance(band_fill) > 0.45
        alt = secondary_rgb if secondary_rgb and _contrast(secondary_rgb, band_fill) >= 2.0 else (_DARK if light_band else _LIGHT)
        accent_rgb = alt
        use_highlight = bool(highlight_idx)
        if use_highlight:
            mark_text = _DARK if _contrast(accent_rgb, _DARK) >= _contrast(accent_rgb, _LIGHT) else _LIGHT
        pill_fill = alt
    pill_text = _DARK if _contrast(pill_fill, _DARK) >= _contrast(pill_fill, _LIGHT) else _LIGHT

    # 5. Draw.
    draw = ImageDraw.Draw(img)
    drawn: list[str] = []
    highlighted: list[str] = []
    for item in placed:
        if item["kind"] == "cta":
            font, pad_x, pad_y = item["font"], item["pad"][0], item["pad"][1]
            draw.rounded_rectangle(
                (item["x"], item["y"], item["x"] + item["w"], item["y"] + item["h"]), radius=item["h"] / 2, fill=pill_fill + (255,)
            )
            draw.text((item["x"] + pad_x, item["y"] + pad_y - font.size * 0.08), item["text"], font=font, fill=pill_text + (255,))
        elif item["kind"] == "hook" and use_highlight:
            font = item["font"]
            space = draw.textlength(" ", font=font)
            cursor, spots = item["x"], []
            for word, marked in item["words"]:
                word_w = draw.textlength(word, font=font)
                spots.append((word, marked, cursor, word_w))
                cursor += word_w + space
            # the block hugs the real letters (cap top to the bottom of descenders) of THIS font, whose glyphs
            # can sit well below the top of their box
            glyph_top, glyph_bottom = draw.textbbox((0, 0), "Hgjy", font=font)[1], draw.textbbox((0, 0), "Hgjy", font=font)[3]
            run: list[tuple[str, bool, float, float]] = []
            for spot in [*spots, None]:  # a block behind each run of consecutive highlighted words
                if spot is not None and spot[1]:
                    run.append(spot)
                    continue
                if run:
                    pad_x, pad_y = font.size * 0.14, font.size * 0.06
                    draw.rounded_rectangle(
                        (run[0][2] - pad_x, item["y"] + glyph_top - pad_y, run[-1][2] + run[-1][3] + pad_x, item["y"] + glyph_bottom + pad_y),
                        radius=font.size * 0.12,
                        fill=accent_rgb + (255,),
                    )
                    run = []
            for word, marked, left, _w in spots:
                draw.text((left, item["y"]), word, font=font, fill=(mark_text if marked else hook_rgb) + (255,))
                if marked:
                    highlighted.append(word)
        else:
            colour = hook_rgb if item["kind"] == "hook" else sub_rgb
            draw.text((item["x"], item["y"]), item["text"], font=item["font"], fill=colour + (255,))
        drawn.append(item["text"])
    return img.convert("RGB"), {
        "zone": zone,
        "align": align,
        "backing": backing,
        "bright_zone": bright,
        "lines": drawn,
        "highlight": " ".join(highlighted),
        "highlight_colour": ("#%02X%02X%02X" % accent_rgb) if use_highlight else "",
        "hook_colour": "#%02X%02X%02X" % hook_rgb,
        "hook_contrast": round(_contrast(hook_rgb, hook_bg), 2),
        "pill_colour": "#%02X%02X%02X" % pill_fill,
    }


async def load_fonts(heading: str | None, body: str | None) -> tuple[dict[str, Path] | None, str]:
    """The brand's two fonts as files, and a note when exact mode cannot be used. Done before the picture
    is generated, so a font that cannot be fetched falls back to the image model drawing the text."""
    import asyncio

    from app.services import brand_fonts

    family = brand_fonts.parse_font_spec(heading)[0]
    if not family:
        return None, "No heading font is saved on the Brand page, so the image model drew the text."
    fonts = await asyncio.to_thread(brand_fonts.load_pair, heading, body)
    if not fonts:
        return None, (
            f"The brand font '{family}' could not be fetched (it may not be a Google font), "
            "so the image model drew the text in a similar style."
        )
    return fonts, ""


async def overlay_result(
    image_result: Any,
    *,
    fonts: dict[str, Path],
    hook: str,
    headline: str,
    cta: str,
    primary: str,
    secondary: str,
    tenant_id: str,
    zone: str = "bottom",
    align: str = "left",
    backing: str = "fade",
) -> Any:
    """Draw the text on a finished image result. If that fails the plain picture is kept and the reason
    recorded: the picture is never lost."""
    import asyncio

    if not isinstance(image_result, dict):
        return image_result
    url = str(image_result.get("url") or "")
    if image_result.get("status") not in {"done", "mock"} or not url.startswith("/files/"):
        return image_result
    if not any(x.strip() for x in (hook, headline, cta)):
        return image_result
    try:
        drawn = await asyncio.to_thread(
            apply_text_overlay,
            image_url=url,
            tenant_id=tenant_id,
            hook=hook,
            headline=headline,
            cta=cta,
            primary=primary,
            secondary=secondary,
            fonts=fonts,
            zone=zone,
            align=align,
            backing=backing,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Exact brand text could not be drawn")
        return {**image_result, "text_mode": "failed", "warnings": [*(image_result.get("warnings") or []), f"The text could not be added: {exc}"]}
    return {
        **image_result,
        "url": drawn["url"],
        "url_without_text": drawn["url_without_text"],
        "text_mode": EXACT,
        "text_font_heading": fonts["heading"].name,
        "text_font_body": fonts["body"].name,
        "text_zone": drawn["zone"],
        "text_align": drawn["align"],
        "text_backing": drawn["backing"],
        "text_lines": drawn["lines"],
    }


def apply_text_overlay(
    *,
    image_url: str,
    tenant_id: str,
    hook: str,
    headline: str,
    cta: str,
    primary: str,
    secondary: str,
    fonts: dict[str, Path],
    zone: str = "bottom",
    align: str = "left",
    backing: str = "fade",
) -> dict[str, Any]:
    """Draw the text on a saved image and save the result as a new file. The plain picture is kept."""
    from app.services.file_service import file_service
    from app.services.logo_overlay import file_url_to_local_path

    path = file_url_to_local_path(str(image_url or "").strip())
    if not path:
        raise ValueError("The picture could not be found to add the text.")
    with Image.open(path) as source:
        drawn, info = render(
            source,
            hook=hook,
            headline=headline,
            cta=cta,
            primary=primary,
            secondary=secondary,
            heading_font=fonts["heading"],
            body_font=fonts["body"],
            zone=zone,
            align=align,
            backing=backing,
        )
    out = io.BytesIO()
    drawn.save(out, format="PNG", optimize=True)
    saved = file_service.save_bytes(
        content=out.getvalue(), tenant_id=tenant_id, subfolder="generated", suffix=".png", content_type="image/png"
    )
    return {"url": str(saved["file_url"]), "url_without_text": str(image_url), **info}
