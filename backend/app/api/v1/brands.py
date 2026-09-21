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
    analyze visual ad style, store in Brand Kit (colors.social_style_profile) for this brand.
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

    await BrandService.persist_social_style_profile(db, brand, profile)
    updated = brand
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


class FetchCompetitorSocialRequest(BaseModel):
    handle_or_url: str = Field(..., min_length=2, description="Competitor Instagram/Facebook URL or @handle")
    platform: str = Field(default="", description="instagram | facebook — auto-detected from URL if empty")
    industry: str = Field(default="", description="Optional industry context for LLM analysis")
    niche: str = Field(default="", description="Optional niche context for LLM analysis")


class DiscoverCompetitorsRequest(BaseModel):
    handle_or_url: str = Field(
        default="",
        description="Client Instagram/Facebook URL or @handle — uses saved Brand Kit social profile if empty",
    )
    platform: str = Field(default="", description="instagram | facebook — auto-detected from URL if empty")
    industry: str = Field(default="", description="Optional industry context")
    niche: str = Field(default="", description="Optional niche / campaign context")
    geography: str = Field(default="", description="Optional service location")


class DiscoverCompetitorsResponse(BaseModel):
    brand_id: str
    competitor_candidates: list[dict]
    message: str = "Competitor suggestions saved — select one to analyze."


class FetchCompetitorSocialResponse(BaseModel):
    brand_id: str
    competitor_insight: dict
    competitor_social_insights: list[dict]
    message: str = "Competitor posting logic saved to Brand Kit."


@router.post("/{brand_id}/fetch-competitor-social", response_model=FetchCompetitorSocialResponse)
async def fetch_brand_competitor_social(
    brand_id: UUID,
    data: FetchCompetitorSocialRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    SociaVault fetch for a COMPETITOR account — extracts posting strategy (not visual identity),
    upserts into Brand Kit competitor_social_insights for this brand.
    """
    from app.services.competitor_social_service import (
        fetch_and_analyze_competitor_social,
        upsert_competitor_insight,
    )
    from app.services.brand_service import competitor_insights_from_brand_and_kit
    from app.services.usage_tracker import record_sociavault

    brand = await BrandService.get_brand(db, brand_id, current_user.tenant_id)
    kit = None
    try:
        kit = await BrandService.get_brand_kit(db, brand_id, current_user.tenant_id)
    except HTTPException:
        pass
    try:
        insight = await fetch_and_analyze_competitor_social(
            platform=data.platform,
            handle_or_url=data.handle_or_url.strip(),
            industry=data.industry,
            niche=data.niche,
        )
    except ValueError as exc:
        record_sociavault(success=False, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        record_sociavault(success=False, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Could not analyze competitor: {exc}") from exc

    existing = competitor_insights_from_brand_and_kit(brand, kit)
    merged = upsert_competitor_insight(existing, insight)
    await BrandService.persist_competitor_social_insights(db, brand, merged)

    from app.services.brand_service import competitor_candidates_from_brand_and_kit
    from app.services.competitor_social_service import _competitor_key

    analyzed_key = _competitor_key(
        str(insight.get("platform") or ""),
        str(insight.get("handle") or ""),
    )
    remaining_candidates = [
        c
        for c in competitor_candidates_from_brand_and_kit(brand, kit)
        if _competitor_key(str(c.get("platform") or ""), str(c.get("handle") or "")) != analyzed_key
    ]
    await BrandService.persist_competitor_candidates(db, brand, remaining_candidates)

    record_sociavault(
        success=True,
        platform=str(insight.get("platform") or ""),
        handle=str(insight.get("handle") or ""),
        post_count=int(insight.get("post_count_analyzed") or 0),
    )
    return FetchCompetitorSocialResponse(
        brand_id=str(brand.id),
        competitor_insight=insight,
        competitor_social_insights=merged,
    )


@router.post("/{brand_id}/discover-competitors", response_model=DiscoverCompetitorsResponse)
async def discover_brand_competitors(
    brand_id: UUID,
    data: DiscoverCompetitorsRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Optional: suggest competitor social pages from client context.
    Does NOT analyze posts — user selects a candidate then calls fetch-competitor-social.
    """
    from app.services.brand_service import (
        competitor_candidates_from_brand_and_kit,
        competitor_insights_from_brand_and_kit,
        social_style_from_brand_and_kit,
    )
    from app.services.competitor_discovery_service import discover_competitor_candidates

    brand = await BrandService.get_brand(db, brand_id, current_user.tenant_id)
    kit = None
    try:
        kit = await BrandService.get_brand_kit(db, brand_id, current_user.tenant_id)
    except HTTPException:
        pass

    client_url = (data.handle_or_url or "").strip()
    client_platform = (data.platform or "").strip()
    if not client_url:
        social = social_style_from_brand_and_kit(brand, kit)
        if social:
            client_url = str(social.get("profile_url") or social.get("handle") or "").strip()
            if client_url and not client_url.startswith("http"):
                client_url = f"@{client_url.lstrip('@')}"
            client_platform = client_platform or str(social.get("platform") or "")

    if not client_url:
        raise HTTPException(
            status_code=400,
            detail="Enter client Facebook/Instagram URL or fetch social style first.",
        )

    geography = (data.geography or "").strip()
    if not geography:
        raise HTTPException(
            status_code=400,
            detail="Set Service Location on the brief (e.g. Melbourne VIC) — competitors are limited to that area and nearby states.",
        )

    try:
        candidates = await discover_competitor_candidates(
            brand_name=brand.name,
            industry=(data.industry or brand.industry or "").strip(),
            niche=data.niche.strip(),
            geography=geography,
            client_handle_or_url=client_url,
            client_platform=client_platform,
            existing_insights=competitor_insights_from_brand_and_kit(brand, kit),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not discover competitors: {exc}") from exc

    await BrandService.persist_competitor_candidates(db, brand, candidates)
    return DiscoverCompetitorsResponse(
        brand_id=str(brand.id),
        competitor_candidates=candidates,
    )


class DeleteCompetitorSocialRequest(BaseModel):
    platform: str = Field(default="", description="instagram | facebook")
    handle: str = Field(..., min_length=1, description="Competitor handle without @")


@router.delete("/{brand_id}/competitor-social")
async def delete_brand_competitor_social(
    brand_id: UUID,
    handle: str,
    platform: str = "",
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove one saved competitor insight from Brand Kit."""
    from app.services.competitor_social_service import remove_competitor_insight
    from app.services.brand_service import competitor_insights_from_brand_and_kit

    brand = await BrandService.get_brand(db, brand_id, current_user.tenant_id)
    kit = None
    try:
        kit = await BrandService.get_brand_kit(db, brand_id, current_user.tenant_id)
    except HTTPException:
        pass
    existing = competitor_insights_from_brand_and_kit(brand, kit)
    merged = remove_competitor_insight(
        existing,
        platform=platform,
        handle=handle.strip().lstrip("@"),
    )
    await BrandService.persist_competitor_social_insights(db, brand, merged)
    return {
        "brand_id": str(brand.id),
        "competitor_social_insights": merged,
        "message": "Competitor removed from Brand Kit.",
    }


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
