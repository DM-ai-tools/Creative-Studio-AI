"""Higgsfield image and video generation providers."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.media.base import ImageGenerationProvider, VideoGenerationProvider
from app.services.media.higgsfield_client_service import (
    extract_media_url,
    subscribe_platform,
    upload_local_image,
)
from app.services.media.higgsfield_models import (
    build_image_arguments,
    build_video_arguments,
    higgsfield_configured,
    higgsfield_supports_native_audio,
    resolve_higgsfield_video_duration,
    resolve_image_spec,
    resolve_video_spec,
)
from app.services.media.runway_providers import _download_asset
from app.services.media.voiceover import HIGGSFIELD_VOICE_PRESET_MAP

logger = logging.getLogger(__name__)


def _local_file_from_url(file_url: str | None) -> Path | None:
    if not file_url:
        return None
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    rel: Path | None = None
    if file_url.startswith("/files/"):
        rel = Path(file_url.removeprefix("/files/"))
    elif file_url.startswith("files/"):
        rel = Path(file_url.removeprefix("files/"))
    if rel is None:
        return None
    path = (upload_root / rel).resolve()
    try:
        path.relative_to(upload_root)
    except ValueError:
        return None
    return path if path.is_file() else None


async def _resolve_image_url_for_video(source_image_url: str | None) -> str | None:
    if not source_image_url:
        return None
    if source_image_url.startswith("http://") or source_image_url.startswith("https://"):
        return source_image_url
    local = _local_file_from_url(source_image_url)
    if local:
        return await upload_local_image(str(local))
    return source_image_url


class HiggsfieldImageProvider(ImageGenerationProvider):
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
        spec = resolve_image_spec(model)
        if not spec:
            return {
                "status": "failed",
                "model": model,
                "prompt": prompt,
                "url": None,
                "provider": "higgsfield",
                "error": f"Unknown Higgsfield image model: {model}",
            }
        if not higgsfield_configured():
            return {
                "status": "mock",
                "model": spec.platform_path,
                "prompt": prompt,
                "url": None,
                "provider": "higgsfield",
            }

        arguments = build_image_arguments(prompt=prompt, format_type=format_type)
        try:
            result = await subscribe_platform(
                spec.platform_path,
                arguments,
                label=f"image ({spec.label})",
            )
            remote_url = extract_media_url(result)
            if not remote_url:
                raise RuntimeError("Higgsfield returned no image URL")

            async with httpx.AsyncClient(timeout=120.0) as client:
                saved = await _download_asset(
                    client,
                    remote_url,
                    tenant_id=tenant_id,
                    kind="image",
                )
            final_url = saved["url"]
            if logo_url and final_url:
                from app.services.logo_overlay import apply_logo_overlay_to_file

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
                "model": spec.platform_path,
                "catalog_model": model,
                "prompt": prompt,
                "url": final_url,
                "provider": "higgsfield",
                "logo_applied": bool(logo_url and final_url),
            }
        except Exception as exc:
            logger.exception("Higgsfield image failed: %s", exc)
            return {
                "status": "failed",
                "model": spec.platform_path,
                "catalog_model": model,
                "prompt": prompt,
                "url": None,
                "provider": "higgsfield",
                "error": str(exc),
            }


class HiggsfieldVideoProvider(VideoGenerationProvider):
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

        spec = resolve_video_spec(model)
        if not spec:
            return self._fallback(
                model,
                brief,
                copy,
                status="failed",
                error=f"Unknown Higgsfield video model: {model}",
            )
        if not higgsfield_configured():
            return self._fallback(spec.platform_path, brief, copy, status="mock")

        requested_duration = resolve_video_duration_seconds(
            brief, override=duration_seconds
        )
        api_duration, duration_warning = resolve_higgsfield_video_duration(
            spec.job_set_type, requested_duration
        )
        image_url = await _resolve_image_url_for_video(source_image_url)
        if spec.requires_image and not image_url:
            return self._fallback(
                spec.platform_path,
                brief,
                copy,
                status="failed",
                error=(
                    "This Higgsfield video model needs a seed image. "
                    "Ensure image generation succeeds first, or pick a model that does not require one."
                ),
            )

        from app.services.media.voiceover import build_voiceover_script

        spoken_script = build_voiceover_script(copy=copy, brief=brief)
        selected_hf_voice = str(brief.get("higgsfield_voice_preset") or "").strip().lower()
        runway_voice_preset = HIGGSFIELD_VOICE_PRESET_MAP.get(selected_hf_voice)

        arguments = build_video_arguments(
            prompt=prompt,
            format_type=format_type,
            duration=api_duration,
            image_url=image_url,
            spec=spec,
            spoken_script=spoken_script,
        )
        try:
            result = await subscribe_platform(
                spec.platform_path,
                arguments,
                label=f"video ({spec.label})",
            )
            remote_url = extract_media_url(result)
            if not remote_url:
                raise RuntimeError("Higgsfield returned no video URL")

            async with httpx.AsyncClient(timeout=300.0) as client:
                saved = await _download_asset(
                    client,
                    remote_url,
                    tenant_id=tenant_id,
                    kind="video",
                )
                final_url = saved["url"]
                native_audio = higgsfield_supports_native_audio(spec.job_set_type)
                voiceover: dict = {"status": "skipped"}
                if settings.RUNWAYML_VOICEOVER_ENABLED and not native_audio:
                    from app.services.media.voiceover import apply_voiceover_to_video_file

                    voiceover = await apply_voiceover_to_video_file(
                        client,
                        final_url,
                        copy=copy,
                        brief=brief,
                        tenant_id=tenant_id,
                        script_override=spoken_script,
                        voice_preset_override=runway_voice_preset,
                    )
                    if voiceover.get("status") == "done" and voiceover.get("url"):
                        final_url = str(voiceover["url"])
                elif not native_audio and not settings.RUNWAYML_VOICEOVER_ENABLED:
                    voiceover = {
                        "status": "skipped",
                        "reason": "Runway TTS disabled (RUNWAYML_VOICEOVER_ENABLED=false)",
                    }

            out: dict = {
                "status": "done",
                "model": spec.platform_path,
                "catalog_model": model,
                "prompt": prompt,
                "url": final_url,
                "duration_seconds": api_duration,
                "requested_duration_seconds": requested_duration,
                "storyboard": [prompt],
                "provider": "higgsfield",
                "voiceover": voiceover,
                "native_audio": native_audio,
                "spoken_script": spoken_script,
            }
            if duration_warning:
                out["duration_warning"] = duration_warning
            return out
        except Exception as exc:
            logger.exception("Higgsfield video failed: %s", exc)
            return self._fallback(
                spec.platform_path,
                brief,
                copy,
                status="failed",
                error=str(exc),
            )

    def _fallback(
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
            "provider": "higgsfield",
            "error": error,
            "storyboard": [
                f"Open on brand hero for {brief.get('brand_name') or brief.get('product_name', 'the offer')}",
                f"Overlay hook: {copy.get('hook', '')}",
                f"Close with CTA: {copy.get('cta', brief.get('cta', 'Shop Now'))}",
            ],
            "url": None,
        }
