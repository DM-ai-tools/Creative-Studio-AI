"""Generate stills via BytePlus ModelArk Seedream (same account as Seedance)."""

from __future__ import annotations

import logging

import httpx

from app.services.brand_prompt import clamp_runway_image_prompt
from app.services.file_service import file_service
from app.services.media.base import ImageGenerationProvider
from app.services.media.byteplus_seedance_client import seedance_async_client
from app.services.media.byteplus_seedream_client import (
    generate_seedream_image,
    is_byteplus_ark_media_url,
    map_format_to_size,
    resolve_seedream_api_model,
    seedream_configured,
)
from app.services.media.openai_image_provider import _load_reference_image_bytes
from app.services.media_content import image_suffix_and_type

logger = logging.getLogger(__name__)


class BytePlusSeedreamProvider(ImageGenerationProvider):
    provider_id = "byteplus"

    async def generate(
        self,
        *,
        prompt: str,
        tenant_id: str,
        model: str,
        format_type: str,
        logo_url: str | None = None,
        logo_on_light_url: str | None = None,
        reference_image_url: str | None = None,
        reference_image_urls: list[str] | None = None,
        reference_purpose: str = "product",
    ) -> dict:
        api_model = resolve_seedream_api_model(model)
        if not seedream_configured():
            return {
                "status": "failed",
                "model": api_model,
                "prompt": prompt,
                "url": None,
                "provider": "byteplus",
                "error": "BytePlus ModelArk API key is not configured (ARK_API_KEY)",
            }

        safe_prompt = clamp_runway_image_prompt(prompt or "", max_len=4000, model="gpt_image_2")
        purpose = (reference_purpose or "product").strip().lower()
        ref_urls: list[str] = []
        for value in [reference_image_url, *(reference_image_urls or [])]:
            url = str(value or "").strip()
            if url and url not in ref_urls:
                ref_urls.append(url)
        ref_url = ref_urls[0] if ref_urls else None
        if ref_url:
            if purpose in {"character", "cast", "person"}:
                fidelity = (
                    "CAST CONTINUITY: Match the attached reference person's face, hair, build, "
                    "skin tone, and wardrobe exactly."
                )
            elif purpose in {"style", "scene"}:
                fidelity = (
                    "STYLE CONTINUITY: Match the attached reference for lighting, palette, "
                    "and environment tone."
                )
            else:
                fidelity = (
                    "PRODUCT FIDELITY: Match the attached product photo exactly — same shape, "
                    "colours, materials, proportions, and branding."
                )
            safe_prompt = f"{safe_prompt}\n\n{fidelity}"[:4000]

        size = map_format_to_size(format_type)
        ref_for_api: str | None = None
        if ref_url:
            if is_byteplus_ark_media_url(ref_url):
                ref_for_api = ref_url
            else:
                loaded = _load_reference_image_bytes(ref_url)
                if loaded:
                    import base64

                    content, _filename, mime = loaded
                    encoded = base64.b64encode(content).decode("ascii")
                    ref_for_api = f"data:{mime};base64,{encoded}"

        try:
            async with seedance_async_client() as client:
                byteplus_url, _raw = await generate_seedream_image(
                    client,
                    prompt=safe_prompt,
                    model=api_model,
                    size=size,
                    reference_image_url=ref_for_api,
                )
                dl = await client.get(byteplus_url, timeout=120.0, follow_redirects=True)
                dl.raise_for_status()
                content = dl.content
        except Exception as exc:
            logger.exception("BytePlus Seedream image generation failed")
            return {
                "status": "failed",
                "model": api_model,
                "prompt": prompt,
                "url": None,
                "provider": "byteplus",
                "error": str(exc)[:800],
            }

        suffix, content_type = image_suffix_and_type(content)
        try:
            saved = file_service.save_bytes(
                content=content,
                tenant_id=tenant_id,
                subfolder="generated",
                suffix=suffix,
                content_type=content_type,
            )
        except OSError as exc:
            return {
                "status": "failed",
                "model": api_model,
                "prompt": prompt,
                "url": None,
                "provider": "byteplus",
                "error": f"Could not save Seedream image locally: {exc}",
                "retryable": False,
            }

        note = (
            "Seedream still saved locally; BytePlus URL passed unchanged to Seedance on approve."
        )
        return {
            "status": "done",
            "model": api_model,
            "prompt": prompt,
            "url": saved["file_url"],
            "byteplus_url": byteplus_url if is_byteplus_ark_media_url(byteplus_url) else None,
            "provider": "byteplus",
            "note": note,
        }
