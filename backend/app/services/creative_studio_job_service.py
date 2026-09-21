"""In-memory Creative Studio jobs — avoid HTTP timeouts on long Higgsfield stitches."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = asyncio.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seedance_segment_durations(total_seconds: int, clip_cap: int = 15) -> list[int]:
    """Split a long Creative Studio runtime into valid Seedance clip lengths."""
    total = max(5, min(600, int(total_seconds or 15)))
    cap = max(5, int(clip_cap or 15))
    count = max(1, (total + cap - 1) // cap)
    base, remainder = divmod(total, count)
    return [base + (1 if i < remainder else 0) for i in range(count)]


async def create_job(*, tenant_id: str, payload: dict[str, Any]) -> str:
    job_id = str(uuid.uuid4())
    async with _LOCK:
        _JOBS[job_id] = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "status": "queued",
            "progress": "Queued — starting soon…",
            "created_at": _now(),
            "updated_at": _now(),
            "payload": payload,
            "result": None,
            "error": None,
            "cancel_requested": False,
            "provider_task_id": None,
        }
    return job_id


async def update_job(job_id: str, **fields: Any) -> None:
    async with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        job.update(fields)
        job["updated_at"] = _now()


def is_job_cancel_requested(job_id: str | None) -> bool:
    if not job_id:
        return False
    job = _JOBS.get(job_id)
    return bool(job and job.get("cancel_requested"))


async def cancel_job(job_id: str, *, tenant_id: str) -> dict[str, Any] | None:
    """User kill-switch — mark cancelled and try to delete BytePlus task if known."""
    provider_task_id: str | None = None
    async with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job.get("tenant_id") != tenant_id:
            return None
        if job.get("status") in {"done", "failed", "cancelled", "mock"}:
            return {
                "job_id": job_id,
                "status": str(job.get("status")),
                "progress": job.get("progress"),
                "error": job.get("error"),
            }
        job["cancel_requested"] = True
        job["status"] = "cancelled"
        job["progress"] = "Stopped by user"
        job["error"] = "Cancelled by user"
        job["updated_at"] = _now()
        provider_task_id = job.get("provider_task_id")
        if isinstance(job.get("result"), dict):
            provider_task_id = provider_task_id or job["result"].get("provider_task_id")
            provider_task_id = provider_task_id or job["result"].get("task_id")

    if provider_task_id:
        try:
            from app.services.media.byteplus_seedance_client import delete_video_task

            await delete_video_task(str(provider_task_id))
        except Exception as exc:
            logger.warning("Could not delete BytePlus task %s: %s", provider_task_id, exc)

    return {
        "job_id": job_id,
        "status": "cancelled",
        "progress": "Stopped by user",
        "error": "Cancelled by user",
    }


async def get_job(job_id: str, *, tenant_id: str | None = None) -> dict[str, Any] | None:
    async with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return None
        if tenant_id and job.get("tenant_id") != tenant_id:
            return None
        # Don't expose internal payload on poll
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "progress": job.get("progress"),
            "error": job.get("error"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            **(job.get("result") or {}),
        }


async def run_creative_studio_job(job_id: str) -> None:
    """Background worker — updates job status until done/failed."""
    from app.services.creative_studio_prompt_service import (
        build_spoken_voiceover,
        sanitize_visual_prompt,
        seed_frame_prompt,
    )
    from app.services.media.byteplus_seedance_provider import is_byteplus_seedance_model
    from app.services.media.higgsfield_models import (
        higgsfield_configured,
        is_higgsfield_video_model,
        resolve_higgsfield_video_duration,
        resolve_video_spec,
    )
    from app.services.media.registry import get_image_provider, get_video_provider
    from app.services.usage_tracker import estimate_media_cost

    job = _JOBS.get(job_id)
    if not job:
        return
    data = job["payload"]
    tenant_id = job["tenant_id"]

    def _format_from_aspect(aspect: str) -> str:
        a = (aspect or "9/16").replace(":", "/")
        if a in {"9/16", "1/4"}:
            return "reel"
        if a in {"16/9"}:
            return "video"
        if a in {"4/3"}:
            return "carousel"
        return "static"

    try:
        if is_job_cancel_requested(job_id):
            await update_job(
                job_id,
                status="cancelled",
                progress="Stopped by user",
                error="Cancelled by user",
            )
            return

        await update_job(job_id, status="running", progress="Preparing prompt…")
        prompt = (data.get("prompt") or "").strip()
        model = (data.get("model") or "").strip()
        neg = (data.get("negative_prompt") or "").strip()
        # Image prompts must exclude typography, but video prompts must retain the user's
        # exact overlay copy. Sanitizing both was silently deleting all requested text.
        visual_prompt = (
            prompt
            if str(data.get("media_mode") or "video").strip().lower() == "video"
            else sanitize_visual_prompt(prompt)
        )
        product_ref_early = str(data.get("product_reference_url") or "").strip()
        if product_ref_early and not re.search(
            r"(?i)product (fidelity|reference)|match the attached product",
            visual_prompt,
        ):
            visual_prompt = (
                f"{visual_prompt} "
                "PRODUCT FIDELITY: match the attached product photo exactly — "
                "same shape, colour, materials, branding."
            )
        if neg:
            visual_prompt = f"{visual_prompt} Avoid: {neg}."
        format_type = _format_from_aspect(str(data.get("aspect") or "9/16"))
        mode = str(data.get("media_mode") or "video").strip().lower()

        if mode == "image":
            if is_job_cancel_requested(job_id):
                await update_job(
                    job_id,
                    status="cancelled",
                    progress="Stopped by user",
                    error="Cancelled by user",
                )
                return
            await update_job(job_id, progress="Generating image…")
            provider = get_image_provider(model)
            product_ref = (
                str(data.get("product_reference_url") or data.get("seed_image_url") or "")
                .strip()
                or None
            )
            if product_ref:
                await update_job(
                    job_id,
                    progress="Generating image from your product photo…",
                )
            result = await provider.generate(
                prompt=visual_prompt,
                tenant_id=tenant_id,
                model=model,
                format_type=format_type,
                reference_image_url=product_ref,
            )
            if is_job_cancel_requested(job_id):
                await update_job(
                    job_id,
                    status="cancelled",
                    progress="Stopped by user",
                    error="Cancelled by user",
                )
                return
            _, credits = estimate_media_cost(
                provider=str((result or {}).get("provider") or "image"),
                model=model,
            )
            note = (result or {}).get("note") or (
                "Still matched to attached product photo."
                if product_ref
                else "Visual-only still (no on-image text requested)."
            )
            await update_job(
                job_id,
                status=str((result or {}).get("status") or "failed"),
                progress="Done" if (result or {}).get("status") == "done" else "Failed",
                error=(result or {}).get("error"),
                result={
                    "url": (result or {}).get("url"),
                    "model": str((result or {}).get("model") or model),
                    "provider": (result or {}).get("provider"),
                    "credits_estimate": credits or None,
                    "product_reference_url": product_ref,
                    "note": note,
                },
            )
            return

        if mode == "storyboard":
            if is_job_cancel_requested(job_id):
                await update_job(
                    job_id,
                    status="cancelled",
                    progress="Stopped by user",
                    error="Cancelled by user",
                )
                return
            scenes_in = data.get("storyboard_scenes") or []
            if not isinstance(scenes_in, list) or not scenes_in:
                await update_job(
                    job_id,
                    status="failed",
                    progress="Failed",
                    error="No storyboard scenes to generate",
                )
                return
            product_ref = (
                str(data.get("product_reference_url") or "").strip() or None
            )
            provider = get_image_provider(model)
            frames: list[dict[str, Any]] = []
            total = min(6, len(scenes_in))
            await update_job(
                job_id,
                progress=f"Storyboard 0/{total} — generating scene stills…",
            )

            async def _one(scene: dict[str, Any], idx: int) -> dict[str, Any]:
                from app.services.creative_studio_storyboard import scene_wants_product

                sp = str(scene.get("image_prompt") or scene.get("prompt") or "").strip()
                title = str(scene.get("title") or f"Scene {idx + 1}")
                index = int(scene.get("index") or idx + 1)
                # Prefer explicit flag from parser; never infer from "close-up" etc.
                if "wants_product" in scene:
                    wants = bool(scene.get("wants_product"))
                else:
                    wants = scene_wants_product(title=title, visual=sp, index=index)

                use_product_ref = bool(product_ref) and wants
                if wants and product_ref and not re.search(
                    r"(?i)match the attached|product fidelity|product photo",
                    sp,
                ):
                    sp = (
                        f"{sp} PRODUCT FIDELITY: match attached product photo exactly."
                    )
                if not wants:
                    # Strip any leaked product-lock lines from earlier drafts
                    sp = re.sub(
                        r"(?i)\s*PRODUCT FIDELITY:.*?(?=\.|$)",
                        "",
                        sp,
                    )
                    sp = re.sub(
                        r"(?i)\s*Product must match the attached[^.]*\.",
                        "",
                        sp,
                    )
                    if not re.search(
                        r"(?i)do NOT show|BEFORE / problem|basic weathered wooden",
                        sp,
                    ):
                        sp = (
                            f"{sp} CRITICAL: Do NOT show the modern product trailer/caravan. "
                            "Only a basic weathered wooden chicken coop (problem state)."
                        )

                res = await provider.generate(
                    prompt=sp[:2200],
                    tenant_id=tenant_id,
                    model=model,
                    format_type=format_type,
                    # Product photo ONLY on Turn / Reveal / Feature / Close — never Hook/Manual
                    reference_image_url=product_ref if use_product_ref else None,
                )
                return {
                    "id": str(scene.get("id") or f"scene-{idx + 1}"),
                    "index": index,
                    "title": title[:80],
                    "image_prompt": sp[:2200],
                    "overlays": list(scene.get("overlays") or [])[:6],
                    "url": (res or {}).get("url"),
                    "status": str((res or {}).get("status") or "failed"),
                    "error": (res or {}).get("error"),
                    "wants_product": wants,
                }

            # Sequential to avoid OpenAI rate spikes; publish frames as each scene lands
            for i, scene in enumerate(scenes_in[:total]):
                if is_job_cancel_requested(job_id):
                    await update_job(
                        job_id,
                        status="cancelled",
                        progress="Stopped by user",
                        error="Cancelled by user",
                        result={"storyboard": frames, "media_mode": "storyboard"},
                    )
                    return
                title_hint = str(
                    (scene or {}).get("title") if isinstance(scene, dict) else f"Scene {i+1}"
                )[:40]
                await update_job(
                    job_id,
                    progress=f"Storyboard {i + 1}/{total} — {title_hint}…",
                    result={
                        "storyboard": frames
                        + [
                            {
                                "id": str((scene or {}).get("id") or f"scene-{i + 1}")
                                if isinstance(scene, dict)
                                else f"scene-{i + 1}",
                                "index": i + 1,
                                "title": title_hint,
                                "url": None,
                                "status": "running",
                            }
                        ],
                        "media_mode": "storyboard",
                    },
                )
                try:
                    frame = await _one(scene if isinstance(scene, dict) else {}, i)
                except Exception as exc:
                    logger.exception("Storyboard scene %s failed", i + 1)
                    frame = {
                        "id": f"scene-{i + 1}",
                        "index": i + 1,
                        "title": title_hint,
                        "image_prompt": "",
                        "overlays": [],
                        "url": None,
                        "status": "failed",
                        "error": str(exc)[:400],
                    }
                frames.append(frame)
                done_urls = [f.get("url") for f in frames if f.get("url")]
                await update_job(
                    job_id,
                    progress=(
                        f"Storyboard {i + 1}/{total} done — "
                        f"{len(done_urls)} image(s) ready…"
                    ),
                    result={
                        "url": done_urls[0] if done_urls else None,
                        "storyboard": list(frames),
                        "media_mode": "storyboard",
                        "product_reference_url": product_ref,
                    },
                )

            ok_frames = [f for f in frames if f.get("url") and f.get("status") in {"done", "mock"}]
            first_url = (ok_frames[0]["url"] if ok_frames else None) or (
                frames[0].get("url") if frames else None
            )
            # Prefer product hero as primary url for approve seed
            hero = None
            for f in ok_frames:
                blob = f"{f.get('title','')}".lower()
                if any(k in blob for k in ("reveal", "feature", "close", "product")):
                    hero = f
                    break
            if hero and hero.get("url"):
                first_url = hero["url"]

            status = "done" if ok_frames else "failed"
            err = None if ok_frames else "All storyboard scenes failed"
            if ok_frames and len(ok_frames) < total:
                err = None  # partial success still usable
            await update_job(
                job_id,
                status=status,
                progress=(
                    f"Storyboard ready — {len(ok_frames)}/{total} scenes"
                    if ok_frames
                    else "Storyboard failed"
                ),
                error=err,
                result={
                    "url": first_url,
                    "model": model,
                    "provider": "openai",
                    "storyboard": frames,
                    "media_mode": "storyboard",
                    "product_reference_url": product_ref,
                    "note": (
                        f"Higgsfield-style storyboard: {len(ok_frames)} scene stills. "
                        "Approve to animate the full multi-scene brief with Seedance."
                    ),
                },
            )
            return

        seed_url: str | None = None
        use_byteplus = is_byteplus_seedance_model(model)
        video_spec = resolve_video_spec(model) if is_higgsfield_video_model(model) else None
        # Chat / uploads can supply a reference frame for Seedance.
        attached_seed = str(data.get("seed_image_url") or "").strip() or None
        if attached_seed:
            seed_url = attached_seed
        # BytePlus Seedance supports text-to-video — seed frame optional (faster path).
        needs_seed = (
            bool(video_spec and video_spec.requires_image)
            and not use_byteplus
            and not seed_url
        )
        requested_duration = max(5, min(600, int(data.get("duration_seconds") or 15)))
        sound_on = bool(data.get("sound_on", False))
        if use_byteplus:
            # Seedance limits one task to 15s. Long Creative Studio videos are
            # generated as valid segments and stitched below.
            api_duration = requested_duration
            duration_warning = (
                f"{requested_duration}s will be generated as "
                f"{len(_seedance_segment_durations(requested_duration))} Seedance segments."
                if requested_duration > 15
                else None
            )
        else:
            api_duration, duration_warning = (
                resolve_higgsfield_video_duration(video_spec.job_set_type, requested_duration)
                if video_spec
                else (requested_duration, None)
            )
        # Ask the model for what it can actually deliver (not the UI wish alone).
        generate_duration = int(api_duration or requested_duration)
        seed_image_role = str(data.get("seed_image_role") or "first_frame").strip().lower()
        if seed_image_role not in {"first_frame", "reference_image"}:
            seed_image_role = "first_frame"
        # Multi-beat prompts should not freeze on the still — prefer reference guidance.
        if re.search(r"(?i)\bCLIP\s*2\b|\bHOOK\b|\bBODY\b", visual_prompt or ""):
            seed_image_role = "reference_image"

        if sound_on:
            motion_prompt = (
                f"{visual_prompt}\n\n"
                f"Perform this as a {generate_duration}-second continuous ad. "
                f"Follow every timed beat — do not freeze on the opening frame. "
                f"AUDIO ON: native diegetic sound (ambient, foley, optional short natural speech). "
                f"Not silent."
            )[:5000]
        else:
            motion_prompt = (
                f"{visual_prompt}\n\n"
                f"Perform this as a {generate_duration}-second continuous ad. "
                f"Follow every timed beat — do not freeze on the opening frame. "
                f"Silent visuals — no speech, no music, no narrator."
            )[:5000]
        # Short marketing VO only for Higgsfield TTS path — Seedance uses native generate_audio.
        spoken = ""
        if sound_on and not use_byteplus:
            spoken = build_spoken_voiceover(
                visual_prompt, duration_seconds=generate_duration
            )
            if any(
                marker in spoken.lower()
                for marker in (
                    "clip 1",
                    "subject continuity",
                    "strict negative",
                    "timing beats",
                    "visual style",
                )
            ):
                spoken = ""

        if needs_seed:
            await update_job(job_id, progress="Creating seed frame…")
            seed_model = (
                "hf-text2image-soul-v2"
                if higgsfield_configured()
                else "openai-gpt-image-1-mini"
            )
            img_provider = get_image_provider(seed_model)
            seed_result = await img_provider.generate(
                prompt=seed_frame_prompt(visual_prompt),
                tenant_id=tenant_id,
                model=seed_model,
                format_type=format_type,
            )
            if (seed_result or {}).get("status") not in {"done", "mock"} or not (
                (seed_result or {}).get("url") or (seed_result or {}).get("remote_url")
            ):
                err = (seed_result or {}).get("error") or (
                    "Could not create seed image required by this video model."
                )
                await update_job(
                    job_id,
                    status="failed",
                    progress="Seed frame failed",
                    error=str(err)[:500],
                    result={"model": model, "provider": "higgsfield"},
                )
                return
            seed_url = str(
                (seed_result or {}).get("remote_url") or (seed_result or {}).get("url")
            )
            await update_job(
                job_id,
                progress="Seed ready — generating one continuous video…",
                result={"seed_image_url": seed_url},
            )

        provider_label = "BytePlus Seedance" if use_byteplus else "Higgsfield"
        await update_job(
            job_id,
            progress=(
                f"{provider_label} generating one {generate_duration}s video "
                f"(no stitch). Keep this tab open — polling in background…"
            ),
        )
        vid_provider = get_video_provider(model)
        # Seedance: native generate_audio follows sound_on only (no TTS spoken required).
        # Higgsfield: still needs spoken VO text when sound is on.
        if use_byteplus:
            skip_vo = not sound_on
        else:
            skip_vo = not sound_on or not spoken
        actual_product_name = str(data.get("product_name") or "the supplied product").strip()
        product_lock = (
            f"\n\nPRODUCT CINEMATOGRAPHY LOCK: Show {actual_product_name} exactly as in the "
            "attached product photo — same silhouette, proportions, stripe/colour, wheels, "
            "door, hardware and scale. Use wide hero, three-quarter, profile, feature-detail, "
            "tracking/orbit, usage and final hero views where appropriate. Never invent a "
            "generic substitute or redesign it."
            if data.get("product_reference_url")
            else ""
        )
        motion_prompt = (motion_prompt + product_lock)[:5000]
        motion_prompt = (
            motion_prompt[:4500]
            + "\n\nFINISHING LOCK: Generate clean footage without readable captions, title cards, "
            "logos, websites or CTA graphics. Exact campaign text, narration and the supplied "
            "brand logo are added deterministically after footage generation. Preserve suitable "
            "negative space for those overlays."
        )[:5000]
        brief = {
            "product_name": actual_product_name,
            "objective": "scene",
            "key_benefits": {},
            "video_duration_seconds": generate_duration,
            "higgsfield_voice_preset": "serene_female" if sound_on and spoken else "",
            "creative_studio_prompt": visual_prompt,
            "creative_studio_aspect": str(data.get("aspect") or "9/16"),
            "creative_studio_resolution": str(data.get("resolution") or "1080p"),
            "aspect": str(data.get("aspect") or "9/16"),
            "resolution": str(data.get("resolution") or "1080p"),
            # Do NOT put the visual prompt in video_script_skeleton — TTS would read it aloud.
            "creative_studio_mode": True,
            "skip_voiceover": skip_vo,
            "creative_studio_job_id": job_id,
            "seed_image_role": seed_image_role,
            "storyboard_image_urls": list(data.get("storyboard_image_urls") or [])[:9],
            "product_reference_url": str(data.get("product_reference_url") or "").strip() or None,
            "additional_reference_urls": list(data.get("additional_reference_urls") or [])[:7],
        }
        copy = {
            "hook": (spoken[:120] if spoken else ""),
            "headline": (spoken[:80] if spoken else ""),
            "body_copy": "",
            "cta": "",
            "hashtags": [],
        }
        if is_job_cancel_requested(job_id):
            await update_job(
                job_id,
                status="cancelled",
                progress="Stopped by user",
                error="Cancelled by user",
            )
            return
        if use_byteplus and generate_duration > 15:
            from app.services.file_service import file_service
            from app.services.ffmpeg_util import probe_video_duration
            from app.services.logo_overlay import file_url_to_local_path
            from app.services.media.seedance_multiscene import (
                concat_video_files,
                trim_video_to_duration,
            )

            segment_durations = _seedance_segment_durations(generate_duration)
            segment_paths: list[Path] = []
            segment_results: list[dict[str, Any]] = []
            partial_warning: str | None = None
            elapsed = 0
            continuity = (
                "\n\nCONTINUITY BIBLE: This is one chapter of the same film. "
                "Preserve the exact product geometry, stripe/colour, wheels, door, hardware, "
                "scale, character face, hairstyle, wardrobe, location and lighting from the "
                "approved references. Never redesign or substitute the product.\n"
            )
            for segment_index, segment_duration in enumerate(segment_durations):
                if is_job_cancel_requested(job_id):
                    await update_job(
                        job_id,
                        status="cancelled",
                        progress="Stopped by user",
                        error="Cancelled by user",
                    )
                    return
                segment_start = elapsed
                segment_end = elapsed + segment_duration
                segment_prompt = (
                    f"{motion_prompt}\n\n"
                    f"SEGMENT {segment_index + 1}/{len(segment_durations)} — "
                    f"TIMELINE {segment_start}-{segment_end}s of {generate_duration}s. "
                    f"Generate only this chapter for exactly {segment_duration}s. "
                    "Start with a purposeful continuation from the previous chapter and "
                    "end on a stable visual handoff to the next chapter. "
                    "Use a different motivated cinematic product view in this chapter when "
                    "the script allows: wide hero, three-quarter, profile, detail, orbit, "
                    "usage, or final hero. "
                    + continuity
                )[:5000]
                await update_job(
                    job_id,
                    progress=(
                        f"Seedance segment {segment_index + 1}/{len(segment_durations)} "
                        f"({segment_start}-{segment_end}s)…"
                    ),
                    result={
                        "requested_duration_seconds": generate_duration,
                        "segment_count": len(segment_durations),
                        "completed_segments": segment_index,
                    },
                )
                segment_result: dict[str, Any] = {}
                for attempt in range(2):
                    segment_result = await vid_provider.generate(
                        prompt=segment_prompt,
                        brief={
                            **brief,
                            "video_duration_seconds": segment_duration,
                            "creative_studio_prompt": segment_prompt,
                        },
                        copy=copy,
                        format_type=format_type,
                        model=model,
                        tenant_id=tenant_id,
                        source_image_url=seed_url if segment_index == 0 else None,
                        duration_seconds=segment_duration,
                    )
                    candidate_url = str(
                        (segment_result or {}).get("url")
                        or (segment_result or {}).get("remote_url")
                        or ""
                    ).strip()
                    if candidate_url or str(
                        (segment_result or {}).get("status") or ""
                    ) == "cancelled":
                        break
                    if attempt == 0:
                        await update_job(
                            job_id,
                            progress=(
                                f"Seedance segment {segment_index + 1} returned no media; "
                                "retrying once…"
                            ),
                        )
                segment_results.append(segment_result or {})
                if str((segment_result or {}).get("status") or "") == "cancelled":
                    await update_job(
                        job_id,
                        status="cancelled",
                        progress="Stopped by user",
                        error="Cancelled by user",
                    )
                    return
                segment_url = str(
                    (segment_result or {}).get("url")
                    or (segment_result or {}).get("remote_url")
                    or ""
                ).strip()
                segment_path = file_url_to_local_path(segment_url)
                if (
                    (not segment_path or not segment_path.is_file())
                    and segment_url.startswith(("http://", "https://"))
                ):
                    # Large provider videos may intentionally remain remote when they
                    # exceed MAX_UPLOAD_SIZE. Download them before concatenation.
                    import httpx
                    from app.services.media.runway_providers import _download_asset

                    async with httpx.AsyncClient(
                        timeout=300.0,
                        follow_redirects=True,
                    ) as download_client:
                        downloaded = await _download_asset(
                            download_client,
                            segment_url,
                            tenant_id=tenant_id,
                            kind="video",
                        )
                    segment_path = file_url_to_local_path(
                        str(downloaded.get("url") or "")
                    )
                if not segment_path or not segment_path.is_file():
                    partial_warning = (
                        f"Segment {segment_index + 1}/{len(segment_durations)} returned no "
                        "usable video after one retry. A partial video was preserved."
                    )
                    logger.error(
                        "%s Provider response: %r",
                        partial_warning,
                        segment_result,
                    )
                    break
                segment_paths.append(segment_path)
                elapsed = segment_end

            if not segment_paths:
                raise RuntimeError(
                    "Seedance returned no usable video segments after retry."
                )
            stitch_dir = Path(file_service.upload_dir) / tenant_id / "generated" / "seedance-stitch"
            stitch_dir.mkdir(parents=True, exist_ok=True)
            stitched_path = stitch_dir / f"creative-studio-{uuid.uuid4()}.mp4"
            concat_video_files(segment_paths, stitched_path)
            trimmed = trim_video_to_duration(stitched_path, float(generate_duration))
            final_path = trimmed or stitched_path
            actual_duration = probe_video_duration(final_path)
            saved = file_service.save_bytes(
                content=final_path.read_bytes(),
                tenant_id=tenant_id,
                subfolder="generated",
                suffix=".mp4",
                content_type="video/mp4",
            )
            result = {
                "status": "done",
                "model": str((segment_results[-1] or {}).get("model") or model),
                "provider": "byteplus",
                "url": saved["file_url"],
                "duration_seconds": (
                    int(round(actual_duration))
                    if actual_duration
                    else generate_duration
                ),
                "requested_duration_seconds": generate_duration,
                "segment_count": len(segment_paths),
                "partial": bool(partial_warning),
                "native_audio": sound_on,
                "storyboard": [motion_prompt],
                "note": (
                    f"Generated {len(segment_paths)} Seedance segments and stitched them "
                    f"into one {generate_duration}s cinematic video."
                    + (f" Warning: {partial_warning}" if partial_warning else "")
                ),
                "duration_warning": partial_warning,
                "voiceover": {
                    "status": "skipped",
                    "reason": "Seedance native audio" if sound_on else "Sound off",
                },
            }
        else:
            result = await vid_provider.generate(
                prompt=motion_prompt,
                brief=brief,
                copy=copy,
                format_type=format_type,
                model=model,
                tenant_id=tenant_id,
                source_image_url=seed_url,
                duration_seconds=generate_duration,
            )
        if (
            isinstance(result, dict)
            and result.get("status") == "done"
            and result.get("url")
        ):
            from app.services.creative_studio_video_finishing import (
                apply_timed_overlays,
                apply_timed_voiceover,
                extract_overlay_events,
                extract_voiceover_events,
            )
            from app.services.video_logo_overlay import apply_logo_overlay_to_video_file

            finishing_brief = str(data.get("source_brief") or visual_prompt or "")
            current_url = str(result["url"])
            voice_events = extract_voiceover_events(finishing_brief)
            overlay_events = extract_overlay_events(finishing_brief)

            if sound_on and voice_events:
                current_url, voiceover_result = await apply_timed_voiceover(
                    current_url,
                    voice_events,
                    tenant_id=tenant_id,
                )
                result["voiceover"] = voiceover_result
            elif sound_on:
                result["voiceover"] = {
                    "status": "skipped",
                    "reason": "No exact voiceover timing lines found in the source brief",
                }

            if overlay_events:
                current_url, overlays_applied = apply_timed_overlays(
                    current_url,
                    overlay_events,
                    tenant_id=tenant_id,
                )
                result["text_overlays_applied"] = overlays_applied
                result["text_overlay_count"] = len(overlay_events)

            logo_url = str(data.get("logo_reference_url") or "").strip()
            if logo_url:
                current_url, logo_applied = apply_logo_overlay_to_video_file(
                    current_url,
                    logo_url,
                    tenant_id=tenant_id,
                    format_type=format_type,
                    brief={
                        "creative_studio_aspect": str(data.get("aspect") or "9/16"),
                        "heygen_settings": {"brand_styled_overlay": True},
                    },
                )
                result["logo_applied"] = logo_applied
            result["url"] = current_url
        if is_job_cancel_requested(job_id) or str((result or {}).get("status") or "") == "cancelled":
            await update_job(
                job_id,
                status="cancelled",
                progress="Stopped by user",
                error="Cancelled by user",
                result={
                    "model": str((result or {}).get("model") or model),
                    "provider": (result or {}).get("provider"),
                    "task_id": (result or {}).get("task_id"),
                },
            )
            return
        _, credits = estimate_media_cost(
            provider=str((result or {}).get("provider") or "video"),
            model=model,
            duration_seconds=float(
                (result or {}).get("duration_seconds") or generate_duration or 15
            ),
        )
        out_warn = (result or {}).get("duration_warning") or duration_warning
        if (
            requested_duration > generate_duration
            and not out_warn
        ):
            out_warn = (
                f"Asked for {requested_duration}s — this model delivers ~{generate_duration}s. "
                "Use Seedance 2.0 (BytePlus) for up to 15s."
            )
        scene_count = (result or {}).get("scene_count")
        stitch_note = (
            f"Stitched {scene_count} short clips into one video."
            if scene_count and int(scene_count) > 1
            else "One continuous video."
        )
        if use_byteplus:
            if (result or {}).get("segment_count"):
                stitch_note = (
                    f"BytePlus Dreamina Seedance 2.0 — stitched "
                    f"{int((result or {}).get('segment_count'))} cinematic segments."
                )
            else:
                stitch_note = "BytePlus Dreamina Seedance 2.0 — one continuous clip."
        if out_warn:
            stitch_note += f" Warning: {out_warn}"
        if sound_on:
            stitch_note += " Native audio requested."
            voice_status = str(
                ((result or {}).get("voiceover") or {}).get("status") or ""
            )
            if voice_status == "done":
                stitch_note += " Exact timed voiceover mixed."
            elif voice_status:
                stitch_note += f" Voiceover {voice_status}."
        else:
            stitch_note += " Sound off — silent video."
        if (result or {}).get("text_overlays_applied"):
            stitch_note += (
                f" {(result or {}).get('text_overlay_count') or 0} exact timed text "
                "overlay(s) applied."
            )
        if (result or {}).get("logo_applied"):
            stitch_note += " Brand logo applied."
        status = str((result or {}).get("status") or "failed")
        await update_job(
            job_id,
            status=status if status in {"done", "mock", "failed"} else "failed",
            progress="Done" if status in {"done", "mock"} else "Failed",
            error=(result or {}).get("error"),
            result={
                "url": (result or {}).get("url"),
                "model": str((result or {}).get("model") or model),
                "provider": (result or {}).get("provider"),
                "seed_image_url": seed_url,
                "duration_seconds": (result or {}).get("duration_seconds")
                or generate_duration,
                "requested_duration_seconds": requested_duration,
                "segment_count": (result or {}).get("segment_count"),
                "partial": bool((result or {}).get("partial")),
                "credits_estimate": credits or None,
                "duration_warning": str(out_warn) if out_warn else None,
                "note": stitch_note,
                "voiceover": (result or {}).get("voiceover"),
                "text_overlays_applied": bool(
                    (result or {}).get("text_overlays_applied")
                ),
                "text_overlay_count": (result or {}).get("text_overlay_count"),
                "logo_applied": bool((result or {}).get("logo_applied")),
            },
        )
    except Exception as exc:
        logger.exception("Creative Studio job %s failed", job_id)
        await update_job(
            job_id,
            status="failed",
            progress="Failed",
            error=str(exc)[:500],
        )
