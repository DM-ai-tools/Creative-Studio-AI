from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from typing import List

import httpx

from app.core.config import settings
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
