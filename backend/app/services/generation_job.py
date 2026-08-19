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
    enforce_brand_identity_in_prompt,
    enforce_fashion_retail_photo_in_prompt,
    enforce_fashion_retail_promo_in_prompt,
    enforce_niche_product_focus_in_prompt,
    enforce_no_spurious_circled_paper_prop,
    enforce_on_image_copy_in_prompt,
    enforce_on_image_style_in_prompt,
    enforce_product_focus_in_prompt,
    consolidate_image_prompt_for_generation,
    _prompt_describes_lifestyle_scene,
    strip_burned_in_copy_from_prompt,
)
from app.services.variant_service import VariantService
from app.services.video_duration import (
    apply_video_settings_to_brief,
    requested_video_duration_seconds,
    resolve_video_duration_seconds,
)

logger = logging.getLogger(__name__)


def _is_last_carousel_card(slot: dict[str, Any] | None, image_variants: list[dict[str, Any]]) -> bool:
    if not isinstance(slot, dict):
        carousel_slots = [
            s for s in image_variants if str(s.get("format") or "").strip().lower() == "carousel"
        ]
        return len(carousel_slots) <= 1
    try:
        idx = int(slot.get("carousel_index") or 0)
        total = int(slot.get("carousel_total") or 0)
        if idx and total:
            return idx >= total
    except (TypeError, ValueError):
        pass
    carousel_slots = [
        s for s in image_variants if str(s.get("format") or "").strip().lower() == "carousel"
    ]
    if len(carousel_slots) <= 1:
        return True
    try:
        return carousel_slots.index(slot) >= len(carousel_slots) - 1
    except ValueError:
        return True


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
    ad_angle = str(slot.get("ad_angle") or "").strip()
    niche = str(slot.get("niche") or "").strip()
    derived_hook, derived_headline = _related_image_lines(
        hook, message, ad_angle=ad_angle, niche=niche
    )
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


def _ensure_on_image_burn_lines(
    *,
    on_image_hook: str,
    on_image_message: str,
    slot: dict[str, Any] | None,
    copy: dict[str, Any],
    niche: str = "",
    ad_angle: str = "",
) -> tuple[str, str]:
    """Guarantee short burn-in lines exist for static/carousel stills."""
    hook = (on_image_hook or "").strip()
    headline = (on_image_message or "").strip()
    if hook and headline:
        return hook, headline

    slot_hook = str((slot or {}).get("hook") or copy.get("hook") or "").strip()
    slot_message = str((slot or {}).get("message") or copy.get("headline") or "").strip()
    if isinstance(slot, dict):
        if not hook:
            hook = _billboard_words(str(slot.get("image_hook") or "").strip(), 6)
        if not headline:
            headline = _billboard_words(str(slot.get("image_headline") or "").strip(), 8)

    if not hook or not headline:
        derived_hook, derived_headline = _related_image_lines(
            slot_hook,
            slot_message,
            ad_angle=ad_angle or str((slot or {}).get("ad_angle") or "").strip(),
            niche=niche,
        )
        hook = hook or derived_hook
        headline = headline or derived_headline

    return _billboard_words(hook, 6), _billboard_words(headline, 8)


def _resolve_burn_in_cta(
    *,
    fmt: str,
    carousel_last: bool,
    slot: dict[str, Any] | None,
    copy: dict[str, Any],
    brief_dict: dict[str, Any],
    brief_cta: str = "",
) -> str:
    """Static ads always need a burned CTA; carousel only on the last card."""
    if fmt == "carousel" and not carousel_last:
        return ""
    for source in (
        str((slot or {}).get("cta") or "").strip(),
        str(copy.get("cta") or "").strip(),
        str(brief_cta or "").strip(),
        resolve_campaign_cta(brief_dict),
    ):
        if source:
            return source[:80]
    return "Learn More"


def _finalize_burn_in_prompt(
    image_prompt: str,
    *,
    fmt: str,
    carousel_last: bool,
    slot: dict[str, Any] | None,
    copy: dict[str, Any],
    brief_dict: dict[str, Any],
    brief_cta: str,
    on_image_hook: str,
    on_image_message: str,
    slot_cta: str,
    slot_hook: str,
    slot_message: str,
    industry: str,
    niche: str,
    primary_color: str,
) -> str:
    """
    Re-pin hook/headline/CTA at the very end of the prompt.

    Product-focus and style locks run after the first enforce pass — this guarantees
    the TEXT-ANCHOR block (with CTA pill) survives and stays last before the API call.
    """
    if fmt == "carousel" and not carousel_last:
        burn_cta = ""
    else:
        burn_cta = _resolve_burn_in_cta(
            fmt=fmt,
            carousel_last=carousel_last,
            slot=slot,
            copy=copy,
            brief_dict=brief_dict,
            brief_cta=brief_cta,
        )
        if not burn_cta:
            burn_cta = slot_cta
    if not on_image_hook and not on_image_message and not burn_cta:
        return image_prompt
    body = strip_burned_in_copy_from_prompt(image_prompt, allow_cta=True)
    return enforce_on_image_copy_in_prompt(
        body,
        image_hook=on_image_hook,
        image_headline=on_image_message,
        cta=burn_cta,
        full_hook=slot_hook or str(copy.get("hook") or ""),
        full_headline=slot_message or str(copy.get("headline") or ""),
        industry=industry,
        niche=niche,
        primary_color=primary_color,
    )


def _append_social_style_to_prompt(image_prompt: str, snap: dict[str, Any]) -> str:
    """Append stored SociaVault social feed style when generating final image prompts."""
    profile = snap.get("social_style_profile")
    if not isinstance(profile, dict):
        return image_prompt
    from app.services.social_style_service import (
        format_social_style_for_llm,
        format_social_style_scene_lock,
        resolve_effective_brand_colors,
    )

    block = format_social_style_for_llm(profile)
    scene_lock = format_social_style_scene_lock(
        profile,
        lifestyle_scene=_prompt_describes_lifestyle_scene(image_prompt),
    )
    if scene_lock and scene_lock not in block:
        block = f"{block} {scene_lock}" if block else scene_lock
    if not block:
        guidance = str(profile.get("prompt_guidance") or "").strip()
        if not guidance:
            return image_prompt
        block = f"Match client social feed style: {guidance}"
    primary, secondary = resolve_effective_brand_colors(
        primary_color=str(snap.get("primary_color") or ""),
        secondary_color=str(snap.get("secondary_color") or ""),
        social_style_profile=profile,
    )
    if primary or secondary:
        colour_line = " Use social feed colours:"
        if primary:
            colour_line += f" CTA pill + headline accent {primary}."
        if secondary:
            colour_line += f" Background/frame {secondary}."
        colour_line += " Do NOT use off-brand blue if feed is black/gold."
        block = f"{block}{colour_line}"
    return f"{image_prompt.rstrip()} {block}"


def _lock_brand_name_on_prompt(
    prompt: str,
    *,
    snap: dict[str, Any],
    brief_dict: dict[str, Any],
    brand: Any,
) -> str:
    name = (
        str(snap.get("brand_name") or "").strip()
        or str(brief_dict.get("brand_name") or "").strip()
        or str(getattr(brand, "name", "") or "").strip()
    )
    industry = str(
        brief_dict.get("target_industry_label")
        or snap.get("agency_industry")
        or getattr(brand, "industry", "")
        or ""
    )
    niche = str(brief_dict.get("niche") or brief_dict.get("product_name") or "")
    locked = enforce_niche_product_focus_in_prompt(
        prompt,
        niche=niche,
        industry=industry,
        brand_name=name,
    )
    return enforce_brand_identity_in_prompt(locked, brand_name=name)


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
    from app.services.usage_tracker import set_usage_context

    set_usage_context(tenant_id=str(tenant_id), operation="generation_job")
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

            image_mode = str(
                brief_dict.get("media_type") or kb_models.get("media_type") or ""
            ) == "image" or all(f in {"static", "carousel"} for f in formats)

            if image_variants and image_mode:
                work_items: list[tuple[str, int]] = []
                for i, slot in enumerate(image_variants):
                    raw = str(slot.get("format") or "").strip().lower()
                    if raw not in {"static", "carousel"}:
                        image_fmts = [f for f in formats if f in {"static", "carousel"}]
                        raw = (
                            image_fmts[0]
                            if len(image_fmts) == 1
                            else (formats[0] if formats else "static")
                        )
                    work_items.append((raw, i))
                brief.variant_count = len(work_items)
            else:
                work_items = []
                vi = 0
                for fmt in formats:
                    for _ in range(count_per_format):
                        work_items.append((fmt, vi))
                        vi += 1

            for fmt, variant_index in work_items:
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
                    slot_photo_only = bool(isinstance(slot, dict) and slot.get("photo_only"))
                    _fashion_niche = str(
                        kb_models.get("niche")
                        or brief_dict.get("niche")
                        or brief.product_name
                        or ""
                    ).lower()
                    _fashion_ind = str(
                        kb_models.get("industry")
                        or brief_dict.get("target_industry_label")
                        or brand.industry
                        or ""
                    ).lower()
                    _is_fashion = any(
                        k in f"{_fashion_niche} {_fashion_ind}"
                        for k in (
                            "fashion", "apparel", "clothing", "runway", "arrivals",
                            "denim", "knitwear", "wardrobe", "retail",
                        )
                    )
                    slot_retail_promo = bool(
                        isinstance(slot, dict)
                        and (slot.get("retail_promo") or (_is_fashion and not slot_photo_only))
                    )
                    carousel_last = fmt != "carousel" or _is_last_carousel_card(
                        slot if isinstance(slot, dict) else None, image_variants
                    )
                    if fmt == "carousel" and not carousel_last:
                        slot_cta = ""

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
                        if slot_cta and not str(copy.get("cta") or "").strip():
                            copy["cta"] = slot_cta
                        elif not slot_cta and str(copy.get("cta") or "").strip():
                            slot_cta = str(copy.get("cta") or "").strip()
                        if fmt == "carousel":
                            copy["cta"] = (
                                slot_cta or resolve_campaign_cta(brief_dict)
                                if carousel_last
                                else ""
                            )
                        elif not str(copy.get("cta") or "").strip():
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
                            ad_angle=slot_ad_angle,
                            niche=str(
                                kb_models.get("niche")
                                or brief_dict.get("niche")
                                or brief.product_name
                                or ""
                            ),
                        )
                        on_image_hook = _billboard_words(slot_image_hook, 6) or derived_image_hook
                        on_image_message = (
                            _billboard_words(slot_image_headline, 8) or derived_image_headline
                        )
                        if fmt == "carousel":
                            copy["cta"] = (
                                slot_cta or resolve_campaign_cta(brief_dict)
                                if carousel_last
                                else ""
                            )
                        elif slot_cta:
                            copy["cta"] = slot_cta
                        elif not str(copy.get("cta") or "").strip():
                            copy["cta"] = resolve_campaign_cta(brief_dict)

                    if slot_photo_only:
                        on_image_hook = ""
                        on_image_message = ""
                        slot_cta = ""
                    elif fmt in {"static", "carousel"}:
                        on_image_hook, on_image_message = _ensure_on_image_burn_lines(
                            on_image_hook=on_image_hook,
                            on_image_message=on_image_message,
                            slot=slot if isinstance(slot, dict) else None,
                            copy=copy,
                            niche=str(
                                kb_models.get("niche")
                                or brief_dict.get("niche")
                                or brief.product_name
                                or ""
                            ),
                            ad_angle=slot_ad_angle,
                        )
                        if not str(copy.get("cta") or "").strip() and not slot_cta:
                            resolved = _resolve_burn_in_cta(
                                fmt=fmt,
                                carousel_last=carousel_last,
                                slot=slot if isinstance(slot, dict) else None,
                                copy=copy,
                                brief_dict=brief_dict,
                                brief_cta=str(brief.cta or ""),
                            )
                            copy["cta"] = resolved
                            slot_cta = resolved
                        logger.info(
                            "Brief %s: burn-in lines variant=%s hook=%r headline=%r cta=%r",
                            brief_id,
                            variant_index,
                            on_image_hook,
                            on_image_message,
                            slot_cta or str(copy.get("cta") or "")[:40],
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
                            _ind = str(
                                kb_models.get("industry")
                                or brief_dict.get("target_industry_label")
                                or brand.industry
                                or ""
                            )
                            _niche = str(
                                kb_models.get("niche")
                                or brief_dict.get("niche")
                                or brief.product_name
                                or ""
                            )
                            from app.services.social_style_service import resolve_effective_brand_colors

                            _brand_primary, _brand_secondary = resolve_effective_brand_colors(
                                primary_color=str(snap.get("primary_color") or ""),
                                secondary_color=str(snap.get("secondary_color") or ""),
                                social_style_profile=snap.get("social_style_profile"),
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
                                if slot_photo_only and slot_prompt:
                                    ratio = (
                                        brief_dict.get("image_aspect_ratio")
                                        or kb_models.get("image_aspect_ratio")
                                        or "4:3"
                                    )
                                    image_prompt = enforce_fashion_retail_photo_in_prompt(
                                        slot_prompt, aspect_ratio=ratio
                                    )
                                    image_prompt = enforce_no_spurious_circled_paper_prop(
                                        image_prompt, industry=_ind, niche=_niche
                                    )
                                    brief_dict["_image_plan_use_cases"] = slot_use_cases
                                    brief_dict["_image_plan_reasoning"] = (
                                        (slot.get("reasoning") if slot else "") or "fashion_retail_photo"
                                    )
                                elif slot_retail_promo and slot_prompt:
                                    ratio = (
                                        str(slot.get("aspect_ratio") or "").strip()
                                        or brief_dict.get("image_aspect_ratio")
                                        or kb_models.get("image_aspect_ratio")
                                        or "1:1"
                                    )
                                    from app.services.icp_image_plan_service import (
                                        _fashion_retail_promo_on_image_lines,
                                        _strip_fashion_photo_only_lock,
                                    )

                                    promo_hook, promo_headline, promo_cta = _fashion_retail_promo_on_image_lines(
                                        seed=slot if isinstance(slot, dict) else None,
                                        hook=slot_hook or str(copy.get("hook") or ""),
                                        message=slot_message or str(copy.get("headline") or ""),
                                        offer=str(slot.get("offer") or copy.get("body_copy") or ""),
                                        cta=slot_cta or str(copy.get("cta") or ""),
                                    )
                                    on_image_hook = promo_hook
                                    on_image_message = promo_headline
                                    copy["cta"] = promo_cta
                                    base = enforce_fashion_retail_promo_in_prompt(
                                        _strip_fashion_photo_only_lock(slot_prompt),
                                        aspect_ratio=ratio,
                                    )
                                    image_prompt = enforce_on_image_copy_in_prompt(
                                        strip_burned_in_copy_from_prompt(base, allow_cta=True),
                                        image_hook=on_image_hook,
                                        image_headline=on_image_message,
                                        cta=promo_cta,
                                        full_hook=slot_hook or str(copy.get("hook") or ""),
                                        full_headline=slot_message or str(copy.get("headline") or ""),
                                        industry=_ind,
                                        niche=_niche,
                                        primary_color=_brand_primary,
                                    )
                                    image_prompt = enforce_no_spurious_circled_paper_prop(
                                        image_prompt, industry=_ind, niche=_niche
                                    )
                                    brief_dict["_image_plan_use_cases"] = slot_use_cases
                                    brief_dict["_image_plan_reasoning"] = (
                                        (slot.get("reasoning") if slot else "") or "fashion_retail_promo"
                                    )
                                elif slot_prompt:
                                    # User (or AI-preview) already wrote the final prompt for this variant.
                                    if fmt == "carousel" and not carousel_last:
                                        image_prompt = enforce_on_image_copy_in_prompt(
                                            strip_burned_in_copy_from_prompt(
                                                slot_prompt, allow_cta=True
                                            ),
                                            image_hook=on_image_hook,
                                            image_headline=on_image_message,
                                            cta="",
                                            full_hook=slot_hook
                                            or str(copy.get("hook") or ""),
                                            full_headline=slot_message
                                            or str(copy.get("headline") or ""),
                                            industry=_ind,
                                            niche=_niche,
                                            primary_color=_brand_primary,
                                        )
                                        copy["cta"] = ""
                                    elif fmt == "carousel" and carousel_last:
                                        closer_cta = (
                                            slot_cta
                                            or str(copy.get("cta") or "").strip()
                                            or resolve_campaign_cta(brief_dict)
                                        )
                                        image_prompt = enforce_on_image_copy_in_prompt(
                                            strip_burned_in_copy_from_prompt(
                                                slot_prompt, allow_cta=True
                                            ),
                                            image_hook=on_image_hook,
                                            image_headline=on_image_message,
                                            cta=closer_cta,
                                            full_hook=slot_hook or str(copy.get("hook") or ""),
                                            full_headline=slot_message
                                            or str(copy.get("headline") or ""),
                                            industry=_ind,
                                            niche=_niche,
                                            primary_color=_brand_primary,
                                        )
                                        copy["cta"] = closer_cta
                                    else:
                                        effective_cta = _resolve_burn_in_cta(
                                            fmt=fmt,
                                            carousel_last=carousel_last,
                                            slot=slot if isinstance(slot, dict) else None,
                                            copy=copy,
                                            brief_dict=brief_dict,
                                            brief_cta=str(brief.cta or ""),
                                        )
                                        copy["cta"] = effective_cta
                                        image_prompt = enforce_on_image_copy_in_prompt(
                                            strip_burned_in_copy_from_prompt(
                                                slot_prompt, allow_cta=True
                                            ),
                                            image_hook=on_image_hook,
                                            image_headline=on_image_message,
                                            cta=effective_cta,
                                            full_hook=slot_hook or str(copy.get("hook") or ""),
                                            full_headline=slot_message
                                            or str(copy.get("headline") or ""),
                                            industry=_ind,
                                            niche=_niche,
                                            primary_color=_brand_primary,
                                        )
                                    image_prompt = enforce_no_spurious_circled_paper_prop(
                                        image_prompt, industry=_ind, niche=_niche
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
                                    if fmt == "carousel" and not carousel_last:
                                        image_prompt = enforce_on_image_copy_in_prompt(
                                            strip_burned_in_copy_from_prompt(
                                                plan.prompt, allow_cta=True
                                            ),
                                            image_hook=on_image_hook
                                            or str(image_copy["hook"]),
                                            image_headline=on_image_message
                                            or str(image_copy["headline"]),
                                            cta="",
                                            full_hook=slot_hook or str(copy.get("hook") or ""),
                                            full_headline=slot_message
                                            or str(copy.get("headline") or ""),
                                            industry=_ind,
                                            niche=_niche,
                                            primary_color=_brand_primary,
                                        )
                                    elif fmt == "carousel" and carousel_last:
                                        closer_cta = (
                                            slot_cta
                                            or str(copy.get("cta") or "").strip()
                                            or resolve_campaign_cta(brief_dict)
                                        )
                                        image_prompt = enforce_on_image_copy_in_prompt(
                                            strip_burned_in_copy_from_prompt(
                                                plan.prompt, allow_cta=True
                                            ),
                                            image_hook=on_image_hook
                                            or str(image_copy["hook"]),
                                            image_headline=on_image_message
                                            or str(image_copy["headline"]),
                                            cta=closer_cta,
                                            full_hook=slot_hook or str(copy.get("hook") or ""),
                                            full_headline=slot_message
                                            or str(copy.get("headline") or ""),
                                            industry=_ind,
                                            niche=_niche,
                                            primary_color=_brand_primary,
                                        )
                                    else:
                                        effective_cta = _resolve_burn_in_cta(
                                            fmt=fmt,
                                            carousel_last=carousel_last,
                                            slot=slot if isinstance(slot, dict) else None,
                                            copy=copy,
                                            brief_dict=brief_dict,
                                            brief_cta=str(brief.cta or ""),
                                        )
                                        copy["cta"] = effective_cta
                                        image_prompt = enforce_on_image_copy_in_prompt(
                                            strip_burned_in_copy_from_prompt(
                                                plan.prompt, allow_cta=True
                                            ),
                                            image_hook=on_image_hook or str(image_copy["hook"]),
                                            image_headline=on_image_message
                                            or str(image_copy["headline"]),
                                            cta=effective_cta,
                                            full_hook=slot_hook or str(copy.get("hook") or ""),
                                            full_headline=slot_message
                                            or str(copy.get("headline") or ""),
                                            industry=_ind,
                                            niche=_niche,
                                            primary_color=_brand_primary,
                                        )
                                    image_prompt = enforce_no_spurious_circled_paper_prop(
                                        image_prompt, industry=_ind, niche=_niche
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
                            carousel_slots = [
                                sv
                                for sv in image_variants
                                if isinstance(sv, dict)
                                and str(sv.get("format") or "").strip().lower() == "carousel"
                            ] or [sv for sv in image_variants if isinstance(sv, dict)]
                            if carousel_slots:
                                slot_themes = []
                                for sv in carousel_slots:
                                    t = (
                                        str(
                                            sv.get("image_hook")
                                            or sv.get("image_headline")
                                            or sv.get("hook")
                                            or sv.get("message")
                                            or ""
                                        ).strip()
                                    )
                                    if t:
                                        slot_themes.append(t[:80])
                                if slot_themes:
                                    themes = slot_themes
                            if not themes:
                                themes = [brief.title or "Offer"]
                            last_cta = str(
                                (slot.get("cta") if isinstance(slot, dict) else "")
                                or copy.get("cta")
                                or brief.cta
                                or "Learn More"
                            )
                            slides = build_carousel_slides(
                                themes,
                                offer=str(kb_models.get("offer") or copy.get("offer") or ""),
                                cta=last_cta if carousel_last else "",
                                vertical_label=str(
                                    kb_models.get("industry")
                                    or brief_dict.get("target_industry_label")
                                    or "brand"
                                ),
                            )
                            copy["carousel_slides"] = slides
                            try:
                                card_i = max(0, int((slot or {}).get("carousel_index") or 0) - 1)
                            except (TypeError, ValueError, AttributeError):
                                card_i = 0
                            if not card_i and carousel_slots and isinstance(slot, dict):
                                try:
                                    card_i = carousel_slots.index(slot)
                                except ValueError:
                                    card_i = variant_index % max(1, len(slides))
                            card_i = min(card_i, max(0, len(slides) - 1))
                            total_cards = int((slot or {}).get("carousel_total") or 0) or len(slides)
                            slide = slides[card_i]
                            theme = str(slide.get("theme") or slide.get("headline") or "Offer")
                            beat = (
                                "PROBLEM opener"
                                if card_i == 0
                                else ("SOLUTION + CTA closer" if carousel_last else "AGITATE / PROOF bridge")
                            )
                            cta_rule = (
                                f' LAST CARD: burn a pill CTA button reading exactly "{last_cta}".'
                                if carousel_last
                                else " No CTA button on this card — CTA burns only on the final swipe card."
                            )
                            image_prompt = (
                                f"{image_prompt.rstrip()} "
                                f"Meta CAROUSEL CARD {card_i + 1} of {total_cards} in ONE swipe story — "
                                f"generate ONE square 1:1 feed card only for theme \"{theme}\". "
                                f"Story beat: {beat}. "
                                "Do NOT render a multi-panel collage, strip, or row of cards in this image. "
                                + cta_rule
                            )
                            logger.info(
                                "Carousel card framed: brief=%s card=%s/%s theme=%r",
                                brief_id,
                                card_i + 1,
                                len(slides),
                                theme,
                            )

                        burn_logo_on_still = fmt not in {"reel", "video"}
                        slot_product_focus = (
                            str(slot.get("product_focus") or "").strip()
                            if isinstance(slot, dict)
                            else ""
                        ) or str(
                            kb_models.get("product_focus")
                            or brief_dict.get("product_focus")
                            or ""
                        ).strip()
                        slot_product_model = (
                            str(slot.get("product_model") or "").strip()
                            if isinstance(slot, dict)
                            else ""
                        )
                        if slot_product_focus:
                            image_prompt = enforce_product_focus_in_prompt(
                                image_prompt,
                                product_focus=slot_product_focus,
                                product_model=slot_product_model,
                                industry=_fashion_ind,
                                niche=_fashion_niche,
                            )
                        campaign_on_image_style = str(
                            kb_models.get("on_image_style")
                            or brief_dict.get("on_image_style")
                            or "auto"
                        ).strip()
                        if campaign_on_image_style:
                            image_prompt = enforce_on_image_style_in_prompt(
                                image_prompt,
                                on_image_style=campaign_on_image_style,
                                niche=_fashion_niche,
                                industry=_fashion_ind,
                                fashion_retail_promo=bool(slot_retail_promo),
                                primary_color=_brand_primary,
                                secondary_color=_brand_secondary,
                                font_heading=str(snap.get("font_heading") or ""),
                                font_body=str(snap.get("font_body") or ""),
                            )
                        image_prompt = _append_social_style_to_prompt(image_prompt, snap)
                        image_prompt = _lock_brand_name_on_prompt(
                            image_prompt, snap=snap, brief_dict=brief_dict, brand=brand
                        )
                        if fmt in {"static", "carousel"} and not slot_photo_only:
                            image_prompt = _finalize_burn_in_prompt(
                                image_prompt,
                                fmt=fmt,
                                carousel_last=carousel_last,
                                slot=slot if isinstance(slot, dict) else None,
                                copy=copy,
                                brief_dict=brief_dict,
                                brief_cta=str(brief.cta or ""),
                                on_image_hook=on_image_hook,
                                on_image_message=on_image_message,
                                slot_cta=slot_cta,
                                slot_hook=slot_hook,
                                slot_message=slot_message,
                                industry=_ind,
                                niche=_niche,
                                primary_color=_brand_primary,
                            )
                            logger.info(
                                "Brief %s: final burn-in variant=%s cta=%r prompt_len=%d",
                                brief_id,
                                variant_index,
                                (
                                    _resolve_burn_in_cta(
                                        fmt=fmt,
                                        carousel_last=carousel_last,
                                        slot=slot if isinstance(slot, dict) else None,
                                        copy=copy,
                                        brief_dict=brief_dict,
                                        brief_cta=str(brief.cta or ""),
                                    )
                                    if fmt == "static" or carousel_last
                                    else ""
                                ),
                                len(image_prompt),
                            )
                        if fmt in {"static", "carousel"} and not slot_photo_only:
                            image_prompt = consolidate_image_prompt_for_generation(
                                image_prompt,
                                scene_prompt=slot_prompt,
                                image_hook=on_image_hook,
                                image_headline=on_image_message,
                                cta=slot_cta
                                or _resolve_burn_in_cta(
                                    fmt=fmt,
                                    carousel_last=carousel_last,
                                    slot=slot if isinstance(slot, dict) else None,
                                    copy=copy,
                                    brief_dict=brief_dict,
                                    brief_cta=str(brief.cta or ""),
                                ),
                                primary_color=_brand_primary,
                                secondary_color=_brand_secondary,
                                brand_name=str(snap.get("brand_name") or brand.name or ""),
                                product_focus=slot_product_focus,
                                niche=_niche,
                                industry=_ind,
                            )
                        if burn_logo_on_still and not img_logo:
                            logger.warning(
                                "Brief %s variant=%s: no brand logo resolved — upload PNG/JPG on Brand Kit",
                                brief_id,
                                variant_index,
                            )
                        elif burn_logo_on_still and slot_product_focus:
                            logger.info(
                                "Brief %s variant=%s: product_focus=%r logo=%s on_light=%s",
                                brief_id,
                                variant_index,
                                slot_product_focus,
                                "yes" if img_logo else "no",
                                "yes" if img_logo_light else "no",
                            )
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
                    image_step = (
                        pipeline.get("image") if isinstance(pipeline.get("image"), dict) else {}
                    )
                    image_failed = (
                        not motion_format
                        and image_step.get("status") == "failed"
                    )
                    if motion_format and not video_ok:
                        variant_status = "FAILED"
                        any_failed_motion = True
                    elif image_failed:
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
                                "cta": (slot_cta or copy.get("cta") or None)
                                if carousel_last
                                else None,
                                "prompt": slot_prompt or None,
                                "ad_angle": slot_ad_angle or None,
                                "hook_framework": slot_ad_angle or None,
                                "carousel_index": (slot or {}).get("carousel_index")
                                if isinstance(slot, dict)
                                else None,
                                "carousel_total": (slot or {}).get("carousel_total")
                                if isinstance(slot, dict)
                                else None,
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


async def run_regenerate_variant_image(
    *,
    variant_id: UUID,
    tenant_id: UUID,
    image_model: str | None = None,
) -> None:
    """
    Re-run ONLY the image step for one existing variant.
    Keeps hook/headline/CTA/copy — does not recreate sibling variants.
    """
    from app.services.usage_tracker import set_usage_context

    set_usage_context(tenant_id=str(tenant_id), operation="regenerate_variant_image")
    async with AsyncSessionLocal() as db:
        try:
            from app.services.brand_logo import resolve_video_logo_urls

            variant = await VariantService.get_variant(db, variant_id, tenant_id)
            brief = await BriefService.get_brief(db, variant.brief_id, tenant_id)
            brand = await BrandService.get_brand(db, variant.brand_id, tenant_id)
            kit = None
            try:
                kit = await BrandService.get_brand_kit(db, brand.id, tenant_id)
            except Exception:
                kit = None

            kb_models = dict(brief.key_benefits) if isinstance(brief.key_benefits, dict) else {}
            brief_dict = enrich_brief_with_brand(
                {
                    "title": brief.title,
                    "product_name": brief.product_name,
                    "objective": brief.objective,
                    "target_audience": brief.target_audience,
                    "ad_copy_tone": brief.ad_copy_tone,
                    "cta": brief.cta,
                    "key_benefits": kb_models,
                    "formats": brief.formats,
                },
                brand,
                kit,
            )
            snap = brand_snapshot(brand, kit)

            params = dict(variant.generation_params or {})
            pipeline = dict(params.get("pipeline") or {})
            models = dict(params.get("models") or {})
            image_plan = dict(params.get("image_plan") or {})
            fmt = variant.format or "static"
            chosen_model = (
                (image_model or "").strip()
                or str(models.get("image") or "").strip()
                or str(kb_models.get("image_model") or "").strip()
                or "gen4_image"
            )

            # Prefer saved slot prompt → last failed prompt → rebuild from copy.
            slot_prompt = str(image_plan.get("prompt") or "").strip()
            prior_image = pipeline.get("image") if isinstance(pipeline.get("image"), dict) else {}
            prior_prompt = str((prior_image or {}).get("prompt") or "").strip()

            variant_index = int(image_plan.get("variant_index") or 0)
            image_variants = [
                sv
                for sv in (kb_models.get("image_variants") or [])
                if isinstance(sv, dict)
            ]
            slot: dict[str, Any] | None = None
            if image_variants:
                if 0 <= variant_index < len(image_variants):
                    slot = image_variants[variant_index]
                if slot is None:
                    want_hook = (variant.hook or "").strip()
                    for sv in image_variants:
                        if str(sv.get("hook") or "").strip() == want_hook and want_hook:
                            slot = sv
                            break
                if slot is None:
                    want_idx = int(image_plan.get("carousel_index") or 0)
                    if want_idx:
                        for sv in image_variants:
                            try:
                                if int(sv.get("carousel_index") or 0) == want_idx:
                                    slot = sv
                                    break
                            except (TypeError, ValueError):
                                continue

            if slot and str(slot.get("prompt") or "").strip():
                slot_prompt = str(slot.get("prompt") or "").strip()

            carousel_slots = [
                sv
                for sv in image_variants
                if str(sv.get("format") or "").strip().lower() == "carousel"
            ]
            carousel_last = fmt != "carousel" or _is_last_carousel_card(
                slot, carousel_slots or image_variants
            )

            on_image_hook = str(
                image_plan.get("image_hook")
                or (slot or {}).get("image_hook")
                or ""
            ).strip()
            on_image_headline = str(
                image_plan.get("image_headline")
                or (slot or {}).get("image_headline")
                or ""
            ).strip()
            if not on_image_hook or not on_image_headline:
                derived_h, derived_m = _related_image_lines(
                    variant.hook or "", variant.headline or ""
                )
                on_image_hook = on_image_hook or derived_h
                on_image_headline = on_image_headline or derived_m

            effective_cta = ""
            if fmt != "carousel" or carousel_last:
                effective_cta = str(
                    (slot or {}).get("cta")
                    or image_plan.get("cta")
                    or variant.cta
                    or brief.cta
                    or ""
                ).strip()

            industry = str(
                kb_models.get("industry")
                or brief_dict.get("target_industry_label")
                or brand.industry
                or ""
            )
            niche = str(
                kb_models.get("niche")
                or brief_dict.get("niche")
                or brief.product_name
                or ""
            )
            from app.services.social_style_service import resolve_effective_brand_colors

            brand_primary, brand_secondary = resolve_effective_brand_colors(
                primary_color=str(snap.get("primary_color") or ""),
                secondary_color=str(snap.get("secondary_color") or ""),
                social_style_profile=snap.get("social_style_profile"),
            )

            slot_photo_only = bool(isinstance(slot, dict) and slot.get("photo_only"))
            if slot_photo_only:
                on_image_hook = ""
                on_image_headline = ""
                effective_cta = ""

            base_prompt = slot_prompt or prior_prompt
            if slot_photo_only and base_prompt:
                ratio = brief_dict.get("image_aspect_ratio") or kb_models.get("image_aspect_ratio") or "4:3"
                image_prompt = enforce_fashion_retail_photo_in_prompt(
                    base_prompt, aspect_ratio=ratio
                )
                image_prompt = enforce_no_spurious_circled_paper_prop(
                    image_prompt, industry=industry, niche=niche
                )
            elif fmt == "carousel" and not carousel_last:
                # Middle/opener cards: no CTA pill, but DO burn hook/headline.
                image_prompt = enforce_on_image_copy_in_prompt(
                    strip_burned_in_copy_from_prompt(
                        base_prompt or "", allow_cta=True
                    ),
                    image_hook=on_image_hook,
                    image_headline=on_image_headline,
                    cta="",
                    full_hook=variant.hook or "",
                    full_headline=variant.headline or "",
                    industry=industry,
                    niche=niche,
                    primary_color=brand_primary,
                )
                image_prompt = enforce_no_spurious_circled_paper_prop(
                    image_prompt, industry=industry, niche=niche
                )
            elif base_prompt:
                image_prompt = enforce_on_image_copy_in_prompt(
                    strip_burned_in_copy_from_prompt(base_prompt, allow_cta=True),
                    image_hook=on_image_hook,
                    image_headline=on_image_headline,
                    cta=effective_cta,
                    full_hook=variant.hook or "",
                    full_headline=variant.headline or "",
                    industry=industry,
                    niche=niche,
                    primary_color=brand_primary,
                )
                image_prompt = enforce_no_spurious_circled_paper_prop(
                    image_prompt, industry=industry, niche=niche
                )
            else:
                image_prompt = build_image_prompt(
                    brand=snap,
                    brief=brief_dict,
                    copy={
                        "hook": on_image_hook or variant.hook,
                        "headline": on_image_headline or variant.headline,
                        "cta": effective_cta,
                        "body_copy": variant.body_copy or "",
                    },
                    format_type=fmt,
                )
                image_prompt = enforce_on_image_copy_in_prompt(
                    image_prompt,
                    image_hook=on_image_hook,
                    image_headline=on_image_headline,
                    cta=effective_cta,
                    full_hook=variant.hook or "",
                    full_headline=variant.headline or "",
                    industry=industry,
                    niche=niche,
                    primary_color=brand_primary,
                )

            img_logo, img_logo_light = resolve_video_logo_urls(brand=snap, brief=brief_dict)
            burn_logo = fmt not in {"reel", "video"}

            pipeline["image"] = {
                "status": "generating",
                "model": chosen_model,
                "prompt": image_prompt[:500],
            }
            params["pipeline"] = pipeline
            models["image"] = chosen_model
            params["models"] = models
            if slot_prompt:
                image_plan["prompt"] = slot_prompt
            image_plan["image_hook"] = on_image_hook or None
            image_plan["image_headline"] = on_image_headline or None
            image_plan["cta"] = effective_cta or None
            if slot:
                image_plan["carousel_index"] = slot.get("carousel_index")
                image_plan["carousel_total"] = slot.get("carousel_total")
            params["image_plan"] = image_plan
            variant.generation_params = params
            variant.status = "GENERATING"
            await db.commit()

            logger.info(
                "Regenerate image start variant=%s model=%s prompt_len=%d "
                "format=%s carousel_last=%s cta=%r",
                variant_id,
                chosen_model,
                len(image_prompt),
                fmt,
                carousel_last,
                effective_cta,
            )

            slot_cta = str((slot or {}).get("cta") or effective_cta or "").strip()
            slot_hook = str((slot or {}).get("hook") or variant.hook or "").strip()
            slot_message = str((slot or {}).get("message") or variant.headline or "").strip()
            regen_copy = {
                "hook": slot_hook or variant.hook or "",
                "headline": slot_message or variant.headline or "",
                "body_copy": variant.body_copy or "",
                "cta": effective_cta or slot_cta,
            }
            slot_product_focus = (
                str(slot.get("product_focus") or "").strip()
                if isinstance(slot, dict)
                else ""
            ) or str(
                kb_models.get("product_focus")
                or brief_dict.get("product_focus")
                or ""
            ).strip()
            slot_product_model = (
                str(slot.get("product_model") or "").strip()
                if isinstance(slot, dict)
                else ""
            )
            if slot_product_focus:
                from app.services.icp_image_plan_service import enforce_product_focus_in_prompt

                image_prompt = enforce_product_focus_in_prompt(
                    image_prompt,
                    product_focus=slot_product_focus,
                    product_model=slot_product_model,
                    industry=industry,
                    niche=niche,
                )
            campaign_on_image_style = str(
                kb_models.get("on_image_style")
                or brief_dict.get("on_image_style")
                or "auto"
            ).strip()
            if campaign_on_image_style:
                from app.services.icp_image_plan_service import enforce_on_image_style_in_prompt

                image_prompt = enforce_on_image_style_in_prompt(
                    image_prompt,
                    on_image_style=campaign_on_image_style,
                    niche=niche,
                    industry=industry,
                    fashion_retail_promo=False,
                    primary_color=brand_primary,
                    secondary_color=brand_secondary,
                    font_heading=str(snap.get("font_heading") or ""),
                    font_body=str(snap.get("font_body") or ""),
                )
            image_prompt = _append_social_style_to_prompt(image_prompt, snap)
            image_prompt = _lock_brand_name_on_prompt(
                image_prompt, snap=snap, brief_dict=brief_dict, brand=brand
            )
            if fmt in {"static", "carousel"} and not slot_photo_only:
                image_prompt = _finalize_burn_in_prompt(
                    image_prompt,
                    fmt=fmt,
                    carousel_last=carousel_last,
                    slot=slot,
                    copy=regen_copy,
                    brief_dict=brief_dict,
                    brief_cta=str(brief.cta or ""),
                    on_image_hook=on_image_hook,
                    on_image_message=on_image_headline,
                    slot_cta=slot_cta,
                    slot_hook=slot_hook,
                    slot_message=slot_message,
                    industry=industry,
                    niche=niche,
                    primary_color=brand_primary,
                )
                logger.info(
                    "Regenerate final burn-in variant=%s cta=%r prompt_len=%d",
                    variant_id,
                    effective_cta or slot_cta,
                    len(image_prompt),
                )
                image_prompt = consolidate_image_prompt_for_generation(
                    image_prompt,
                    scene_prompt=slot_prompt,
                    image_hook=on_image_hook,
                    image_headline=on_image_headline,
                    cta=effective_cta or slot_cta,
                    primary_color=brand_primary,
                    secondary_color=brand_secondary,
                    brand_name=str(snap.get("brand_name") or brand.name or ""),
                    product_focus=str(slot.get("product_focus") or "").strip()
                    if isinstance(slot, dict)
                    else "",
                    niche=niche,
                    industry=industry,
                )
            image_result = await ai_service.generate_image_asset(
                prompt=image_prompt,
                tenant_id=str(tenant_id),
                model=chosen_model,
                format_type=fmt,
                logo_url=img_logo if burn_logo else None,
                logo_on_light_url=img_logo_light if burn_logo else None,
            )

            # Re-load in case of concurrent edits
            variant = await VariantService.get_variant(db, variant_id, tenant_id)
            params = dict(variant.generation_params or {})
            pipeline = dict(params.get("pipeline") or {})
            pipeline["image"] = image_result
            params["pipeline"] = pipeline
            models = dict(params.get("models") or {})
            models["image"] = chosen_model
            params["models"] = models
            variant.generation_params = params

            ok = (
                isinstance(image_result, dict)
                and image_result.get("status") in {"done", "mock"}
                and bool(image_result.get("url"))
            )
            variant.status = "READY" if ok else "FAILED"
            await db.commit()
            logger.info(
                "Regenerate image done variant=%s status=%s image=%s",
                variant_id,
                variant.status,
                image_result.get("status") if isinstance(image_result, dict) else "?",
            )
        except Exception:
            logger.exception("Regenerate image failed variant=%s", variant_id)
            try:
                variant = await VariantService.get_variant(db, variant_id, tenant_id)
                params = dict(variant.generation_params or {})
                pipeline = dict(params.get("pipeline") or {})
                prev = pipeline.get("image") if isinstance(pipeline.get("image"), dict) else {}
                pipeline["image"] = {
                    **(prev or {}),
                    "status": "failed",
                    "url": None,
                    "error": "Image regeneration failed — check model settings / Runway credits, then retry.",
                }
                params["pipeline"] = pipeline
                variant.generation_params = params
                variant.status = "FAILED"
                await db.commit()
            except Exception:
                logger.exception("Could not mark variant %s failed after regenerate error", variant_id)

