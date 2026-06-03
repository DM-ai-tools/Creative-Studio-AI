import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.brief import Brief
from app.models.variant import Variant
from app.schemas.brief import BriefCreate, BriefResponse, BriefUpdate, GenerationRequest
from app.services.ai_service import ai_service
from app.services.brand_prompt import brand_snapshot, build_image_prompt, enrich_brief_with_brand
from app.services.brand_service import BrandService
from app.services.brief_service import BriefService
from app.services.cta_defaults import resolve_campaign_cta
from app.services.pdf_script_extract import extract_text_from_pdf_bytes
from app.services.video_duration import (
    apply_video_settings_to_brief,
    requested_video_duration_seconds,
    resolve_video_duration_seconds,
)
from pydantic import BaseModel

router = APIRouter(prefix="/briefs", tags=["briefs"])
logger = logging.getLogger(__name__)


class ScriptPdfUploadResponse(BaseModel):
    character_count: int
    preview: str
    filename: str


@router.post("/", response_model=BriefResponse, status_code=201)
async def create_brief(
    data: BriefCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await BriefService.create_brief(db, current_user.tenant_id, current_user.id, data)


@router.get("/", response_model=list[BriefResponse])
async def list_briefs(
    status: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await BriefService.list_briefs(db, current_user.tenant_id, status, limit, offset)


@router.get("/{brief_id}", response_model=BriefResponse)
async def get_brief(
    brief_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await BriefService.get_brief(db, brief_id, current_user.tenant_id)


@router.put("/{brief_id}", response_model=BriefResponse)
async def update_brief(
    brief_id: UUID,
    data: BriefUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await BriefService.update_brief(db, brief_id, current_user.tenant_id, data)


@router.delete("/{brief_id}", status_code=204)
async def delete_brief(
    brief_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await BriefService.delete_brief(db, brief_id, current_user.tenant_id)


@router.post("/{brief_id}/submit", response_model=BriefResponse)
async def submit_brief(
    brief_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await BriefService.submit_brief(db, brief_id, current_user.tenant_id)


@router.post("/{brief_id}/script-pdf", response_model=ScriptPdfUploadResponse)
async def upload_script_pdf(
    brief_id: UUID,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract full script from PDF; HeyGen uses this as the only spoken script (avatar + voice from UI)."""
    brief = await BriefService.get_brief(db, brief_id, current_user.tenant_id)
    fname = (file.filename or "").strip().lower()
    if not fname.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    body = await file.read()
    try:
        text = extract_text_from_pdf_bytes(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    kb = dict(brief.key_benefits) if isinstance(brief.key_benefits, dict) else {}
    kb["script_source"] = "pdf"
    kb["pdf_filename"] = file.filename or "script.pdf"
    kb["pdf_script_text"] = text
    kb["avatar_script"] = text
    brief.key_benefits = kb
    await db.commit()
    await db.refresh(brief)
    preview = text[:500] + ("…" if len(text) > 500 else "")
    return ScriptPdfUploadResponse(
        character_count=len(text),
        preview=preview,
        filename=str(kb.get("pdf_filename") or "script.pdf"),
    )


@router.delete("/{brief_id}/script-pdf", response_model=BriefResponse)
async def clear_script_pdf(
    brief_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    brief = await BriefService.get_brief(db, brief_id, current_user.tenant_id)
    kb = dict(brief.key_benefits) if isinstance(brief.key_benefits, dict) else {}
    for key in ("pdf_filename", "pdf_script_text", "avatar_script"):
        kb.pop(key, None)
    kb["script_source"] = "manual"
    brief.key_benefits = kb
    await db.commit()
    return await BriefService.get_brief(db, brief_id, current_user.tenant_id)


class ProductionScriptPreview(BaseModel):
    skeleton: str
    spoken_script: str
    veo_prompt: str


@router.get("/{brief_id}/production-script", response_model=ProductionScriptPreview)
async def preview_production_script(
    brief_id: UUID,
    format_type: str = Query("reel"),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Preview filled 30s skeleton before generating video."""
    from app.services.video_script_skeleton import (
        build_veo_prompt_from_skeleton,
        ensure_production_skeleton,
        extract_heygen_spoken_script,
    )

    brief = await BriefService.get_brief(db, brief_id, current_user.tenant_id)
    brand = await BrandService.get_brand(db, brief.brand_id, current_user.tenant_id)
    kit = None
    try:
        kit = await BrandService.get_brand_kit(db, brand.id, current_user.tenant_id)
    except HTTPException:
        kit = None

    brief_dict = enrich_brief_with_brand(
        {
            "product_name": brief.product_name,
            "objective": brief.objective,
            "target_audience": brief.target_audience,
            "ad_copy_tone": brief.ad_copy_tone,
            "cta": resolve_campaign_cta({"cta": brief.cta, "key_benefits": brief.key_benefits}),
            "key_benefits": brief.key_benefits,
        },
        brand,
        kit,
    )
    brief_dict = apply_video_settings_to_brief(brief_dict)
    duration = resolve_video_duration_seconds(brief_dict)
    copy = {
        "hook": brief.product_name or "",
        "headline": brief.objective or "",
        "body_copy": "",
        "cta": brief_dict.get("cta") or "Learn more",
    }
    skeleton = await ensure_production_skeleton(
        brief_dict,
        copy,
        duration=duration,
        format_type=format_type,
        force_refresh=True,
    )
    spoken = extract_heygen_spoken_script(skeleton, target_seconds=duration)
    veo = build_veo_prompt_from_skeleton(
        skeleton,
        brief=brief_dict,
        copy=copy,
        format_type=format_type,
        duration=duration,
    )
    return ProductionScriptPreview(skeleton=skeleton, spoken_script=spoken, veo_prompt=veo)


@router.post("/{brief_id}/generate")
async def generate_variants(
    brief_id: UUID,
    data: GenerationRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    brief = await BriefService.get_brief(db, brief_id, current_user.tenant_id)
    brand = await BrandService.get_brand(db, brief.brand_id, current_user.tenant_id)

    formats = data.formats or brief.formats or ["static"]
    kb_models = dict(brief.key_benefits) if isinstance(brief.key_benefits, dict) else {}

    count_per_format = data.count_per_format
    target_count = kb_models.get("target_variant_count")
    if target_count:
        try:
            count_per_format = max(1, round(int(target_count) / len(formats)))
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    brief.status = "RUNNING"
    brief.variant_count = len(formats) * count_per_format
    brief.completed_variants = 0
    await db.commit()
    logger.info(
        "Brief %s generation started: %s formats × %s (video_model=%s)",
        brief_id,
        formats,
        count_per_format,
        data.video_model or kb_models.get("video_model"),
    )

    kit = None
    try:
        kit = await BrandService.get_brand_kit(db, brand.id, current_user.tenant_id)
    except HTTPException:
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
        duration_override=data.video_duration_seconds or kb_models.get("video_duration_seconds"),
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
        kb_models = {**kb_models, "higgsfield_voice_preset": data.higgsfield_voice_preset}
    if kb_models != brief.key_benefits:
        brief.key_benefits = kb_models
        brief_dict["key_benefits"] = kb_models
    image_model = data.image_model or kb_models.get("image_model") or "nano-banana-2"
    video_model = data.video_model or kb_models.get("video_model") or "veo-3.1"
    vm = (video_model or "").strip().lower()
    uses_heygen_video = vm == "heygen" or vm.startswith("heygen-") or vm.startswith("heygen_")
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
    try:
        for fmt in formats:
            for _ in range(count_per_format):
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

                # HeyGen Video Agent builds the full video (avatar + B-roll) — no Runway still needed.
                skip_image_for_heygen = uses_heygen_video and fmt in {"reel", "video"}
                if skip_image_for_heygen:
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
                    # Video/reel: logo is burned once on the final MP4 (finalize), not on the seed still.
                    burn_logo_on_still = fmt not in {"reel", "video"}
                    pipeline["image"] = await ai_service.generate_image_asset(
                        prompt=image_prompt,
                        tenant_id=str(current_user.tenant_id),
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
                    # Resolve on_light logo from kit logo_variations if not on snap root
                    _vid_on_light = snap.get("logo_on_light_url") or brief_dict.get("logo_on_light_url")
                    if not _vid_on_light and isinstance(snap.get("logo_variations"), dict):
                        _vid_on_light = snap["logo_variations"].get("on_light")
                    if not _vid_on_light and isinstance(kit and kit.logo_variations, dict):
                        _vid_on_light = kit.logo_variations.get("on_light")

                    pipeline["video"] = await ai_service.generate_video_storyboard(
                        brief=brief_dict,
                        copy=copy,
                        format_type=fmt,
                        model=video_model,
                        tenant_id=str(current_user.tenant_id),
                        source_image_url=image_url,
                        duration_seconds=data.video_duration_seconds or video_duration,
                        logo_url=snap.get("logo_url") or brief_dict.get("logo_url"),
                        logo_on_light_url=_vid_on_light,
                    )
                else:
                    pipeline["video"] = {"status": "skipped", "model": video_model}

                motion_format = fmt in {"reel", "video"}
                video_step = pipeline.get("video") if isinstance(pipeline.get("video"), dict) else {}
                video_ok = (
                    video_step.get("status") == "done"
                    and bool(video_step.get("url"))
                )
                if motion_format and not video_ok:
                    variant_status = "FAILED"
                    any_failed_motion = True
                else:
                    variant_status = "READY"

                variant = Variant(
                    brief_id=brief.id,
                    brand_id=brand.id,
                    tenant_id=current_user.tenant_id,
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
                video_err = (
                    video_step.get("error") if isinstance(video_step, dict) else None
                )
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
        return {"message": "Generation complete", "variants_created": created}

    except Exception as exc:
        logger.exception("Brief %s generation failed after %s variants", brief_id, created)
        brief.status = "FAILED" if created == 0 else "PARTIAL"
        brief.completed_variants = created
        await db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Generation stopped: {exc!s}. {created} variant(s) may have been saved — refresh the brief.",
        ) from exc
