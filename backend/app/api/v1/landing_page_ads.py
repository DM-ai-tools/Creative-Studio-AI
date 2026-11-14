from io import BytesIO
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from PIL import Image
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.asset import Asset
from app.models.brand import Brand
from app.services.file_service import file_service
from app.services.usage_allowance import require_usage_allowance
from app.services.landing_page_ads_service import (
    MAX_REFERENCES,
    create_landing_page_job,
    get_landing_page_job,
    list_landing_page_jobs,
    regenerate_landing_page_slides,
    run_landing_page_job,
)


router = APIRouter(prefix="/landing-page-ads", tags=["landing-page-ads"], redirect_slashes=False)

ALLOWED_REFERENCE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_REFERENCE_BYTES = 10 * 1024 * 1024


class LandingPageAdJobRequest(BaseModel):
    landing_page_url: HttpUrl
    user_prompt: str = Field(min_length=3, max_length=8_000)
    reference_asset_ids: list[UUID] = Field(default_factory=list, max_length=MAX_REFERENCES)
    brand_id: UUID | None = None
    image_model: str = Field(default="openai-gpt-image-2.6-sunburst", min_length=2, max_length=120)

    @field_validator("landing_page_url")
    @classmethod
    def require_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("Landing-page URL must use HTTPS")
        return value


class LandingPageAdRevisionRequest(BaseModel):
    user_prompt: str = Field(min_length=2, max_length=2_000)
    target_slide_indexes: list[int] = Field(min_length=1, max_length=20)

    @field_validator("target_slide_indexes")
    @classmethod
    def validate_indexes(cls, value: list[int]) -> list[int]:
        clean = sorted(set(value))
        if not clean or any(index < 1 for index in clean):
            raise ValueError("Slide indexes must be positive integers")
        return clean


async def _validate_brand(db: AsyncSession, tenant_id: UUID, brand_id: UUID | None) -> None:
    if not brand_id:
        return
    result = await db.execute(select(Brand.id).where(Brand.id == brand_id, Brand.tenant_id == tenant_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Brand not found")


async def _validate_references(
    db: AsyncSession,
    tenant_id: UUID,
    reference_ids: list[UUID],
) -> None:
    if not reference_ids:
        return
    result = await db.execute(
        select(Asset.id).where(Asset.id.in_(reference_ids), Asset.tenant_id == tenant_id)
    )
    found = {row[0] for row in result.all()}
    missing = [str(item) for item in reference_ids if item not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"Reference assets not found: {', '.join(missing)}")


@router.post("/references", status_code=status.HTTP_201_CREATED)
async def upload_landing_page_references(
    files: Annotated[list[UploadFile], File(...)],
    brand_id: Annotated[UUID | None, Form()] = None,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not files or len(files) > MAX_REFERENCES:
        raise HTTPException(status_code=422, detail=f"Upload between 1 and {MAX_REFERENCES} images")
    await _validate_brand(db, current_user.tenant_id, brand_id)

    created: list[dict] = []
    for order, upload in enumerate(files, start=1):
        content_type = (upload.content_type or "").lower()
        if content_type not in ALLOWED_REFERENCE_TYPES:
            raise HTTPException(status_code=415, detail=f"Unsupported reference type: {content_type or 'unknown'}")
        content = await upload.read()
        if not content or len(content) > MAX_REFERENCE_BYTES:
            raise HTTPException(status_code=413, detail="Each reference image must be 10 MB or less")
        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
            with Image.open(BytesIO(content)) as image:
                width, height = image.size
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid image: {upload.filename}") from exc

        suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[content_type]
        saved = file_service.save_bytes(
            content,
            str(current_user.tenant_id),
            "landing-page-ad-references",
            suffix,
            content_type,
        )
        asset = Asset(
            tenant_id=current_user.tenant_id,
            brand_id=brand_id,
            asset_type="landing_page_ad_reference",
            created_by=current_user.id,
            file_name=(upload.filename or saved["file_name"])[:500],
            file_path=saved["file_path"],
            file_url=saved["file_url"],
            file_type=content_type,
            file_size=len(content),
            width=width,
            height=height,
            asset_metadata={"source": "landing_page_ads", "role": "visual_reference", "order": order},
        )
        db.add(asset)
        await db.flush()
        created.append(
            {
                "id": str(asset.id),
                "file_name": asset.file_name,
                "file_url": asset.file_url,
                "width": width,
                "height": height,
            }
        )
    await db.commit()
    return created


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_usage_allowance)])
async def create_job(
    payload: LandingPageAdJobRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _validate_brand(db, current_user.tenant_id, payload.brand_id)
    await _validate_references(db, current_user.tenant_id, payload.reference_asset_ids)
    job = create_landing_page_job(
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id),
        payload={
            "landing_page_url": str(payload.landing_page_url),
            "user_prompt": payload.user_prompt,
            "reference_asset_ids": [str(item) for item in payload.reference_asset_ids],
            "brand_id": str(payload.brand_id) if payload.brand_id else None,
            "image_model": payload.image_model,
        },
    )
    background_tasks.add_task(run_landing_page_job, job["id"])
    return job


@router.get("/jobs")
async def list_jobs(current_user=Depends(get_current_user)):
    return list_landing_page_jobs(str(current_user.tenant_id))


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, current_user=Depends(get_current_user)):
    job = get_landing_page_job(job_id, str(current_user.tenant_id))
    if not job:
        raise HTTPException(status_code=404, detail="Landing-page ad job not found")
    return job


@router.post("/jobs/{job_id}/revisions", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_usage_allowance)])
async def revise_job(
    job_id: str,
    payload: LandingPageAdRevisionRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    job = get_landing_page_job(job_id, str(current_user.tenant_id))
    if not job:
        raise HTTPException(status_code=404, detail="Landing-page ad job not found")
    if job.get("status") not in {"completed", "partial"}:
        raise HTTPException(status_code=409, detail="Wait for the current generation to finish")
    background_tasks.add_task(
        regenerate_landing_page_slides,
        job_id,
        str(current_user.tenant_id),
        payload.user_prompt,
        payload.target_slide_indexes,
    )
    return {**job, "status": "queued", "phase": "revision_queued"}
