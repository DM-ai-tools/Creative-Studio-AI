"""In-memory Creative Studio jobs — avoid HTTP timeouts on long Higgsfield stitches."""

from __future__ import annotations

import asyncio
import logging
import math
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
        from app.services.file_service import file_service

        # Image/video providers can charge before returning bytes. Prove that
        # the completed media can be persisted before submitting any paid task.
        file_service.assert_writable(tenant_id, "generated")
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
            brand_name = str(data.get("brand_name") or "").strip()
            character_ref: str | None = None
            for asset in data.get("reference_assets") or []:
                if not isinstance(asset, dict):
                    continue
                if str(asset.get("role") or "").strip().lower() == "character":
                    character_ref = str(asset.get("url") or "").strip() or None
                    break
            provider = get_image_provider(model)
            frames: list[dict[str, Any]] = []
            total = min(6, len(scenes_in))
            style_anchor: str | None = None
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

                contains_person = bool(re.search(
                    r"(?i)\b(?:person|people|woman|man|adult|homeowner|customer|worker|staff|presenter|talent|creator|actor)\b",
                    f"{title} {sp}",
                ))
                # A person/scene anchor takes priority for identity and natural
                # continuity. Product geometry remains locked in the text when
                # the image API offers only one reference slot.
                ref_url = None
                ref_purpose = "style"
                if contains_person and character_ref:
                    ref_url = character_ref
                    ref_purpose = "character"
                elif contains_person and style_anchor:
                    ref_url = style_anchor
                    ref_purpose = "style"
                elif bool(product_ref) and wants:
                    ref_url = product_ref
                    ref_purpose = "product"
                elif style_anchor:
                    ref_url = style_anchor
                    ref_purpose = "style"
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
                    if not re.search(r"(?i)cast continuity", sp):
                        sp = (
                            f"{sp} CAST CONTINUITY: keep the same person identity, face, hair, "
                            "and wardrobe when people appear — do not swap models between scenes."
                        )
                if brand_name:
                    sp = (
                        f"{sp} Keep all screens, clothing, cartons, signs and packaging clean "
                        "and unbranded. Verified brand artwork is composited after generation."
                    )

                res = await provider.generate(
                    prompt=sp[:2200],
                    tenant_id=tenant_id,
                    model=model,
                    format_type=format_type,
                    reference_image_url=ref_url,
                    reference_purpose=ref_purpose,
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
                if frame.get("url") and not style_anchor:
                    style_anchor = str(frame["url"])
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
            # The first approved scene is the opening seed. Product hero frames
            # remain available in the board but must never replace the story opening.

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
        if use_byteplus and requested_duration > 120:
            raise ValueError(
                "Creative Studio Seedance long-video mode supports up to 120 seconds. "
                "Choose 2m or shorter."
            )
        sound_on = bool(data.get("sound_on", True))
        from app.core.config import settings
        from app.services.creative_studio_video_finishing import extract_voiceover_events, voiceover_requested
        from app.services.creative_studio_timeline import (
            segment_motion_prompt, validate_video_prompt, explicit_shot_windows,
            select_complete_timeline_prompt,
        )

        finishing_brief = str(data.get("source_brief") or visual_prompt or "")
        if use_byteplus and requested_duration > 15:
            # The user's timed brief is authoritative. A later planning rewrite
            # can round its final timestamp (for example 26s to 25s/30s); choose
            # the candidate that actually covers the requested duration.
            visual_prompt = select_complete_timeline_prompt(
                finishing_brief,
                visual_prompt,
                total=requested_duration,
            )
        voice_events = extract_voiceover_events(
            finishing_brief, duration_seconds=requested_duration
        )
        if sound_on and not voice_events:
            voice_events = extract_voiceover_events(
                visual_prompt, duration_seconds=requested_duration
            )
        if sound_on and not voice_events:
            from app.services.creative_studio_video_finishing import plan_requested_voiceover

            try:
                voice_events = await plan_requested_voiceover(
                    finishing_brief, duration_seconds=requested_duration
                )
            except Exception:
                logger.exception("Narration planning failed; requesting native narration")
        prepared_narration = None
        narration_fallback = False
        timed_tts = bool(sound_on and voice_events)
        if timed_tts:
            from app.services.creative_studio_video_finishing import normalize_voiceover_windows

            voice_events = normalize_voiceover_windows(
                voice_events, duration_seconds=requested_duration,
            )
        from app.services.creative_studio_preflight import validate_video_preflight
        preflight_report = validate_video_preflight(
            prompt=visual_prompt,
            duration_seconds=requested_duration,
            storyboard_image_urls=list(data.get("storyboard_image_urls") or []),
            seed_image_url=seed_url,
            sound_on=sound_on,
            voice_events=voice_events,
            reference_assets=list(data.get("reference_assets") or []),
            product_reference_url=str(data.get("product_reference_url") or "").strip() or None,
            logo_reference_url=str(data.get("logo_reference_url") or "").strip() or None,
        )
        await update_job(
            job_id,
            progress=(
                f"Preflight passed — {preflight_report['scene_count']} timed scene(s), "
                f"{preflight_report['storyboard_count']} approved frame(s)…"
            ),
            result={"preflight": preflight_report},
        )
        if timed_tts:
            from app.services.creative_studio_speech import prepare_narration

            await update_job(job_id, progress="Preparing exact OpenAI narration before video generation…")
            try:
                prepared_narration = await prepare_narration(
                    voice_events, tenant_id=tenant_id, brief=finishing_brief,
                )
            except (ValueError, RuntimeError, OSError) as exc:
                if use_byteplus:
                    logger.warning(
                        "TTS preflight failed for Seedance; using native audio instead: %s",
                        exc,
                    )
                    timed_tts = False
                    prepared_narration = None
                    narration_fallback = True
                else:
                    raise
        if use_byteplus:
            from app.services.creative_studio_picture import compile_picture_prompt
            visual_prompt = compile_picture_prompt(visual_prompt, duration=requested_duration)
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
        # An approved still is always the exact opening composition. Multi-beat
        # motion is driven by the timed prompt and additional storyboard refs;
        # it must not weaken the approved opening into a generic style reference.

        if sound_on:
            motion_prompt = (
                f"{visual_prompt}\n\n"
                f"Perform this as a {generate_duration}-second continuous ad. "
                f"Follow every timed beat — do not freeze on the opening frame. "
                f"AUDIO ON: native diegetic sound (ambient, foley, optional short natural speech). "
                f"Not silent."
            )
        else:
            motion_prompt = (
                f"{visual_prompt}\n\n"
                f"Perform this as a {generate_duration}-second continuous ad. "
                f"Follow every timed beat — do not freeze on the opening frame. "
                f"Silent visuals — no speech, no music, no narrator."
            )
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
        # A long video is generated as independent Seedance tasks. Letting each task
        # synthesize speech can change narrator identity at every seam. When exact
        # timed narration has been prepared, keep every provider clip silent and mix
        # the single locked voice across the completed timeline in post-production.
        if use_byteplus:
            skip_vo = not sound_on or timed_tts
        else:
            skip_vo = not sound_on or not spoken
        actual_product_name = str(data.get("product_name") or "the supplied product").strip()
        product_lock = (
            "\n\nPRODUCT CINEMATOGRAPHY LOCK: Show the supplied product exactly as in the "
            "attached product photo — same silhouette, proportions, colour, materials "
            "and scale. Use wide hero, three-quarter, profile, feature-detail, "
            "tracking/orbit, usage and final hero views where appropriate. Never invent a "
            "generic substitute or redesign it."
            if data.get("product_reference_url")
            else ""
        )
        motion_prompt = motion_prompt + product_lock
        motion_prompt = (
            motion_prompt
            + "\n\nFINISHING LOCK: Generate clean footage without readable captions, title cards, "
            "logos, websites or CTA graphics. Supported timed campaign text and the supplied "
            "brand logo are added after footage generation. Preserve suitable "
            "negative space for those overlays."
        )
        from app.services.creative_studio_picture import brand_surface_lock

        if "BRAND-SURFACE LOCK:" not in motion_prompt:
            motion_prompt += "\n\n" + brand_surface_lock()
        if sound_on and timed_tts:
            for _, _, line in voice_events:
                motion_prompt = motion_prompt.replace(line, "[Narration supplied in post-production]")
            motion_prompt += (
                "\nAUDIO: Generate ambience and foley only. NO speech, dialogue or narration; "
                "the exact voiceover is mixed separately. Never read production directions aloud."
            )
        elif sound_on and voice_events:
            motion_prompt += "\nAUDIO: Speak only the exact labelled narration at its specified times. Never read production directions.\n"
        elif sound_on and voiceover_requested(finishing_brief):
            motion_prompt += (
                "\nAUDIO: Include a short natural voiceover relevant to the scene and campaign. "
                "Do not read camera directions, scene labels, or production instructions."
            )
        def native_narration(start: float, end: float) -> str:
            if not sound_on or timed_tts:
                return ""
            return "\n".join(
                f'Voiceover, {max(a, start) - start:g}–{min(b, end) - start:g} seconds: "{line}"'
                for a, b, line in voice_events if a < end and b > start
            )
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
            # Lock narration in post while retaining Seedance ambience and foley.
            "creative_studio_generate_audio": bool(sound_on),
            "creative_studio_job_id": job_id,
            "seed_image_role": seed_image_role,
            "storyboard_image_urls": list(data.get("storyboard_image_urls") or [])[:9],
            "product_reference_url": str(data.get("product_reference_url") or "").strip() or None,
            "additional_reference_urls": list(data.get("additional_reference_urls") or [])[:7],
            "reference_assets": list(data.get("reference_assets") or []),
            "strict_character_reference": any(
                isinstance(asset, dict)
                and asset.get("role") == "character"
                and str(asset.get("url") or "").strip()
                for asset in data.get("reference_assets") or []
            ),
            "logo_reference_url": str(data.get("logo_reference_url") or "").strip() or None,
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
        shot_windows = explicit_shot_windows(motion_prompt, total=generate_duration) if use_byteplus else []
        # Keep short multi-shot ads in one model context for product/cast continuity.
        if use_byteplus and generate_duration > 15:
            from app.services.file_service import file_service
            from app.services.ffmpeg_util import probe_video_duration
            from app.services.logo_overlay import file_url_to_local_path
            from app.services.media.seedance_multiscene import (
                build_continuity_contract,
                coalesce_shot_windows,
                concat_video_files,
                conform_shot_duration,
                save_continuity_frame,
                save_privacy_safe_scene_frame,
                trim_video_to_duration,
            )

            storyboard_urls = [
                str(url or "").strip()
                for url in brief.get("storyboard_image_urls") or []
                if str(url or "").strip()
            ]
            # When every authored scene has an approved storyboard frame, animate
            # each exact scene from its own frame. Packing unrelated locations into
            # one 15s call causes skipped beats, replacement actors and invented
            # branding. If coverage is incomplete, retain chapter grouping and
            # final-frame continuity as the safer fallback.
            exact_storyboard_mode = bool(
                shot_windows and len(storyboard_urls) >= len(shot_windows)
            )
            chapter_windows = (
                list(shot_windows)
                if exact_storyboard_mode
                else coalesce_shot_windows(shot_windows, 15) if shot_windows else []
            )
            segment_durations = [b - a for a, b in chapter_windows] or _seedance_segment_durations(
                generate_duration
            )
            generated_seconds = 0
            segment_paths: list[Path] = []
            segment_results: list[dict[str, Any]] = []
            partial_warning: str | None = None
            continuity_reference_url: str | None = None
            cast_reference_url: str | None = None
            continuity_frame_count = 0
            continuity_privacy_fallback_count = 0
            elapsed = 0
            # Preflight every chapter before submitting any billable provider task.
            segment_prompts: list[str] = []
            offset = 0
            for segment_index, seconds in enumerate(segment_durations):
                local_prompt = segment_motion_prompt(
                    motion_prompt, start=offset, end=offset + seconds, total=generate_duration
                )
                # Timeline slicing keeps only the current authored beat. Repeat
                # the brand invariant on every billable scene request so it can
                # never be lost with another global finishing section.
                if "BRAND-SURFACE LOCK:" not in local_prompt:
                    local_prompt += "\n\n" + brand_surface_lock()
                # Validate the complete first-pass prompt for every chapter before
                # submitting any billable task. Continuation instructions are short
                # and use this already validated chapter prompt as their base.
                validate_video_prompt(
                    local_prompt + "\n" + native_narration(offset, offset + seconds)
                    + build_continuity_contract(
                        segment_index=segment_index,
                        segment_count=len(segment_durations),
                        start=offset,
                        end=offset + seconds,
                        total_duration=generate_duration,
                        has_previous_frame=segment_index > 0 and not exact_storyboard_mode,
                    )
                    + (
                        f"\nComplete this shot's action within the first {seconds:g}s; "
                        f"hold the final composition for the remaining {max(4, math.ceil(seconds)) - seconds:g}s. "
                        "The extra tail is removed in editing."
                        if seconds < 4 or seconds != int(seconds) else ""
                    )
                )
                segment_prompts.append(local_prompt)
                offset += seconds
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
                chapter_storyboard_urls: list[str] = []
                if storyboard_urls:
                    board_index = next(
                        (
                            index for index, (shot_start, _) in enumerate(shot_windows)
                            if abs(float(shot_start) - float(segment_start)) <= 0.05
                        ),
                        min(len(storyboard_urls) - 1, segment_index),
                    )
                    board_index = min(len(storyboard_urls) - 1, board_index)
                    chapter_storyboard_urls = [storyboard_urls[board_index]]
                if exact_storyboard_mode and chapter_storyboard_urls:
                    # A scene's approved frame is its authoritative opening. Do
                    # not let the previous scene's handoff displace this frame.
                    continuity_reference_url = None
                    cast_reference_url = None
                chapter_remaining = float(segment_duration)
                chapter_elapsed = 0.0
                chapter_complete = False
                # The provider minimum is four seconds. Allow a small number of
                # extra continuations for unexpectedly short but valid media while
                # bounding provider spend if a task repeatedly returns tiny clips.
                max_parts = max(2, math.ceil(float(segment_duration) / 4.0) + 2)
                for continuation_index in range(max_parts):
                    if chapter_remaining <= 0.08:
                        chapter_complete = True
                        break
                    if is_job_cancel_requested(job_id):
                        await update_job(
                            job_id,
                            status="cancelled",
                            progress="Stopped by user",
                            error="Cancelled by user",
                        )
                        return

                    part_start = segment_start + chapter_elapsed
                    provider_duration = max(4, min(15, math.ceil(chapter_remaining)))
                    continuation_instruction = ""
                    if continuation_index:
                        continuation_instruction = (
                            "\n\nCONTINUATION PASS: The attached CONTINUITY FRAME is the exact "
                            "last frame already generated for this chapter. Continue forward from "
                            f"global {part_start:g}s through {segment_end:g}s. Do not replay, recap, "
                            "freeze, or slow down earlier action. Keep natural real-time motion and "
                            "complete only the remaining authored action."
                        )
                    segment_prompt = validate_video_prompt(
                        segment_prompts[segment_index]
                        + "\n"
                        + native_narration(part_start, segment_end)
                        + build_continuity_contract(
                            segment_index=segment_index,
                            segment_count=len(segment_durations),
                            start=part_start,
                            end=segment_end,
                            total_duration=generate_duration,
                            has_previous_frame=bool(continuity_reference_url),
                        )
                        + continuation_instruction
                        + (
                            f"\nComplete the remaining action within the first {chapter_remaining:g}s; "
                            f"hold the final composition for the remaining "
                            f"{provider_duration - chapter_remaining:g}s. The extra tail is removed in editing."
                            if chapter_remaining < 4 or chapter_remaining != int(chapter_remaining)
                            else ""
                        )
                    )
                    await update_job(
                        job_id,
                        progress=(
                            f"Seedance chapter {segment_index + 1}/{len(segment_durations)}, "
                            f"part {continuation_index + 1} "
                            f"({part_start:g}-{segment_end:g}s remaining)…"
                        ),
                        result={
                            "requested_duration_seconds": generate_duration,
                            "segment_count": len(segment_durations),
                            "completed_segments": segment_index,
                            "generated_clips": len(segment_paths),
                        },
                    )

                    segment_result: dict[str, Any] = {}
                    source_path: Path | None = None
                    use_privacy_safe_handoff = False
                    for attempt in range(2):
                        attempt_prompt = segment_prompt
                        # The official logo is reserved for deterministic finishing.
                        # Giving it to Seedance encourages approximate badges and
                        # wordmarks on clothing, boxes and signs.
                        attempt_reference_assets = [
                            asset for asset in (brief.get("reference_assets") or [])
                            if not (
                                isinstance(asset, dict)
                                and str(asset.get("role") or "").strip().lower() == "logo"
                            )
                        ]
                        attempt_cast_reference_url = cast_reference_url
                        attempt_continuity_reference_url = continuity_reference_url
                        attempt_strict_continuity = bool(continuity_reference_url)
                        if use_privacy_safe_handoff:
                            safe_handoff_url = save_privacy_safe_scene_frame(
                                segment_paths[-1], tenant_id=tenant_id,
                            )
                            attempt_reference_assets = [
                                asset for asset in attempt_reference_assets
                                if not (
                                    isinstance(asset, dict)
                                    and str(asset.get("role") or "").lower() == "character"
                                )
                            ]
                            attempt_reference_assets.append(
                                {"url": safe_handoff_url, "role": "scene"}
                            )
                            attempt_cast_reference_url = None
                            attempt_continuity_reference_url = None
                            attempt_strict_continuity = False
                            attempt_prompt += (
                                "\n\nPRIVACY-SAFE HANDOFF: BytePlus rejected the full photoreal "
                                "handoff frame. The attached SCENE reference is a lower-frame crop. "
                                "Use it only to preserve product position, wardrobe colours, props, "
                                "lighting, camera direction and set geometry. Continue the same "
                                "written character and action forward without replaying earlier action."
                            )
                            continuity_privacy_fallback_count += 1

                        segment_result = await vid_provider.generate(
                            prompt=attempt_prompt,
                            brief={
                                **brief,
                                "logo_reference_url": None,
                                "video_duration_seconds": provider_duration,
                                "creative_studio_prompt": attempt_prompt,
                                "storyboard_image_urls": chapter_storyboard_urls,
                                "reference_assets": attempt_reference_assets,
                                "cast_reference_url": attempt_cast_reference_url,
                                "continuity_reference_url": attempt_continuity_reference_url,
                                "strict_continuity_reference": attempt_strict_continuity,
                            },
                            copy=copy,
                            format_type=format_type,
                            model=model,
                            tenant_id=tenant_id,
                            source_image_url=(
                                chapter_storyboard_urls[0]
                                if chapter_storyboard_urls and continuation_index == 0
                                else seed_url
                                if segment_index == 0 and continuation_index == 0
                                else None
                            ),
                            duration_seconds=provider_duration,
                        )
                        generated_seconds += provider_duration
                        segment_results.append(segment_result or {})
                        if str((segment_result or {}).get("status") or "") == "cancelled":
                            await update_job(
                                job_id,
                                status="cancelled",
                                progress="Stopped by user",
                                error="Cancelled by user",
                            )
                            return
                        if (segment_result or {}).get("retryable") is False:
                            raise RuntimeError(
                                str((segment_result or {}).get("error") or "Seedance request failed")
                            )
                        segment_url = str(
                            (segment_result or {}).get("url")
                            or (segment_result or {}).get("remote_url")
                            or ""
                        ).strip()
                        source_path = file_url_to_local_path(segment_url)
                        if (
                            (not source_path or not source_path.is_file())
                            and segment_url.startswith(("http://", "https://"))
                        ):
                            # Large provider videos may remain remote. Download the
                            # successful task output; never resubmit merely because the
                            # first local storage attempt failed.
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
                            source_path = file_url_to_local_path(
                                str(downloaded.get("url") or "")
                            )
                        if source_path and source_path.is_file():
                            break
                        if segment_url:
                            # The provider task succeeded. Do not create and charge
                            # another generation just because its media could not be
                            # persisted locally; preserve a partial result instead.
                            break
                        if attempt == 0:
                            provider_error = str((segment_result or {}).get("error") or "")
                            privacy_blocked = bool(continuity_reference_url) and (
                                "previous chapter's continuity frame" in provider_error.lower()
                                or "privacy" in provider_error.lower()
                                or "real person" in provider_error.lower()
                            )
                            if privacy_blocked and not brief.get("strict_character_reference"):
                                use_privacy_safe_handoff = True
                                await update_job(
                                    job_id,
                                    progress=(
                                        "BytePlus blocked the photoreal face handoff; retrying "
                                        "with a product/scene continuity crop…"
                                    ),
                                )
                            else:
                                await update_job(
                                    job_id,
                                    progress=(
                                        f"Seedance chapter {segment_index + 1}, part "
                                        f"{continuation_index + 1} returned no media; retrying once…"
                                    ),
                                )

                    if not source_path or not source_path.is_file():
                        partial_warning = (
                            f"Chapter {segment_index + 1}/{len(segment_durations)}, part "
                            f"{continuation_index + 1} returned no usable video. "
                            "A partial video was preserved."
                        )
                        logger.error(
                            "%s Provider response: %r",
                            partial_warning,
                            segment_result,
                        )
                        break

                    actual_part_duration = probe_video_duration(source_path)
                    if actual_part_duration is None or actual_part_duration <= 0.1:
                        partial_warning = (
                            f"Chapter {segment_index + 1}/{len(segment_durations)}, part "
                            f"{continuation_index + 1} had no measurable video duration. "
                            "A partial video was preserved."
                        )
                        logger.error("%s", partial_warning)
                        break
                    usable_duration = min(float(actual_part_duration), chapter_remaining)
                    edit_dir = Path(file_service.upload_dir) / tenant_id / "generated" / "shot-edits"
                    segment_path = conform_shot_duration(
                        source_path,
                        edit_dir / f"{job_id}-{segment_index}-{continuation_index}.mp4",
                        usable_duration,
                    )
                    segment_paths.append(segment_path)
                    chapter_elapsed += usable_duration
                    chapter_remaining = max(0.0, float(segment_duration) - chapter_elapsed)

                    needs_handoff = (
                        chapter_remaining > 0.08
                        or (
                            segment_index + 1 < len(segment_durations)
                            and not exact_storyboard_mode
                        )
                    )
                    if needs_handoff:
                        continuity_reference_url = save_continuity_frame(
                            segment_path,
                            tenant_id=tenant_id,
                        )
                        if cast_reference_url is None and not brief.get("strict_character_reference"):
                            cast_reference_url = continuity_reference_url
                        continuity_frame_count += 1
                    if chapter_remaining <= 0.08:
                        chapter_complete = True
                        break

                    await update_job(
                        job_id,
                        progress=(
                            f"Provider returned {actual_part_duration:.1f}s; continuing the missing "
                            f"{chapter_remaining:.1f}s at normal speed…"
                        ),
                        result={
                            "requested_duration_seconds": generate_duration,
                            "segment_count": len(segment_durations),
                            "completed_segments": segment_index,
                            "generated_clips": len(segment_paths),
                            "continuity_chained": True,
                        },
                    )

                if not chapter_complete:
                    if partial_warning is None:
                        partial_warning = (
                            f"Chapter {segment_index + 1}/{len(segment_durations)} remained "
                            f"{chapter_remaining:.1f}s short after {max_parts} continuation parts. "
                            "A partial video was preserved."
                        )
                    break
                elapsed = segment_end

            if not segment_paths:
                raise RuntimeError(
                    "Seedance returned no usable video segments after retry."
                )
            if len(segment_paths) == 1:
                # A later chapter may fail after a usable first chapter was
                # generated. Preserve that partial result directly instead of
                # copying it through the transient stitching directory.
                final_path = segment_paths[0]
            else:
                stitch_dir = (
                    Path(file_service.upload_dir) / tenant_id / "generated" / "seedance-stitch"
                ).resolve()
                stitch_dir.mkdir(parents=True, exist_ok=True)
                # Keep the final path comfortably below legacy Windows MAX_PATH.
                # Deep OneDrive checkouts plus the old descriptive UUID filename
                # exceeded 260 characters after FFmpeg had already written the file,
                # causing Python's validation to report a false stitching failure.
                stitched_path = stitch_dir / f"cs-{job_id[:12]}.mp4"
                concat_video_files(segment_paths, stitched_path)
                if not stitched_path.is_file():
                    raise RuntimeError("Seedance stitching completed without an output file")
                trimmed = trim_video_to_duration(stitched_path, float(generate_duration))
                final_path = trimmed or stitched_path
            actual_duration = probe_video_duration(final_path)
            if not final_path.is_file():
                raise RuntimeError("Seedance produced no readable final video file")
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
                "generated_duration_seconds": generated_seconds,
                "continuity_chained": continuity_frame_count > 0,
                "continuity_frame_count": continuity_frame_count,
                "continuity_privacy_fallback_count": continuity_privacy_fallback_count,
                "storyboard_scene_anchored": exact_storyboard_mode,
                "partial": bool(partial_warning),
                "audio_requested": sound_on,
                "provider_usage": [
                    usage for r in segment_results for usage in (r.get("provider_usage") or [])
                ],
                "storyboard": [motion_prompt],
                "note": (
                    f"Generated {len(segment_paths)} Seedance segments and stitched them "
                    f"into one {generate_duration}s cinematic video."
                    + (
                        " BytePlus privacy-safe scene continuity was used after a photoreal "
                        "handoff rejection."
                        if continuity_privacy_fallback_count else ""
                    )
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
                prompt=validate_video_prompt(motion_prompt + "\n" + native_narration(0, generate_duration)),
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
            result["preflight"] = preflight_report
            from app.services.creative_studio_video_finishing import (
                apply_timed_overlays,
                apply_timed_voiceover,
                extract_overlay_events,
                extract_voiceover_events,
            )
            from app.services.video_logo_overlay import apply_logo_overlay_to_video_file

            finishing_brief = str(data.get("source_brief") or visual_prompt or "")
            current_url = str(result["url"])
            overlay_events = extract_overlay_events(finishing_brief)

            if timed_tts:
                try:
                    current_url, voiceover_result = await apply_timed_voiceover(
                        current_url, voice_events, tenant_id=tenant_id,
                        prepared_narration=prepared_narration,
                        allow_time_stretch=not bool(re.search(
                            r"(?i)rather than mechanically speeding|(?:do not|no|without)\s+(?:mechanical(?:ly)?\s+)?(?:speed(?:ing)?|time[- ]stretch)",
                            finishing_brief,
                        )),
                    )
                except Exception as exc:
                    logger.exception("Creative Studio narration finishing failed")
                    voiceover_result = {"status": "failed", "error": str(exc)[:300]}
                result["voiceover"] = voiceover_result
                if voiceover_result.get("status") != "done":
                    result["audio_warning"] = "Requested narration could not be mixed: " + str(
                        voiceover_result.get("error") or voiceover_result.get("reason")
                    )
            elif sound_on and voice_events:
                result["voiceover"] = {
                    "status": "native_requested",
                    "reason": "Exact narration sent to Seedance; dedicated TTS is not configured",
                }
            elif sound_on:
                result["voiceover"] = {
                    "status": "skipped",
                    "reason": "No exact voiceover timing lines found in the source brief",
                }

            if overlay_events:
                from app.services.creative_studio_picture import compose_campaign_graphics
                current_url, overlays_applied = compose_campaign_graphics(
                    current_url, overlay_events, tenant_id=tenant_id,
                    logo_url=str(data.get("logo_reference_url") or "").strip() or None,
                )
                result["text_overlays_applied"] = overlays_applied
                result["text_overlay_count"] = len(overlay_events)
                result["logo_applied"] = bool(data.get("logo_reference_url") and overlays_applied)
            if timed_tts and (result.get("voiceover") or {}).get("status") != "done":
                mix_error = result.get("audio_warning") or "Required narration finishing failed"
                result["audio_warning"] = mix_error
                if not (use_byteplus and result.get("url")):
                    result["status"] = "failed"
                    result["error"] = mix_error
            if narration_fallback:
                # This is a supported continuation path: the exact labelled lines and
                # timings remain in the Seedance prompt, so a separate TTS failure must
                # not turn a completed video into a persistent user-facing error.
                result["voiceover"] = {
                    "status": "native",
                    "provider": "seedance",
                }
            result["url"] = current_url
            from app.services.ffmpeg_util import probe_has_audio
            from app.services.video_subtitles import _ensure_local_video

            audio_path = _ensure_local_video(current_url, tenant_id=tenant_id)
            has_audio = probe_has_audio(audio_path) if audio_path else None
            result["audio_present"] = has_audio
            if sound_on and has_audio is not True:
                missing_audio = (
                    "The generated video has no audio track. Requested voiceover/audio is missing."
                    if has_audio is False else "Could not verify the final video's audio track."
                )
                existing = str(result.get("audio_warning") or "").strip()
                result["audio_warning"] = (
                    f"{existing} {missing_audio}".strip() if existing else missing_audio
                )
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
                if (result or {}).get("continuity_chained"):
                    stitch_note += (
                        f" Character and scene continuity chained through "
                        f"{(result or {}).get('continuity_frame_count') or 0} final-frame handoffs."
                    )
                if (result or {}).get("continuity_privacy_fallback_count"):
                    stitch_note += (
                        " BytePlus rejected a photoreal face handoff, so the affected chapter "
                        "used a privacy-safe product/scene continuity crop."
                    )
                if (result or {}).get("generated_duration_seconds"):
                    stitch_note += (
                        f" Provider minimums require {result['generated_duration_seconds']} generated "
                        f"seconds, edited to the {requested_duration}s timeline."
                    )
            else:
                stitch_note = "BytePlus Dreamina Seedance 2.0 — one continuous clip."
        if out_warn:
            stitch_note += f" Warning: {out_warn}"
        if sound_on:
            stitch_note += " Native audio requested."
            if (result or {}).get("audio_warning"):
                stitch_note += " Warning: " + str(result["audio_warning"])
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
        provider_usage = (result or {}).get("provider_usage") or []
        if provider_usage:
            measured_tokens = sum(int(u.get("total_tokens") or u.get("completion_tokens") or 0) for u in provider_usage)
            stitch_note += (
                f" Provider-reported video tokens: {measured_tokens:,}."
                " Exact USD charge is unavailable in the task response; check BytePlus billing."
            )
        status = str((result or {}).get("status") or "failed")
        await update_job(
            job_id,
            status=status if status in {"done", "mock", "failed"} else "failed",
            progress=("Completed with audio warnings" if (result or {}).get("audio_warning") else "Done")
            if status in {"done", "mock"} else "Failed",
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
                "continuity_chained": bool((result or {}).get("continuity_chained")),
                "continuity_frame_count": (result or {}).get("continuity_frame_count"),
                "continuity_privacy_fallback_count": (
                    result or {}
                ).get("continuity_privacy_fallback_count"),
                "storyboard_scene_anchored": bool(
                    (result or {}).get("storyboard_scene_anchored")
                ),
                "partial": bool((result or {}).get("partial")),
                "credits_estimate": credits or None,
                "duration_warning": str(out_warn) if out_warn else None,
                "note": stitch_note,
                "voiceover": (result or {}).get("voiceover"),
                "audio_present": (result or {}).get("audio_present"),
                "audio_warning": (result or {}).get("audio_warning"),
                "provider_usage": (result or {}).get("provider_usage"),
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
