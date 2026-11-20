from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.product_scope import require_full_studio_access
from app.core.security import get_current_user
from app.services.usage_allowance import require_usage_allowance
from app.schemas.variant import VariantResponse, VariantUpdate, slim_generation_params_for_list
from app.services.ai_service import ai_service
from app.services.brand_prompt import enrich_brief_with_brand
from app.services.brand_service import BrandService
from app.services.brief_service import BriefService
from app.services.generation_job import run_regenerate_variant_image
from app.services.variant_service import VariantService

router = APIRouter(prefix="/variants", tags=["variants"], redirect_slashes=False)


class RegenerateImageRequest(BaseModel):
    """Optional override — otherwise reuses the model stored on the variant / brief."""
    image_model: str | None = Field(default=None, description="Image model id from catalog")


class CreateFromMediaRequest(BaseModel):
    """Save a Creative Studio (or other) media URL as a Variant library row."""
    media_url: str
    media_mode: str = Field(default="video", description="image | video")
    aspect: str = "9/16"
    model: str = "creative-studio"
    prompt: str = ""
    duration_seconds: int | None = None
    seed_image_url: str | None = None
    brief_id: UUID | None = None
    brand_id: UUID | None = None
    brief_title: str | None = None
    product_name: str = ""


@router.post("/from-media", response_model=VariantResponse)
async def create_variant_from_media(
    data: CreateFromMediaRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Attach a finished Creative Studio image/video to the Variants page."""
    variant = await VariantService.create_from_creative_studio(
        db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        brief_id=data.brief_id,
        brand_id=data.brand_id,
        media_url=data.media_url,
        media_mode=data.media_mode,
        aspect=data.aspect,
        model=data.model,
        prompt=data.prompt,
        duration_seconds=data.duration_seconds,
        seed_image_url=data.seed_image_url,
        brief_title=data.brief_title,
        product_name=data.product_name,
    )
    await db.commit()
    await db.refresh(variant)
    return _to_variant_response(variant, slim=False)



def _to_variant_response(variant, *, slim: bool = False) -> VariantResponse:
    data = VariantResponse.model_validate(variant)
    if slim:
        data.generation_params = slim_generation_params_for_list(data.generation_params)
    if data.compliance_notes is None:
        data.compliance_notes = {}
    if data.hashtags is None:
        data.hashtags = []
    return data


@router.get("/fatigue-alerts")
async def fatigue_alerts(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await VariantService.get_fatigue_alerts(db, current_user.tenant_id)


@router.get("", response_model=list[VariantResponse], include_in_schema=False)
@router.get("/", response_model=list[VariantResponse])
async def list_variants(
    brief_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    compliance_status: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await VariantService.list_variants(
        db,
        current_user.tenant_id,
        brief_id,
        status,
        compliance_status,
        limit,
        offset,
    )
    # Slim payloads so Variant Library stays fast (full prompts stay on get-by-id).
    return [_to_variant_response(v, slim=True) for v in rows]


@router.get("/{variant_id}", response_model=VariantResponse)
async def get_variant(
    variant_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    variant = await VariantService.get_variant(db, variant_id, current_user.tenant_id)
    return _to_variant_response(variant, slim=False)


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
    require_full_studio_access(current_user)
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


class PlaceLogoRequest(BaseModel):
    corner: str = Field(min_length=1, max_length=20, description="top_left … bottom_center, center, auto or none")
    backing: str = Field(default="", max_length=10, description="'' plain, 'plate' (white plate behind the logo) or 'bar' (logo in a new strip)")


@router.post("/{variant_id}/place-logo", response_model=VariantResponse)
async def place_variant_logo(
    variant_id: UUID,
    data: PlaceLogoRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Put the real Brand Kit logo on a finished still, exactly where the user chose. No AI, no credits.

    Always starts from the picture without a logo, so the position can be changed again and again, and
    the logo is never moved off the chosen spot (the user is looking at the picture and decides)."""
    import asyncio

    from app.services import ad_image_logo as ad_logo
    from app.services.brand_logo import resolve_video_logo_urls
    from app.services.brand_prompt import brand_snapshot
    from app.services.creative_studio_still_logo import CORNER_LABELS, place_logo_in_corner

    variant = await VariantService.get_variant(db, variant_id, current_user.tenant_id)
    if (variant.format or "static") in {"reel", "video"}:
        raise HTTPException(status_code=400, detail="Logo placement here is for still images only")
    backing = (data.backing or "").strip().lower()
    if backing not in {"", "over", "plate", "bar"}:
        raise HTTPException(status_code=422, detail="Logo style must be smart, over, plate or bar")
    mode = ad_logo.normalize_mode(data.corner)
    if not mode:
        raise HTTPException(status_code=422, detail="Choose a corner, a centre position, auto or none")

    params = dict(variant.generation_params or {})
    pipeline = dict(params.get("pipeline") or {})
    image = dict(pipeline.get("image") or {})
    url = str(image.get("url") or "")
    plain = str(image.get("url_without_logo") or (url if not image.get("logo_applied") else ""))
    if not plain.startswith("/files/"):
        raise HTTPException(
            status_code=400,
            detail="This image was made with the old white logo strip, so the logo cannot be moved. Regenerate it with a logo position chosen.",
        )

    if mode == ad_logo.NONE:
        image.update({"url": plain, "url_without_logo": plain, "logo_applied": False, "logo_corner": ad_logo.NONE, "logo_manual": True, "warnings": []})
        image.pop("logo_corner_label", None)
    else:
        brand = await BrandService.get_brand(db, variant.brand_id, current_user.tenant_id)
        try:
            kit = await BrandService.get_brand_kit(db, brand.id, current_user.tenant_id)
        except Exception:
            kit = None
        logo, logo_light = resolve_video_logo_urls(brand=brand_snapshot(brand, kit), tenant_id=str(current_user.tenant_id))
        if not logo:
            raise HTTPException(status_code=400, detail="No Brand Kit logo found. Upload a PNG or JPG logo in the Brand Kit.")
        try:
            placed = await asyncio.to_thread(
                place_logo_in_corner,
                image_url=plain,
                corner=mode,
                tenant_id=str(current_user.tenant_id),
                logo_url=logo,
                logo_on_light_url=logo_light,
                avoid_text=False,  # the user chose this spot: the logo goes exactly there
                backing=backing,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        image.update(
            {
                "url": placed["url"],
                "url_without_logo": plain,
                "logo_applied": True,
                "logo_corner": placed["corner"],
                "logo_corner_label": CORNER_LABELS[placed["corner"]],
                "logo_auto": placed["auto"],
                "logo_manual": True,
                "logo_backing": backing,
                "logo_background": placed["background"],
                "logo_version": placed["logo_version"],
                "warnings": placed["warnings"],
            }
        )
    pipeline["image"] = image
    params["pipeline"] = pipeline
    return await VariantService.update_variant(
        db, variant_id, current_user.tenant_id, VariantUpdate(generation_params=params)
    )


@router.post("/{variant_id}/regenerate-image", response_model=VariantResponse, dependencies=[Depends(require_usage_allowance)])
async def regenerate_variant_image(
    variant_id: UUID,
    background_tasks: BackgroundTasks,
    data: RegenerateImageRequest = RegenerateImageRequest(),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retry ONLY this variant's image — keeps copy/hook/CTA and does not touch other variants.
    Runs in the background; poll the variant until status is READY or FAILED.
    """
    require_full_studio_access(current_user)
    variant = await VariantService.get_variant(db, variant_id, current_user.tenant_id)
    if variant.format in {"reel", "video"}:
        raise HTTPException(
            status_code=400,
            detail="Use Generate video for reel/video variants. This endpoint retries still images only.",
        )
    if variant.status == "GENERATING":
        return _to_variant_response(variant)

    params = dict(variant.generation_params or {})
    pipeline = dict(params.get("pipeline") or {})
    prev_img = pipeline.get("image") if isinstance(pipeline.get("image"), dict) else {}
    pipeline["image"] = {
        **(prev_img or {}),
        "status": "generating",
        "url": None,
        "error": None,
    }
    params["pipeline"] = pipeline
    variant.generation_params = params
    variant.status = "GENERATING"
    await db.commit()
    await db.refresh(variant)

    background_tasks.add_task(
        run_regenerate_variant_image,
        variant_id=variant_id,
        tenant_id=current_user.tenant_id,
        image_model=data.image_model,
    )
    return _to_variant_response(variant)


@router.post("/{variant_id}/regenerate", response_model=VariantResponse, dependencies=[Depends(require_usage_allowance)])
async def regenerate_variant(
    variant_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_full_studio_access(current_user)
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
