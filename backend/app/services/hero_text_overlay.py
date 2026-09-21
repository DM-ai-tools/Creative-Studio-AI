"""Deterministic text overlay for Hero AI Image outputs."""

from __future__ import annotations

import io
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.services.logo_overlay import file_url_to_local_path


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def apply_hero_copy(file_url: str, hook: str, headline: str) -> bytes:
    path = file_url_to_local_path(file_url)
    if not path:
        raise ValueError("Generated Hero image is not locally available")
    image = Image.open(path).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    pad = max(24, image.width // 18)
    headline_font = _font(max(28, image.width // 18), bold=True)
    hook_font = _font(max(20, image.width // 30), bold=False)
    y = image.height - pad
    for text, font, fill in (
        (headline.strip(), headline_font, (255, 255, 255, 255)),
        (hook.strip(), hook_font, (255, 255, 255, 255)),
    ):
        if not text:
            continue
        font_size = getattr(font, "size", max(20, image.width // 30))
        chars_per_line = max(12, int((image.width - pad * 2) / max(font_size * 0.56, 1)))
        wrapped = "\n".join(textwrap.wrap(text, width=chars_per_line, break_long_words=False))
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=6)
        height = bbox[3] - bbox[1]
        y -= height
        draw.rounded_rectangle(
            (pad - 12, y - 12, image.width - pad + 12, y + height + 12),
            radius=12,
            fill=(0, 0, 0, 155),
        )
        draw.multiline_text(
            (pad, y),
            wrapped,
            font=font,
            fill=fill,
            spacing=6,
            stroke_width=1,
            stroke_fill=(0, 0, 0, 180),
        )
        y -= 20
    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()
