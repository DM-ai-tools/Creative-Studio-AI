"""Vision analysis of user reference images for image prompt planning."""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

REFERENCE_ANALYSIS_PROMPT = """You analyze a REFERENCE IMAGE for AI ad image generation.
Return ONLY valid JSON (no markdown fences) describing what you see:
{
  "color_palette": ["#hex", ...],
  "product_description": "specific product/object, angle, materials, packaging",
  "visual_themes": {
    "layout": "",
    "typography_style": "",
    "mood": "",
    "backgrounds": "",
    "recurring_elements": [],
    "avoid": []
  },
  "prompt_guidance": "2-4 sentences telling an image model how to match this reference's look, product, and palette",
  "summary": "one short line for UI (max 120 chars)"
}

Rules:
- Extract REAL hex colours when visible (backgrounds, product, text, accents).
- Describe the PRODUCT precisely (shape, colour, branding on product) if any product is shown.
- If lifestyle/scene only, describe setting, lighting, and mood.
- Do NOT invent brand names or text not visible in the image.
- Australian English in summary/guidance when writing prose."""


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def _get_openrouter_client():
    import openai

    headers = {"X-Title": settings.APP_NAME}
    referer = settings.openrouter_http_referer
    if referer:
        headers["HTTP-Referer"] = referer
    return openai.OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        default_headers=headers,
    )


def _vision_model_candidates() -> list[str]:
    primary = (settings.OPENROUTER_MODEL_VISION or "").strip()
    models: list[str] = []
    if primary:
        models.append(primary)
    for m in (
        "google/gemini-2.5-flash",
        "google/gemini-2.5-pro",
        "google/gemini-3-flash-preview",
    ):
        if m not in models:
            models.append(m)
    return models


def _normalize_analysis(data: dict[str, Any]) -> dict[str, Any]:
    palette = data.get("color_palette")
    if not isinstance(palette, list):
        palette = []
    palette = [str(c).strip() for c in palette if str(c).strip()]

    themes = data.get("visual_themes")
    if not isinstance(themes, dict):
        themes = {}

    summary = str(data.get("summary") or "").strip()
    if not summary:
        product = str(data.get("product_description") or "").strip()
        summary = product[:120] if product else "Reference image style"

    return {
        "color_palette": palette,
        "product_description": str(data.get("product_description") or "").strip(),
        "visual_themes": themes,
        "prompt_guidance": str(data.get("prompt_guidance") or "").strip(),
        "summary": summary,
    }


def _heuristic_analysis(brand_name: str = "", niche: str = "") -> dict[str, Any]:
    label = niche or brand_name or "reference"
    return {
        "color_palette": [],
        "product_description": f"Product or scene from uploaded reference ({label})",
        "visual_themes": {},
        "prompt_guidance": (
            f"Match the uploaded reference image's overall look, product presentation, "
            f"and colour mood for {label}."
        ),
        "summary": "Uploaded reference image (vision unavailable)",
    }


async def analyze_reference_image(
    image_bytes: bytes,
    *,
    mime_type: str = "image/png",
    brand_name: str = "",
    niche: str = "",
) -> dict[str, Any]:
    if not image_bytes:
        raise ValueError("Image is empty")
    if not settings.OPENROUTER_API_KEY:
        return _heuristic_analysis(brand_name=brand_name, niche=niche)

    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64}"
    context = ""
    if brand_name or niche:
        context = f"Brand: {brand_name or '—'}\nNiche/campaign: {niche or '—'}\n\n"

    client = _get_openrouter_client()
    last_err: Exception | None = None
    for model in _vision_model_candidates():
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": REFERENCE_ANALYSIS_PROMPT + "\n\n" + context,
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url, "detail": "high"},
                            },
                        ],
                    }
                ],
                max_tokens=1200,
                temperature=0.2,
            )
            raw = (response.choices[0].message.content or "").strip()
            data = _parse_json_object(raw)
            if not isinstance(data, dict):
                raise ValueError("Vision model returned non-object JSON")
            return _normalize_analysis(data)
        except Exception as exc:
            last_err = exc
            logger.warning("Reference image vision failed on %s: %s", model, exc)

    logger.exception("All vision models failed for reference image: %s", last_err)
    return _heuristic_analysis(brand_name=brand_name, niche=niche)


def _analysis_from_ref(ref: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    analysis = ref.get("analysis")
    if isinstance(analysis, dict) and analysis:
        return analysis
    meta = ref.get("metadata")
    if isinstance(meta, dict) and meta.get("analysis"):
        return meta.get("analysis")
    return None


def format_reference_guidance_for_llm(
    reference_images: list[dict[str, Any]] | None,
) -> str:
    """Build LLM block from one or more reference image analyses."""
    if not reference_images:
        return ""

    lines = [
        "CLIENT REFERENCE IMAGE(S) (match product, palette, and visual style from these uploads):",
    ]
    palettes: list[str] = []
    for i, ref in enumerate(reference_images[:5], start=1):
        if not isinstance(ref, dict):
            continue
        analysis = _analysis_from_ref(ref)
        if not analysis:
            url = str(ref.get("file_url") or "").strip()
            if url:
                lines.append(f"Reference {i}: image at {url} — match its visual style.")
            continue
        summary = str(analysis.get("summary") or "").strip()
        product = str(analysis.get("product_description") or "").strip()
        guidance = str(analysis.get("prompt_guidance") or "").strip()
        palette = analysis.get("color_palette") or []
        if isinstance(palette, list):
            for c in palette:
                cs = str(c).strip()
                if cs and cs not in palettes:
                    palettes.append(cs)

        parts = [f"Reference {i}:"]
        if summary:
            parts.append(summary)
        if product:
            parts.append(f"Product/scene: {product}")
        if guidance:
            parts.append(guidance)
        lines.append(" — ".join(parts))

    if palettes:
        lines.append(
            "REFERENCE COLOUR PALETTE (prefer these over generic defaults when visible in refs): "
            + ", ".join(palettes[:8])
        )
    lines.append(
        "Keep the SAME product type, materials, and colour story as the reference — do not swap category."
    )
    return "\n".join(lines)


def reference_primary_secondary(
    reference_images: list[dict[str, Any]] | None,
) -> tuple[str, str]:
    """First two hex colours from reference palettes for brand colour hints."""
    if not reference_images:
        return "", ""
    primary = ""
    secondary = ""
    for ref in reference_images:
        analysis = _analysis_from_ref(ref if isinstance(ref, dict) else {})
        if not analysis:
            continue
        palette = analysis.get("color_palette") or []
        if not isinstance(palette, list):
            continue
        for c in palette:
            cs = str(c).strip()
            if not cs:
                continue
            if not primary:
                primary = cs
            elif cs != primary and not secondary:
                secondary = cs
                break
        if primary and secondary:
            break
    return primary, secondary


def append_reference_guidance_to_prompt(
    image_prompt: str,
    reference_images: list[dict[str, Any]] | None,
) -> str:
    block = format_reference_guidance_for_llm(reference_images)
    if not block:
        return image_prompt
    base = (image_prompt or "").strip()
    if not base:
        return block
    return f"{base}\n\n{block}"
