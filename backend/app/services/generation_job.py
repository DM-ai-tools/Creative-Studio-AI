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
from app.services.video_duration import (
    apply_video_settings_to_brief,
    requested_video_duration_seconds,
    resolve_video_duration_seconds,
)

logger = logging.getLogger(__name__)


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

            for fmt in formats:
                for _ in range(count_per_format):
                    # Touch updated_at so stale-RUNNING reconciliation does not abort long HeyGen jobs.
                    brief.status = "RUNNING"
                    await db.commit()

                    logger.info("Brief %s: generating variant format=%s", brief_id, fmt)
                    copy = await ai_service.generate_ad_copy(
                        brand_voice=voice,
                        forbidden_words=brand.forbidden_words or [],
                        brief=brief_dict,
                        format_type=fmt,
                        model=data.ai_model,
                    )
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

                        img_logo, img_logo_light = resolve_video_logo_urls(
                            brand=snap,
                            brief=brief_dict,
                        )
                        image_prompt = build_image_prompt(
                            brand=snap,
                            brief=brief_dict,
                            copy=copy,
                            format_type=fmt,
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
                        },
                        status=variant_status,
                        compliance_status="PASSED" if compliance["passed"] else "FAILED",
                        compliance_notes=compliance,
                    )
                    db.add(variant)
                    created += 1
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
