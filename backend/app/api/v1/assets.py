from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.asset import Asset
from app.schemas.performance import AssetResponse
from app.services.file_service import file_service

router = APIRouter(prefix="/assets", tags=["assets"])


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


@router.get("/", response_model=list[AssetResponse])
async def list_assets(
    variant_id: Optional[UUID] = Query(None),
    asset_type: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Asset).where(Asset.tenant_id == current_user.tenant_id)
    if variant_id:
        q = q.where(Asset.variant_id == variant_id)
    if asset_type:
        q = q.where(Asset.asset_type == asset_type)
    result = await db.execute(q.order_by(Asset.created_at.desc()))
    return list(result.scalars().all())


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
        from fastapi import HTTPException, status
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
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    await file_service.delete_file(asset.file_path)
    await db.delete(asset)
