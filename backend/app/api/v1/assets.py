import mimetypes
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.asset import Asset
from app.schemas.performance import AssetResponse
from app.services.file_service import file_service

router = APIRouter(prefix="/assets", tags=["assets"], redirect_slashes=False)


class RegisterGeneratedAssetRequest(BaseModel):
    file_url: str = Field(min_length=1)
    brand_id: UUID | None = None
    file_name: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/upload", response_model=AssetResponse, status_code=201)
async def upload_asset(
    file: UploadFile = File(...),
    variant_id: Optional[UUID] = Form(None),
    brand_id: Optional[UUID] = Form(None),
    asset_type: str = Form("image"),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    file_data = await file_service.save_file(file, str(current_user.tenant_id), asset_type)
    asset = Asset(
        tenant_id=current_user.tenant_id,
        variant_id=variant_id,
        brand_id=brand_id,
        asset_type=asset_type,
        created_by=current_user.id,
        **file_data,
    )
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return asset


@router.get("", response_model=list[AssetResponse], include_in_schema=False)
@router.get("/", response_model=list[AssetResponse])
async def list_assets(
    variant_id: Optional[UUID] = Query(None),
    brand_id: Optional[UUID] = Query(None),
    asset_type: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Asset).where(Asset.tenant_id == current_user.tenant_id)
    if variant_id:
        q = q.where(Asset.variant_id == variant_id)
    if brand_id:
        q = q.where(Asset.brand_id == brand_id)
    if asset_type:
        q = q.where(Asset.asset_type == asset_type)
        # Image-brief Brand Kit references are created by the analyzed
        # reference-image flow. Creative Studio attachments use a separate
        # asset type and legacy unclassified uploads must not leak into this
        # library.
        if asset_type == "reference_image":
            q = q.where(Asset.asset_metadata["analysis"].is_not(None))
    result = await db.execute(q.order_by(Asset.created_at.desc()))
    return list(result.scalars().all())


@router.post("/register-generated", response_model=AssetResponse)
async def register_generated_asset(
    data: RegisterGeneratedAssetRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a tenant-owned Creative Studio image to the reusable image library."""
    tenant_id = str(current_user.tenant_id)
    prefix = f"/files/{tenant_id}/"
    file_url = unquote(data.file_url.strip())
    if not file_url.startswith(prefix):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only images generated in this workspace can be saved to the library",
        )

    upload_root = Path(file_service.upload_dir).resolve()
    local_path = (upload_root / file_url.removeprefix("/files/")).resolve()
    try:
        local_path.relative_to(upload_root)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid generated image path") from exc
    if not local_path.is_file():
        raise HTTPException(status_code=404, detail="Generated image file not found")

    existing_result = await db.execute(
        select(Asset).where(
            Asset.tenant_id == current_user.tenant_id,
            Asset.file_url == file_url,
            Asset.asset_type == "creative_studio_reference",
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        return existing

    content_type = mimetypes.guess_type(local_path.name)[0] or "image/png"
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="Only generated images can be saved to this library")
    width: int | None = None
    height: int | None = None
    try:
        from PIL import Image

        with Image.open(local_path) as image:
            width, height = image.size
    except Exception:
        pass

    metadata = dict(data.metadata or {})
    metadata.update({"source": "creative_studio_generated", "reusable": True})
    asset = Asset(
        tenant_id=current_user.tenant_id,
        brand_id=data.brand_id,
        asset_type="creative_studio_reference",
        created_by=current_user.id,
        file_name=(data.file_name or local_path.name)[:500],
        file_path=str(local_path),
        file_url=file_url,
        file_type=content_type,
        file_size=local_path.stat().st_size,
        width=width,
        height=height,
        asset_metadata=metadata,
    )
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return asset


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.tenant_id == current_user.tenant_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(
    asset_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.tenant_id == current_user.tenant_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    await file_service.delete_file(asset.file_path)
    await db.delete(asset)
