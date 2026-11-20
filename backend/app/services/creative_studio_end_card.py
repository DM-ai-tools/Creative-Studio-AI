"""Creative Studio end card: the brand logo and exact call-to-action text, laid over the last seconds.

Built to avoid the usual overlay mistakes:
- The logo is the uploaded file, scaled with its aspect ratio kept. It is never recoloured, stretched
  or redrawn. The card colour (white or dark navy) is chosen to suit the logo, not the other way round.
- Text is typed by the app (not drawn by an AI model), so wording is exactly what the script says.
  It is measured, wrapped and shrunk to fit inside safe margins, so it can never be cut off. If the
  lines cannot fit at a readable size, the request fails with a clear message instead.
- In portrait video the card stays out of the top and bottom strips that social apps cover.
- A preview (the card on the real frame) can be produced before the video is encoded.
"""

from __future__ import annotations

import functools
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

DEFAULT_BUTTON_HEX = "#1D6FE8"  # blue call-to-action button
DEFAULT_ACCENT_HEX = "#2FA862"  # small green accent
HOLD_MIN_SECONDS, HOLD_MAX_SECONDS, HOLD_DEFAULT_SECONDS = 2.0, 6.0, 4.0
FADE_SECONDS = 0.35
MAX_LINE_CHARS = 120
MAX_SUBLINES = 3

_NAVY = (14, 27, 51)
_NAVY_SOFT = (68, 84, 111)
_WHITE = (255, 255, 255)
_ON_DARK_SOFT = (205, 214, 228)
_SCALES = (1.0, 0.92, 0.85, 0.78, 0.7, 0.62, 0.55, 0.48)  # text shrinks stepwise until it fits

_BOLD_FONTS = (
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)
_REGULAR_FONTS = (
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)


# ── small helpers ───────────────────────────────────────────────────────────


def parse_hex_colour(value: str | None, default: str) -> tuple[int, int, int]:
    raw = (value or "").strip() or default
    if not re.fullmatch(r"#?[0-9a-fA-F]{6}", raw):
        raise ValueError(f"'{raw}' is not a colour like {default}.")
    raw = raw.lstrip("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


@functools.lru_cache(maxsize=2)
def _font_path(bold: bool) -> str:
    for candidate in _BOLD_FONTS if bold else _REGULAR_FONTS:
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError(
        "No usable font was found on the server for the end card. Install a font package "
        "(for example fonts-dejavu-core) and try again."
    )


def _font(bold: bool, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_font_path(bold), max(8, int(round(size))))


def _wrap(font: ImageFont.FreeTypeFont, text: str, max_width: float) -> list[str] | None:
    """Wrap text to a width. None when a single word is wider than the line, so the caller shrinks."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        if font.getlength(word) > max_width:
            return None
        trial = f"{current} {word}".strip()
        if font.getlength(trial) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def is_light_mark(logo: Image.Image) -> bool:
    """True when the logo's visible pixels are nearly white, so it needs a dark card to be seen."""
    small = logo.convert("RGBA").resize((64, 64), Image.Resampling.BILINEAR)
    total = count = 0.0
    for r, g, b, a in small.getdata():
        if a > 128:
            total += 0.299 * r + 0.587 * g + 0.114 * b
            count += 1
    return bool(count) and total / count > 225


def clean_lines(headline: str, sublines: list[str], button_text: str) -> tuple[str, list[str], str]:
    head = " ".join((headline or "").split())
    button = " ".join((button_text or "").split())
    subs = [" ".join(s.split()) for s in (sublines or []) if " ".join(str(s).split())]
    if not head:
        raise ValueError("The end card needs a headline.")
    if len(head) > MAX_LINE_CHARS or len(button) > MAX_LINE_CHARS or any(len(s) > MAX_LINE_CHARS for s in subs):
        raise ValueError(f"Each end card line must be {MAX_LINE_CHARS} characters or fewer.")
    if len(subs) > MAX_SUBLINES:
        raise ValueError(f"Use at most {MAX_SUBLINES} lines between the headline and the button.")
    return head, subs, button


# ── drawing the card ────────────────────────────────────────────────────────


def render_end_card(
    size: tuple[int, int],
    *,
    logo: Image.Image | None,
    headline: str,
    sublines: list[str] | None = None,
    button_text: str = "",
    button_rgb: tuple[int, int, int] = (29, 111, 232),
    accent_rgb: tuple[int, int, int] = (47, 168, 98),
) -> tuple[Image.Image, dict[str, Any]]:
    """Draw the end card on a transparent frame of the video's size.

    Returns the RGBA image and a layout summary (card box, safe zone, final scale) for checks.
    """
    width, height = size
    head, subs, button = clean_lines(headline, sublines or [], button_text)
    if logo is not None:
        # Cut away fully transparent margins so the mark lines up with the text. Visible pixels
        # are untouched; only empty padding goes.
        visible = logo.getchannel("A").getbbox()
        logo = logo.crop(visible) if visible else None
    portrait = height > width * 1.2
    if portrait:
        # keep clear of the top and bottom strips that Reels/Shorts/TikTok interface elements cover
        card_w, card_x = round(width * 0.84), round(width * 0.08)
        zone_top, zone_bottom = round(height * 0.12), round(height * 0.80)
    else:
        card_w, card_x = round(width * 0.46), round(width * 0.05)
        zone_top, zone_bottom = round(height * 0.08), round(height * 0.92)
    zone_h = zone_bottom - zone_top
    pad = round(card_w * 0.07)
    inner_w = card_w - 2 * pad

    dark = logo is not None and is_light_mark(logo)
    card_fill = (*_NAVY, 245) if dark else (*_WHITE, 245)
    head_rgb = _WHITE if dark else _NAVY
    sub_rgb = _ON_DARK_SOFT if dark else _NAVY_SOFT

    def layout(scale: float):
        head_font = _font(True, card_w * 0.080 * scale)
        sub_font = _font(False, card_w * 0.050 * scale)
        btn_font = _font(True, card_w * 0.056 * scale)
        gap = round(card_w * 0.045 * scale)
        ops: list[tuple] = []
        y = 0
        if logo is not None:
            max_w = inner_w * 0.60
            max_h = height * (0.085 if portrait else 0.12) * scale
            factor = min(max_w / logo.width, max_h / logo.height, 3.0)
            mark = logo.resize((max(1, round(logo.width * factor)), max(1, round(logo.height * factor))), Image.Resampling.LANCZOS)
            ops.append(("logo", y, mark))
            y += mark.height + gap
        head_lines = _wrap(head_font, head, inner_w)
        if head_lines is None:
            return None
        head_lh = round(head_font.size * 1.2)
        ops.append(("text", y, head_lines, head_font, head_rgb, head_lh))
        y += head_lh * len(head_lines)
        bar_h = max(4, round(card_w * 0.012))
        y += round(gap * 0.5)
        ops.append(("bar", y, round(inner_w * 0.2), bar_h))
        y += bar_h + round(gap * 0.6)
        for sub in subs:
            lines = _wrap(sub_font, sub, inner_w)
            if lines is None:
                return None
            sub_lh = round(sub_font.size * 1.3)
            ops.append(("text", y, lines, sub_font, sub_rgb, sub_lh))
            y += sub_lh * len(lines) + round(gap * 0.25)
        if button:
            btn_w = btn_font.getlength(button) + btn_font.size * 2.4
            if btn_w > inner_w:
                return None
            btn_h = round(btn_font.size * 2.1)
            y += round(gap * 0.6)
            ops.append(("button", y, round(btn_w), btn_h, button, btn_font))
            y += btn_h
        return ops, y

    chosen = None
    for scale in _SCALES:
        attempt = layout(scale)
        if attempt and attempt[1] + 2 * pad <= zone_h:
            chosen = (scale, *attempt)
            break
    if chosen is None:
        raise ValueError("These end card lines are too long to fit at a readable size. Shorten them.")
    scale, ops, content_h = chosen

    card_h = content_h + 2 * pad
    card_y = zone_top + (zone_h - card_h) // 2
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    # Pillow's rectangle end coordinates are inclusive, so subtract 1 to match the reported box.
    draw.rounded_rectangle((card_x, card_y, card_x + card_w - 1, card_y + card_h - 1), radius=round(card_w * 0.05), fill=card_fill)
    left, top = card_x + pad, card_y + pad
    for op in ops:
        kind, y = op[0], top + op[1]
        if kind == "logo":
            canvas.alpha_composite(op[2], (left, y))
        elif kind == "text":
            _, _, lines, font, rgb, line_h = op
            for i, line in enumerate(lines):
                draw.text((left, y + i * line_h), line, font=font, fill=(*rgb, 255))
        elif kind == "bar":
            draw.rounded_rectangle((left, y, left + op[2] - 1, y + op[3] - 1), radius=op[3] // 2, fill=(*accent_rgb, 255))
        elif kind == "button":
            _, _, btn_w, btn_h, label, font = op
            draw.rounded_rectangle((left, y, left + btn_w - 1, y + btn_h - 1), radius=btn_h // 2, fill=(*button_rgb, 255))
            draw.text((left + btn_w / 2, y + btn_h / 2), label, font=font, fill=(*_WHITE, 255), anchor="mm")
    layout_info = {
        "card_box": (card_x, card_y, card_x + card_w, card_y + card_h),
        "safe_zone": (zone_top, zone_bottom),
        "scale": scale,
        "theme": "dark" if dark else "light",
        "portrait": portrait,
    }
    return canvas, layout_info


# ── putting it on a video ───────────────────────────────────────────────────


def _load_logo(tenant_id: str, logo_url: str | None, logo_on_light_url: str | None, brand: dict | None) -> Image.Image | None:
    """The brand logo file exactly as uploaded (RGBA). None when no usable file exists."""
    from app.services.brand_logo import logo_local_path, resolve_video_logo_urls

    primary, on_light = resolve_video_logo_urls(
        brand=brand, logo_url=logo_url, logo_on_light_url=logo_on_light_url, tenant_id=tenant_id
    )
    # The on-light (dark) mark suits a white card, so try it first.
    for url in (on_light, primary):
        path = logo_local_path(url) if url else None
        if path and path.is_file():
            try:
                return Image.open(path).convert("RGBA")
            except Exception:  # noqa: BLE001 - a bad file must not stop the text-only card
                logger.exception("End card: logo file could not be read: %s", path)
    return None


def add_end_card_to_video(
    *,
    video_url: str,
    tenant_id: str,
    headline: str,
    sublines: list[str] | None = None,
    button_text: str = "",
    logo_url: str | None = None,
    logo_on_light_url: str | None = None,
    brand: dict | None = None,
    button_hex: str | None = None,
    accent_hex: str | None = None,
    hold_seconds: float = HOLD_DEFAULT_SECONDS,
    preview: bool = False,
) -> dict[str, Any]:
    """Lay the end card over the last ``hold_seconds`` of a video (or, with ``preview``, one still)."""
    from app.services.creative_studio_caption_logo import _output_size
    from app.services.creative_studio_picture import media_dimensions
    from app.services.ffmpeg_util import probe_video_duration, require_ffmpeg
    from app.services.file_service import file_service
    from app.services.video_subtitles import _ensure_local_video

    button_rgb = parse_hex_colour(button_hex, DEFAULT_BUTTON_HEX)
    accent_rgb = parse_hex_colour(accent_hex, DEFAULT_ACCENT_HEX)
    hold = min(max(float(hold_seconds or HOLD_DEFAULT_SECONDS), HOLD_MIN_SECONDS), HOLD_MAX_SECONDS)

    video_path = _ensure_local_video(str(video_url or "").strip(), tenant_id=tenant_id)
    if not video_path or not video_path.is_file():
        raise ValueError("The video file could not be found. Generate or re-open the video and retry.")
    ffmpeg = require_ffmpeg()
    duration = float(probe_video_duration(video_path) or 0.0)
    if duration <= 0:
        raise ValueError("The video length could not be read.")
    hold = min(hold, duration)
    start = max(0.0, duration - hold)
    src_w, src_h = media_dimensions(video_path)
    out_w, out_h = _output_size(src_w, src_h)

    warnings: list[str] = []
    logo = _load_logo(tenant_id, logo_url, logo_on_light_url, brand)
    if logo is None:
        warnings.append("No brand logo was found, so the end card has text only. Upload a logo to the brand or attach one with the Logo role.")
    card, info = render_end_card(
        (out_w, out_h),
        logo=logo,
        headline=headline,
        sublines=sublines,
        button_text=button_text,
        button_rgb=button_rgb,
        accent_rgb=accent_rgb,
    )

    with tempfile.TemporaryDirectory(prefix="cs_endcard_") as tmp:
        work = Path(tmp)
        shutil.copy2(video_path, work / "input.mp4")
        card.save(work / "card.png", format="PNG")

        if preview:
            frame = work / "frame.png"
            proc = subprocess.run(
                [ffmpeg, "-y", "-ss", f"{start:.3f}", "-i", "input.mp4", "-frames:v", "1",
                 "-vf", f"scale={out_w}:{out_h}:flags=lanczos", "frame.png"],
                capture_output=True, text=True, cwd=str(work),
            )
            base = Image.open(frame).convert("RGBA") if proc.returncode == 0 and frame.is_file() else Image.new("RGBA", (out_w, out_h), (96, 96, 96, 255))
            base.alpha_composite(card)
            out = work / "preview.png"
            base.convert("RGB").save(out, format="PNG")
            saved = file_service.save_bytes(content=out.read_bytes(), tenant_id=tenant_id, suffix=".png", subfolder="generated", content_type="image/png")
            kind = "preview"
        else:
            graph = (
                f"[0:v]scale={out_w}:{out_h}:flags=lanczos,setsar=1[base];"
                f"[1:v]format=rgba,fade=t=in:st=0:d={FADE_SECONDS}:alpha=1,setpts=PTS+{start:.3f}/TB[card];"
                "[base][card]overlay=0:0:eof_action=pass:format=auto[out]"
            )
            command = [
                ffmpeg, "-y", "-i", "input.mp4", "-loop", "1", "-framerate", "24", "-t", f"{hold:.3f}", "-i", "card.png",
                "-filter_complex", graph, "-map", "[out]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
                "-c:a", "copy", "-movflags", "+faststart", "output.mp4",
            ]
            proc = subprocess.run(command, capture_output=True, text=True, cwd=str(work))
            out = work / "output.mp4"
            if proc.returncode != 0 or not out.is_file() or out.stat().st_size < 1000:
                logger.error("Creative Studio end card failed: %s", (proc.stderr or "")[-1200:])
                raise RuntimeError("The end card could not be added to this video.")
            saved = file_service.save_bytes(content=out.read_bytes(), tenant_id=tenant_id, suffix=".mp4", subfolder="generated", content_type="video/mp4")
            kind = "video"

    return {
        "kind": kind,
        "url": str(saved["file_url"]),
        "source_url": str(video_url),
        "width": out_w,
        "height": out_h,
        "duration_seconds": round(duration, 2),
        "start_seconds": round(start, 2),
        "hold_seconds": round(hold, 2),
        "logo_applied": logo is not None,
        "theme": info["theme"],
        "warnings": warnings,
    }
