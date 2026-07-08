"""LLM agent that analyses campaign inputs and recommends image + video + copy models."""

from __future__ import annotations

import json
import logging
import re

from app.core.config import settings
from app.schemas.generation import GenerationModelOption

logger = logging.getLogger(__name__)


def _strip_json_fence(raw: str) -> str:
    """Extract a JSON object from an LLM response that may have preamble or code fences."""
    text = (raw or "").strip()
    if "```" in text:
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = re.sub(r"```", "", text)
        text = text.strip()
    if text and text[0] in ("{", "["):
        return text
    for char in ("{", "["):
        idx = text.find(char)
        if idx != -1:
            candidate = text[idx:]
            last = max(candidate.rfind("}"), candidate.rfind("]"))
            if last != -1:
                return candidate[: last + 1]
            return candidate
    return text


SYSTEM_PROMPT = """
You are a creative ad-tech model selector. Given a campaign brief, you choose the best
image model, video model, and copy model from the exact lists provided.

Rules:
- Pick ONLY ids that appear in the lists. Never invent ids.
- For "image_reason", "video_reason", "copy_reason" keep it to 1 short sentence (≤ 12 words).
- If the brief has no video format, set video_model to "" and video_reason to "No video format selected.".
- Prefer HeyGen for avatar/presenter briefs. Prefer Veo 3.1 for cinematic/lifestyle briefs.
- Prefer Nano Banana 2 for speed/cost. Prefer Gen-4 Pro for premium stills.
- Prefer Claude for nuanced/story copy. Prefer GPT for direct-response/ecommerce.

Return ONLY valid JSON with these exact keys:
{
  "image_model": "<id>",
  "image_reason": "<sentence>",
  "video_model": "<id or empty string>",
  "video_reason": "<sentence>",
  "copy_model": "<id>",
  "copy_reason": "<sentence>"
}
""".strip()


async def suggest_models(
    *,
    campaign_name: str,
    objective: str,
    formats: list[str],
    target_audience: str,
    offer: str,
    product_name: str,
    ad_copy_tone: str,
    cta: str,
    duration_seconds: int,
    brand_name: str,
    image_models: list[GenerationModelOption],
    video_models: list[GenerationModelOption],
    copy_models: list[GenerationModelOption],
) -> dict:
    """Return image_model, video_model, copy_model ids + one-line reasons."""

    wants_video = any(f in formats for f in ("reel", "video"))

    image_list = ", ".join(f'{m.id} ({m.label})' for m in image_models) or "nano-banana-2"
    video_list = ", ".join(f'{m.id} ({m.label})' for m in video_models) or "veo-3.1"
    copy_list = ", ".join(f'{m.id} ({m.label})' for m in copy_models) or "claude, openai"

    user_content = "\n".join([
        f"Campaign name: {campaign_name or 'Not specified'}",
        f"Objective: {objective or 'Not specified'}",
        f"Creative formats: {', '.join(formats) if formats else 'Not specified'}",
        f"Target audience: {target_audience or 'Not specified'}",
        f"Offer / key message: {offer or 'Not specified'}",
        f"Product / service: {product_name or 'Not specified'}",
        f"Ad copy tone: {ad_copy_tone or 'Not specified'}",
        f"CTA: {cta or 'Not specified'}",
        f"Video duration (seconds): {duration_seconds}",
        f"Brand: {brand_name or 'Not specified'}",
        f"Wants video: {wants_video}",
        "",
        f"Available image model ids: {image_list}",
        f"Available video model ids: {video_list}",
        f"Available copy model ids: {copy_list}",
    ])

    # Fast fallback (no API key)
    if not settings.OPENROUTER_API_KEY:
        default_video = video_models[0].id if video_models else "veo-3.1"
        default_image = next(
            (m.id for m in image_models if "nano-banana-2" in m.id),
            image_models[0].id if image_models else "nano-banana-2",
        )
        default_copy = copy_models[0].id if copy_models else "claude"
        return {
            "image_model": default_image,
            "image_reason": "Default high-quality image model.",
            "video_model": default_video if wants_video else "",
            "video_reason": "Default video provider." if wants_video else "No video format selected.",
            "copy_model": default_copy,
            "copy_reason": "Default copy model.",
        }

    from app.services.ai_service import ai_service

    try:
        client = ai_service._get_client()
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL_CLAUDE_SCRIPT,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=350,
        )
        raw = _strip_json_fence(response.choices[0].message.content or "")
        data = json.loads(raw)

        # Validate ids — fall back to first available if LLM hallucinated
        img_ids = {m.id for m in image_models}
        vid_ids = {m.id for m in video_models}
        copy_ids = {m.id for m in copy_models}

        if data.get("image_model") not in img_ids:
            data["image_model"] = image_models[0].id if image_models else "nano-banana-2"
        if wants_video and data.get("video_model") not in vid_ids:
            data["video_model"] = video_models[0].id if video_models else "veo-3.1"
        if not wants_video:
            data["video_model"] = ""
        if data.get("copy_model") not in copy_ids:
            data["copy_model"] = copy_models[0].id if copy_models else "claude"

        return data

    except Exception:
        logger.exception("Model suggestion failed — returning defaults")
        default_video = video_models[0].id if (video_models and wants_video) else ""
        default_image = image_models[0].id if image_models else "nano-banana-2"
        default_copy = copy_models[0].id if copy_models else "claude"
        return {
            "image_model": default_image,
            "image_reason": "Default — analysis unavailable.",
            "video_model": default_video,
            "video_reason": "Default — analysis unavailable." if wants_video else "No video format selected.",
            "copy_model": default_copy,
            "copy_reason": "Default — analysis unavailable.",
        }
