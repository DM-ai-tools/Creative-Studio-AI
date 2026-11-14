from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.usage_allowance_reset import UsageAllowanceReset
from app.models.usage_event import UsageEvent
from app.models.user import User
from app.services.usage_tracker import effective_cost_usd

DEFAULT_USER_ALLOWANCE_USD = 30.0
# Temporarily disabled: keep spend tracking, reset history, and admin reporting,
# but do not stop paid generation at $30. Set this back to True when management
# wants the approval gate enabled again.
USAGE_ALLOWANCE_ENFORCEMENT_ENABLED = False


async def _latest_reset(db: AsyncSession, user_id: UUID) -> UsageAllowanceReset | None:
    result = await db.execute(
        select(UsageAllowanceReset)
        .where(UsageAllowanceReset.user_id == user_id)
        .order_by(UsageAllowanceReset.reset_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _usage_rows(db: AsyncSession, user_id: UUID, since: datetime | None = None) -> list[UsageEvent]:
    # Count recorded spend, including a failed provider call when it carried a real charge.
    # Zero-cost failures naturally add nothing through effective_cost_usd().
    query = select(UsageEvent).where(UsageEvent.user_id == user_id)
    if since is not None:
        query = query.where(UsageEvent.created_at >= since)
    return list((await db.execute(query)).scalars().all())


async def allowance_status(db: AsyncSession, user: User) -> dict[str, Any]:
    exempt = user.role == "admin"
    latest = await _latest_reset(db, user.id)
    limit_usd = float(latest.limit_usd) if latest else DEFAULT_USER_ALLOWANCE_USD
    period_started_at = latest.reset_at if latest else user.created_at
    period_rows = await _usage_rows(db, user.id, period_started_at)
    lifetime_rows = await _usage_rows(db, user.id)
    period_spend = round(sum(effective_cost_usd(row) for row in period_rows), 4)
    lifetime_spend = round(sum(effective_cost_usd(row) for row in lifetime_rows), 4)
    reset_count = int(
        (await db.execute(
            select(func.count()).select_from(UsageAllowanceReset).where(
                UsageAllowanceReset.user_id == user.id
            )
        )).scalar() or 0
    )
    reached = (
        USAGE_ALLOWANCE_ENFORCEMENT_ENABLED
        and (not exempt)
        and period_spend >= limit_usd
    )
    return {
        "user_id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "exempt": exempt,
        "limit_usd": limit_usd,
        "period_spend_usd": period_spend,
        "remaining_usd": None if exempt else round(max(0.0, limit_usd - period_spend), 4),
        "lifetime_spend_usd": lifetime_spend,
        "limit_reached": reached,
        "period_started_at": period_started_at.isoformat() if period_started_at else None,
        "last_reset_at": latest.reset_at.isoformat() if latest else None,
        "reset_count": reset_count,
    }


async def require_usage_allowance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not USAGE_ALLOWANCE_ENFORCEMENT_ENABLED:
        return current_user
    if current_user.role == "admin":
        return current_user
    snapshot = await allowance_status(db, current_user)
    if snapshot["limit_reached"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "USER_USAGE_LIMIT_REACHED",
                "message": "Your generation allowance is currently paused. Please contact an administrator.",
                "limit_usd": snapshot["limit_usd"],
                "period_spend_usd": snapshot["period_spend_usd"],
            },
        )
    return current_user


async def reset_allowance(
    db: AsyncSession,
    *,
    target_user: User,
    reset_by: User,
    note: str = "",
) -> dict[str, Any]:
    if target_user.role == "admin":
        raise HTTPException(status_code=400, detail="Admin accounts are exempt and cannot be reset")
    before = await allowance_status(db, target_user)
    row = UsageAllowanceReset(
        tenant_id=target_user.tenant_id,
        user_id=target_user.id,
        reset_by=reset_by.id,
        limit_usd=DEFAULT_USER_ALLOWANCE_USD,
        previous_period_spend_usd=before["period_spend_usd"],
        note=(note or "")[:500],
        reset_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    return await allowance_status(db, target_user)
