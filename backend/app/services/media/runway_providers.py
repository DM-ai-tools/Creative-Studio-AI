"""Runway ML image and video generation providers."""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings
from app.services.file_service import file_service
from app.services.media.base import ImageGenerationProvider, VideoGenerationProvider
from app.services.media.runway_client import (
    file_url_to_data_uri,
    ratio_for_video,
    runway_configured,
    submit_task_and_wait,
)
from app.services.media.runway_errors import format_runway_error
from app.services.brand_prompt import clamp_runway_image_prompt
from app.services.logo_overlay import apply_logo_overlay_to_file
from app.services.media.runway_models import (
    VIDEO_MODELS_REQUIRING_IMAGE,
    build_text_to_image_payload,
    normalize_runway_video_model_id,
    resolve_image_model,
    resolve_video_model,
)
from app.services.media_content import image_suffix_and_type, video_suffix_and_type

logger = logging.getLogger(__name__)

# Runway image_to_video — Veo 3 / 3.1 (official SDK union types, May 2026)
_VEO31_RATIOS = frozenset({"1280:720", "720:1280", "1080:1920", "1920:1080"})


def _normalize_runway_image_to_video_duration(provider_model: str, duration: int) -> int:
    """Map requested seconds to values Runway accepts for the given video model."""
    from app.services.video_duration import clamp_video_duration

    m = normalize_runway_video_model_id(provider_model)
    if m in ("veo3.1", "veo3.1.fast"):
        allowed = (4, 6, 8)
        if duration in allowed:
            return duration
        best, best_dist = allowed[0], abs(duration - allowed[0])
        for x in allowed[1:]:
            d = abs(duration - x)
            if d < best_dist or (d == best_dist and x > best):
                best, best_dist = x, d
        if best != duration:
            logger.info(
                "Runway Veo 3.1: duration %ss not supported (use 4, 6, or 8) — using %ss",
                duration,
                best,
            )
        return best
    if m == "veo3":
        return 8
    if m == "seedance2":
        return max(2, min(15, duration))
    if m in ("gen4.5", "gen4.turbo", "gen3a.turbo"):
        return max(2, min(10, duration))
    return clamp_video_duration(duration)


def _ratio_for_image_to_video(provider_model: str, format_type: str) -> str:
    """Aspect ratio string must match Runway's literal union for each model."""
    m = normalize_runway_video_model_id(provider_model)
    raw = ratio_for_video(format_type)
    if m in ("veo3.1", "veo3.1.fast", "veo3"):
        if raw in _VEO31_RATIOS:
            return raw
        ft = (format_type or "").lower()
        if ft in {"reel", "video", "stories"}:
            return "1080:1920"
        if ft == "carousel":
            return "1920:1080"
        return "1280:720"
    return raw


async def _download_asset(
    client: httpx.AsyncClient,
    url: str,
    *,
    tenant_id: str,
    kind: str,
) -> dict:
    from app.services.http_retry import async_request_with_retry

    download_headers: dict[str, str] | None = None
    if "runwayml.com" in url:
        download_headers = {"Authorization": f"Bearer {settings.RUNWAYML_API_KEY}"}
    response = await async_request_with_retry(
        client,
        "GET",
        url,
        follow_redirects=True,
        timeout=300.0,
        headers=download_headers,
        max_attempts=8,
        base_delay_sec=3.0,
        label="Asset download",
    )
    response.raise_for_status()
    content = response.content
    if len(content) < 32:
        raise ValueError(f"Downloaded asset too small ({len(content)} bytes)")

    if kind == "image":
        suffix, content_type = image_suffix_and_type(content)
    else:
        suffix, content_type = video_suffix_and_type(content)

    if len(content) <= settings.MAX_UPLOAD_SIZE:
        saved = file_service.save_bytes(
            content=content,
            tenant_id=tenant_id,
            subfolder="generated",
            suffix=suffix,
            content_type=content_type,
        )
        return {"url": saved["file_url"], "remote_url": url}
    return {"url": url, "remote_url": url}


class RunwayImageProvider(ImageGenerationProvider):
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
        provider_model = resolve_image_model(model)
        if not runway_configured():
            return {"status": "mock", "model": provider_model, "prompt": prompt, "url": None}

        safe_prompt = clamp_runway_image_prompt(prompt)
        payload = build_text_to_image_payload(
            model=provider_model,
            prompt=safe_prompt,
            format_type=format_type,
        )

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                outputs = await submit_task_and_wait(
                    client,
                    "/text_to_image",
                    payload,
                    label="Runway image",
                )
                saved = await _download_asset(
                    client,
                    outputs[0],
                    tenant_id=tenant_id,
                    kind="image",
                )
                final_url = saved["url"]
                if logo_url and final_url:
                    overlaid = apply_logo_overlay_to_file(
                        final_url,
                        logo_url,
                        tenant_id=tenant_id,
                        logo_on_light_url=logo_on_light_url,
                        format_type=format_type,
                    )
                    if overlaid:
                        final_url = overlaid
                return {
                    "status": "done",
                    "model": provider_model,
                    "prompt": prompt,
                    "url": final_url,
                    "provider": "runway",
                    "logo_applied": bool(logo_url and final_url),
                }
        except Exception as exc:
            err = format_runway_error(exc)
            if "not enough credits" in err.lower():
                logger.warning(
                    "Runway image skipped (no credits) — HeyGen video will still generate"
                )
            else:
                logger.exception("Runway image generation failed: %s", exc)
            return {
                "status": "failed",
                "model": provider_model,
                "prompt": prompt,
                "url": None,
                "provider": "runway",
                "error": err,
            }


class RunwayVideoProvider(VideoGenerationProvider):
    async def generate(
        self,
        *,
        prompt: str,
        brief: dict,
        copy: dict,
        format_type: str,
        model: str,
        tenant_id: str,
        source_image_url: str | None = None,
        duration_seconds: int | None = None,
    ) -> dict:
        from app.services.video_duration import resolve_video_duration_seconds

        provider_model = resolve_video_model(model)
        if not runway_configured():
            return self._storyboard_fallback(provider_model, brief, copy, status="mock")

        duration = resolve_video_duration_seconds(brief, override=duration_seconds)
        duration = _normalize_runway_image_to_video_duration(provider_model, duration)
        ratio = _ratio_for_image_to_video(provider_model, format_type)
        payload: dict = {
            "model": provider_model,
            "promptText": prompt,
            "ratio": ratio,
            "duration": duration,
        }

        from app.services.media.runway_client import file_url_to_data_uri_for_video

        prompt_image = file_url_to_data_uri_for_video(source_image_url)
        model_key = normalize_runway_video_model_id(provider_model)
        needs_image = model_key in VIDEO_MODELS_REQUIRING_IMAGE or model_key in (
            "veo3.1",
            "veo3.1.fast",
            "veo3",
        )
        if prompt_image:
            payload["promptImage"] = prompt_image
        elif needs_image:
            return self._storyboard_fallback(
                provider_model,
                brief,
                copy,
                status="failed",
                error=(
                    f"Runway {provider_model} needs a seed image. Image generation failed or "
                    "returned no file — fix the image step or pick a model that supports "
                    "text-only video, then regenerate."
                ),
            )

        label = f"Runway video ({provider_model})"
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                outputs = await submit_task_and_wait(
                    client,
                    "/image_to_video",
                    payload,
                    label=label,
                )
                saved = await _download_asset(
                    client,
                    outputs[0],
                    tenant_id=tenant_id,
                    kind="video",
                )
                final_url = saved["url"]
                voiceover: dict = {"status": "skipped"}
                if settings.RUNWAYML_VOICEOVER_ENABLED:
                    from app.services.media.voiceover import apply_voiceover_to_video_file

                    voiceover = await apply_voiceover_to_video_file(
                        client,
                        final_url,
                        copy=copy,
                        brief=brief,
                        tenant_id=tenant_id,
                    )
                    if voiceover.get("status") == "done" and voiceover.get("url"):
                        final_url = str(voiceover["url"])

                return {
                    "status": "done",
                    "model": provider_model,
                    "prompt": prompt,
                    "url": final_url,
                    "duration_seconds": duration,
                    "storyboard": [prompt],
                    "provider": "runway",
                    "voiceover": voiceover,
                }
        except Exception as exc:
            logger.exception("Runway video generation failed: %s", exc)
            return self._storyboard_fallback(
                provider_model,
                brief,
                copy,
                status="failed",
                error=format_runway_error(exc),
            )

    def _storyboard_fallback(
        self,
        provider_model: str,
        brief: dict,
        copy: dict,
        *,
        status: str,
        error: str | None = None,
    ) -> dict:
        return {
            "status": status,
            "model": provider_model,
            "provider": "runway",
            "error": error,
            "storyboard": [
                f"Open on brand hero for {brief.get('brand_name') or brief.get('product_name', 'the offer')}",
                f"Overlay hook: {copy.get('hook', '')}",
                f"Close with CTA: {copy.get('cta', brief.get('cta', 'Shop Now'))}",
            ],
            "url": None,
        }
