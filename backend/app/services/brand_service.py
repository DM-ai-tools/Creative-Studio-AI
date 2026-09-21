from typing import Any
from uuid import UUID

import logging
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand, BrandKit
from app.schemas.brand import BrandCreate, BrandKitCreate, BrandUpdate


from app.services.competitor_social_service import normalize_competitor_insights

logger = logging.getLogger(__name__)


def social_style_from_brand_and_kit(
    brand: Brand | None = None,
    kit: BrandKit | None = None,
) -> dict[str, Any] | None:
    """Read stored social feed style — Brand Kit is canonical, voice_rules is fallback."""
    if kit and isinstance(kit.colors, dict):
        raw = kit.colors.get("social_style_profile")
        if isinstance(raw, dict):
            return raw
    if brand and isinstance(brand.voice_rules, dict):
        raw = brand.voice_rules.get("social_style_profile")
        if isinstance(raw, dict):
            return raw
    return None


def competitor_insights_from_brand_and_kit(
    brand: Brand | None = None,
    kit: BrandKit | None = None,
) -> list[dict[str, Any]]:
    """Read stored competitor social insights — Brand Kit is canonical, voice_rules is fallback."""
    if kit and isinstance(kit.colors, dict):
        raw = kit.colors.get("competitor_social_insights")
        items = normalize_competitor_insights(raw)
        if items:
            return items
    if brand and isinstance(brand.voice_rules, dict):
        raw = brand.voice_rules.get("competitor_social_insights")
        return normalize_competitor_insights(raw)
    return []


def competitor_candidates_from_brand_and_kit(
    brand: Brand | None = None,
    kit: BrandKit | None = None,
) -> list[dict[str, Any]]:
    """Read suggested (unanalyzed) competitor candidates from Brand Kit."""
    from app.services.competitor_discovery_service import normalize_competitor_candidates

    if kit and isinstance(kit.colors, dict):
        raw = kit.colors.get("competitor_candidates")
        items = normalize_competitor_candidates(raw)
        if items:
            return items
    if brand and isinstance(brand.voice_rules, dict):
        raw = brand.voice_rules.get("competitor_candidates")
        return normalize_competitor_candidates(raw)
    return []


class BrandService:
    @staticmethod
    def _persist_remote_logo_variations(
        variations: dict[str, Any] | None,
        *,
        tenant_id: UUID,
    ) -> dict[str, Any]:
        """Download scraped http(s) logo URLs into /files/ so compositing always works."""
        if not variations or not isinstance(variations, dict):
            return variations or {}
        from app.services.brand_logo import persist_remote_logo_url

        out = dict(variations)
        for key, value in list(out.items()):
            if not value or not str(value).strip().startswith(("http://", "https://")):
                continue
            persisted = persist_remote_logo_url(str(value), tenant_id=str(tenant_id))
            if persisted:
                out[key] = persisted
        return out

    @staticmethod
    async def repair_brand_logo_if_needed(
        db: AsyncSession,
        brand: Brand,
        tenant_id: UUID,
    ) -> Brand:
        """Convert scraped SVG/remote logos to /files/ PNG so compositing works."""
        raw = str(brand.logo_url or "").strip()
        if not raw.startswith(("http://", "https://")):
            return brand
        from app.services.brand_logo import persist_remote_logo_url, resolve_downloadable_logo_url

        downloadable = resolve_downloadable_logo_url(raw)
        persisted = persist_remote_logo_url(downloadable, tenant_id=str(tenant_id))
        if persisted and persisted != raw:
            brand.logo_url = persisted
            await db.flush()
            await db.refresh(brand)
            logger.info("Repaired brand logo for %s → %s", brand.name, persisted)
        return brand

    @staticmethod
    async def create_brand(db: AsyncSession, tenant_id: UUID, data: BrandCreate) -> Brand:
        payload = data.model_dump()
        if payload.get("logo_url") and str(payload["logo_url"]).startswith(("http://", "https://")):
            from app.services.brand_logo import persist_remote_logo_url

            persisted = persist_remote_logo_url(
                str(payload["logo_url"]),
                tenant_id=str(tenant_id),
            )
            if persisted:
                payload["logo_url"] = persisted
        brand = Brand(tenant_id=tenant_id, **payload)
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
        payload = data.model_dump(exclude_none=True)
        if payload.get("logo_url") and str(payload["logo_url"]).startswith(("http://", "https://")):
            from app.services.brand_logo import persist_remote_logo_url

            persisted = persist_remote_logo_url(
                str(payload["logo_url"]),
                tenant_id=str(tenant_id),
            )
            if persisted:
                payload["logo_url"] = persisted
        for field, value in payload.items():
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
        payload = data.model_dump()
        payload["logo_variations"] = BrandService._persist_remote_logo_variations(
            payload.get("logo_variations"),
            tenant_id=tenant_id,
        )
        kit = BrandKit(brand_id=brand_id, **payload)
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
    async def persist_social_style_profile(
        db: AsyncSession,
        brand: Brand,
        profile: dict[str, Any],
    ) -> BrandKit:
        """Store social media visual style on the brand's Brand Kit (and mirror in voice_rules)."""
        voice_rules = dict(brand.voice_rules or {})
        voice_rules["social_style_profile"] = profile
        voice_rules["social_style_fetched_at"] = profile.get("fetched_at")
        brand.voice_rules = voice_rules

        result = await db.execute(select(BrandKit).where(BrandKit.brand_id == brand.id))
        kit = result.scalars().first()
        if not kit:
            kit = BrandKit(
                brand_id=brand.id,
                name="Default Kit",
                colors={
                    "primary": brand.primary_color or "#0F1B3D",
                    "secondary": brand.secondary_color or "#00C2A8",
                },
                fonts={},
                logo_variations={},
            )
            db.add(kit)

        colors = dict(kit.colors or {})
        colors["social_style_profile"] = profile
        colors["social_style_fetched_at"] = profile.get("fetched_at")
        if profile.get("effective_primary_color"):
            colors["social_primary"] = profile["effective_primary_color"]
        if profile.get("effective_secondary_color"):
            colors["social_secondary"] = profile["effective_secondary_color"]
        kit.colors = colors

        await db.flush()
        await db.refresh(brand)
        await db.refresh(kit)
        return kit

    @staticmethod
    async def persist_competitor_social_insights(
        db: AsyncSession,
        brand: Brand,
        insights: list[dict[str, Any]],
    ) -> BrandKit:
        """Store competitor social strategy on Brand Kit (mirror in voice_rules)."""
        voice_rules = dict(brand.voice_rules or {})
        voice_rules["competitor_social_insights"] = insights
        fetched_at = max(
            (str(i.get("fetched_at") or "") for i in insights),
            default="",
        )
        if fetched_at:
            voice_rules["competitor_social_fetched_at"] = fetched_at
        brand.voice_rules = voice_rules

        result = await db.execute(select(BrandKit).where(BrandKit.brand_id == brand.id))
        kit = result.scalars().first()
        if not kit:
            kit = BrandKit(
                brand_id=brand.id,
                name="Default Kit",
                colors={
                    "primary": brand.primary_color or "#0F1B3D",
                    "secondary": brand.secondary_color or "#00C2A8",
                },
                fonts={},
                logo_variations={},
            )
            db.add(kit)

        colors = dict(kit.colors or {})
        colors["competitor_social_insights"] = insights
        if fetched_at:
            colors["competitor_social_fetched_at"] = fetched_at
        kit.colors = colors

        await db.flush()
        await db.refresh(brand)
        await db.refresh(kit)
        return kit

    @staticmethod
    async def persist_competitor_candidates(
        db: AsyncSession,
        brand: Brand,
        candidates: list[dict[str, Any]],
    ) -> BrandKit:
        """Store suggested competitor list on Brand Kit (mirror in voice_rules)."""
        voice_rules = dict(brand.voice_rules or {})
        voice_rules["competitor_candidates"] = candidates
        brand.voice_rules = voice_rules

        result = await db.execute(select(BrandKit).where(BrandKit.brand_id == brand.id))
        kit = result.scalars().first()
        if not kit:
            kit = BrandKit(
                brand_id=brand.id,
                name="Default Kit",
                colors={
                    "primary": brand.primary_color or "#0F1B3D",
                    "secondary": brand.secondary_color or "#00C2A8",
                },
                fonts={},
                logo_variations={},
            )
            db.add(kit)

        colors = dict(kit.colors or {})
        colors["competitor_candidates"] = candidates
        kit.colors = colors

        await db.flush()
        await db.refresh(brand)
        await db.refresh(kit)
        return kit

    @staticmethod
    async def update_brand_kit(db: AsyncSession, kit_id: UUID, tenant_id: UUID, data: BrandKitCreate) -> BrandKit:
        result = await db.execute(
            select(BrandKit).join(Brand).where(BrandKit.id == kit_id, Brand.tenant_id == tenant_id)
        )
        kit = result.scalar_one_or_none()
        if not kit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand kit not found")
        payload = data.model_dump(exclude_none=True)
        if "logo_variations" in payload:
            payload["logo_variations"] = BrandService._persist_remote_logo_variations(
                payload.get("logo_variations"),
                tenant_id=tenant_id,
            )
        for field, value in payload.items():
            setattr(kit, field, value)
        await db.flush()
        await db.refresh(kit)
        return kit
