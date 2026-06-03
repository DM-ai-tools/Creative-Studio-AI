from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import get_current_user
from app.schemas.avatar_script import AvatarScriptRequest, AvatarScriptResponse
from app.schemas.generation import GenerationCatalogResponse
from app.services.avatar_script_service import generate_avatar_script
from app.services.generation_catalog import get_generation_catalog
from app.services.video_script_skeleton import (
    build_skeleton_context,
    build_veo_prompt_from_skeleton,
    ensure_production_skeleton,
    extract_heygen_spoken_script,
    render_skeleton,
)

router = APIRouter(prefix="/generation", tags=["generation"])


@router.get("/catalog", response_model=GenerationCatalogResponse)
async def generation_catalog():
    return get_generation_catalog()


@router.post("/avatar-script", response_model=AvatarScriptResponse)
async def avatar_script(
    data: AvatarScriptRequest,
    _current_user=Depends(get_current_user),
):
    return await generate_avatar_script(data)


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
