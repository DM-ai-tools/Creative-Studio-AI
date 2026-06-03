from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.variant import Variant
from app.models.performance import PerformanceRollup
from app.schemas.variant import VariantUpdate


class VariantService:
    @staticmethod
    async def list_variants(
        db: AsyncSession,
        tenant_id: UUID,
        brief_id: UUID | None = None,
        variant_status: str | None = None,
        compliance_status: str | None = None,
    ) -> list[Variant]:
        q = select(Variant).where(Variant.tenant_id == tenant_id)
        if brief_id:
            q = q.where(Variant.brief_id == brief_id)
        if variant_status:
            q = q.where(Variant.status == variant_status)
        if compliance_status:
            q = q.where(Variant.compliance_status == compliance_status)
        q = q.order_by(Variant.created_at.desc())
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def get_variant(db: AsyncSession, variant_id: UUID, tenant_id: UUID) -> Variant:
        result = await db.execute(
            select(Variant).where(Variant.id == variant_id, Variant.tenant_id == tenant_id)
        )
        variant = result.scalar_one_or_none()
        if not variant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
        return variant

    @staticmethod
    async def update_variant(
        db: AsyncSession, variant_id: UUID, tenant_id: UUID, data: VariantUpdate
    ) -> Variant:
        variant = await VariantService.get_variant(db, variant_id, tenant_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(variant, field, value)
        await db.flush()
        await db.refresh(variant)
        return variant

    @staticmethod
    async def approve_variant(db: AsyncSession, variant_id: UUID, tenant_id: UUID) -> Variant:
        variant = await VariantService.get_variant(db, variant_id, tenant_id)
        variant.status = "APPROVED"
        await db.flush()
        await db.refresh(variant)
        return variant

    @staticmethod
    async def reject_variant(db: AsyncSession, variant_id: UUID, tenant_id: UUID) -> Variant:
        variant = await VariantService.get_variant(db, variant_id, tenant_id)
        variant.status = "REJECTED"
        await db.flush()
        await db.refresh(variant)
        return variant

    @staticmethod
    def _unlink_pipeline_file(file_url: str | None) -> None:
        if not file_url or not file_url.startswith("/files/"):
            return
        upload_root = Path(settings.UPLOAD_DIR).resolve()
        rel = file_url.removeprefix("/files/")
        path = (upload_root / rel).resolve()
        try:
            path.relative_to(upload_root)
        except ValueError:
            return
        if path.is_file():
            path.unlink()

    @staticmethod
    async def delete_variant(db: AsyncSession, variant_id: UUID, tenant_id: UUID) -> None:
        variant = await VariantService.get_variant(db, variant_id, tenant_id)
        pipeline = (variant.generation_params or {}).get("pipeline") or {}
        for step in ("image", "video"):
            media = pipeline.get(step) or {}
            VariantService._unlink_pipeline_file(media.get("url"))
        await db.delete(variant)
        await db.flush()

    @staticmethod
    async def get_fatigue_alerts(db: AsyncSession, tenant_id: UUID) -> list[dict]:
        result = await db.execute(
            select(PerformanceRollup, Variant)
            .join(Variant, PerformanceRollup.variant_id == Variant.id)
            .where(PerformanceRollup.tenant_id == tenant_id, PerformanceRollup.is_fatigued == True)
            .order_by(PerformanceRollup.roas_7d.asc())
        )
        alerts = []
        for rollup, variant in result.all():
            drop_pct = 0.0
            if rollup.roas_personal_best > 0:
                drop_pct = round(
                    (1 - float(rollup.roas_7d) / float(rollup.roas_personal_best)) * 100, 1
                )
            alerts.append({
                "variant_id": str(variant.id),
                "hook": variant.hook,
                "format": variant.format,
                "roas_personal_best": float(rollup.roas_personal_best),
                "roas_7d": float(rollup.roas_7d),
                "drop_pct": drop_pct,
                "frequency_7d": float(rollup.frequency_7d),
                "status": rollup.status,
            })
        return alerts
