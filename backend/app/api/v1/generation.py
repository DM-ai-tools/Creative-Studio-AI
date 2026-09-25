from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from uuid import UUID
import logging

import httpx

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.avatar_script import (
    AvatarScriptRequest,
    AvatarScriptResponse,
    IcpScriptRequest,
    IcpScriptResponse,
    MasterScriptPreviewRequest,
    MasterScriptPreviewResponse,
    MasterScriptBeat,
    StrategyPreviewRequest,
    StrategyPreviewResponse,
    StatsImageExtractionResponse,
    WebsiteScriptRequest,
    WebsiteScriptResponse,
)
from app.schemas.generation import GenerationCatalogResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.avatar_script_service import generate_avatar_script
from app.services.generation_catalog import get_generation_catalog
from app.services.icp_service import generate_icp_script
from app.services.model_suggestion_service import suggest_models
from app.services.stats_image_service import _guess_image_mime, extract_stats_from_image
from app.services.strategy_preview_service import generate_strategy_preview
from app.services.website_script_service import generate_website_script
from app.services.video_script_skeleton import (
    build_master_production_timeline,
    build_skeleton_context,
    build_veo_prompt_from_skeleton,
    ensure_production_skeleton,
    extract_heygen_spoken_script,
    render_skeleton,
)

router = APIRouter(prefix="/generation", tags=["generation"])


@router.get("/catalog", response_model=GenerationCatalogResponse)
async def generation_catalog(refresh: bool = False):
    return get_generation_catalog(refresh=refresh)


@router.post("/avatar-script", response_model=AvatarScriptResponse)
async def avatar_script(
    data: AvatarScriptRequest,
    _current_user=Depends(get_current_user),
):
    try:
        return await generate_avatar_script(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/master-script-preview", response_model=MasterScriptPreviewResponse)
async def master_script_preview(
    data: MasterScriptPreviewRequest,
    _current_user=Depends(get_current_user),
):
    """Unified timeline: voice + B-roll + stat images per beat (approve before generate)."""
    beats_raw, warnings = build_master_production_timeline(
        data.avatar_script,
        data.scene_broll_directions,
        duration=data.target_seconds,
        stats_per_image=data.performance_stats_per_image,
    )
    beats = [MasterScriptBeat(**b) for b in beats_raw]
    ready = bool(beats) and bool((data.avatar_script or "").strip())
    return MasterScriptPreviewResponse(beats=beats, warnings=warnings, ready=ready)


@router.post("/extract-stats-image", response_model=StatsImageExtractionResponse)
async def extract_stats_image(
    file: UploadFile = File(...),
    _current_user=Depends(get_current_user),
):
    """Read ROAS / ROI / conversion stats from a performance dashboard screenshot."""
    raw = await file.read()
    try:
        mime = _guess_image_mime(raw, file.filename or "", file.content_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        stats = await extract_stats_from_image(
            raw,
            mime_type=mime,
            filename=file.filename or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not analyze image: {e}")
    return StatsImageExtractionResponse(stats=stats, filename=file.filename or "")


class ReferenceImageAnalysisResponse(BaseModel):
    file_url: str | None = None
    asset_id: str | None = None
    analysis: dict
    summary: str = ""


class ProductReferenceRequest(BaseModel):
    source: str
    brand_id: str
    brand_name: str = ""
    niche: str = ""


class ProductReferenceResponse(ReferenceImageAnalysisResponse):
    source_url: str
    slug: str = ""


class HeroImageResponse(BaseModel):
    image_url: str = ""
    hook: str
    headline: str
    prompt: str


@router.post("/analyze-reference-image", response_model=ReferenceImageAnalysisResponse)
async def analyze_reference_image(
    file: UploadFile = File(...),
    brand_id: Optional[str] = Form(None),
    brand_name: str = Form(""),
    niche: str = Form(""),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Vision-parse a reference image; optionally persist to brand reference library."""
    from app.models.asset import Asset
    from app.services.brand_service import BrandService
    from app.services.file_service import file_service
    from app.services.media_content import image_suffix_and_type
    from app.services.reference_image_service import analyze_reference_image as analyze_ref

    raw = await file.read()
    if len(raw) > 12_000_000:
        raise HTTPException(status_code=400, detail="Image is too large (max 12MB)")
    try:
        mime = _guess_image_mime(raw, file.filename or "", file.content_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        analysis = await analyze_ref(
            raw,
            mime_type=mime,
            brand_name=brand_name.strip(),
            niche=niche.strip(),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not analyze reference image: {e}") from e

    summary = str(analysis.get("summary") or "").strip()
    file_url: str | None = None
    asset_id: str | None = None

    brand_uuid: UUID | None = None
    if (brand_id or "").strip():
        try:
            brand_uuid = UUID(brand_id.strip())
            await BrandService.get_brand(db, brand_uuid, current_user.tenant_id)
        except (ValueError, HTTPException):
            brand_uuid = None

    if brand_uuid:
        suffix, content_type = image_suffix_and_type(
            raw,
            fallback_suffix=(file.filename or "").rsplit(".", 1)[-1] if "." in (file.filename or "") else "",
        )
        saved = file_service.save_bytes(
            raw,
            str(current_user.tenant_id),
            "reference_image",
            suffix,
            content_type,
        )
        asset = Asset(
            tenant_id=current_user.tenant_id,
            brand_id=brand_uuid,
            asset_type="reference_image",
            created_by=current_user.id,
            asset_metadata={"analysis": analysis, "summary": summary},
            **saved,
        )
        db.add(asset)
        await db.flush()
        await db.refresh(asset)
        file_url = asset.file_url
        asset_id = str(asset.id)

    return ReferenceImageAnalysisResponse(
        file_url=file_url,
        asset_id=asset_id,
        analysis=analysis,
        summary=summary,
    )


@router.post("/product-reference", response_model=ProductReferenceResponse)
async def create_product_reference(
    data: ProductReferenceRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch and save one exact product image into the selected brand's kit."""
    from app.models.asset import Asset
    from app.services.brand_service import BrandService
    from app.services.file_service import file_service
    from app.services.product_reference_service import resolve_product_reference
    from app.services.reference_image_service import analyze_reference_image as analyze_ref

    try:
        brand_uuid = UUID(data.brand_id.strip())
        await BrandService.get_brand(db, brand_uuid, current_user.tenant_id)
        resolved = await resolve_product_reference(data.source)
        analysis = await analyze_ref(
            resolved["image_bytes"],
            mime_type=resolved["mime_type"],
            brand_name=data.brand_name.strip(),
            niche=data.niche.strip(),
        )
        summary = str(analysis.get("summary") or "").strip()
        saved = file_service.save_bytes(
            resolved["image_bytes"],
            str(current_user.tenant_id),
            "product_reference",
            resolved["suffix"],
            resolved["mime_type"],
        )
        asset = Asset(
            tenant_id=current_user.tenant_id,
            brand_id=brand_uuid,
            asset_type="product_reference",
            created_by=current_user.id,
            asset_metadata={
                "analysis": analysis,
                "summary": summary,
                "source_url": resolved["source_url"],
                "final_url": resolved["final_url"],
                "image_url": resolved["image_url"],
                "slug": resolved["slug"],
            },
            **saved,
        )
        db.add(asset)
        await db.flush()
        await db.refresh(asset)
        return ProductReferenceResponse(
            file_url=asset.file_url,
            asset_id=str(asset.id),
            analysis=analysis,
            summary=summary,
            source_url=resolved["source_url"],
            slug=resolved["slug"],
        )
    except (ValueError, HTTPException) as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Product reference extraction failed")
        raise HTTPException(status_code=502, detail=f"Could not fetch product image: {exc}") from exc


@router.post("/hero-ai-image", response_model=HeroImageResponse)
async def create_hero_ai_image(
    file: UploadFile = File(...),
    brand_name: str = Form(""),
    industry: str = Form(""),
    niche: str = Form(""),
    product_name: str = Form(""),
    hook: str = Form(""),
    headline: str = Form(""),
    model: str = Form("openai-gpt-image-2"),
    logo_url: str = Form(""),
    logo_on_light_url: str = Form(""),
    prompt: str = Form(""),
    generate_image: bool = Form(True),
    current_user=Depends(get_current_user),
):
    """Generate a Hero image from an upload and burn the final copy deterministically."""
    from app.services.ai_service import AIService
    from app.services.file_service import file_service
    from app.services.media_content import image_suffix_and_type
    from app.services.reference_image_service import analyze_reference_image as analyze_ref

    raw = await file.read()
    if len(raw) > 12_000_000:
        raise HTTPException(status_code=400, detail="Hero image is too large (max 12MB)")
    try:
        suffix, mime = image_suffix_and_type(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Please upload a valid image") from exc

    try:
        copy = {"hook": hook.strip(), "headline": headline.strip()}
        image_analysis = await analyze_ref(
            raw,
            mime_type=mime,
            brand_name=brand_name.strip(),
            niche=niche.strip(),
        )
        if not copy["hook"] or not copy["headline"]:
            generated = await AIService().generate_ad_copy(
                brand_voice=(
                    "On-brand, visually clear, concise. The industry and niche are authoritative. "
                    "If the niche describes a service, gym, clinic, class, venue, or experience, "
                    "write service-led copy and never turn the image into an ecommerce product ad."
                ),
                forbidden_words=[],
                brief={
                    "brand_name": brand_name.strip(),
                    "product_name": product_name.strip(),
                    "objective": "Create a hero image for the selected brand and niche",
                    "target_audience": niche.strip(),
                    "ad_copy_tone": "Premium and attention-grabbing",
                    "cta": "",
                    "key_benefits": {
                        "industry": industry.strip(),
                        "niche": niche.strip(),
                        "uploaded_image_context": image_analysis.get("product_description", ""),
                        "copy_rule": (
                            "Follow the selected niche exactly. Promote the service or experience "
                            "when the niche is service-led; do not invent product/gear claims."
                        ),
                    },
                },
                format_type="static",
            )
            copy["hook"] = copy["hook"] or str(generated.get("hook") or "").strip()
            copy["headline"] = copy["headline"] or str(generated.get("headline") or "").strip()
        if not copy["hook"] or not copy["headline"]:
            raise ValueError("Could not generate Hero hook and headline")

        uploaded = file_service.save_bytes(
            raw,
            str(current_user.tenant_id),
            "hero_reference",
            suffix,
            mime,
        )
        subject_rule = (
            "The uploaded image may show a person, gym, class, service environment, or lifestyle scene. "
            "Preserve that subject and do not convert it into an ecommerce product shot."
            if not product_name.strip()
            else "Preserve the named product exactly and do not invent a different product."
        )
        copy_layout = (
            f'Render the exact on-image copy as part of the professional ad design. '
            f'Hook text: "{copy["hook"]}". Headline text: "{copy["headline"]}". '
            "Use clean typography, natural spacing, strong hierarchy, and a layout that suits the "
            "uploaded composition. Place text where it does not cover the subject. "
            "Do not use a large black rectangle, black banner, or bottom overlay. "
            "Do not paraphrase, truncate, misspell, or add extra copy."
        )
        generation_prompt = (
            f"{prompt.strip()}\n\n{copy_layout}"
            if prompt.strip()
            else (
                f"Create a premium hero advertisement using the uploaded image as the primary visual source. "
                f"Preserve the exact subject/product, shape, colours, materials, proportions, and visible branding. "
                f"Brand: {brand_name.strip() or 'the selected brand'}. Industry: {industry.strip()}. "
                f"Authoritative niche: {niche.strip()}. Product: {product_name.strip() or 'not specified'}. "
                f"{subject_rule} {copy_layout}"
            )
        )
        if not generate_image:
            return HeroImageResponse(
                hook=copy["hook"],
                headline=copy["headline"],
                prompt=generation_prompt,
            )
        hero_model = (
            model.strip()
            if "gpt-image-2" in model.strip().lower()
            else "openai-gpt-image-2"
        )
        generated_image = await AIService().generate_image_asset(
            prompt=generation_prompt,
            tenant_id=str(current_user.tenant_id),
            model=hero_model,
            format_type="static",
            logo_url=logo_url.strip() or None,
            logo_on_light_url=logo_on_light_url.strip() or None,
            reference_image_url=uploaded["file_url"],
        )
        generated_url = str((generated_image or {}).get("url") or "").strip()
        if not generated_url:
            raise ValueError(str((generated_image or {}).get("error") or "Image generation failed"))
        return HeroImageResponse(
            image_url=generated_url,
            hook=copy["hook"],
            headline=copy["headline"],
            prompt=generation_prompt,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Hero AI Image generation failed")
        raise HTTPException(status_code=502, detail=f"Could not generate Hero image: {exc}") from exc


class StrategyVariantPlan(BaseModel):
    id: str = ""
    format: str = "static"
    ad_angle: str = ""
    use_cases: list[str] = []
    hook: str = ""
    message: str = ""
    image_hook: str = ""
    image_headline: str = ""
    cta: str = ""
    offer: str = ""
    prompt: str = ""
    reasoning: str = ""
    creative_type: str = "photo"
    carousel_index: int | None = None
    carousel_total: int | None = None
    carousel_group: str | None = None
    photo_only: bool = False
    retail_promo: bool = False
    aspect_ratio: str | None = None
    # Preserve document-provided creative metadata for downstream image prompting.
    post_type: str = ""
    product_name: str = ""
    design_notes: str = ""
    product_focus: str = ""


class StrategyParseResponse(BaseModel):
    brand_name: str = ""
    industry: str = ""
    niche: str = ""
    geography: str = ""
    age_range: str = ""
    audience_type: str = ""
    languages: str = "English"
    objective_id: str = "lead_generation"
    cta: str = ""
    offer: str = ""
    product_name: str = ""
    ad_copy_tone: str = ""
    placements: list[str] = []
    formats: list[str] = []
    hook_frameworks: list[str] = []
    target_variant_count: int = 1
    notes: str = ""
    reasoning: str = ""
    filename: str = ""
    variants: list[StrategyVariantPlan] = []
    image_aspect_ratio: str = ""
    creative_style: str = ""


@router.post("/parse-strategy", response_model=StrategyParseResponse)
async def parse_strategy_file(
    file: UploadFile = File(...),
    _current_user=Depends(get_current_user),
):
    """Read a client strategy .md/.txt/.docx and fill a CreativeStudio brief + variant plans."""
    name = (file.filename or "strategy.md").lower()
    from app.services.strategy_document_io import strategy_bytes_to_text, strategy_filename_ok

    if not strategy_filename_ok(name):
        raise HTTPException(
            status_code=400,
            detail="Upload a strategy file (.md, .txt, .docx, or .doc)",
        )
    raw = await file.read()
    if len(raw) > 6_000_000:
        raise HTTPException(status_code=400, detail="Strategy file is too large (max 6MB)")
    try:
        text = strategy_bytes_to_text(raw, filename=file.filename or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    from app.services.strategy_parse_service import (
        parse_strategy_markdown,
        strip_embedded_images_for_parse,
    )

    text = strip_embedded_images_for_parse(text)
    if len(text.encode("utf-8")) > 400_000:
        raise HTTPException(
            status_code=400,
            detail="Strategy text is too large after removing embedded images (max 400KB)",
        )

    try:
        parsed = await parse_strategy_markdown(text, filename=file.filename or "")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.exception("Strategy parse failed")
        raise HTTPException(status_code=502, detail=f"Could not read strategy: {e}") from e
    return StrategyParseResponse(**parsed)


class ModelSuggestionRequest(BaseModel):
    campaign_name: str = ""
    objective: str = ""
    formats: List[str] = []
    target_audience: str = ""
    offer: str = ""
    product_name: str = ""
    ad_copy_tone: str = ""
    cta: str = ""
    duration_seconds: int = 30
    brand_name: str = ""


class ModelSuggestionResponse(BaseModel):
    image_model: str
    image_reason: str
    video_model: str
    video_reason: str
    copy_model: str
    copy_reason: str


@router.post("/suggest-models", response_model=ModelSuggestionResponse)
async def suggest_models_endpoint(
    data: ModelSuggestionRequest,
    _current_user=Depends(get_current_user),
):
    """Analyse campaign inputs and recommend the best image, video, and copy models."""
    catalog = get_generation_catalog()
    result = await suggest_models(
        campaign_name=data.campaign_name,
        objective=data.objective,
        formats=data.formats,
        target_audience=data.target_audience,
        offer=data.offer,
        product_name=data.product_name,
        ad_copy_tone=data.ad_copy_tone,
        cta=data.cta,
        duration_seconds=data.duration_seconds,
        brand_name=data.brand_name,
        image_models=catalog.image_models,
        video_models=catalog.video_models,
        copy_models=catalog.copy_models,
    )
    return ModelSuggestionResponse(**result)


@router.post("/strategy-preview", response_model=StrategyPreviewResponse)
async def strategy_preview(
    data: StrategyPreviewRequest,
    _current_user=Depends(get_current_user),
):
    """Build ICP + HALO + hooks + body outline + competitor positioning for manager review."""
    result = await generate_strategy_preview(
        campaign_name=data.campaign_name,
        brand_name=data.brand_name,
        product_name=data.product_name,
        offer=data.offer,
        target_audience=data.target_audience,
        ad_copy_tone=data.ad_copy_tone,
        cta=data.cta,
        target_seconds=data.target_seconds,
        hook_frameworks=data.hook_frameworks,
        competitors=data.competitors,
        objective=data.objective,
        placements=data.placements,
        formats=data.formats,
        website_url=data.website_url,
    )
    return StrategyPreviewResponse(**result)


@router.post("/website-script", response_model=WebsiteScriptResponse)
async def website_script(
    data: WebsiteScriptRequest,
    _current_user=Depends(get_current_user),
):
    """Scrape a webpage, pick a duration-based framework, generate a spoken avatar script."""
    from fastapi import HTTPException
    try:
        script, page, framework = await generate_website_script(
            url=data.url,
            target_seconds=data.target_seconds,
            brand_name=data.brand_name,
            product_name=data.product_name,
            offer=data.offer,
            ad_copy_tone=data.ad_copy_tone,
            cta=data.cta,
            target_audience=data.target_audience,
            avatar_label=data.avatar_label,
            voice_label=data.voice_label,
            forbidden_words=data.forbidden_words,
            variation=data.variation,
            performance_stats=data.performance_stats,
        )
        return WebsiteScriptResponse(
            script=script,
            page_title=page.get("title", ""),
            page_description=page.get("description", ""),
            framework_name=framework["name"],
            framework_description=framework["description"],
            url=data.url,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch website: {e}")


@router.post("/icp-script", response_model=IcpScriptResponse)
async def icp_script(
    data: IcpScriptRequest,
    _current_user=Depends(get_current_user),
):
    """Build an ICP profile first, then use it to generate a spoken avatar script."""
    return await generate_icp_script(data)


class ImagePromptRequest(BaseModel):
    product_name: str = ""
    brand_name: str = ""
    offer: str = ""
    target_audience: str = ""
    ad_copy_tone: str = ""
    image_use_case: str = ""          # legacy single
    image_use_cases: list[str] = []   # new multi-select
    image_aspect_ratio: str = "1:1"
    forbidden_words: list[str] = []
    user_prompt: str = ""             # when set, used as primary prompt seed


class ImagePromptResponse(BaseModel):
    prompt: str


@router.post("/image-prompt", response_model=ImagePromptResponse)
async def generate_image_prompt_endpoint(
    data: ImagePromptRequest,
    _current_user=Depends(get_current_user),
):
    """Generate a detailed AI image generation prompt from brief context."""
    from app.services.image_prompt_service import generate_image_prompt
    return ImagePromptResponse(prompt=await generate_image_prompt(data))


class ImagePlanRequest(BaseModel):
    """Campaign context for intelligent use-case selection + prompt generation."""
    brand_name: str = ""
    industry: str = ""
    product_name: str = ""
    offer: str = ""
    target_audience: str = ""
    ad_copy_tone: str = ""
    objective_id: str = ""
    cta: str = ""
    image_aspect_ratio: str = "1:1"
    image_use_cases: list[str] = []    # user-selected hints (optional)
    image_prompt_override: str = ""    # user-written prompt to refine (optional)
    notes: str = ""
    # Optional ad copy to bake into the prompt (hook, headline, body)
    hook: str = ""
    headline: str = ""
    body_copy: str = ""
    # Increment this on each retry to get a different creative angle
    variant_index: int = 0


class ImagePlanResponse(BaseModel):
    use_cases: list[str]
    prompt: str
    reasoning: str


@router.post("/preview-image-plan", response_model=ImagePlanResponse)
async def preview_image_plan(
    data: ImagePlanRequest,
    _current_user=Depends(get_current_user),
):
    """
    Intelligent preview: LLM reads campaign brief, selects best image use cases,
    and returns the final image generation prompt — before the brief is created.
    """
    from app.services.image_prompt_service import select_and_build_image_plan

    brief = {
        "brand_name": data.brand_name,
        "target_industry_label": data.industry,
        "campaign_product": data.product_name,
        "product_name": data.product_name,
        "key_benefits": {"offer": data.offer},
        "audience": data.target_audience,
        "audience_type": data.target_audience,
        "ad_copy_tone": data.ad_copy_tone,
        "objective_id": data.objective_id,
        "cta_text": data.cta,
        "image_aspect_ratio": data.image_aspect_ratio,
        "image_use_cases": data.image_use_cases,
        "image_prompt_override": data.image_prompt_override,
        "notes": data.notes,
    }
    brand = {"brand_name": data.brand_name, "agency_industry": data.industry}
    copy = {
        "hook": data.hook,
        "headline": data.headline,
        "body_copy": data.body_copy,
        "cta": data.cta,
    } if (data.hook or data.headline) else None
    plan = await select_and_build_image_plan(brief, brand, copy=copy, variant_index=data.variant_index)
    return ImagePlanResponse(**plan.to_dict())


class IcpImageVariantPlanItem(BaseModel):
    use_cases: list[str]
    hook: str
    message: str
    image_hook: str = ""
    image_headline: str = ""
    cta: str = ""
    offer: str = ""
    prompt: str
    reasoning: str
    ad_angle: str = ""


class SuggestAdAnglesRequest(BaseModel):
    campaign_name: str = Field(..., min_length=2)
    brand_name: str = ""
    industry: str = ""
    niche: str = ""
    objective_id: str = ""
    variant_count: int = Field(default=2, ge=1, le=100)


class SuggestAdAnglesResponse(BaseModel):
    suggested_angles: list[str]
    reasoning: str
    icp_text: str = ""
    source: str = "rules"  # "ai" | "rules"


@router.post("/suggest-ad-angles", response_model=SuggestAdAnglesResponse)
async def suggest_ad_angles_endpoint(
    data: SuggestAdAnglesRequest,
    _current_user=Depends(get_current_user),
):
    """Suggest ad angles from industry + niche + ICP (business logic)."""
    from app.services.ad_angle_library import suggest_ad_angles

    result = await suggest_ad_angles(
        campaign_name=data.campaign_name.strip(),
        brand_name=data.brand_name,
        industry=data.industry,
        niche=data.niche,
        objective_id=data.objective_id,
        variant_count=data.variant_count,
    )
    return SuggestAdAnglesResponse(**result)

class IcpImagePlanRequest(BaseModel):
    """ICP-driven image plans from industry + niche + objective + brand."""
    campaign_name: str = Field(..., min_length=3)
    brand_name: str = ""
    industry: str = ""
    niche: str = ""
    objective_id: str = ""
    cta: str = ""
    offer: str = ""
    geography: str = Field(
        default="",
        description="Service / audience location from the brief (e.g. North Brisbane). Used on-image — never invent Western Sydney/Brisbane from ICP archetypes.",
    )
    brand_facts: dict | None = Field(
        default=None,
        description="Verified facts scraped from the brand website (services, rates, reviews, locations). ACCC whitelist.",
    )
    image_aspect_ratio: str = "1:1"
    hook_frameworks: list[str] = Field(default_factory=list)
    variant_count: int = Field(default=1, ge=1, le=100)
    existing_hooks: list[str] = Field(default_factory=list)
    existing_prompts: list[str] = Field(default_factory=list)
    creative_format: str = Field(
        default="static",
        description="static | carousel | mixed — carousel cards form one swipe story",
    )
    strategy_notes: str = ""
    strategy_variants: list[dict] = Field(
        default_factory=list,
        description="Client MD seeds (scene / intent). Knowledge only — do not paste verbatim.",
    )
    on_image_style: str = Field(
        default="auto",
        description="Campaign on-image typography: auto | retail_modern | jewellery_luxury | fashion_editorial | high_contrast",
    )
    image_visual_style: str = Field(
        default="auto",
        description="Optional illustration treatment: auto | sketch_illustration | flat_cartoon | clay_3d | 3d_metaphor",
    )
    product_focus: str = Field(
        default="",
        description="Campaign shot style: empty=auto | product_only | with_person — applies to all variants",
    )
    primary_color: str = Field(default="", description="Brand primary hex from website / Brand Kit")
    secondary_color: str = Field(default="", description="Brand secondary hex from website / Brand Kit")
    font_heading: str = Field(default="", description="Heading font family from website / Brand Kit")
    font_body: str = Field(default="", description="Body font family from website / Brand Kit")
    brand_id: str = Field(
        default="",
        description="Brand Kit id — when set, saved social media visual style is loaded automatically for image prompts.",
    )
    social_style_profile: dict | None = Field(
        default=None,
        description="Client social feed visual style (SociaVault) — match their posted ad look.",
    )
    competitor_social_insights: list[dict] | None = Field(
        default=None,
        description="Saved competitor posting strategy from Brand Kit — content structure only.",
    )
    use_competitor_insights: bool = Field(
        default=False,
        description="When true, apply saved competitor posting logic to image plans.",
    )
    reference_images: list[dict] = Field(
        default_factory=list,
        description="Optional brand reference uploads: { asset_id, file_url, analysis }.",
    )
    exact_product_reference: bool = Field(
        default=False,
        description="Use the selected product reference as the authoritative product source.",
    )
    llm_model: str = Field(
        default="",
        description="OpenRouter model slug for prompt generation (e.g. anthropic/claude-sonnet-4.6).",
    )


class IcpImagePlanResponse(BaseModel):
    icp_text: str
    variants: list[IcpImageVariantPlanItem]
    campaign_hook: str = ""
    campaign_headline: str = ""
    campaign_cta: str = ""


@router.post("/icp-image-plan", response_model=IcpImagePlanResponse)
async def icp_image_plan(
    data: IcpImagePlanRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Build ICP from industry + niche + objective + brand, then return N distinct
    image variant plans (hook/headline + catchy on-image lines + prompt).
    """
    from app.services.brand_service import BrandService, competitor_insights_from_brand_and_kit, social_style_from_brand_and_kit
    from app.services.competitor_social_service import normalize_competitor_insights
    from app.services.icp_image_plan_service import generate_icp_image_plan
    from app.services.prompt_llm_catalog import resolve_prompt_llm_model

    social_profile = data.social_style_profile
    competitor_insights = normalize_competitor_insights(data.competitor_social_insights)
    brand = None
    kit = None
    if (data.brand_id or "").strip():
        try:
            brand = await BrandService.get_brand(db, UUID(data.brand_id.strip()), current_user.tenant_id)
            try:
                kit = await BrandService.get_brand_kit(db, UUID(data.brand_id.strip()), current_user.tenant_id)
            except HTTPException:
                pass
            if not social_profile:
                social_profile = social_style_from_brand_and_kit(brand, kit)
            if not competitor_insights:
                competitor_insights = competitor_insights_from_brand_and_kit(brand, kit)
        except HTTPException:
            social_profile = social_profile
            competitor_insights = competitor_insights

    if not data.use_competitor_insights:
        competitor_insights = []

    reference_images = [r for r in (data.reference_images or []) if isinstance(r, dict)]
    if not reference_images and brand:
        from sqlalchemy import select
        from app.models.asset import Asset

        asset_rows = await db.execute(
            select(Asset)
            .where(
                Asset.tenant_id == current_user.tenant_id,
                Asset.brand_id == brand.id,
                Asset.asset_type == "reference_image",
                Asset.asset_metadata["analysis"].is_not(None),
            )
            .order_by(Asset.created_at.desc())
            .limit(5)
        )
        for asset in asset_rows.scalars().all():
            meta = asset.asset_metadata if isinstance(asset.asset_metadata, dict) else {}
            reference_images.append(
                {
                    "asset_id": str(asset.id),
                    "file_url": asset.file_url,
                    "analysis": meta.get("analysis") if isinstance(meta.get("analysis"), dict) else meta,
                }
            )

    result = await generate_icp_image_plan(
        campaign_name=data.campaign_name.strip(),
        brand_name=data.brand_name,
        industry=data.industry,
        niche=data.niche,
        objective_id=data.objective_id,
        cta=data.cta,
        offer=data.offer,
        geography=data.geography,
        brand_facts=data.brand_facts,
        image_aspect_ratio=data.image_aspect_ratio,
        hook_frameworks=data.hook_frameworks,
        variant_count=data.variant_count,
        existing_hooks=data.existing_hooks,
        existing_prompts=data.existing_prompts,
        creative_format=data.creative_format,
        strategy_notes=data.strategy_notes,
        strategy_variants=data.strategy_variants,
        on_image_style=data.on_image_style,
        image_visual_style=data.image_visual_style,
        product_focus=data.product_focus,
        primary_color=data.primary_color,
        secondary_color=data.secondary_color,
        font_heading=data.font_heading,
        font_body=data.font_body,
        social_style_profile=social_profile,
        competitor_social_insights=competitor_insights,
        reference_images=reference_images,
        llm_model=resolve_prompt_llm_model(data.llm_model),
    )
    return IcpImagePlanResponse(**result)


class FetchBrandFromUrlRequest(BaseModel):
    url: str = Field(..., min_length=4)


class FetchBrandFromUrlResponse(BaseModel):
    source_url: str
    brand_name: str
    industry: str
    niche: str = ""
    primary_color: str
    secondary_color: str
    font_heading: str | None = None
    font_body: str | None = None
    logo_url: str | None = None
    page_title: str = ""
    description: str = ""
    provider: str = "firecrawl"
    warning: str | None = None
    brand_facts: dict | None = None


@router.post("/fetch-brand-from-url", response_model=FetchBrandFromUrlResponse)
async def fetch_brand_from_url(
    data: FetchBrandFromUrlRequest,
    current_user=Depends(get_current_user),
):
    """Scrape a website (Firecrawl) and return brand identity + claimable business facts."""
    from app.services.brand_logo import persist_remote_logo_url
    from app.services.firecrawl_brand_service import fetch_brand_from_website

    try:
        result = await fetch_brand_from_website(data.url)
        if result.get("logo_url"):
            persisted = persist_remote_logo_url(
                str(result["logo_url"]),
                tenant_id=str(current_user.tenant_id),
            )
            if persisted:
                result["logo_url"] = persisted
    except ValueError as exc:
        from app.services.usage_tracker import record_firecrawl

        record_firecrawl(success=False, url=data.url, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        from app.services.usage_tracker import record_firecrawl

        record_firecrawl(success=False, url=data.url, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Could not fetch brand from URL: {exc}") from exc
    return FetchBrandFromUrlResponse(**result)


class ProductionScriptFromBriefRequest(BaseModel):
    brand_name: str = ""
    product_name: str = ""
    objective: str = ""
    target_audience: str = ""
    ad_copy_tone: str = ""
    cta: str = "Learn more"
    offer: str = ""
    notes: str = ""
    target_industry_label: str = ""
    hook: str = ""
    headline: str = ""
    body_copy: str = ""
    duration_seconds: int = 30
    format_type: str = "reel"
    use_ai_fill: bool = True


class ProductionScriptResponse(BaseModel):
    skeleton: str
    spoken_script: str
    veo_prompt: str
    draft_only: bool = False


@router.post("/production-script", response_model=ProductionScriptResponse)
async def production_script_from_brief(
    data: ProductionScriptFromBriefRequest,
    _current_user=Depends(get_current_user),
):
    """Build filled skeleton from brief form fields (composer preview)."""
    brief = {
        "brand_name": data.brand_name,
        "product_name": data.product_name,
        "campaign_product": data.product_name,
        "objective": data.objective,
        "target_audience": data.target_audience,
        "ad_copy_tone": data.ad_copy_tone,
        "cta": data.cta,
        "target_industry_label": data.target_industry_label or "local business",
        "key_benefits": {"offer": data.offer, "notes_for_ai": data.notes},
    }
    copy = {
        "hook": data.hook,
        "headline": data.headline,
        "body_copy": data.body_copy,
        "cta": data.cta,
    }
    if data.use_ai_fill:
        skeleton = await ensure_production_skeleton(
            brief,
            copy,
            duration=data.duration_seconds,
            format_type=data.format_type,
            force_refresh=True,
        )
        draft_only = False
    else:
        ctx = build_skeleton_context(
            brief, copy, duration=data.duration_seconds, format_type=data.format_type
        )
        skeleton = render_skeleton(ctx)
        draft_only = True

    spoken = extract_heygen_spoken_script(skeleton, target_seconds=data.duration_seconds)
    veo = build_veo_prompt_from_skeleton(
        skeleton,
        brief=brief,
        copy=copy,
        format_type=data.format_type,
        duration=data.duration_seconds,
    )
    return ProductionScriptResponse(
        skeleton=skeleton,
        spoken_script=spoken,
        veo_prompt=veo,
        draft_only=draft_only,
    )


# ---------------------------------------------------------------------------
# Voice catalog
# ---------------------------------------------------------------------------

class VoiceOption(BaseModel):
    id: str
    label: str
    gender: str | None = None
    language: str | None = None
    preview_url: str | None = None


class VoiceCatalogResponse(BaseModel):
    voices: List[VoiceOption]


@router.get("/voices", response_model=VoiceCatalogResponse)
async def list_voices(_current_user=Depends(get_current_user)):
    """Return voice catalog — first tries HeyGen /v2/voices, falls back to env config."""
    from app.services.generation_catalog import get_generation_catalog

    catalog = get_generation_catalog()
    voices = [
        VoiceOption(id=o.id, label=o.label, gender=o.gender)
        for o in (catalog.heygen_voice_options or [])
    ]

    if not voices and settings.HEYGEN_API_KEY:
        base = settings.HEYGEN_BASE_URL.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.get(
                    f"{base}/v2/voices",
                    headers={"X-Api-Key": settings.HEYGEN_API_KEY},
                )
                r.raise_for_status()
                data = r.json().get("data") or {}
                raw_voices = data.get("voices") or data if isinstance(data, list) else []
                for v in raw_voices:
                    if not isinstance(v, dict):
                        continue
                    vid = v.get("voice_id") or v.get("id")
                    if not vid:
                        continue
                    voices.append(
                        VoiceOption(
                            id=str(vid),
                            label=v.get("name") or str(vid),
                            gender=(v.get("gender") or "").lower() or None,
                            language=v.get("language") or v.get("locale") or None,
                            preview_url=v.get("preview_audio") or v.get("sample_url") or None,
                        )
                    )
        except Exception:
            pass

    return VoiceCatalogResponse(voices=voices)


# ---------------------------------------------------------------------------
# Voice preview (TTS)
# ---------------------------------------------------------------------------

class VoicePreviewResponse(BaseModel):
    audio_url: str


@router.get("/voice-preview", response_model=VoicePreviewResponse)
async def voice_preview(
    voice_id: str = Query(..., description="HeyGen voice ID"),
    text: str = Query(
        default="Hi, I'm your AI video presenter. Let me tell you something exciting today!",
        max_length=300,
    ),
    _current_user=Depends(get_current_user),
):
    """Generate a short TTS audio preview for the selected voice via HeyGen /v2/text_to_speech."""
    if not settings.HEYGEN_API_KEY:
        raise HTTPException(status_code=503, detail="HEYGEN_API_KEY not configured")

    base = settings.HEYGEN_BASE_URL.rstrip("/")
    payload = {
        "voice_id": voice_id,
        "text": text,
        "speed": 1.0,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{base}/v2/text_to_speech",
                headers={
                    "X-Api-Key": settings.HEYGEN_API_KEY,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if r.status_code == 400:
                detail = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
                raise HTTPException(status_code=400, detail=f"HeyGen rejected request: {detail}")
            r.raise_for_status()
            data = r.json()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"HeyGen TTS error: {exc.response.status_code}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"HeyGen TTS failed: {exc}")

    audio_url = (
        (data.get("data") or {}).get("audio_url")
        or data.get("audio_url")
        or data.get("url")
    )
    if not audio_url:
        raise HTTPException(status_code=502, detail="HeyGen TTS did not return an audio URL")

    return VoicePreviewResponse(audio_url=audio_url)


# ---------------------------------------------------------------------------
# Photo Avatar — create a custom HeyGen avatar from an uploaded photo
# ---------------------------------------------------------------------------

class PhotoAvatarCreateResponse(BaseModel):
    photo_avatar_id: str
    status: str  # "processing" | "completed" | "failed"
    look_id: str | None = None
    name: str


class PhotoAvatarStatusResponse(BaseModel):
    photo_avatar_id: str
    status: str  # "processing" | "completed" | "failed"
    look_id: str | None = None
    name: str
    error: str | None = None


def _heygen_headers() -> dict[str, str]:
    return {"X-Api-Key": settings.HEYGEN_API_KEY, "Accept": "application/json"}


@router.post("/photo-avatar", response_model=PhotoAvatarCreateResponse, status_code=201)
async def create_photo_avatar(
    photo: UploadFile = File(..., description="Portrait photo (JPEG/PNG, ≤32 MB)"),
    name: str = Form(..., description="Display name for this avatar"),
    _current_user=Depends(get_current_user),
):
    """Upload a photo and kick off HeyGen photo-avatar creation (v3 API).

    Step 1 — POST /v3/assets (multipart) → returns ``asset_id``.
    Step 2 — POST /v3/avatars with type=photo + asset_id → returns ``avatar_item.id``.

    The avatar typically finishes processing within 30–90 seconds.
    Poll ``GET /generation/photo-avatar/{avatar_id}`` to check progress.
    """
    if not settings.HEYGEN_API_KEY:
        raise HTTPException(status_code=503, detail="HEYGEN_API_KEY not configured")

    raw = await photo.read()
    if len(raw) > 32 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Photo must be ≤ 32 MB")

    content_type = photo.content_type or "image/jpeg"
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are accepted")

    filename = photo.filename or f"photo.{content_type.split('/')[-1]}"
    base = settings.HEYGEN_BASE_URL.rstrip("/")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # --- Step 1: upload via POST /v3/assets (multipart/form-data) ---
        upload_resp = await client.post(
            f"{base}/v3/assets",
            headers=_heygen_headers(),
            files={"file": (filename, raw, content_type)},
        )
        if upload_resp.status_code not in (200, 201):
            raise HTTPException(
                status_code=502,
                detail=f"HeyGen asset upload failed ({upload_resp.status_code}): {upload_resp.text[:300]}",
            )
        upload_data = upload_resp.json()
        asset_id = (upload_data.get("data") or {}).get("asset_id") or upload_data.get("asset_id")
        if not asset_id:
            raise HTTPException(
                status_code=502,
                detail=f"HeyGen upload did not return asset_id: {upload_data}",
            )

        # --- Step 2: POST /v3/avatars with type=photo ---
        create_resp = await client.post(
            f"{base}/v3/avatars",
            headers={**_heygen_headers(), "Content-Type": "application/json"},
            json={
                "type": "photo",
                "name": name.strip(),
                "file": {"type": "asset_id", "asset_id": asset_id},
            },
        )
        if create_resp.status_code not in (200, 201):
            raise HTTPException(
                status_code=502,
                detail=f"HeyGen avatar creation failed ({create_resp.status_code}): {create_resp.text[:300]}",
            )
        create_data = create_resp.json()
        # Response shape: {"data": {"avatar_item": {"id": "...", "status": "..."}}}
        inner = create_data.get("data") or create_data
        avatar_item = inner.get("avatar_item") or inner
        avatar_id = avatar_item.get("id") or avatar_item.get("avatar_id")
        if not avatar_id:
            raise HTTPException(
                status_code=502,
                detail=f"HeyGen did not return avatar id: {create_data}",
            )

        raw_status = (avatar_item.get("status") or "processing").lower()
        # Map HeyGen statuses → our internal names
        if raw_status in ("completed", "active", "ready"):
            mapped_status = "completed"
        elif raw_status in ("failed", "error"):
            mapped_status = "failed"
        else:
            mapped_status = "processing"

        # If already done, the look_id == avatar_id for v3 photo avatars
        look_id: str | None = str(avatar_id) if mapped_status == "completed" else None

    return PhotoAvatarCreateResponse(
        photo_avatar_id=str(avatar_id),
        status=mapped_status,
        look_id=look_id,
        name=name.strip(),
    )


@router.get("/photo-avatar/{photo_avatar_id}", response_model=PhotoAvatarStatusResponse)
async def get_photo_avatar_status(
    photo_avatar_id: str,
    _current_user=Depends(get_current_user),
):
    """Poll the status of a photo-avatar creation job (v3 API).

    Returns ``status="completed"`` and a ``look_id`` once ready.
    The ``look_id`` (same as ``photo_avatar_id`` for v3) is used as the ``avatar_id``
    when generating a video.
    """
    if not settings.HEYGEN_API_KEY:
        raise HTTPException(status_code=503, detail="HEYGEN_API_KEY not configured")

    base = settings.HEYGEN_BASE_URL.rstrip("/")

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            f"{base}/v3/avatars/{photo_avatar_id}",
            headers=_heygen_headers(),
        )
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail="Avatar not found")
        r.raise_for_status()
        data = r.json()

    inner = data.get("data") or data
    avatar_item = inner.get("avatar_item") or inner
    raw_status = (avatar_item.get("status") or "processing").lower()

    if raw_status in ("completed", "active", "ready"):
        mapped_status = "completed"
    elif raw_status in ("failed", "error"):
        mapped_status = "failed"
    else:
        mapped_status = "processing"

    look_id: str | None = photo_avatar_id if mapped_status == "completed" else None
    name_val = avatar_item.get("name") or avatar_item.get("avatar_name") or photo_avatar_id

    return PhotoAvatarStatusResponse(
        photo_avatar_id=photo_avatar_id,
        status=mapped_status,
        look_id=look_id,
        name=str(name_val),
        error=avatar_item.get("error") or None,
    )


class CreativeStudioGenerateRequest(BaseModel):
    media_mode: str = Field(..., description="image | video")
    model: str
    prompt: str
    duration_seconds: int = Field(default=15, ge=5, le=600)
    aspect: str = "9/16"
    resolution: str = "1080p"
    sound_on: bool = True
    negative_prompt: str = ""


class CreativeStudioGenerateResponse(BaseModel):
    status: str
    job_id: str | None = None
    progress: str | None = None
    url: str | None = None
    model: str | None = None
    provider: str | None = None
    error: str | None = None
    seed_image_url: str | None = None
    duration_seconds: int | None = None
    requested_duration_seconds: int | None = None
    segment_count: int | None = None
    continuity_chained: bool = False
    continuity_frame_count: int | None = None
    partial: bool = False
    credits_estimate: float | None = None
    audio_present: bool | None = None
    audio_warning: str | None = None
    voiceover: dict | None = None
    provider_usage: list[dict] | None = None
    duration_warning: str | None = None
    note: str | None = None
    storyboard: list[dict] | None = None
    media_mode: str | None = None
    product_reference_url: str | None = None


class CreativeStudioPromptRequest(BaseModel):
    niche: str
    media_mode: str = "video"
    duration_seconds: int = Field(default=15, ge=5, le=600)
    style: str = "auto"
    genre: str = "general"
    camera: str = "auto"
    aspect: str = "9/16"
    product_name: str = ""
    brand_name: str = ""
    notes: str = ""


class CreativeStudioPromptResponse(BaseModel):
    prompt: str
    niche: str


class CreativeStudioNicheOption(BaseModel):
    id: str
    label: str


class CreativeStudioChatMessage(BaseModel):
    role: str = Field(..., description="user | assistant")
    content: str = ""


class CreativeStudioReference(BaseModel):
    url: str = Field(min_length=1)
    role: Literal["product", "logo", "scene", "character", "reference"]


class CreativeStudioChatRequest(BaseModel):
    messages: list[CreativeStudioChatMessage] = Field(default_factory=list)
    mode: str = Field(default="auto", description="auto | ask | generate")
    chat_model: str = "auto"
    duration_seconds: int | None = Field(default=None, ge=5, le=600)
    aspect: str = "9/16"
    resolution: str = "1080p"
    sound_on: bool = True
    attachment_urls: list[str] = Field(default_factory=list)
    brand_name: str = ""
    product_name: str = ""
    # Supercomputer pipeline
    action: str = Field(
        default="continue",
        description="continue | generate_image | regenerate_image | approve_next | generate_video",
    )
    image_prompt: str = ""
    video_prompt: str = ""
    approved_image_url: str = ""
    image_model: str = ""
    revision_notes: str = ""
    phase: str = ""
    product_reference_url: str = ""
    logo_reference_url: str = ""
    additional_reference_urls: list[str] = Field(default_factory=list)
    reference_assets: list[CreativeStudioReference] = Field(default_factory=list, max_length=9)
    storyboard_image_urls: list[str] = Field(default_factory=list)


class CreativeStudioChatResponse(BaseModel):
    assistant_message: str
    intent: str
    phase: str | None = None
    suggested_actions: list[str] = Field(default_factory=list)
    chat_model: str | None = None
    image_model: str | None = None
    video_model: str | None = None
    job_id: str | None = None
    status: str = "ok"
    media_mode: str | None = None
    model: str | None = None
    image_prompt: str | None = None
    video_prompt: str | None = None
    approved_image_url: str | None = None
    product_reference_url: str | None = None
    storyboard_scenes: list[dict] | None = None
    duration_seconds: int | None = None
    requested_duration_seconds: int | None = None
    segment_count: int | None = None
    partial: bool = False
    aspect: str | None = None
    error: str | None = None


@router.get("/creative-studio/niches", response_model=list[CreativeStudioNicheOption])
async def creative_studio_niches(_current_user=Depends(get_current_user)):
    from app.services.creative_studio_prompt_service import CREATIVE_STUDIO_NICHES

    return [CreativeStudioNicheOption(**n) for n in CREATIVE_STUDIO_NICHES]


@router.get("/creative-studio/models")
async def creative_studio_models(_current_user=Depends(get_current_user)):
    """Creative Studio catalog: OpenRouter chat + GPT Image 2 + Seedance."""
    from app.services.media.byteplus_seedance_catalog import (
        byteplus_seedance_video_catalog_options,
    )
    from app.services.media.byteplus_seedance_client import ark_configured
    from app.services.media.higgsfield_catalog import (
        higgsfield_image_catalog_options,
        higgsfield_video_catalog_options,
    )
    from app.services.media.higgsfield_models import higgsfield_configured
    from app.services.media.openai_image_catalog import (
        openai_configured,
        openai_image_catalog_options,
    )
    from app.services.prompt_llm_catalog import (
        default_prompt_llm_model,
        prompt_llm_catalog_options,
    )

    hf_ok = higgsfield_configured()
    ark_ok = ark_configured()
    oai_ok = openai_configured()
    video_models = []
    video_models.extend(byteplus_seedance_video_catalog_options())
    if hf_ok:
        video_models.extend(higgsfield_video_catalog_options())
    image_models = []
    image_models.extend(openai_image_catalog_options())
    if hf_ok:
        image_models.extend(higgsfield_image_catalog_options())
    chat_models = prompt_llm_catalog_options()

    messages: list[str] = []
    if not settings.OPENROUTER_API_KEY:
        messages.append("Set OPENROUTER_API_KEY for chat models.")
    if not oai_ok:
        messages.append("Set OPENAI_API_KEY for GPT Image 2 stills.")
    if not ark_ok:
        messages.append("Set ARK_API_KEY for BytePlus Seedance 2.0.")
    if not hf_ok:
        messages.append("Optional: HIGGSFIELD keys for extra image/video models.")

    return {
        "configured": bool(settings.OPENROUTER_API_KEY) or ark_ok or hf_ok or oai_ok,
        "chat_models": chat_models,
        "default_chat_model": default_prompt_llm_model(),
        "image_model_default": "openai-gpt-image-2",
        "video_model_default": "ark-seedance-2-0",
        "image_models": image_models,
        "video_models": video_models,
        "message": " ".join(messages) if messages else None,
    }


@router.post("/creative-studio/chat", response_model=CreativeStudioChatResponse)
async def creative_studio_chat(
    data: CreativeStudioChatRequest,
    current_user=Depends(get_current_user),
):
    """One Supercomputer-style chat turn (plan → GPT Image 2 → Seedance)."""
    from app.services.creative_studio_chat_service import run_creative_studio_chat_turn

    if not data.messages and data.action in {"continue", ""}:
        raise HTTPException(status_code=422, detail="messages required")
    # Pipeline buttons may send empty messages with action + prompts
    msgs = [m.model_dump() for m in data.messages] if data.messages else []
    if not msgs and data.action not in {
        "generate_image",
        "regenerate_image",
        "approve_next",
        "generate_video",
    }:
        raise HTTPException(status_code=422, detail="messages required")
    result = await run_creative_studio_chat_turn(
        tenant_id=str(current_user.tenant_id),
        messages=msgs,
        mode=data.mode,
        chat_model=data.chat_model,
        duration_seconds=data.duration_seconds,
        aspect=data.aspect,
        resolution=data.resolution,
        sound_on=data.sound_on,
        attachment_urls=list(data.attachment_urls or []),
        brand_name=data.brand_name,
        product_name=data.product_name,
        action=data.action,
        image_prompt=data.image_prompt,
        video_prompt=data.video_prompt,
        approved_image_url=data.approved_image_url,
        image_model=data.image_model,
        revision_notes=data.revision_notes,
        phase=data.phase,
        product_reference_url=data.product_reference_url or (
            (data.attachment_urls or [None])[0] if data.attachment_urls else ""
        ) or "",
        logo_reference_url=data.logo_reference_url,
        additional_reference_urls=list(data.additional_reference_urls or []),
        reference_assets=[asset.model_dump() for asset in data.reference_assets],
        storyboard_image_urls=list(data.storyboard_image_urls or []),
    )
    return CreativeStudioChatResponse(**result)


@router.post("/creative-studio/prompt", response_model=CreativeStudioPromptResponse)
async def creative_studio_prompt(
    data: CreativeStudioPromptRequest,
    _current_user=Depends(get_current_user),
):
    """Auto-generate a Higgsfield/Cinema Studio prompt from niche + scene settings."""
    from app.services.creative_studio_prompt_service import generate_creative_studio_prompt

    niche = (data.niche or "").strip()
    if not niche:
        raise HTTPException(status_code=422, detail="Select or enter a niche first")
    try:
        prompt = await generate_creative_studio_prompt(
            niche=niche,
            media_mode=data.media_mode,
            duration_seconds=data.duration_seconds,
            style=data.style,
            genre=data.genre,
            camera=data.camera,
            aspect=data.aspect,
            product_name=data.product_name,
            brand_name=data.brand_name,
            notes=data.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CreativeStudioPromptResponse(prompt=prompt, niche=niche)


def _cs_format_from_aspect(aspect: str) -> str:
    a = (aspect or "9/16").replace(":", "/")
    if a in {"9/16", "1/4"}:
        return "reel"
    if a in {"16/9"}:
        return "video"
    if a in {"4/3"}:
        return "carousel"
    return "static"


@router.post("/creative-studio", response_model=CreativeStudioGenerateResponse)
async def creative_studio_generate(
    data: CreativeStudioGenerateRequest,
    current_user=Depends(get_current_user),
):
    """Start Creative Studio generate in the background (avoids browser HTTP timeouts)."""
    import asyncio

    from app.services.creative_studio_job_service import (
        create_job,
        run_creative_studio_job,
    )

    prompt = (data.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="Prompt is required")
    model = (data.model or "").strip()
    if not model:
        raise HTTPException(status_code=422, detail="Model is required")

    tenant_id = str(current_user.tenant_id)
    job_id = await create_job(
        tenant_id=tenant_id,
        payload={
            "media_mode": data.media_mode,
            "model": model,
            "prompt": prompt,
            "duration_seconds": data.duration_seconds,
            "aspect": data.aspect,
            "resolution": data.resolution,
            "sound_on": data.sound_on,
            "negative_prompt": data.negative_prompt,
        },
    )
    asyncio.create_task(run_creative_studio_job(job_id))
    return CreativeStudioGenerateResponse(
        status="queued",
        job_id=job_id,
        progress="Queued — Higgsfield jobs can take 15–40 min for a 15s stitch. This tab will poll until done.",
        note="Running in background so the browser does not time out.",
    )


@router.get("/creative-studio/jobs/{job_id}", response_model=CreativeStudioGenerateResponse)
async def creative_studio_job_status(
    job_id: str,
    current_user=Depends(get_current_user),
):
    """Poll a Creative Studio background job."""
    from app.services.creative_studio_job_service import get_job

    job = await get_job(job_id, tenant_id=str(current_user.tenant_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found (server may have restarted)")
    return CreativeStudioGenerateResponse(
        status=str(job.get("status") or "failed"),
        job_id=str(job.get("job_id") or job_id),
        progress=job.get("progress"),
        url=job.get("url"),
        model=job.get("model"),
        provider=job.get("provider"),
        error=job.get("error"),
        seed_image_url=job.get("seed_image_url"),
        duration_seconds=job.get("duration_seconds"),
        requested_duration_seconds=job.get("requested_duration_seconds"),
        segment_count=job.get("segment_count"),
        continuity_chained=bool(job.get("continuity_chained")),
        continuity_frame_count=job.get("continuity_frame_count"),
        partial=bool(job.get("partial")),
        audio_present=job.get("audio_present"),
        audio_warning=job.get("audio_warning"),
        voiceover=job.get("voiceover"),
        provider_usage=job.get("provider_usage"),
        credits_estimate=job.get("credits_estimate"),
        duration_warning=job.get("duration_warning"),
        note=job.get("note"),
        storyboard=job.get("storyboard") if isinstance(job.get("storyboard"), list) else None,
        media_mode=job.get("media_mode"),
        product_reference_url=job.get("product_reference_url"),
    )


@router.post("/creative-studio/jobs/{job_id}/cancel", response_model=CreativeStudioGenerateResponse)
async def creative_studio_job_cancel(
    job_id: str,
    current_user=Depends(get_current_user),
):
    """Kill switch — stop a running Creative Studio job."""
    from app.services.creative_studio_job_service import cancel_job

    job = await cancel_job(job_id, tenant_id=str(current_user.tenant_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return CreativeStudioGenerateResponse(
        status=str(job.get("status") or "cancelled"),
        job_id=str(job.get("job_id") or job_id),
        progress=job.get("progress") or "Stopped by user",
        error=job.get("error") or "Cancelled by user",
    )
