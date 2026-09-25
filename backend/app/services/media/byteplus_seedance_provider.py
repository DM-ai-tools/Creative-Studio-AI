"""BytePlus ModelArk Seedance 2.0 video generation provider (Dreamina)."""

from __future__ import annotations

import logging
import re

import httpx

from app.core.config import settings
from app.services.media.base import VideoGenerationProvider
from app.services.media.byteplus_seedance_client import (
    ark_configured,
    ark_seedance_model,
    clamp_seedance_duration,
    create_video_task,
    extract_video_url,
    is_seedance_person_privacy_block,
    map_aspect_to_ratio,
    map_resolution,
    poll_video_task,
)
from app.services.media.runway_client import file_url_to_data_uri
from app.services.media.runway_providers import _download_asset
from app.services.media.seedance_references import (
    filter_manifest_for_privacy_retry,
    reference_instructions,
    reference_manifest,
)
from app.services.video_duration import requested_video_duration_seconds

logger = logging.getLogger(__name__)

# Catalog ids used in Creative Studio / generation UI
BYTEPLUS_SEEDANCE_MODEL_IDS = frozenset(
    {
        "ark-seedance-2-0",
        "ark-seedance-2",
        "byteplus-seedance-2-0",
        "seedance-2-0-byteplus",
        "dreamina-seedance-2-0",
    }
)


def is_byteplus_seedance_model(model: str | None) -> bool:
    if not model:
        return False
    mid = model.strip().lower().replace("_", "-")
    if mid in BYTEPLUS_SEEDANCE_MODEL_IDS:
        return True
    if mid.startswith("ark-seedance"):
        return True
    if "dreamina-seedance" in mid:
        return True
    # Env model id used directly
    env_model = ark_seedance_model().lower()
    return bool(env_model and mid == env_model.lower())


def resolve_byteplus_api_model(model: str | None) -> str:
    """Map catalog id → BytePlus model string."""
    mid = (model or "").strip()
    if mid.startswith("dreamina-seedance"):
        return mid
    return ark_seedance_model()


_PRIVACY_ANCHORS_WARNING = (
    "BytePlus privacy filter blocked photoreal reference images (often AI-generated people). "
    "Retried with product/logo/scene anchors only; product identity is prompt-guided for people and compositions."
)
_PRIVACY_TEXT_TO_VIDEO_WARNING = (
    "BytePlus privacy filter blocked attaching reference images (photoreal faces). "
    "Continued as text-to-video; product identity is prompt-guided from the written brief."
)


class BytePlusSeedanceVideoProvider(VideoGenerationProvider):
    async def _run_seedance_attempt(
        self,
        *,
        client: httpx.AsyncClient,
        motion_prompt: str,
        api_model: str,
        model: str,
        duration: int,
        ratio: str,
        resolution: str,
        generate_audio: bool,
        bound_assets: list[dict[str, str]],
        image_ref: str | None,
        send_role: str,
        extra_refs: list[dict[str, str]],
        tenant_id: str,
        cs_job_id: str | None,
        cancel_check,
    ) -> dict:
        task_id = await create_video_task(
            client,
            prompt=motion_prompt,
            model=api_model,
            duration=duration,
            ratio=ratio,
            resolution=resolution,
            generate_audio=generate_audio,
            image_data_uri_or_url=image_ref,
            image_role=send_role,
            extra_image_refs=extra_refs or None,
        )

        if cs_job_id:
            from app.services.creative_studio_job_service import update_job

            await update_job(
                cs_job_id,
                provider_task_id=task_id,
                progress="Seedance running — you can Stop anytime…",
            )

        if cancel_check():
            from app.services.media.byteplus_seedance_client import delete_video_task

            await delete_video_task(task_id, client=client)
            return {
                "status": "cancelled",
                "model": api_model,
                "catalog_model": model,
                "prompt": motion_prompt,
                "url": None,
                "provider": "byteplus",
                "error": "Cancelled by user",
                "task_id": task_id,
            }

        task = await poll_video_task(
            client,
            task_id,
            label=f"BytePlus Seedance ({api_model})",
            cancel_check=cancel_check,
        )
        remote_url = extract_video_url(task)
        from app.services.media.byteplus_usage import video_task_usage
        from app.services.usage_tracker import record_usage

        provider_usage = video_task_usage(task, task_id=task_id, model=api_model)
        record_usage(
            provider="byteplus",
            model=api_model,
            operation="video_generation",
            prompt_tokens=provider_usage.get("prompt_tokens") or 0,
            completion_tokens=provider_usage.get("completion_tokens") or 0,
            total_tokens=provider_usage.get("total_tokens") or 0,
            tenant_id=tenant_id,
            extra=provider_usage,
        )
        if not remote_url:
            raise RuntimeError(f"BytePlus Seedance returned no video URL: {task!r}"[:400])

        download_warning: str | None = None
        try:
            saved = await _download_asset(
                client,
                remote_url,
                tenant_id=tenant_id,
                kind="video",
            )
        except Exception as exc:
            # The billable provider task already succeeded. Preserve its remote
            # URL so the caller can retry only the download; never submit and
            # charge for another generation because local storage failed.
            logger.exception("Seedance output download failed; preserving provider URL: %s", exc)
            saved = {"url": remote_url, "remote_url": remote_url}
            download_warning = (
                "Seedance generation succeeded, but its output could not be saved locally. "
                f"The provider URL was preserved for download recovery: {exc}"
            )
        final_url = saved["url"]

        if cancel_check():
            return {
                "status": "cancelled",
                "model": api_model,
                "catalog_model": model,
                "prompt": motion_prompt,
                "url": None,
                "provider": "byteplus",
                "error": "Cancelled by user",
                "task_id": task_id,
            }

        reported = int(task.get("duration") or duration)
        result = {
            "status": "done",
            "model": api_model,
            "catalog_model": model,
            "prompt": motion_prompt,
            "url": final_url,
            "remote_url": saved.get("remote_url"),
            "duration_seconds": reported,
            "storyboard": [motion_prompt],
            "provider": "byteplus",
            "audio_requested": generate_audio,
            "provider_usage": [provider_usage],
            "voiceover": {
                "status": "skipped",
                "reason": "Seedance native audio" if generate_audio else "Sound off",
            },
            "task_id": task_id,
            "reference_bindings": [
                {"image": i, "role": asset["role"]} for i, asset in enumerate(bound_assets, 1)
            ],
        }
        if download_warning:
            result["download_warning"] = download_warning[:500]
        return result

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
        api_model = resolve_byteplus_api_model(model)
        if not ark_configured():
            return {
                "status": "mock",
                "model": api_model,
                "catalog_model": model,
                "prompt": prompt,
                "url": None,
                "provider": "byteplus",
                "error": "ARK_API_KEY not set",
            }

        requested = requested_video_duration_seconds(brief, override=duration_seconds)
        max_sec = 30 if "2-5" in api_model or "2.5" in api_model else 15
        duration = clamp_seedance_duration(requested, max_seconds=max_sec)

        aspect = str(
            brief.get("creative_studio_aspect")
            or brief.get("aspect")
            or ""
        )
        ratio = map_aspect_to_ratio(aspect, format_type)
        resolution = map_resolution(
            str(brief.get("creative_studio_resolution") or brief.get("resolution") or "720p")
        )
        generate_audio = not bool(brief.get("skip_voiceover"))
        if brief.get("creative_studio_mode"):
            generate_audio = bool(
                brief.get("creative_studio_generate_audio", generate_audio)
            )

        image_role = str(brief.get("seed_image_role") or "first_frame").strip().lower()
        if image_role not in {"first_frame", "last_frame", "reference_image"}:
            image_role = "first_frame"
        def _resolve_img(u: str | None) -> str | None:
            if not u:
                return None
            resolved = file_url_to_data_uri(u)
            if resolved:
                return resolved
            if u.startswith("http://") or u.startswith("https://") or u.startswith("data:"):
                return u
            return None

        manifest = reference_manifest(brief, source_image_url)
        strict_character_reference = bool(brief.get("strict_character_reference")) and any(
            asset.get("role") == "character" for asset in manifest
        )
        strict_continuity_reference = bool(brief.get("strict_continuity_reference")) and any(
            asset.get("role") == "continuity" for asset in manifest
        )
        strict_reference_lock = strict_character_reference or strict_continuity_reference
        use_multimodal = image_role == "reference_image" or len(manifest) > 1 or any(
            asset["role"] != "storyboard" for asset in manifest
        )
        base_prompt = (prompt or "").strip()
        cs_job_id = str(brief.get("creative_studio_job_id") or "").strip() or None

        def _cancel_check() -> bool:
            if not cs_job_id:
                return False
            from app.services.creative_studio_job_service import is_job_cancel_requested

            return is_job_cancel_requested(cs_job_id)

        def _build_submission(
            assets: list[dict[str, str]],
            *,
            multimodal: bool,
            pin_primary: bool,
            prompt_suffix: str = "",
        ) -> tuple[str, str | None, str, list[dict[str, str]], list[dict[str, str]]]:
            primary_url: str | None = None
            if pin_primary:
                primary_url = str(brief.get("continuity_reference_url") or "").strip() or None
                if not primary_url and image_role in {"first_frame", "last_frame"}:
                    primary_url = str(source_image_url or "").strip() or None

            ordered_assets = list(assets)
            if primary_url:
                ordered_assets = [
                    {
                        "url": primary_url,
                        "role": "continuity" if brief.get("continuity_reference_url") else "opening",
                    },
                    *[asset for asset in ordered_assets if asset.get("url") != primary_url],
                ]
            # Seedance accepts at most nine images total. Keep the exact primary
            # frame first, then the highest-priority dynamic references.
            ordered_assets = ordered_assets[:9]
            # BytePlus does not allow first_frame/last_frame content to be mixed
            # with reference_image content in one task. When an exact opening or
            # continuation frame is present, submit that image alone. Its scene
            # already contains the approved character/product/location state.
            submitted_assets = ordered_assets[:1] if primary_url else ordered_assets
            motion = base_prompt + prompt_suffix + reference_instructions(submitted_assets)
            if multimodal and assets:
                image_ref = _resolve_img(primary_url) if primary_url else None
                if primary_url and not image_ref:
                    raise ValueError("Cannot load the approved opening/continuity frame. Reattach it before generation.")
                extra_refs: list[dict[str, str]] = []
                for asset in submitted_assets:
                    if primary_url and asset.get("url") == primary_url:
                        continue
                    resolved = _resolve_img(asset["url"])
                    if not resolved:
                        raise ValueError(
                            f"Cannot load the {asset['role']} reference image. Reattach it before generation."
                        )
                    extra_refs.append({"url": resolved, "role": "reference_image"})
                return (
                    motion,
                    image_ref,
                    "first_frame" if primary_url else "reference_image",
                    extra_refs,
                    submitted_assets,
                )
            if source_image_url and not multimodal:
                image_ref = _resolve_img(source_image_url)
                if not image_ref:
                    raise ValueError("Cannot load the approved still. Reattach it before generation.")
                return motion, image_ref, image_role, [], []
            return motion, None, "first_frame", [], []

        anchor_assets = filter_manifest_for_privacy_retry(manifest)
        attempt_plan: list[tuple[str, list[dict[str, str]], bool, str, str | None]] = [
            ("full", manifest, use_multimodal, "", None),
        ]
        if not strict_reference_lock:
            if anchor_assets and anchor_assets != manifest:
                attempt_plan.append(
                    ("anchors", anchor_assets, True, "", _PRIVACY_ANCHORS_WARNING),
                )
            attempt_plan.append(
                (
                    "text_to_video",
                    [],
                    False,
                    "\n\nNOTE: No reference images attached — BytePlus privacy filter rejected photoreal faces. "
                    "Follow the written brief; product identity is prompt-guided.",
                    _PRIVACY_TEXT_TO_VIDEO_WARNING,
                ),
            )

        privacy_exc: Exception | None = None
        try:
            if _cancel_check():
                return {
                    "status": "cancelled",
                    "model": api_model,
                    "catalog_model": model,
                    "prompt": prompt,
                    "url": None,
                    "provider": "byteplus",
                    "error": "Cancelled by user",
                }

            async with httpx.AsyncClient(timeout=180.0) as client:
                for tier_index, (tier, assets, multimodal, suffix, warning) in enumerate(attempt_plan):
                    if tier == "anchors" and not assets:
                        continue
                    motion_prompt, image_ref, send_role, extra_refs, bound_assets = _build_submission(
                        assets,
                        multimodal=multimodal,
                        pin_primary=tier == "full",
                        prompt_suffix=suffix,
                    )
                    if cs_job_id and tier != "full":
                        from app.services.creative_studio_job_service import update_job

                        label = (
                            "Retrying Seedance with product/logo anchors only…"
                            if tier == "anchors"
                            else "Retrying Seedance as text-to-video (privacy filter)…"
                        )
                        await update_job(cs_job_id, progress=label)

                    try:
                        out = await self._run_seedance_attempt(
                            client=client,
                            motion_prompt=motion_prompt,
                            api_model=api_model,
                            model=model,
                            duration=duration,
                            ratio=ratio,
                            resolution=resolution,
                            generate_audio=generate_audio,
                            bound_assets=bound_assets,
                            image_ref=image_ref,
                            send_role=send_role,
                            extra_refs=extra_refs,
                            tenant_id=tenant_id,
                            cs_job_id=cs_job_id,
                            cancel_check=_cancel_check,
                        )
                        if out.get("status") != "done":
                            return out
                        out["requested_duration_seconds"] = requested
                        if warning:
                            out["duration_warning"] = warning
                            out["privacy_fallback"] = tier
                        return out
                    except Exception as exc:
                        if "cancelled by user" in str(exc).lower():
                            raise
                        if is_seedance_person_privacy_block(exc):
                            privacy_exc = exc
                            logger.warning(
                                "BytePlus Seedance privacy filter on tier %s — trying fallback",
                                tier,
                            )
                            continue
                        raise

            if privacy_exc:
                raise privacy_exc
            raise RuntimeError("BytePlus Seedance failed without a provider error")
        except Exception as exc:
            logger.exception("BytePlus Seedance video failed: %s", exc)
            err = str(exc)
            billing_blocked = any(
                marker in err.lower()
                for marker in (
                    "accountoverdueerror",
                    "overdue balance",
                    "insufficient balance",
                    "insufficient funds",
                )
            )
            if "cancelled by user" in err.lower():
                return {
                    "status": "cancelled",
                    "model": api_model,
                    "catalog_model": model,
                    "prompt": prompt,
                    "url": None,
                    "provider": "byteplus",
                    "error": "Cancelled by user",
                }
            if billing_blocked:
                return {
                    "status": "failed",
                    "model": api_model,
                    "catalog_model": model,
                    "prompt": prompt,
                    "url": None,
                    "provider": "byteplus",
                    "error": (
                        "BytePlus Seedance rejected the request because the BytePlus account "
                        "has an overdue or insufficient balance. Settle/recharge BytePlus billing, "
                        "then retry. No video segment was generated."
                    ),
                    "retryable": False,
                    "error_code": "AccountOverdueError",
                }
            if is_seedance_person_privacy_block(exc):
                if strict_continuity_reference:
                    err = (
                        "Seedance blocked the previous chapter's continuity frame. The long video "
                        "was stopped instead of inventing a different person or scene. Use a "
                        "non-photoreal character anchor, or generate the affected chapter again."
                    )
                elif strict_character_reference:
                    err = (
                        "Seedance blocked the selected character reference as photoreal identity content. "
                        "No replacement person was generated. Choose a non-photoreal or 2D character "
                        "anchor, or remove the character lock and try again."
                    )
                else:
                    err = (
                        "BytePlus Seedance privacy filter blocked all reference images (photoreal faces). "
                        "Automatic text-to-video fallback also failed. This is provider moderation — "
                        "not a content violation on your side."
                    )
            return {
                "status": "failed",
                "model": api_model,
                "catalog_model": model,
                "prompt": prompt,
                "url": None,
                "provider": "byteplus",
                "error": err[:500],
                "retryable": True,
            }
