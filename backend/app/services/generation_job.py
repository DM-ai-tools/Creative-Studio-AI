"""Background brief → variant generation (survives client disconnect / proxy timeouts)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.core.database import AsyncSessionLocal
from app.models.variant import Variant
from app.schemas.brief import GenerationRequest
from app.services.ai_service import ai_service
from app.services.brand_prompt import brand_snapshot, build_image_prompt, enrich_brief_with_brand
from app.services.brand_service import BrandService
from app.services.brief_service import BriefService
from app.services.cta_defaults import resolve_campaign_cta
from app.services.icp_image_plan_service import (
    _billboard_words,
    _related_image_lines,
    enforce_on_image_copy_in_prompt,
)
from app.services.video_duration import (
    apply_video_settings_to_brief,
    requested_video_duration_seconds,
    resolve_video_duration_seconds,
)

logger = logging.getLogger(__name__)


def _slot_has_saved_plan(slot: dict[str, Any] | None) -> bool:
    """True when the brief stores user/AI variant fields that must drive generation."""
    if not isinstance(slot, dict):
        return False
    return bool(
        str(slot.get("prompt") or "").strip()
        or str(slot.get("hook") or "").strip()
        or str(slot.get("message") or "").strip()
        or str(slot.get("offer") or "").strip()
        or str(slot.get("image_hook") or "").strip()
        or str(slot.get("image_headline") or "").strip()
        or str(slot.get("cta") or "").strip()
    )


def _copy_from_image_slot(slot: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    """Build feed copy + on-image lines from a saved image_variants slot."""
    hook = str(slot.get("hook") or "").strip()
    message = str(slot.get("message") or "").strip()
    offer = str(slot.get("offer") or "").strip()
    cta = str(slot.get("cta") or "").strip()
    image_hook = str(slot.get("image_hook") or "").strip()
    image_headline = str(slot.get("image_headline") or "").strip()
    derived_hook, derived_headline = _related_image_lines(hook, message)
    on_image_hook = _billboard_words(image_hook, 6) or derived_hook
    on_image_headline = _billboard_words(image_headline, 8) or derived_headline
    copy = {
        "hook": hook,
        "headline": message,
        "body_copy": offer,
        "cta": cta,
        "hashtags": [],
    }
    return copy, on_image_hook, on_image_headline


async def run_brief_generation_job(
    *,
    brief_id: UUID,
    tenant_id: UUID,
    request_data: dict[str, Any],
) -> None:
    """Run HeyGen / media generation outside the HTTP request lifecycle.

    Railway and browsers often drop long-lived `/generate` connections (network error)
    while HeyGen is still rendering. Keeping work in this job lets the brief stay RUNNING
    until variants are saved.
    """
    data = GenerationRequest.model_validate(request_data)
    async with AsyncSessionLocal() as db:
        try:
            brief = await BriefService.get_brief(db, brief_id, tenant_id)
            brand = await BrandService.get_brand(db, brief.brand_id, tenant_id)

            formats = data.formats or brief.formats or ["static"]
            kb_models = dict(brief.key_benefits) if isinstance(brief.key_benefits, dict) else {}

            count_per_format = data.count_per_format
            target_count = kb_models.get("target_variant_count")
            if target_count:
                try:
                    count_per_format = max(1, round(int(target_count) / len(formats)))
                except (TypeError, ValueError, ZeroDivisionError):
                    pass

            if brief.status != "RUNNING":
                brief.status = "RUNNING"
                brief.variant_count = len(formats) * count_per_format
                brief.completed_variants = 0
                await db.commit()

            logger.info(
                "Background generation brief=%s formats=%s × %s video_model=%s",
                brief_id,
                formats,
                count_per_format,
                data.video_model or kb_models.get("video_model"),
            )

            kit = None
            try:
                kit = await BrandService.get_brand_kit(db, brand.id, tenant_id)
            except Exception:
                kit = None

            brief_dict = enrich_brief_with_brand(
                {
                    "product_name": brief.product_name,
                    "objective": brief.objective,
                    "target_audience": brief.target_audience,
                    "ad_copy_tone": brief.ad_copy_tone,
                    "cta": resolve_campaign_cta(
                        {
                            "cta": brief.cta,
                            "key_benefits": brief.key_benefits,
                            "target_industry_id": kb_models.get("target_industry_id"),
                        }
                    ),
                    "key_benefits": brief.key_benefits,
                },
                brand,
                kit,
            )
            snap = brand_snapshot(brand, kit)
            voice = snap.get("voice") or brief_dict.get("ad_copy_tone", "")

            brief_dict = apply_video_settings_to_brief(
                brief_dict,
                duration_override=data.video_duration_seconds
                or kb_models.get("video_duration_seconds"),
            )
            brief_dict["heygen_avatar_id"] = (
                data.heygen_avatar_id or kb_models.get("heygen_avatar_id") or None
            )
            brief_dict["heygen_voice_id"] = (
                data.heygen_voice_id or kb_models.get("heygen_voice_id") or None
            )
            brief_dict["higgsfield_voice_preset"] = (
                data.higgsfield_voice_preset
                or kb_models.get("higgsfield_voice_preset")
                or None
            )
            avatar_script = data.avatar_script or kb_models.get("avatar_script")
            heygen_settings = data.heygen_settings or kb_models.get("heygen_settings")
            if avatar_script:
                brief_dict["avatar_script"] = avatar_script
                kb_models = {**kb_models, "avatar_script": avatar_script}
            if isinstance(heygen_settings, dict):
                brief_dict["heygen_settings"] = heygen_settings
                kb_models = {**kb_models, "heygen_settings": heygen_settings}
            if data.higgsfield_voice_preset:
                kb_models = {
                    **kb_models,
                    "higgsfield_voice_preset": data.higgsfield_voice_preset,
                }
            if kb_models != brief.key_benefits:
                brief.key_benefits = kb_models
                brief_dict["key_benefits"] = kb_models
                await db.commit()

            image_model = data.image_model or kb_models.get("image_model") or "nano-banana-2"
            video_model = data.video_model or kb_models.get("video_model") or "veo-3.1"
            vm = (video_model or "").strip().lower()
            uses_heygen_video = (
                vm == "heygen" or vm.startswith("heygen-") or vm.startswith("heygen_")
            )
            video_duration = resolve_video_duration_seconds(
                brief_dict,
                override=data.video_duration_seconds,
            )
            requested_duration = requested_video_duration_seconds(
                brief_dict,
                override=data.video_duration_seconds,
            )

            created = 0
            any_failed_motion = False
            variant_index = 0

            # Flatten image-mode fields from key_benefits onto brief_dict for prompt builders.
            for _kb_key in (
                "media_type",
                "image_aspect_ratio",
                "image_use_cases",
                "image_prompt_override",
                "image_variants",
            ):
                if _kb_key in kb_models and _kb_key not in brief_dict:
                    brief_dict[_kb_key] = kb_models[_kb_key]

            image_variants = kb_models.get("image_variants")
            if not isinstance(image_variants, list):
                image_variants = []
            # Filter to only dicts (drop corrupted entries).
            image_variants = [v for v in image_variants if isinstance(v, dict)]

            if image_variants and not target_count:
                count_per_format = max(
                    count_per_format,
                    max(1, len(image_variants) // max(1, len(formats))),
                )
                brief.variant_count = len(formats) * count_per_format

            for fmt in formats:
                for _ in range(count_per_format):
                    # Touch updated_at so stale-RUNNING reconciliation does not abort long HeyGen jobs.
                    brief.status = "RUNNING"
                    await db.commit()

                    if variant_index < len(image_variants):
                        slot = image_variants[variant_index]
                    elif image_variants:
                        # More variants requested than saved slots: cycle through existing slots
                        # so we never fall back to AI-generated copy for an unsaved variant.
                        slot = image_variants[variant_index % len(image_variants)]
                        logger.info(
                            "Brief %s: variant_index=%s exceeds image_variants (%s) — cycling slot %s",
                            brief_id,
                            variant_index,
                            len(image_variants),
                            variant_index % len(image_variants),
                        )
                    else:
                        slot = None
                    slot_use_cases = (
                        list(slot.get("use_cases") or [])
                        if isinstance(slot, dict)
                        else []
                    )
                    slot_hook = (str(slot.get("hook") or "").strip() if slot else "")
                    slot_message = (str(slot.get("message") or "").strip() if slot else "")
                    slot_cta = (str(slot.get("cta") or "").strip() if slot else "")
                    slot_prompt = (str(slot.get("prompt") or "").strip() if slot else "")
                    slot_ad_angle = (str(slot.get("ad_angle") or "").strip() if slot else "")

                    logger.info(
                        "Brief %s: generating variant format=%s index=%s slot=%s",
                        brief_id,
                        fmt,
                        variant_index,
                        bool(slot),
                    )
                    on_image_hook = ""
                    on_image_message = ""
                    if _slot_has_saved_plan(slot):
                        copy, on_image_hook, on_image_message = _copy_from_image_slot(slot)
                        if not str(copy.get("cta") or "").strip():
                            copy["cta"] = resolve_campaign_cta(brief_dict)
                        logger.info(
                            "Brief %s: variant %s uses saved image_variants plan "
                            "(hook=%r on_image_hook=%r prompt_len=%d)",
                            brief_id,
                            variant_index,
                            (copy.get("hook") or "")[:60],
                            on_image_hook,
                            len(slot_prompt),
                        )
                    else:
                        copy = await ai_service.generate_ad_copy(
                            brand_voice=voice,
                            forbidden_words=brand.forbidden_words or [],
                            brief=brief_dict,
                            format_type=fmt,
                            model=data.ai_model,
                        )
                        # Full post hook/headline stay as-is from the variant slot when provided.
                        if slot_hook:
                            copy["hook"] = slot_hook
                        if slot_message:
                            copy["headline"] = slot_message
                        # Catchy RELATED lines for the photo only (not a paste of full hook/headline).
                        slot_image_hook = (
                            str(slot.get("image_hook") or "").strip()
                            if isinstance(slot, dict)
                            else ""
                        )
                        slot_image_headline = (
                            str(slot.get("image_headline") or "").strip()
                            if isinstance(slot, dict)
                            else ""
                        )
                        derived_image_hook, derived_image_headline = _related_image_lines(
                            slot_hook or str(copy.get("hook") or ""),
                            slot_message or str(copy.get("headline") or ""),
                        )
                        on_image_hook = _billboard_words(slot_image_hook, 6) or derived_image_hook
                        on_image_message = (
                            _billboard_words(slot_image_headline, 8) or derived_image_headline
                        )
                        if slot_cta:
                            copy["cta"] = slot_cta
                        elif not str(copy.get("cta") or "").strip():
                            copy["cta"] = resolve_campaign_cta(brief_dict)

                    compliance = await ai_service.run_compliance_check(
                        copy,
                        brand.forbidden_words or [],
                        brief_dict.get("target_industry_id") or brand.industry,
                    )

                    pipeline: dict = {
                        "copy": {"status": "done", "model": data.ai_model},
                        "compliance": {
                            "status": "passed" if compliance["passed"] else "failed",
                            "score": compliance["score"],
                        },
                    }

                    skip_image_for_heygen = uses_heygen_video and fmt in {"reel", "video"}
                    reference_image_url = kb_models.get("reference_image_url")
                    user_image_url = reference_image_url
                    if user_image_url:
                        pipeline["image"] = {
                            "status": "done",
                            "url": user_image_url,
                            "source": "user_reference" if reference_image_url else "stats_dashboard",
                        }
                    elif skip_image_for_heygen:
                        pipeline["image"] = {
                            "status": "skipped",
                            "model": image_model,
                            "reason": "not_required_for_heygen_video",
                        }
                    elif fmt in {"static", "carousel", "reel", "video"}:
                        from app.services.brand_logo import resolve_video_logo_urls
                        from app.services.image_prompt_service import select_and_build_image_plan

                        img_logo, img_logo_light = resolve_video_logo_urls(
                            brand=snap,
                            brief=brief_dict,
                        )

                        # ── Intelligent LLM pipeline ───────────────────────────────────────
                        # For still-image formats (static/carousel):
                        #   Prefer per-variant slot prompt/use-cases when provided.
                        # For video formats: use existing template (video pipeline unchanged)
                        if fmt in {"static", "carousel"}:
                            media_type = (
                                brief_dict.get("media_type")
                                or kb_models.get("media_type")
                                or "image"
                            )
                            if media_type == "image":
                                # Apply this variant's creative direction onto brief for planning.
                                variant_brief = {
                                    **brief_dict,
                                    "image_use_cases": slot_use_cases
                                    or brief_dict.get("image_use_cases")
                                    or kb_models.get("image_use_cases")
                                    or [],
                                    "image_prompt_override": slot_prompt
                                    or brief_dict.get("image_prompt_override")
                                    or kb_models.get("image_prompt_override")
                                    or "",
                                    "image_aspect_ratio": (
                                        "1:1"
                                        if fmt == "carousel"
                                        else (
                                            brief_dict.get("image_aspect_ratio")
                                            or kb_models.get("image_aspect_ratio")
                                            or "1:1"
                                        )
                                    ),
                                }
                                if slot_prompt:
                                    # User (or AI-preview) already wrote the final prompt for this variant.
                                    # Strip any invented on-image slogans and pin EXACT condensed lines.
                                    effective_cta = slot_cta or str(copy.get("cta") or "").strip()
                                    image_prompt = enforce_on_image_copy_in_prompt(
                                        slot_prompt,
                                        image_hook=on_image_hook,
                                        image_headline=on_image_message,
                                        cta=effective_cta,
                                        full_hook=slot_hook or str(copy.get("hook") or ""),
                                        full_headline=slot_message
                                        or str(copy.get("headline") or ""),
                                    )
                                    brief_dict["_image_plan_use_cases"] = slot_use_cases
                                    brief_dict["_image_plan_reasoning"] = (
                                        (slot.get("reasoning") if slot else "") or "per_variant_prompt"
                                    )
                                    logger.info(
                                        "Image slot prompt enforced: index=%s hook=%r headline=%r prompt_len=%d",
                                        variant_index,
                                        on_image_hook,
                                        on_image_message,
                                        len(image_prompt),
                                    )
                                else:
                                    # Pass short on-image lines for burn-in; keep feed copy separate.
                                    image_copy = {
                                        **copy,
                                        "hook": on_image_hook
                                        or _billboard_words(str(copy.get("hook") or ""), 6),
                                        "headline": on_image_message
                                        or _billboard_words(str(copy.get("headline") or ""), 8),
                                    }
                                    plan = await select_and_build_image_plan(
                                        variant_brief, snap, copy=image_copy
                                    )
                                    effective_cta = slot_cta or str(copy.get("cta") or "").strip()
                                    image_prompt = enforce_on_image_copy_in_prompt(
                                        plan.prompt,
                                        image_hook=on_image_hook or str(image_copy["hook"]),
                                        image_headline=on_image_message
                                        or str(image_copy["headline"]),
                                        cta=effective_cta,
                                        full_hook=slot_hook or str(copy.get("hook") or ""),
                                        full_headline=slot_message
                                        or str(copy.get("headline") or ""),
                                    )
                                    brief_dict["_image_plan_use_cases"] = plan.use_cases
                                    brief_dict["_image_plan_reasoning"] = plan.reasoning
                                    logger.info(
                                        "Image plan enforced: index=%s use_cases=%s prompt_len=%d",
                                        variant_index,
                                        plan.use_cases,
                                        len(image_prompt),
                                    )
                            else:
                                # Video stills for non-image mode: keep old template
                                image_prompt = build_image_prompt(
                                    brand=snap,
                                    brief=brief_dict,
                                    copy=copy,
                                    format_type=fmt,
                                )
                        else:
                            # reel / video: template-based still for seed frame only
                            image_prompt = build_image_prompt(
                                brand=snap,
                                brief=brief_dict,
                                copy=copy,
                                format_type=fmt,
                            )

                        # Meta carousel = one square card per variant (not a collage).
                        if fmt == "carousel":
                            from app.services.campaign_themes import (
                                build_carousel_slides,
                                parse_campaign_themes,
                            )

                            themes = parse_campaign_themes(
                                brief.product_name
                                or str(kb_models.get("niche") or "")
                                or brief.title
                                or "",
                                brief_dict,
                            )
                            # Prefer per-slot themes when image variants exist
                            if image_variants:
                                slot_themes = []
                                for sv in image_variants:
                                    if not isinstance(sv, dict):
                                        continue
                                    t = (
                                        str(sv.get("message") or sv.get("image_headline") or sv.get("hook") or "")
                                        .strip()
                                    )
                                    if t:
                                        slot_themes.append(t[:80])
                                if slot_themes:
                                    themes = slot_themes
                            if not themes:
                                themes = [brief.title or "Offer"]
                            slides = build_carousel_slides(
                                themes,
                                offer=str(kb_models.get("offer") or copy.get("offer") or ""),
                                cta=str(copy.get("cta") or brief.cta or "Learn More"),
                                vertical_label=str(
                                    kb_models.get("industry")
                                    or brief_dict.get("target_industry_label")
                                    or "brand"
                                ),
                            )
                            copy["carousel_slides"] = slides
                            card_i = variant_index % max(1, len(slides))
                            slide = slides[card_i]
                            theme = str(slide.get("theme") or slide.get("headline") or "Offer")
                            image_prompt = (
                                f"{image_prompt.rstrip()} "
                                f"Meta CAROUSEL CARD {card_i + 1} of {len(slides)} in ONE swipe story — "
                                f"generate ONE square 1:1 feed card only for theme \"{theme}\". "
                                f"Story beat: "
                                f"{'PROBLEM opener' if card_i == 0 else ('SOLUTION + CTA closer' if card_i == len(slides) - 1 else 'AGITATE / PROOF bridge')}. "
                                "Do NOT render a multi-panel collage, strip, or row of cards in this image. "
                                "This card must feel like the next swipe after the previous card in the same campaign."
                            )
                            logger.info(
                                "Carousel card framed: brief=%s card=%s/%s theme=%r",
                                brief_id,
                                card_i + 1,
                                len(slides),
                                theme,
                            )

                        burn_logo_on_still = fmt not in {"reel", "video"}
                        pipeline["image"] = await ai_service.generate_image_asset(
                            prompt=image_prompt,
                            tenant_id=str(tenant_id),
                            model=image_model,
                            format_type=fmt,
                            logo_url=img_logo if burn_logo_on_still else None,
                            logo_on_light_url=img_logo_light if burn_logo_on_still else None,
                        )
                    else:
                        pipeline["image"] = {"status": "skipped", "model": image_model}

                    if fmt in {"reel", "video"}:
                        from app.services.video_script_skeleton import (
                            ensure_production_skeleton,
                            merge_skeleton_into_key_benefits,
                        )

                        production_skeleton = await ensure_production_skeleton(
                            brief_dict,
                            copy,
                            duration=requested_duration,
                            format_type=fmt,
                            force_refresh=True,
                        )
                        kb_models = merge_skeleton_into_key_benefits(kb_models, production_skeleton)
                        brief_dict["key_benefits"] = kb_models
                        brief_dict["video_script_skeleton"] = production_skeleton
                        brief.key_benefits = kb_models

                        image_url = None
                        if isinstance(pipeline.get("image"), dict):
                            image_url = pipeline["image"].get("url")
                        _vid_on_light = snap.get("logo_on_light_url") or brief_dict.get(
                            "logo_on_light_url"
                        )
                        if not _vid_on_light and isinstance(snap.get("logo_variations"), dict):
                            _vid_on_light = snap["logo_variations"].get("on_light")
                        if not _vid_on_light and isinstance(
                            kit and kit.logo_variations, dict
                        ):
                            _vid_on_light = kit.logo_variations.get("on_light")

                        pipeline["video"] = await ai_service.generate_video_storyboard(
                            brief=brief_dict,
                            copy=copy,
                            format_type=fmt,
                            model=video_model,
                            tenant_id=str(tenant_id),
                            source_image_url=image_url,
                            duration_seconds=data.video_duration_seconds or video_duration,
                            logo_url=snap.get("logo_url") or brief_dict.get("logo_url"),
                            logo_on_light_url=_vid_on_light,
                        )
                    else:
                        pipeline["video"] = {"status": "skipped", "model": video_model}

                    motion_format = fmt in {"reel", "video"}
                    video_step = (
                        pipeline.get("video") if isinstance(pipeline.get("video"), dict) else {}
                    )
                    video_ok = video_step.get("status") == "done" and bool(video_step.get("url"))
                    if motion_format and not video_ok:
                        variant_status = "FAILED"
                        any_failed_motion = True
                    else:
                        variant_status = "READY"

                    variant = Variant(
                        brief_id=brief.id,
                        brand_id=brand.id,
                        tenant_id=tenant_id,
                        format=fmt,
                        hook=copy.get("hook", ""),
                        headline=copy.get("headline", ""),
                        body_copy=copy.get("body_copy", ""),
                        cta=copy.get("cta", ""),
                        hashtags=copy.get("hashtags", []),
                        ai_model=data.ai_model,
                        generation_params={
                            "format": fmt,
                            "tone": brief.ad_copy_tone,
                            "pipeline": pipeline,
                            "models": {
                                "copy": data.ai_model,
                                "image": image_model,
                                "video": video_model,
                                "video_duration_seconds": requested_duration,
                            },
                            # Image plan metadata (populated for image-mode stills)
                            "image_plan": {
                                "use_cases": brief_dict.get("_image_plan_use_cases") or [],
                                "reasoning": brief_dict.get("_image_plan_reasoning") or "",
                                "variant_index": variant_index,
                                "hook": slot_hook or None,
                                "message": slot_message or None,
                                "image_hook": on_image_hook or None,
                                "image_headline": on_image_message or None,
                                "cta": slot_cta or copy.get("cta") or None,
                                "prompt": slot_prompt or None,
                                "ad_angle": slot_ad_angle or None,
                                "hook_framework": slot_ad_angle or None,
                            },
                            "hook_framework": slot_ad_angle or None,
                        },
                        status=variant_status,
                        compliance_status="PASSED" if compliance["passed"] else "FAILED",
                        compliance_notes=compliance,
                    )
                    db.add(variant)
                    created += 1
                    variant_index += 1
                    brief.completed_variants = created
                    await db.commit()
                    video_err = video_step.get("error") if isinstance(video_step, dict) else None
                    logger.info(
                        "Brief %s: variant %s saved status=%s video=%s",
                        brief_id,
                        created,
                        variant_status,
                        "ok" if video_ok else (video_err or "failed"),
                    )

            if created == 0:
                brief.status = "FAILED"
            elif any_failed_motion:
                brief.status = "PARTIAL"
            else:
                brief.status = "READY"
            await db.commit()
            logger.info(
                "Background generation done brief=%s status=%s variants=%s",
                brief_id,
                brief.status,
                created,
            )
        except Exception:
            logger.exception("Background generation failed brief=%s", brief_id)
            try:
                brief = await BriefService.get_brief(db, brief_id, tenant_id)
                if brief.completed_variants and brief.completed_variants > 0:
                    brief.status = "PARTIAL"
                else:
                    brief.status = "FAILED"
                await db.commit()
            except Exception:
                logger.exception("Could not mark brief %s failed after job error", brief_id)
