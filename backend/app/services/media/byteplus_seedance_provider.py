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


class BytePlusSeedanceVideoProvider(VideoGenerationProvider):
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
        if brief.get("creative_studio_mode") and brief.get("skip_voiceover"):
            generate_audio = False

        image_role = str(brief.get("seed_image_role") or "first_frame").strip().lower()
        if image_role not in {"first_frame", "last_frame", "reference_image"}:
            image_role = "first_frame"
        # Multi-beat / storyboard → multimodal reference mode (not pinned first_frame).
        multi_beat = bool(
            re.search(
                r"(?i)\bCLIP\s*2\b|\bHOOK\b|\bBODY\b|\bScene\s*2\b",
                (prompt or "") + " " + str(brief.get("creative_studio_prompt") or ""),
            )
        )
        raw_board = brief.get("storyboard_image_urls") or []
        if multi_beat or (isinstance(raw_board, list) and len(raw_board) > 0):
            image_role = "reference_image"

        def _resolve_img(u: str | None) -> str | None:
            if not u:
                return None
            resolved = file_url_to_data_uri(u)
            if resolved:
                return resolved
            if u.startswith("http://") or u.startswith("https://") or u.startswith("data:"):
                return u
            return None

        primary_ref = _resolve_img(source_image_url)

        # Collect storyboard + product refs (Seedance 2.0: up to 9 reference images)
        board_refs: list[str] = []
        if isinstance(raw_board, list):
            for item in raw_board[:9]:
                u = item.strip() if isinstance(item, str) else str((item or {}).get("url") or "").strip()
                if u and u != (source_image_url or ""):
                    board_refs.append(u)
        product_ref = str(brief.get("product_reference_url") or "").strip() or None
        raw_additional = brief.get("additional_reference_urls") or []
        additional_refs = [
            str(item or "").strip()
            for item in raw_additional
            if str(item or "").strip()
        ][:7]

        # CRITICAL BytePlus rule: first_frame/last_frame XOR reference_* — never mix.
        use_multimodal = image_role == "reference_image" or bool(board_refs)
        extra_refs: list[dict[str, str]] = []
        image_ref: str | None = None
        send_role = image_role

        if use_multimodal:
            send_role = "reference_image"
            seen: set[str] = set()
            for u in [source_image_url, product_ref, *additional_refs, *board_refs]:
                if not u or u in seen:
                    continue
                seen.add(u)
                resolved = _resolve_img(u)
                if resolved:
                    extra_refs.append({"url": resolved, "role": "reference_image"})
            extra_refs = extra_refs[:9]
            # All refs go in extra_image_refs; no pinned first_frame
            image_ref = None
        else:
            # Classic image-to-video: single first_frame only
            image_ref = primary_ref
            send_role = "first_frame" if image_ref else "reference_image"

        privacy_fallback_note: str | None = None
        motion_prompt = (prompt or "").strip()
        if use_multimodal and len(extra_refs) > 1:
            motion_prompt = (
                f"{motion_prompt}\n\n"
                f"MULTIMODAL REFERENCES: {len(extra_refs)} reference images are attached "
                "(product + supporting scene/character references + storyboard beats). "
                "Use each reference for its intended identity/continuity role; "
                "follow the timed CLIP beats in order; do not freeze on one frame."
            )[:4000]
        cs_job_id = str(brief.get("creative_studio_job_id") or "").strip() or None

        def _cancel_check() -> bool:
            if not cs_job_id:
                return False
            from app.services.creative_studio_job_service import is_job_cancel_requested

            return is_job_cancel_requested(cs_job_id)

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
                try:
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
                except Exception as create_exc:
                    # BytePlus privacy filter often flags photoreal AI people as "real person".
                    # Preserve the product reference if possible; removing every image destroys
                    # product continuity and makes the result unrelated to the supplied product.
                    has_imgs = bool(image_ref or extra_refs)
                    if has_imgs and is_seedance_person_privacy_block(create_exc):
                        logger.warning(
                            "Seedance blocked seed still (person/privacy filter); "
                            "retrying with product-only reference when available."
                        )
                        product_ref_resolved = _resolve_img(product_ref)
                        fallback_prompt = (
                            f"{motion_prompt}\n\n"
                            "REFERENCE FALLBACK: Some human storyboard references were removed by "
                            "the provider privacy filter. The attached product reference is authoritative. "
                            "Use the exact product silhouette, wheels, door, stripe, hardware, colour, "
                            "scale and branding from it in every product beat. Keep the same woman, "
                            "wardrobe and location across all scenes using the written brief. "
                            "Do not substitute a generic trailer or redesign the product. "
                            "Follow every scene and action; do not freeze on one frame."
                        )[:4000]
                        if product_ref_resolved:
                            try:
                                task_id = await create_video_task(
                                    client,
                                    prompt=fallback_prompt,
                                    model=api_model,
                                    duration=duration,
                                    ratio=ratio,
                                    resolution=resolution,
                                    generate_audio=generate_audio,
                                    image_data_uri_or_url=None,
                                    image_role="reference_image",
                                    extra_image_refs=[
                                        {
                                            "url": product_ref_resolved,
                                            "role": "reference_image",
                                        }
                                    ],
                                )
                                privacy_fallback_note = (
                                    "Human storyboard references were blocked by BytePlus privacy "
                                    "filter; regenerated with the supplied product photo as the "
                                    "authoritative reference."
                                )
                            except Exception as product_exc:
                                logger.warning(
                                    "Product-only Seedance reference also failed: %s",
                                    product_exc,
                                )
                                product_ref_resolved = None
                        if not product_ref_resolved:
                            privacy_fallback_note = (
                                "BytePlus blocked photoreal human references with its privacy "
                                "filter; regenerated text-to-video, so product identity is "
                                "prompt-guided only."
                            )
                            task_id = await create_video_task(
                                client,
                                prompt=fallback_prompt,
                                model=api_model,
                                duration=duration,
                                ratio=ratio,
                                resolution=resolution,
                                generate_audio=generate_audio,
                                image_data_uri_or_url=None,
                                extra_image_refs=None,
                            )
                        motion_prompt = fallback_prompt
                    else:
                        raise

                if cs_job_id:
                    from app.services.creative_studio_job_service import update_job

                    await update_job(
                        cs_job_id,
                        provider_task_id=task_id,
                        progress="Seedance running — you can Stop anytime…",
                    )

                if _cancel_check():
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
                    cancel_check=_cancel_check,
                )
                remote_url = extract_video_url(task)
                if not remote_url:
                    raise RuntimeError(f"BytePlus Seedance returned no video URL: {task!r}"[:400])

                saved = await _download_asset(
                    client,
                    remote_url,
                    tenant_id=tenant_id,
                    kind="video",
                )
                final_url = saved["url"]

            if _cancel_check():
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
            out: dict = {
                "status": "done",
                "model": api_model,
                "catalog_model": model,
                "prompt": motion_prompt,
                "url": final_url,
                "remote_url": saved.get("remote_url"),
                "duration_seconds": reported,
                "requested_duration_seconds": requested,
                "storyboard": [motion_prompt],
                "provider": "byteplus",
                "native_audio": generate_audio,
                "voiceover": {
                    "status": "skipped",
                    "reason": "Seedance native audio"
                    if generate_audio
                    else "Sound off",
                },
                "task_id": task_id,
                "seed_image_skipped_privacy": bool(privacy_fallback_note),
            }
            if privacy_fallback_note:
                out["duration_warning"] = privacy_fallback_note
                out["note"] = privacy_fallback_note
            return out
        except Exception as exc:
            logger.exception("BytePlus Seedance video failed: %s", exc)
            err = str(exc)
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
            if is_seedance_person_privacy_block(exc):
                err = (
                    "BytePlus Seedance privacy filter blocked the still (it may look like a real person). "
                    "This is their moderation — not a content violation on your side. "
                    "Regenerate the still without a clear face, or retry video without attaching the image."
                )
            return {
                "status": "failed",
                "model": api_model,
                "catalog_model": model,
                "prompt": prompt,
                "url": None,
                "provider": "byteplus",
                "error": err[:500],
            }
