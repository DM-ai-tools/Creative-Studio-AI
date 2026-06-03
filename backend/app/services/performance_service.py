from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.performance import PerformanceMetric, PerformanceRollup
from app.models.variant import Variant
from app.schemas.performance import DashboardStats, MetricResponse


class PerformanceService:
    @staticmethod
    async def get_dashboard_stats(db: AsyncSession, tenant_id: UUID) -> DashboardStats:
        active_result = await db.execute(
            select(func.count()).where(
                Variant.tenant_id == tenant_id, Variant.status == "ACTIVE"
            )
        )
        active_variants = active_result.scalar() or 0

        roas_result = await db.execute(
            select(func.avg(PerformanceRollup.roas_7d)).where(
                PerformanceRollup.tenant_id == tenant_id
            )
        )
        avg_roas = float(roas_result.scalar() or 0.0)

        safety_result = await db.execute(
            select(
                func.sum(PerformanceRollup.passed),
                func.sum(PerformanceRollup.checked),
            ).where(PerformanceRollup.tenant_id == tenant_id)
        )
        row = safety_result.first()
        passed, checked = (row[0] or 0), (row[1] or 0)
        pass_rate = (passed / checked) if checked > 0 else 1.0

        fatigued_result = await db.execute(
            select(func.count()).where(
                PerformanceRollup.tenant_id == tenant_id,
                PerformanceRollup.is_fatigued == True,
            )
        )
        fatigued_count = fatigued_result.scalar() or 0

        return DashboardStats(
            active_variants=active_variants,
            avg_roas_7d=round(avg_roas, 2),
            brand_safety_pass_rate=round(pass_rate, 4),
            fatigued_count=fatigued_count,
        )

    @staticmethod
    async def get_variant_metrics(
        db: AsyncSession, variant_id: UUID, tenant_id: UUID, days: int = 30
    ) -> list[MetricResponse]:
        cutoff = date.today() - timedelta(days=days)
        result = await db.execute(
            select(PerformanceMetric)
            .where(
                PerformanceMetric.variant_id == variant_id,
                PerformanceMetric.tenant_id == tenant_id,
                PerformanceMetric.date >= cutoff,
            )
            .order_by(PerformanceMetric.date.asc())
        )
        return [MetricResponse.model_validate(m) for m in result.scalars().all()]

    @staticmethod
    async def get_top_performers(db: AsyncSession, tenant_id: UUID, limit: int = 10) -> list[dict]:
        result = await db.execute(
            select(PerformanceRollup, Variant)
            .join(Variant, PerformanceRollup.variant_id == Variant.id)
            .where(PerformanceRollup.tenant_id == tenant_id)
            .order_by(PerformanceRollup.roas_7d.desc())
            .limit(limit)
        )
        return [
            {
                "variant_id": str(v.id),
                "hook": v.hook,
                "format": v.format,
                "roas_7d": float(r.roas_7d),
                "status": r.status,
            }
            for r, v in result.all()
        ]

    @staticmethod
    async def get_fatigue_alerts(db: AsyncSession, tenant_id: UUID) -> list[dict]:
        from app.services.variant_service import VariantService
        return await VariantService.get_fatigue_alerts(db, tenant_id)
