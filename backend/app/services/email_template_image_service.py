"""Generate a picture that fits one image spot of a customer's email template.

Image models only produce a few fixed shapes (square, 3:2 landscape, 2:3 portrait), so we
ask for the closest one with a composition hint and then crop and resize in code to the
exact pixel shape of the spot, at 2x for sharp phone screens, saved as a light JPEG.
"""

from __future__ import annotations

import io
import logging
from typing import Any

import httpx
from PIL import Image, ImageOps

from app.services.file_service import file_service
from app.services.logo_overlay import file_url_to_local_path

logger = logging.getLogger(__name__)

MIN_SIDE = 16
MAX_SIDE = 4000
RETINA_SCALE = 2
MAX_OUTPUT_WIDTH = 1600
JPEG_QUALITY = 84

_ROLE_PURPOSE = {
    "hero": "the large hero picture at the top of the email",
    "banner": "a wide banner background behind the email's text",
    "product": "a product or feature picture in the body of the email",
    "content": "a supporting picture in the body of the email",
    "other": "a picture in the email",
}


def aspect_format_type(width: int, height: int) -> str:
    """Pick the image model shape closest to the target. Maps to square / 3:2 / 2:3."""
    ratio = width / height
    if ratio >= 1.25:
        return "video"  # landscape 3:2
    if ratio <= 0.8:
        return "reel"  # portrait 2:3
    return "static"  # square


def _composition_hint(width: int, height: int) -> str:
    ratio = width / height
    if ratio >= 3.0:
        return (
            "Ultra-wide panoramic composition: the subject sits in the centre band, the top and "
            "bottom edges are simple and uncluttered because they will be cropped away."
        )
    if ratio >= 1.25:
        return (
            "Landscape composition with the subject slightly to one side and clean negative space "
            "for the email's own text. Keep important detail away from the edges."
        )
    if ratio <= 0.8:
        return "Portrait composition with the subject centred and room above and below."
    return "Square composition with the subject centred. Keep important detail away from the edges."


def build_slot_prompt(
    *,
    role: str,
    width: int,
    height: int,
    description: str,
    alt: str,
    context_text: str,
    brand_name: str,
    campaign_name: str,
    palette: tuple[str, str] | None,
    notes: str,
) -> str:
    purpose = _ROLE_PURPOSE.get(role, _ROLE_PURPOSE["other"])
    parts = [
        f"Create a premium commercial photograph for a marketing email from {brand_name or 'a brand'}.",
        f"It will be used as {purpose}.",
    ]
    if campaign_name:
        parts.append(f"Campaign: {campaign_name}.")
    subject = (description or "").strip() or (alt or "").strip() or (context_text or "").strip()
    if subject:
        parts.append(f"The picture should show: {subject}.")
    if notes.strip():
        parts.append(f"Art direction: {notes.strip()}.")
    if palette:
        parts.append(f"Brand colours to echo where natural: {palette[0]} and {palette[1]}.")
    parts.append(_composition_hint(width, height))
    parts.append("Realistic lighting, high-end art direction.")
    parts.append("IMAGE ONLY: no text, no letters, no numbers, no logos, no buttons, no watermarks, no fake interface.")
    return " ".join(parts)


def crop_to_target(
    image_bytes: bytes,
    target_width: int,
    target_height: int,
    *,
    scale: int = RETINA_SCALE,
    max_width: int = MAX_OUTPUT_WIDTH,
) -> tuple[bytes, tuple[int, int]]:
    """Centre-crop to the target shape, resize to ``scale`` x the display size, return a JPEG."""
    if not (MIN_SIDE <= target_width <= MAX_SIDE and MIN_SIDE <= target_height <= MAX_SIDE):
        raise ValueError(f"Target size must be between {MIN_SIDE} and {MAX_SIDE}px per side")
    with Image.open(io.BytesIO(image_bytes)) as src:
        image = ImageOps.exif_transpose(src)
        if image.mode in ("RGBA", "LA", "P"):
            rgba = image.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.split()[3])
            image = flat
        else:
            image = image.convert("RGB")

    target_ratio = target_width / target_height
    src_w, src_h = image.size
    if src_w / src_h > target_ratio:
        crop_w, crop_h = round(src_h * target_ratio), src_h
    else:
        crop_w, crop_h = src_w, round(src_w / target_ratio)
    left = (src_w - crop_w) // 2
    top = (src_h - crop_h) // 2
    image = image.crop((left, top, left + crop_w, top + crop_h))

    # 2x for sharp screens, but never enlarge beyond the pixels we actually have.
    out_w = max(1, min(target_width * scale, crop_w, max_width))
    out_h = max(1, round(out_w / target_ratio))
    if (out_w, out_h) != image.size:
        image = image.resize((out_w, out_h), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return buffer.getvalue(), (out_w, out_h)


async def _read_generated_image(url: str) -> bytes:
    path = file_url_to_local_path(url)
    if path is not None:
        return path.read_bytes()
    if url.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    raise RuntimeError("Generated image could not be read")


async def generate_slot_image(
    *,
    tenant_id: str,
    model: str,
    role: str,
    width: int,
    height: int,
    description: str,
    alt: str,
    context_text: str,
    brand_name: str,
    campaign_name: str,
    palette: tuple[str, str] | None,
    notes: str,
) -> dict[str, Any]:
    """Generate, crop and store one image. Returns {url, width, height, file_size} or raises."""
    from app.services.ai_service import AIService

    prompt = build_slot_prompt(
        role=role, width=width, height=height, description=description, alt=alt,
        context_text=context_text, brand_name=brand_name, campaign_name=campaign_name,
        palette=palette, notes=notes,
    )
    result = await AIService().generate_image_asset(
        prompt=prompt,
        tenant_id=tenant_id,
        model=model,
        format_type=aspect_format_type(width, height),
    )
    generated_url = str((result or {}).get("url") or (result or {}).get("image_url") or "").strip()
    if not generated_url:
        raise RuntimeError(str((result or {}).get("error") or "Image generation returned no image"))

    raw = await _read_generated_image(generated_url)
    jpeg, (out_w, out_h) = crop_to_target(raw, width, height)
    saved = file_service.save_bytes(
        content=jpeg,
        tenant_id=tenant_id,
        subfolder="email-images",
        suffix=".jpg",
        content_type="image/jpeg",
    )
    return {
        "url": saved["file_url"],
        "width": out_w,
        "height": out_h,
        "display_width": width,
        "display_height": height,
        "file_size": saved["file_size"],
        "prompt": prompt,
    }
