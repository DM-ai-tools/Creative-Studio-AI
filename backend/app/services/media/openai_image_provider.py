"""Generate images via the official OpenAI Images API (not Runway / Higgsfield)."""

from __future__ import annotations

import base64
import logging

import httpx

from app.core.config import settings
from app.services.file_service import file_service
from app.services.logo_overlay import apply_logo_overlay_to_file
from app.services.media.base import ImageGenerationProvider
from app.services.brand_prompt import clamp_runway_image_prompt
from app.services.media.openai_image_catalog import (
    openai_configured,
    resolve_openai_image_model,
)
from app.services.media_content import image_suffix_and_type

logger = logging.getLogger(__name__)


def _size_for(api_model: str, format_type: str) -> str:
    ft = (format_type or "").lower()
    portrait = ft in {"reel", "stories"}
    landscape = ft in {"video", "carousel"}
    if api_model.startswith("dall-e-2"):
        return "1024x1024"
    if api_model.startswith("dall-e-3"):
        if portrait:
            return "1024x1792"
        if landscape:
            return "1792x1024"
        return "1024x1024"
    # gpt-image-* 
    if portrait:
        return "1024x1536"
    if landscape:
        return "1536x1024"
    return "1024x1024"


class OpenAIImageProvider(ImageGenerationProvider):
    provider_id = "openai"

    async def generate(
        self,
        *,
        prompt: str,
        tenant_id: str,
        model: str,
        format_type: str,
        logo_url: str | None = None,
        logo_on_light_url: str | None = None,
    ) -> dict:
        api_model = resolve_openai_image_model(model)
        if not openai_configured():
            return {
                "status": "failed",
                "model": api_model,
                "prompt": prompt,
                "url": None,
                "provider": "openai",
                "error": "OPENAI_API_KEY is not configured",
            }

        size = _size_for(api_model, format_type)
        prompt_limit = 32_000 if api_model.startswith("gpt-image") else 4_000
        clamp_model = "gpt_image_2" if api_model.startswith("gpt-image") else None
        safe_prompt = clamp_runway_image_prompt(
            prompt or "",
            max_len=prompt_limit,
            model=clamp_model,
        )
        payload: dict = {
            "model": api_model,
            "prompt": safe_prompt,
            "size": size,
        }
        if api_model.startswith("dall-e"):
            payload["n"] = 1
        if api_model.startswith("gpt-image"):
            payload["quality"] = "high"
        elif api_model.startswith("dall-e-3"):
            payload["quality"] = "hd"
            payload["response_format"] = "b64_json"

        base = (settings.OPENAI_BASE_URL or "https://api.openai.com/v1").rstrip("/")
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY.strip()}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{base}/images/generations",
                    headers=headers,
                    json=payload,
                )
                if response.status_code >= 400 and payload.get("quality") == "high":
                    retry_payload = {**payload, "quality": "auto"}
                    retry = await client.post(
                        f"{base}/images/generations",
                        headers=headers,
                        json=retry_payload,
                    )
                    if retry.status_code < 400:
                        response = retry
                if response.status_code >= 400 and size != "1024x1024":
                    retry_payload = {**payload, "size": "1024x1024"}
                    retry = await client.post(
                        f"{base}/images/generations",
                        headers=headers,
                        json=retry_payload,
                    )
                    if retry.status_code < 400:
                        response = retry
                if response.status_code >= 400:
                    err_txt = response.text[:800]
                    logger.warning("OpenAI image failed (%s): %s", response.status_code, err_txt)
                    return {
                        "status": "failed",
                        "model": api_model,
                        "prompt": prompt,
                        "url": None,
                        "provider": "openai",
                        "error": f"OpenAI Images API {response.status_code}: {err_txt}",
                    }
                body = response.json()
                data = (body.get("data") or [None])[0] or {}
                content: bytes | None = None
                b64 = data.get("b64_json")
                if b64:
                    content = base64.b64decode(b64)
                elif data.get("url"):
                    dl = await client.get(str(data["url"]), timeout=120.0, follow_redirects=True)
                    dl.raise_for_status()
                    content = dl.content
                if not content:
                    raise ValueError("OpenAI image response had no image bytes")

                suffix, content_type = image_suffix_and_type(content)
                saved = file_service.save_bytes(
                    content=content,
                    tenant_id=tenant_id,
                    subfolder="generated",
                    suffix=suffix,
                    content_type=content_type,
                )
                final_url = saved["file_url"]
                logo_applied = False
                if logo_url and final_url:
                    overlaid = apply_logo_overlay_to_file(
                        final_url,
                        logo_url,
                        tenant_id=tenant_id,
                        logo_on_light_url=logo_on_light_url,
                        format_type=format_type,
                    )
                    if overlaid and overlaid != final_url:
                        final_url = overlaid
                        logo_applied = True
                    elif overlaid:
                        final_url = overlaid
                return {
                    "status": "done",
                    "model": api_model,
                    "prompt": prompt,
                    "url": final_url,
                    "provider": "openai",
                    "logo_applied": logo_applied,
                }
        except Exception as exc:
            logger.exception("OpenAI image generation failed")
            return {
                "status": "failed",
                "model": api_model,
                "prompt": prompt,
                "url": None,
                "provider": "openai",
                "error": str(exc)[:800],
            }
