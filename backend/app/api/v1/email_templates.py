from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.brand import Brand
from app.models.email_template import EmailTemplate
from app.services.ai_service import AIService
from app.services.email_template_layout_service import (
    extract_palette_from_html,
    load_layout_base,
    resolve_layout_asset_url,
    save_layout_base,
)
from app.services.email_template_image_service import generate_slot_image
from app.services.email_template_import_service import (
    MAX_HTML_CHARS,
    analyze_email_html,
    apply_image_replacements,
)
from app.services.media.openai_image_catalog import OPENAI_IMAGE_DEFAULT_CATALOG_ID
from app.services.public_urls import absolute_media_url, normalize_stored_file_url
from app.services.usage_allowance import require_usage_allowance
from app.services.usage_tracker import set_usage_context


router = APIRouter(prefix="/email-templates", tags=["email-templates"], redirect_slashes=False)


class EmailLayoutBaseRequest(BaseModel):
    label: str = Field(default="Email layout base", max_length=120)
    layout_image_url: str | None = Field(default=None, max_length=2000)
    layout_asset_id: UUID | None = None
    layout_html: str | None = Field(default=None, max_length=200_000)


class EmailTemplateGenerateRequest(BaseModel):
    brand_id: UUID | None = None
    campaign_name: str = Field(min_length=2, max_length=255)
    email_type: str = Field(default="promotional", min_length=2, max_length=80)
    audience: str = Field(default="", max_length=1500)
    offer: str = Field(default="", max_length=2000)
    landing_page_url: HttpUrl | None = None
    notes: str = Field(default="", max_length=3000)
    image_model: str = Field(default=OPENAI_IMAGE_DEFAULT_CATALOG_ID, max_length=120)
    use_layout_base: bool = False
    hero_mode: str = Field(default="generate_from_layout", max_length=40)


class EmailTemplateUpdateRequest(BaseModel):
    campaign_name: str = Field(min_length=2, max_length=255)
    email_type: str = Field(default="promotional", min_length=2, max_length=80)
    subject: str = Field(default="", max_length=255)
    preheader: str = Field(default="", max_length=500)
    content: dict = Field(default_factory=dict)


def _response(row: EmailTemplate) -> dict:
    return {
        "id": str(row.id),
        "brand_id": str(row.brand_id) if row.brand_id else None,
        "campaign_name": row.campaign_name,
        "email_type": row.email_type,
        "status": row.status,
        "subject": row.subject,
        "preheader": row.preheader,
        "content": row.content or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def _brand(db: AsyncSession, tenant_id: UUID, brand_id: UUID | None) -> Brand | None:
    if not brand_id:
        return None
    result = await db.execute(select(Brand).where(Brand.id == brand_id, Brand.tenant_id == tenant_id))
    brand = result.scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    return brand


@router.get("/layout-base")
async def get_email_layout_base(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await load_layout_base(db, current_user.tenant_id)


@router.put("/layout-base")
async def put_email_layout_base(
    payload: EmailLayoutBaseRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    image_url = (payload.layout_image_url or "").strip() or None
    if payload.layout_asset_id and not image_url:
        image_url = await resolve_layout_asset_url(
            db, current_user.tenant_id, payload.layout_asset_id, None
        )
    saved = await save_layout_base(
        db,
        current_user.tenant_id,
        label=payload.label,
        layout_image_url=image_url,
        layout_asset_id=payload.layout_asset_id,
        layout_html=payload.layout_html,
    )
    await db.commit()
    return saved


@router.get("")
async def list_email_templates(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = list((await db.execute(
        select(EmailTemplate)
        .where(EmailTemplate.tenant_id == current_user.tenant_id)
        .order_by(EmailTemplate.updated_at.desc())
    )).scalars().all())
    return [_response(row) for row in rows]


@router.get("/{template_id}")
async def get_email_template(
    template_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(EmailTemplate).where(
        EmailTemplate.id == template_id,
        EmailTemplate.tenant_id == current_user.tenant_id,
    ))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Email template not found")
    return _response(row)


@router.post("/generate", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_usage_allowance)])
async def generate_email_template(
    payload: EmailTemplateGenerateRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    brand = await _brand(db, current_user.tenant_id, payload.brand_id)
    brand_name = brand.name if brand else "Your brand"
    primary = (brand.primary_color if brand else None) or "#111827"
    secondary = (brand.secondary_color if brand else None) or "#A3D16B"
    voice = ""
    if brand and isinstance(brand.voice_rules, dict):
        voice = str(brand.voice_rules.get("description") or "")

    set_usage_context(
        user_id=str(current_user.id),
        tenant_id=str(current_user.tenant_id),
        brand_id=str(brand.id) if brand else None,
        brand_name=brand_name,
        operation="email_template_generation",
    )
    brief = {
        "product_name": payload.campaign_name,
        "objective": f"Create a {payload.email_type} email. Offer: {payload.offer}",
        "target_audience": payload.audience,
        "ad_copy_tone": voice or "Clear, warm and persuasive",
        "cta": "Find out more",
        "key_benefits": {"offer": payload.offer, "notes": payload.notes},
    }
    copy = await AIService().generate_ad_copy(
        brand_voice=voice,
        forbidden_words=list(brand.forbidden_words or []) if brand else [],
        brief=brief,
        format_type="responsive marketing email",
        model="claude",
    )
    subject = str(copy.get("hook") or payload.campaign_name).strip()[:255]
    headline = str(copy.get("headline") or payload.campaign_name).strip()
    body = str(copy.get("body_copy") or payload.offer or payload.notes).strip()
    cta = str(copy.get("cta") or "Find out more").strip()
    preheader = (payload.offer or body or f"An update from {brand_name}").strip()[:180]

    layout_ref_url: str | None = None
    layout_html = ""
    layout_asset_id: UUID | None = None
    if payload.use_layout_base:
        base = await load_layout_base(db, current_user.tenant_id)
        layout_html = str(base.get("layout_html") or "")
        raw_asset = base.get("layout_asset_id")
        if raw_asset:
            try:
                layout_asset_id = UUID(str(raw_asset))
            except ValueError:
                layout_asset_id = None
        layout_ref_url = await resolve_layout_asset_url(
            db,
            current_user.tenant_id,
            layout_asset_id,
            str(base.get("layout_image_url") or ""),
        )
        if layout_html:
            palette = extract_palette_from_html(layout_html)
            primary = palette.get("primary_color") or primary
            secondary = palette.get("secondary_color") or secondary

    hero_mode = (payload.hero_mode or "generate_from_layout").strip().lower()
    hero_url = ""
    if payload.use_layout_base and layout_ref_url and hero_mode == "use_layout_image":
        hero_url = layout_ref_url
    else:
        image_prompt = (
            f"Create a premium landscape hero photograph for a {payload.email_type} marketing email from {brand_name}. "
            f"Campaign: {payload.campaign_name}. Audience: {payload.audience}. Offer/context: {payload.offer}. "
            f"Notes: {payload.notes}. Brand palette: {primary} and {secondary}. "
            "Email-safe composition, subject placed to one side with clean negative space for HTML copy, realistic lighting, "
            "high-end commercial art direction. IMAGE ONLY: no text, no letters, no CTA button, no logo, no fake interface."
        )
        if layout_ref_url:
            image_prompt += (
                " Match the colour balance, lighting and visual rhythm of the uploaded email layout reference "
                "(same brand feel; do not copy any text from the reference)."
            )
        ref_url = layout_ref_url if payload.use_layout_base and layout_ref_url and hero_mode == "generate_from_layout" else None
        image_result = await AIService().generate_image_asset(
            prompt=image_prompt,
            tenant_id=str(current_user.tenant_id),
            model=payload.image_model,
            format_type="video",
            reference_image_url=ref_url,
        )
        hero_url = str(image_result.get("url") or image_result.get("image_url") or "").strip()
        if not hero_url:
            raise HTTPException(status_code=502, detail=str(image_result.get("error") or "Hero image generation failed"))

    content = {
        "brand_name": brand_name,
        "logo_url": brand.logo_url if brand else None,
        "primary_color": primary,
        "secondary_color": secondary,
        "background_color": "#F5F5F2",
        "surface_color": "#FFFFFF",
        "text_color": "#202124",
        "eyebrow": payload.email_type.replace("_", " ").title(),
        "headline": headline,
        "body": body,
        "cta_text": cta,
        "cta_url": str(payload.landing_page_url or "#"),
        "hero_url": hero_url,
        "layout_reference_url": layout_ref_url,
        "layout_html_snippet": layout_html[:8000] if layout_html else None,
        "footer_text": f"You are receiving this email from {brand_name}.",
        "show_logo": True,
        "show_hero": True,
    }
    row = EmailTemplate(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        brand_id=payload.brand_id,
        campaign_name=payload.campaign_name,
        email_type=payload.email_type,
        subject=subject,
        preheader=preheader,
        content=content,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return _response(row)


# ── Use the customer's own HTML email: find image spots, fit AI pictures, export ──────────


class ImportAnalyzeRequest(BaseModel):
    html: str = Field(min_length=10, max_length=MAX_HTML_CHARS)


class ImportGenerateImageRequest(BaseModel):
    brand_id: UUID | None = None
    campaign_name: str = Field(default="", max_length=255)
    slot_id: str = Field(min_length=2, max_length=20)
    role: str = Field(default="content", max_length=20)
    width: int = Field(ge=16, le=4000)
    height: int = Field(ge=16, le=4000)
    description: str = Field(default="", max_length=600)
    alt: str = Field(default="", max_length=300)
    context_text: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=1000)
    image_model: str = Field(default=OPENAI_IMAGE_DEFAULT_CATALOG_ID, max_length=120)


class ImportExportRequest(BaseModel):
    html: str = Field(min_length=10, max_length=MAX_HTML_CHARS)
    replacements: dict[str, str] = Field(default_factory=dict, max_length=60)


@router.post("/import/analyze")
async def analyze_imported_email(
    payload: ImportAnalyzeRequest,
    current_user=Depends(get_current_user),
):
    """List the image spots in an uploaded email. Nothing is generated or changed."""
    try:
        return analyze_email_html(payload.html)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import/generate-image", dependencies=[Depends(require_usage_allowance)])
async def generate_imported_email_image(
    payload: ImportGenerateImageRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate one picture cropped to the exact shape of one image spot."""
    brand = await _brand(db, current_user.tenant_id, payload.brand_id)
    set_usage_context(
        user_id=str(current_user.id),
        tenant_id=str(current_user.tenant_id),
        brand_id=str(brand.id) if brand else None,
        brand_name=brand.name if brand else None,
        operation="email_template_image",
    )
    palette = None
    if brand and brand.primary_color and brand.secondary_color:
        palette = (brand.primary_color, brand.secondary_color)
    try:
        image = await generate_slot_image(
            tenant_id=str(current_user.tenant_id),
            model=payload.image_model,
            role=payload.role,
            width=payload.width,
            height=payload.height,
            description=payload.description,
            alt=payload.alt,
            context_text=payload.context_text,
            brand_name=brand.name if brand else "",
            campaign_name=payload.campaign_name,
            palette=palette,
            notes=payload.notes,
        )
    except Exception as exc:  # provider errors must not look like a server crash
        raise HTTPException(status_code=502, detail=f"Image generation failed: {str(exc)[:300]}") from exc
    return {"slot_id": payload.slot_id, **image, "absolute_url": absolute_media_url(image["url"])}


@router.post("/import/export")
async def export_imported_email(
    payload: ImportExportRequest,
    current_user=Depends(get_current_user),
):
    """Return the customer's HTML with only the chosen image addresses swapped."""
    tenant_prefix = f"/files/{current_user.tenant_id}/"
    resolved: dict[str, str] = {}
    for slot_id, raw_url in payload.replacements.items():
        url = (raw_url or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            # An app file path: it must belong to this workspace.
            stored = normalize_stored_file_url(url)
            if not stored.startswith(tenant_prefix):
                raise HTTPException(status_code=400, detail=f"Image for {slot_id} is not from this workspace")
        resolved[slot_id] = absolute_media_url(url)
    try:
        return apply_image_replacements(payload.html, resolved)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{template_id}")
async def update_email_template(
    template_id: UUID,
    payload: EmailTemplateUpdateRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(EmailTemplate).where(
        EmailTemplate.id == template_id,
        EmailTemplate.tenant_id == current_user.tenant_id,
    ))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Email template not found")
    row.campaign_name = payload.campaign_name
    row.email_type = payload.email_type
    row.subject = payload.subject
    row.preheader = payload.preheader
    row.content = dict(payload.content or {})
    await db.flush()
    await db.refresh(row)
    return _response(row)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_email_template(
    template_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(EmailTemplate).where(
        EmailTemplate.id == template_id,
        EmailTemplate.tenant_id == current_user.tenant_id,
    ))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Email template not found")
    await db.delete(row)

