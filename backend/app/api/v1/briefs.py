import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.brief import Brief
from app.schemas.brief import BriefCreate, BriefResponse, BriefUpdate, GenerationRequest
from app.services.brand_service import BrandService
from app.services.brief_service import BriefService
from app.services.generation_job import run_brief_generation_job
from app.services.pdf_script_extract import extract_text_from_pdf_bytes
from pydantic import BaseModel

router = APIRouter(prefix="/briefs", tags=["briefs"], redirect_slashes=False)
logger = logging.getLogger(__name__)


class ScriptPdfUploadResponse(BaseModel):
    character_count: int
    preview: str
    filename: str


@router.post("", response_model=BriefResponse, status_code=201, include_in_schema=False)
@router.post("/", response_model=BriefResponse, status_code=201)
async def create_brief(
    data: BriefCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await BriefService.create_brief(db, current_user.tenant_id, current_user.id, data)


@router.get("", response_model=list[BriefResponse], include_in_schema=False)
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
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start generation in the background and return immediately.

    HeyGen often takes 10–35+ minutes. Holding the HTTP request open causes Railway /
    browsers to show "Network Error" even though HeyGen finished. The brief stays
    RUNNING; the UI polls until variants appear.
    """
    brief = await BriefService.get_brief(db, brief_id, current_user.tenant_id)
    await BrandService.get_brand(db, brief.brand_id, current_user.tenant_id)

    if brief.status == "RUNNING":
        return {
            "message": "Generation already running — stay on this page; variants appear when ready.",
            "variants_created": int(brief.completed_variants or 0),
            "status": "RUNNING",
        }

    formats = data.formats or brief.formats or ["static"]
    kb_models = dict(brief.key_benefits) if isinstance(brief.key_benefits, dict) else {}

    count_per_format = data.count_per_format
    target_count = kb_models.get("target_variant_count")
    if target_count:
        try:
            count_per_format = max(1, round(int(target_count) / len(formats)))
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    # Persist optional generation overrides onto the brief before the background job.
    merged_kb = {**kb_models}
    if data.video_model:
        merged_kb["video_model"] = data.video_model
    if data.image_model:
        merged_kb["image_model"] = data.image_model
    if data.ai_model:
        merged_kb["copy_model"] = data.ai_model
    if data.video_duration_seconds:
        merged_kb["video_duration_seconds"] = data.video_duration_seconds
    if data.heygen_avatar_id:
        merged_kb["heygen_avatar_id"] = data.heygen_avatar_id
    if data.heygen_voice_id:
        merged_kb["heygen_voice_id"] = data.heygen_voice_id
    if data.higgsfield_voice_preset:
        merged_kb["higgsfield_voice_preset"] = data.higgsfield_voice_preset
    if data.avatar_script:
        merged_kb["avatar_script"] = data.avatar_script
    if isinstance(data.heygen_settings, dict):
        merged_kb["heygen_settings"] = data.heygen_settings
    if data.stats_image_url:
        merged_kb["stats_image_url"] = data.stats_image_url
    if data.stats_image_urls:
        merged_kb["stats_image_urls"] = data.stats_image_urls

    brief.key_benefits = merged_kb
    brief.status = "RUNNING"
    brief.variant_count = len(formats) * count_per_format
    brief.completed_variants = 0
    await db.commit()

    logger.info(
        "Brief %s generation queued (background): %s formats × %s (video_model=%s)",
        brief_id,
        formats,
        count_per_format,
        data.video_model or merged_kb.get("video_model"),
    )

    background_tasks.add_task(
        run_brief_generation_job,
        brief_id=brief_id,
        tenant_id=current_user.tenant_id,
        request_data=data.model_dump(mode="json"),
    )

    return {
        "message": (
            "Generation started. HeyGen can take 10–35 minutes — keep this page open; "
            "variants appear automatically when ready."
        ),
        "variants_created": 0,
        "status": "RUNNING",
    }
