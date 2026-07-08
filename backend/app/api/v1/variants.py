from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.variant import VariantResponse, VariantUpdate
from app.services.ai_service import ai_service
from app.services.brand_prompt import enrich_brief_with_brand
from app.services.brand_service import BrandService
from app.services.brief_service import BriefService
from app.services.variant_service import VariantService

router = APIRouter(prefix="/variants", tags=["variants"])


@router.get("/fatigue-alerts")
async def fatigue_alerts(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await VariantService.get_fatigue_alerts(db, current_user.tenant_id)


@router.get("/", response_model=list[VariantResponse])
async def list_variants(
    brief_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    compliance_status: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await VariantService.list_variants(db, current_user.tenant_id, brief_id, status, compliance_status)


@router.get("/{variant_id}", response_model=VariantResponse)
async def get_variant(
    variant_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await VariantService.get_variant(db, variant_id, current_user.tenant_id)


@router.delete("/{variant_id}", status_code=204)
async def delete_variant(
    variant_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await VariantService.delete_variant(db, variant_id, current_user.tenant_id)


@router.put("/{variant_id}", response_model=VariantResponse)
async def update_variant(
    variant_id: UUID,
    data: VariantUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await VariantService.update_variant(db, variant_id, current_user.tenant_id, data)


@router.post("/{variant_id}/approve", response_model=VariantResponse)
async def approve_variant(
    variant_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await VariantService.approve_variant(db, variant_id, current_user.tenant_id)


@router.post("/{variant_id}/reject", response_model=VariantResponse)
async def reject_variant(
    variant_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await VariantService.reject_variant(db, variant_id, current_user.tenant_id)


@router.post("/{variant_id}/fix-portrait", response_model=VariantResponse)
async def fix_variant_portrait(
    variant_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-process an existing reel/video to 1080x1920 (removes HeyGen letterboxing)."""
    import asyncio

    from app.services.video_portrait import normalize_video_file, should_normalize_format

    variant = await VariantService.get_variant(db, variant_id, current_user.tenant_id)
    if not should_normalize_format(variant.format):
        raise HTTPException(status_code=400, detail="Only reel or landscape video variants can be fixed")

    pipeline = dict(variant.generation_params or {})
    video_step = dict((pipeline.get("pipeline") or {}).get("video") or {})
    url = video_step.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Variant has no video file")

    fitted = await asyncio.to_thread(
        normalize_video_file,
        url,
        tenant_id=str(current_user.tenant_id),
        format_type=variant.format,
    )
    if not fitted:
        raise HTTPException(
            status_code=500,
            detail="Frame normalize failed — install ffmpeg and ensure VIDEO_PORTRAIT_NORMALIZE=true",
        )

    inner = dict(pipeline.get("pipeline") or {})
    inner["video"] = {**video_step, "url": fitted, "frame_normalized": True, "portrait_normalized": True}
    pipeline["pipeline"] = inner
    return await VariantService.update_variant(
        db,
        variant_id,
        current_user.tenant_id,
        VariantUpdate(generation_params=pipeline),
    )


@router.post("/{variant_id}/regenerate", response_model=VariantResponse)
async def regenerate_variant(
    variant_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    variant = await VariantService.get_variant(db, variant_id, current_user.tenant_id)
    brief = await BriefService.get_brief(db, variant.brief_id, current_user.tenant_id)
    brand = await BrandService.get_brand(db, variant.brand_id, current_user.tenant_id)

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
            "cta": brief.cta,
            "key_benefits": brief.key_benefits,
        },
        brand,
        kit,
    )
    voice = brief_dict.get("voice") or (
        brand.voice_rules.get("description", "") if brand.voice_rules else ""
    )

    copy = await ai_service.generate_ad_copy(
        brand_voice=voice,
        forbidden_words=brand.forbidden_words or [],
        brief=brief_dict,
        format_type=variant.format,
        model=variant.ai_model,
    )
    compliance = await ai_service.run_compliance_check(
        copy,
        brand.forbidden_words or [],
        brief_dict.get("target_industry_id") or brand.industry,
    )

    from app.schemas.variant import VariantUpdate as VU
    return await VariantService.update_variant(
        db, variant_id, current_user.tenant_id,
        VU(
            hook=copy.get("hook"),
            headline=copy.get("headline"),
            body_copy=copy.get("body_copy"),
            cta=copy.get("cta"),
            hashtags=copy.get("hashtags"),
            status="READY",
            compliance_status="PASSED" if compliance["passed"] else "FAILED",
            compliance_notes=compliance,
        ),
    )
