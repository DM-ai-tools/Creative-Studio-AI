from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.brand import BrandCreate, BrandKitCreate, BrandKitResponse, BrandResponse, BrandUpdate
from app.services.brand_service import BrandService
from app.services.file_service import file_service

router = APIRouter(prefix="/brands", tags=["brands"], redirect_slashes=False)


@router.post("", response_model=BrandResponse, status_code=201, include_in_schema=False)
@router.post("/", response_model=BrandResponse, status_code=201)
async def create_brand(
    data: BrandCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await BrandService.create_brand(db, current_user.tenant_id, data)


@router.get("", response_model=list[BrandResponse], include_in_schema=False)
@router.get("/", response_model=list[BrandResponse])
async def list_brands(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await BrandService.list_brands(db, current_user.tenant_id)


@router.get("/{brand_id}", response_model=BrandResponse)
async def get_brand(
    brand_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await BrandService.get_brand(db, brand_id, current_user.tenant_id)


@router.post("/{brand_id}/logo", response_model=BrandResponse)
async def upload_brand_logo(
    brand_id: UUID,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await BrandService.get_brand(db, brand_id, current_user.tenant_id)
    saved = await file_service.save_file(file, str(current_user.tenant_id), "brand")
    return await BrandService.update_brand(
        db,
        brand_id,
        current_user.tenant_id,
        BrandUpdate(logo_url=saved["file_url"]),
    )


@router.post("/{brand_id}/logo/on-light", response_model=BrandKitResponse)
async def upload_brand_logo_on_light(
    brand_id: UUID,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Logo with dark text for white/light ad backgrounds (optional; auto-adjust also applied)."""
    await BrandService.get_brand(db, brand_id, current_user.tenant_id)
    saved = await file_service.save_file(file, str(current_user.tenant_id), "brand")
    try:
        kit = await BrandService.get_brand_kit(db, brand_id, current_user.tenant_id)
        variations = dict(kit.logo_variations or {})
        variations["on_light"] = saved["file_url"]
        return await BrandService.update_brand_kit(
            db,
            kit.id,
            current_user.tenant_id,
            BrandKitCreate(
                name=kit.name,
                colors=kit.colors or {},
                fonts=kit.fonts or {},
                logo_variations=variations,
                guidelines_url=kit.guidelines_url,
            ),
        )
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        return await BrandService.create_brand_kit(
            db,
            brand_id,
            current_user.tenant_id,
            BrandKitCreate(logo_variations={"on_light": saved["file_url"]}),
        )


@router.put("/{brand_id}", response_model=BrandResponse)
async def update_brand(
    brand_id: UUID,
    data: BrandUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await BrandService.update_brand(db, brand_id, current_user.tenant_id, data)


class FetchSocialStyleRequest(BaseModel):
    handle_or_url: str = Field(..., min_length=2, description="Instagram/Facebook URL or @handle")
    platform: str = Field(default="", description="instagram | facebook — auto-detected from URL if empty")


class FetchSocialStyleResponse(BaseModel):
    brand_id: str
    social_style_profile: dict
    message: str = "Social style saved to Brand Kit for AI image prompts."


@router.post("/{brand_id}/fetch-social-style", response_model=FetchSocialStyleResponse)
async def fetch_brand_social_style(
    brand_id: UUID,
    data: FetchSocialStyleRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    One-time SociaVault fetch: pull public posts from Instagram/Facebook,
    analyze visual ad style, store in brand.voice_rules.social_style_profile.
    """
    from app.services.social_style_service import fetch_and_analyze_social_style
    from app.services.usage_tracker import record_sociavault

    brand = await BrandService.get_brand(db, brand_id, current_user.tenant_id)
    try:
        profile = await fetch_and_analyze_social_style(
            platform=data.platform,
            handle_or_url=data.handle_or_url.strip(),
            brand_name=brand.name,
        )
    except ValueError as exc:
        record_sociavault(success=False, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        record_sociavault(success=False, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Could not fetch social style: {exc}") from exc

    voice_rules = dict(brand.voice_rules or {})
    voice_rules["social_style_profile"] = profile
    voice_rules["social_style_fetched_at"] = profile.get("fetched_at")
    updated = await BrandService.update_brand(
        db,
        brand_id,
        current_user.tenant_id,
        BrandUpdate(voice_rules=voice_rules),
    )
    record_sociavault(
        success=True,
        platform=str(profile.get("platform") or ""),
        handle=str(profile.get("handle") or ""),
        post_count=int(profile.get("post_count_analyzed") or 0),
    )
    return FetchSocialStyleResponse(
        brand_id=str(updated.id),
        social_style_profile=profile,
    )


@router.delete("/{brand_id}", status_code=204)
async def delete_brand(
    brand_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await BrandService.delete_brand(db, brand_id, current_user.tenant_id)


@router.post("/{brand_id}/kit", response_model=BrandKitResponse, status_code=201)
async def create_kit(
    brand_id: UUID,
    data: BrandKitCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await BrandService.create_brand_kit(db, brand_id, current_user.tenant_id, data)


@router.get("/{brand_id}/kit", response_model=BrandKitResponse)
async def get_kit(
    brand_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await BrandService.get_brand_kit(db, brand_id, current_user.tenant_id)


@router.put("/{brand_id}/kit/{kit_id}", response_model=BrandKitResponse)
async def update_kit(
    brand_id: UUID,
    kit_id: UUID,
    data: BrandKitCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await BrandService.update_brand_kit(db, kit_id, current_user.tenant_id, data)
