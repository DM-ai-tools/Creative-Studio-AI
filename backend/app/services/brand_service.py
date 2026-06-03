from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand, BrandKit
from app.schemas.brand import BrandCreate, BrandKitCreate, BrandUpdate


class BrandService:
    @staticmethod
    async def create_brand(db: AsyncSession, tenant_id: UUID, data: BrandCreate) -> Brand:
        brand = Brand(tenant_id=tenant_id, **data.model_dump())
        db.add(brand)
        await db.flush()
        await db.refresh(brand)
        return brand

    @staticmethod
    async def get_brand(db: AsyncSession, brand_id: UUID, tenant_id: UUID) -> Brand:
        result = await db.execute(
            select(Brand).where(Brand.id == brand_id, Brand.tenant_id == tenant_id)
        )
        brand = result.scalar_one_or_none()
        if not brand:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
        return brand

    @staticmethod
    async def list_brands(db: AsyncSession, tenant_id: UUID) -> list[Brand]:
        result = await db.execute(select(Brand).where(Brand.tenant_id == tenant_id))
        return list(result.scalars().all())

    @staticmethod
    async def update_brand(db: AsyncSession, brand_id: UUID, tenant_id: UUID, data: BrandUpdate) -> Brand:
        brand = await BrandService.get_brand(db, brand_id, tenant_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(brand, field, value)
        await db.flush()
        await db.refresh(brand)
        return brand

    @staticmethod
    async def delete_brand(db: AsyncSession, brand_id: UUID, tenant_id: UUID) -> None:
        brand = await BrandService.get_brand(db, brand_id, tenant_id)
        await db.delete(brand)

    @staticmethod
    async def create_brand_kit(db: AsyncSession, brand_id: UUID, tenant_id: UUID, data: BrandKitCreate) -> BrandKit:
        await BrandService.get_brand(db, brand_id, tenant_id)
        kit = BrandKit(brand_id=brand_id, **data.model_dump())
        db.add(kit)
        await db.flush()
        await db.refresh(kit)
        return kit

    @staticmethod
    async def get_brand_kit(db: AsyncSession, brand_id: UUID, tenant_id: UUID) -> BrandKit:
        await BrandService.get_brand(db, brand_id, tenant_id)
        result = await db.execute(select(BrandKit).where(BrandKit.brand_id == brand_id))
        kit = result.scalars().first()
        if not kit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand kit not found")
        return kit

    @staticmethod
    async def update_brand_kit(db: AsyncSession, kit_id: UUID, tenant_id: UUID, data: BrandKitCreate) -> BrandKit:
        result = await db.execute(
            select(BrandKit).join(Brand).where(BrandKit.id == kit_id, Brand.tenant_id == tenant_id)
        )
        kit = result.scalar_one_or_none()
        if not kit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand kit not found")
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(kit, field, value)
        await db.flush()
        await db.refresh(kit)
        return kit
