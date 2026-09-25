"""Higgsfield image and video generation providers."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.file_service import file_service
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
    is_seedance_video_spec,
    resolve_higgsfield_video_duration,
    resolve_image_spec,
    resolve_video_spec,
    supports_dop_clip_stitch,
)
from app.services.media.seedance_multiscene import (
    SEEDANCE_MAX_TOTAL_SECONDS,
    build_seedance_scene_prompt,
    concat_video_files,
    plan_seedance_scenes,
    scene_broll_from_brief,
    seedance_multiscene_requested,
    trim_video_to_duration,
)
from app.services.media.runway_providers import _download_asset
from app.services.media.voiceover import HIGGSFIELD_VOICE_PRESET_MAP
from app.services.video_duration import (
    requested_video_duration_seconds,
    resolve_video_duration_seconds,
)

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
    """Prefer already-hosted https URLs — avoid Higgsfield S3 re-upload (often 403)."""
    if not source_image_url:
        return None
    if source_image_url.startswith("http://") or source_image_url.startswith("https://"):
        return source_image_url
    local = _local_file_from_url(source_image_url)
    if not local:
        return source_image_url
    try:
        return await upload_local_image(str(local))
    except Exception as exc:
        logger.error(
            "Cannot re-upload local seed to Higgsfield (%s). "
            "Pass a remote https seed URL from image generation instead.",
            exc,
        )
        raise RuntimeError(
            "Seed image is only saved locally and Higgsfield file-upload is failing (S3 403). "
            "Retry Generate so the seed keeps its Higgsfield https URL, or pick a model that "
            "does not need a seed."
        ) from exc


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
        reference_image_url: str | None = None,
        reference_purpose: str = "product",
    ) -> dict:
        _ = reference_purpose
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
                try:
                    saved = await _download_asset(
                        client,
                        remote_url,
                        tenant_id=tenant_id,
                        kind="image",
                    )
                    final_url = saved["url"]
                except Exception as dl_exc:
                    # Presigned S3 URLs sometimes fail to mirror locally — keep remote URL
                    # so Creative Studio / video seed can still proceed.
                    logger.warning(
                        "Higgsfield image download failed (%s) — using remote URL",
                        dl_exc,
                    )
                    final_url = remote_url
            if logo_url and final_url and not final_url.startswith("http"):
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
                "remote_url": remote_url,
                "provider": "higgsfield",
                "logo_applied": bool(logo_url and final_url and not str(final_url).startswith("http")),
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

        if is_seedance_video_spec(spec) or supports_dop_clip_stitch(spec.job_set_type):
            requested_duration = min(
                requested_video_duration_seconds(brief, override=duration_seconds),
                SEEDANCE_MAX_TOTAL_SECONDS,
            )
        else:
            requested_duration = resolve_video_duration_seconds(
                brief, override=duration_seconds
            )

        production_skeleton = str(brief.get("video_script_skeleton") or "")

        if seedance_multiscene_requested(spec.job_set_type, requested_duration):
            return await self._generate_seedance_multiscene(
                spec=spec,
                model=model,
                brief=brief,
                copy=copy,
                format_type=format_type,
                tenant_id=tenant_id,
                source_image_url=source_image_url,
                requested_duration=requested_duration,
                production_skeleton=production_skeleton,
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

        skip_vo = bool(brief.get("skip_voiceover")) or (
            bool(brief.get("creative_studio_mode"))
            and not str(brief.get("higgsfield_voice_preset") or "").strip()
        )
        spoken_script = ""
        if not skip_vo:
            spoken_script = build_voiceover_script(copy=copy, brief=brief)
            # Never let TTS narrate a Creative Studio / Seedance shot-list prompt
            if brief.get("creative_studio_mode") or brief.get("creative_studio_prompt"):
                low = spoken_script.lower()
                if any(
                    m in low
                    for m in (
                        "clip 1",
                        "subject continuity",
                        "strict negative",
                        "timing beats",
                        "visual style",
                        "single continuous",
                    )
                ):
                    spoken_script = ""
                    skip_vo = True
        selected_hf_voice = str(brief.get("higgsfield_voice_preset") or "").strip().lower()
        runway_voice_preset = HIGGSFIELD_VOICE_PRESET_MAP.get(selected_hf_voice)

        arguments = build_video_arguments(
            prompt=prompt,
            format_type=format_type,
            duration=api_duration,
            image_url=image_url,
            spec=spec,
            spoken_script=spoken_script if not skip_vo else None,
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
                if (
                    settings.RUNWAYML_VOICEOVER_ENABLED
                    and not native_audio
                    and not skip_vo
                    and spoken_script.strip()
                ):
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
                elif skip_vo:
                    voiceover = {
                        "status": "skipped",
                        "reason": "Creative Studio sound off / no spoken script",
                    }
                elif not native_audio and not settings.RUNWAYML_VOICEOVER_ENABLED:
                    voiceover = {
                        "status": "skipped",
                        "reason": "Runway TTS disabled (RUNWAYML_VOICEOVER_ENABLED=false)",
                    }

            from app.services.ffmpeg_util import probe_video_duration

            probed = None
            local_video = _local_file_from_url(final_url)
            if local_video:
                try:
                    probed = probe_video_duration(local_video)
                except Exception:
                    probed = None

            reported = int(round(probed)) if probed and probed > 0.5 else None
            out_warn = duration_warning
            if reported and abs(reported - int(api_duration)) >= 2:
                out_warn = (
                    f"File is {reported}s (requested {api_duration}s). "
                    "Cinema Studio / DoP often returns ~5s — use Seedance 2.0 for 10–15s."
                )

            out: dict = {
                "status": "done",
                "model": spec.platform_path,
                "catalog_model": model,
                "prompt": prompt,
                "url": final_url,
                "duration_seconds": reported or api_duration,
                "requested_duration_seconds": requested_duration,
                "storyboard": [prompt],
                "provider": "higgsfield",
                "voiceover": voiceover,
                "native_audio": native_audio,
                "spoken_script": spoken_script if not skip_vo else "",
            }
            if out_warn:
                out["duration_warning"] = out_warn
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

    async def _generate_seedance_multiscene(
        self,
        *,
        spec,
        model: str,
        brief: dict,
        copy: dict,
        format_type: str,
        tenant_id: str,
        source_image_url: str | None,
        requested_duration: int,
        production_skeleton: str,
    ) -> dict:
        from app.services.media.voiceover import build_voiceover_script

        image_url = await _resolve_image_url_for_video(source_image_url)
        if spec.requires_image and not image_url:
            return self._fallback(
                spec.platform_path,
                brief,
                copy,
                status="failed",
                error=(
                    "Seedance multi-scene needs a seed image. "
                    "Ensure image generation succeeds first."
                ),
            )

        scenes = plan_seedance_scenes(
            requested_duration,
            job_set_type=spec.job_set_type,
            broll_raw=scene_broll_from_brief(brief),
            scene_prompt=str(
                brief.get("creative_studio_prompt")
                or production_skeleton
                or copy.get("body_copy")
                or ""
            ),
        )
        if not scenes:
            return self._fallback(
                spec.platform_path,
                brief,
                copy,
                status="failed",
                error="Could not plan Seedance scenes for the requested duration.",
            )

        spoken_script = build_voiceover_script(copy=copy, brief=brief)
        selected_hf_voice = str(brief.get("higgsfield_voice_preset") or "").strip().lower()
        runway_voice_preset = HIGGSFIELD_VOICE_PRESET_MAP.get(selected_hf_voice)
        native_audio = higgsfield_supports_native_audio(spec.job_set_type)

        scene_prompts: list[str] = []
        clip_paths: list[Path] = []
        stitch_dir = Path(file_service.upload_dir) / tenant_id / "generated" / "seedance-stitch"
        stitch_dir.mkdir(parents=True, exist_ok=True)

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                # Reuse the ORIGINAL Higgsfield seed for every clip.
                # Mid-stitch last-frame re-uploads hit S3 403 and waste credits —
                # ffmpeg still joins clips into the full requested length.
                current_image_url = image_url
                logger.info(
                    "Multi-scene stitch: %s clips planned for %ss (%s)",
                    len(scenes),
                    requested_duration,
                    spec.label,
                )
                from app.services.ffmpeg_util import probe_video_duration
                from app.services.media.registry import get_image_provider
                from app.services.media.higgsfield_models import higgsfield_configured

                for scene in scenes:
                    scene_prompt = build_seedance_scene_prompt(
                        scene,
                        brief=brief,
                        copy=copy,
                        format_type=format_type,
                        production_skeleton=production_skeleton,
                        total_duration=requested_duration,
                    )
                    scene_prompts.append(scene_prompt)
                    api_duration = int(scene["duration"])

                    # Per-CLIP seed when we have a beat visual — matches prompt better than
                    # reusing one seed for every scene (avoids frozen/split-screen loops).
                    scene_image_url = current_image_url
                    visual = str(scene.get("visual") or "").strip()
                    if visual and higgsfield_configured() and int(scene.get("index") or 0) > 0:
                        try:
                            seed_model = "hf-text2image-soul-v2"
                            img_provider = get_image_provider(seed_model)
                            seed_prompt = (
                                f"{visual}. Vertical 9:16 single full-frame commercial still. "
                                "ONE shot only — no split screen, no collage, no stacked panels, "
                                "no text, no logos as readable words."
                            )[:1600]
                            seed_res = await img_provider.generate(
                                prompt=seed_prompt,
                                tenant_id=tenant_id,
                                model=seed_model,
                                format_type=format_type,
                            )
                            next_seed = (
                                (seed_res or {}).get("remote_url")
                                or (seed_res or {}).get("url")
                            )
                            if (seed_res or {}).get("status") in {"done", "mock"} and next_seed:
                                scene_image_url = str(next_seed)
                        except Exception as seed_exc:
                            logger.warning(
                                "Per-clip seed failed for scene %s (%s); reusing prior seed",
                                scene["index"] + 1,
                                seed_exc,
                            )

                    arguments = build_video_arguments(
                        prompt=scene_prompt,
                        format_type=format_type,
                        duration=api_duration,
                        image_url=scene_image_url,
                        spec=spec,
                        spoken_script=spoken_script,
                    )
                    result = await subscribe_platform(
                        spec.platform_path,
                        arguments,
                        label=f"video scene {scene['index'] + 1}/{len(scenes)} ({spec.label})",
                    )
                    remote_url = extract_media_url(result)
                    if not remote_url:
                        raise RuntimeError(
                            f"Scene {scene['index'] + 1} returned no video URL"
                        )

                    saved = await _download_asset(
                        client,
                        remote_url,
                        tenant_id=tenant_id,
                        kind="video",
                    )
                    local_path = _local_file_from_url(saved["url"])
                    if not local_path:
                        raise RuntimeError(
                            f"Scene {scene['index'] + 1} could not be saved locally"
                        )
                    clip_dur = probe_video_duration(local_path)
                    logger.info(
                        "Stitch clip %s/%s duration=%.2fs (requested %ss)",
                        scene["index"] + 1,
                        len(scenes),
                        clip_dur or 0,
                        api_duration,
                    )
                    clip_paths.append(local_path)
                    current_image_url = scene_image_url

                if not clip_paths:
                    raise RuntimeError("No video clips were generated for stitch")

                stitched_path = stitch_dir / f"seedance-{uuid.uuid4()}.mp4"
                concat_video_files(clip_paths, stitched_path)
                trimmed = trim_video_to_duration(stitched_path, float(requested_duration))
                if trimmed:
                    stitched_path = trimmed

                saved_final = file_service.save_bytes(
                    content=stitched_path.read_bytes(),
                    tenant_id=tenant_id,
                    subfolder="generated",
                    suffix=".mp4",
                    content_type="video/mp4",
                )
                final_url = saved_final.get("file_url") or saved_final.get("url")
                if not final_url:
                    raise RuntimeError("Stitched video saved but no file URL was returned")

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

            clip_max = scenes[0]["duration"] if scenes else 5
            from app.services.ffmpeg_util import probe_video_duration

            actual_duration = probe_video_duration(stitched_path)
            reported = int(round(actual_duration)) if actual_duration else None
            return {
                "status": "done",
                "model": spec.platform_path,
                "catalog_model": model,
                "prompt": scene_prompts[0] if scene_prompts else "",
                "url": final_url,
                "duration_seconds": reported or requested_duration,
                "requested_duration_seconds": requested_duration,
                "storyboard": scene_prompts,
                "provider": "higgsfield",
                "voiceover": voiceover,
                "native_audio": native_audio,
                "spoken_script": spoken_script,
                "seedance_multiscene": True,
                "scene_count": len(clip_paths),
                "clip_duration_seconds": clip_max,
                "duration_warning": (
                    f"Stitched {len(clip_paths)} clips with {spec.label} → "
                    f"actual {reported or '?'}s (asked for {requested_duration}s)."
                    + (
                        " Duration probe was missing earlier — UI now shows real file length."
                        if reported and abs(reported - requested_duration) >= 2
                        else ""
                    )
                ),
            }
        except Exception as exc:
            logger.exception("Seedance multi-scene failed: %s", exc)
            # If we already paid for clip(s), return what we have instead of total loss
            if clip_paths:
                try:
                    partial = stitch_dir / f"seedance-partial-{uuid.uuid4()}.mp4"
                    concat_video_files(clip_paths, partial)
                    saved_partial = file_service.save_bytes(
                        content=partial.read_bytes(),
                        tenant_id=tenant_id,
                        subfolder="generated",
                        suffix=".mp4",
                        content_type="video/mp4",
                    )
                    partial_url = saved_partial.get("file_url") or saved_partial.get("url")
                    if not partial_url:
                        raise RuntimeError("Partial stitch saved but no file URL was returned")
                    return {
                        "status": "done",
                        "model": spec.platform_path,
                        "catalog_model": model,
                        "prompt": scene_prompts[0] if scene_prompts else "",
                        "url": partial_url,
                        "duration_seconds": sum(
                            int(s.get("duration") or 5) for s in scenes[: len(clip_paths)]
                        ),
                        "requested_duration_seconds": requested_duration,
                        "provider": "higgsfield",
                        "seedance_multiscene": True,
                        "scene_count": len(clip_paths),
                        "duration_warning": (
                            f"Partial stitch: got {len(clip_paths)}/{len(scenes)} clips "
                            f"before error ({exc}). Returning what completed so credits are not wasted."
                        ),
                        "error": None,
                    }
                except Exception as partial_exc:
                    logger.warning("Partial stitch save failed: %s", partial_exc)
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
