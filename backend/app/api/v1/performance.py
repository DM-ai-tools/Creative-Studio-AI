from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.performance import DashboardStats, MetricResponse
from app.services.performance_service import PerformanceService

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard_stats(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await PerformanceService.get_dashboard_stats(db, current_user.tenant_id)


@router.get("/top-performers")
async def top_performers(
    limit: int = Query(10, le=50),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await PerformanceService.get_top_performers(db, current_user.tenant_id, limit)


@router.get("/fatigue-alerts")
async def fatigue_alerts(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await PerformanceService.get_fatigue_alerts(db, current_user.tenant_id)


@router.get("/variants/{variant_id}/metrics", response_model=list[MetricResponse])
async def variant_metrics(
    variant_id: UUID,
    days: int = Query(30, le=365),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await PerformanceService.get_variant_metrics(db, variant_id, current_user.tenant_id, days)
