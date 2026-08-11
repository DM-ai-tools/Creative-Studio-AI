from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.tenant import Tenant
from app.models.brand import Brand
from app.models.brief import Brief
from app.models.variant import Variant
from app.models.asset import Asset
from app.schemas.auth import UserResponse
from app.schemas.admin import AdminClientResponse, AdminStatsResponse
from app.services.auth_service import _user_response
from app.services.usage_tracker import usage_summary

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(current_user=Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def _is_platform_admin(user: User) -> bool:
    return (user.email or "").strip().lower() == settings.ADMIN_EMAIL.strip().lower()


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    current_user=Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    platform = _is_platform_admin(current_user)
    if platform:
        result = await db.execute(select(User).order_by(User.created_at.desc()))
    else:
        result = await db.execute(
            select(User)
            .where(User.tenant_id == current_user.tenant_id)
            .order_by(User.created_at.desc())
        )
    users = list(result.scalars().all())
    if not users:
        return []

    tenant_ids = {u.tenant_id for u in users if u.tenant_id}
    tenant_names: dict[UUID, str] = {}
    if tenant_ids:
        t_result = await db.execute(select(Tenant.id, Tenant.name).where(Tenant.id.in_(tenant_ids)))
        tenant_names = {row.id: row.name for row in t_result.all()}

    user_ids = [u.id for u in users]
    brief_counts: dict[UUID, int] = {}
    variant_counts: dict[UUID, int] = {}
    b_result = await db.execute(
        select(Brief.created_by, func.count())
        .where(Brief.created_by.in_(user_ids))
        .group_by(Brief.created_by)
    )
    brief_counts = {row[0]: int(row[1]) for row in b_result.all() if row[0]}
    v_result = await db.execute(
        select(Brief.created_by, func.count())
        .select_from(Variant)
        .join(Brief, Variant.brief_id == Brief.id)
        .where(Brief.created_by.in_(user_ids))
        .group_by(Brief.created_by)
    )
    variant_counts = {row[0]: int(row[1]) for row in v_result.all() if row[0]}

    out: list[UserResponse] = []
    for u in users:
        out.append(
            await _user_response(
                db,
                u,
                tenant_name=tenant_names.get(u.tenant_id) if u.tenant_id else None,
                brief_count=brief_counts.get(u.id, 0),
                variant_count=variant_counts.get(u.id, 0),
            )
        )
    return out


@router.get("/clients", response_model=list[AdminClientResponse])
async def list_clients(
    current_user=Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Platform admin: every client workspace. Workspace admin: their own client only."""
    if _is_platform_admin(current_user):
        t_result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    else:
        t_result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenants = list(t_result.scalars().all())
    if not tenants:
        return []

    ids = [t.id for t in tenants]

    async def _counts(model, col):
        rows = await db.execute(
            select(col, func.count()).where(col.in_(ids)).group_by(col)
        )
        return {row[0]: int(row[1]) for row in rows.all()}

    users = await _counts(User, User.tenant_id)
    brands = await _counts(Brand, Brand.tenant_id)
    briefs = await _counts(Brief, Brief.tenant_id)
    variants = await _counts(Variant, Variant.tenant_id)

    last_brief = await db.execute(
        select(Brief.tenant_id, func.max(Brief.updated_at)).where(Brief.tenant_id.in_(ids)).group_by(Brief.tenant_id)
    )
    last_login = await db.execute(
        select(User.tenant_id, func.max(User.last_login_at)).where(User.tenant_id.in_(ids)).group_by(User.tenant_id)
    )
    last_b = {row[0]: row[1] for row in last_brief.all()}
    last_l = {row[0]: row[1] for row in last_login.all()}

    out: list[AdminClientResponse] = []
    for t in tenants:
        activity = [d for d in (last_b.get(t.id), last_l.get(t.id), t.updated_at) if d]
        out.append(
            AdminClientResponse(
                id=t.id,
                name=t.name,
                slug=t.slug,
                plan=t.plan,
                is_active=t.is_active,
                user_count=users.get(t.id, 0),
                brand_count=brands.get(t.id, 0),
                brief_count=briefs.get(t.id, 0),
                variant_count=variants.get(t.id, 0),
                created_at=t.created_at,
                last_activity_at=max(activity) if activity else t.created_at,
            )
        )
    return out


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: UUID,
    role: str,
    current_user=Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    if role not in ("admin", "member", "viewer"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")

    query = select(User).where(User.id == user_id)
    if not _is_platform_admin(current_user):
        query = query.where(User.tenant_id == current_user.tenant_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if (
        (user.email or "").strip().lower() == settings.ADMIN_EMAIL.strip().lower()
        and role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change the platform admin role",
        )

    user.role = role
    await db.flush()
    return await _user_response(db, user)


@router.delete("/users/{user_id}", status_code=204)
async def deactivate_user(
    user_id: UUID,
    current_user=Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate yourself")

    query = select(User).where(User.id == user_id)
    if not _is_platform_admin(current_user):
        query = query.where(User.tenant_id == current_user.tenant_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if (user.email or "").strip().lower() == settings.ADMIN_EMAIL.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate the platform admin",
        )

    user.is_active = False
    await db.flush()


@router.get("/stats", response_model=AdminStatsResponse)
async def admin_stats(
    current_user=Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    platform = _is_platform_admin(current_user)

    def _scoped(query, model):
        if platform:
            return query
        return query.where(model.tenant_id == current_user.tenant_id)

    user_q = select(func.count()).select_from(User)
    if not platform:
        user_q = user_q.where(User.tenant_id == current_user.tenant_id)

    users_today_q = select(func.count()).select_from(User).where(User.created_at >= day_ago)
    users_week_q = select(func.count()).select_from(User).where(User.created_at >= week_ago)
    if not platform:
        users_today_q = users_today_q.where(User.tenant_id == current_user.tenant_id)
        users_week_q = users_week_q.where(User.tenant_id == current_user.tenant_id)

    client_q = select(func.count()).select_from(Tenant)
    if not platform:
        client_q = client_q.where(Tenant.id == current_user.tenant_id)

    brief_q = _scoped(select(func.count()).select_from(Brief), Brief)
    variant_q = _scoped(select(func.count()).select_from(Variant), Variant)
    brand_q = _scoped(select(func.count()).select_from(Brand), Brand)
    storage_q = select(func.coalesce(func.sum(Asset.file_size), 0))
    if not platform:
        storage_q = storage_q.where(Asset.tenant_id == current_user.tenant_id)

    user_count = (await db.execute(user_q)).scalar() or 0
    users_today = (await db.execute(users_today_q)).scalar() or 0
    users_week = (await db.execute(users_week_q)).scalar() or 0
    client_count = (await db.execute(client_q)).scalar() or 0
    brief_count = (await db.execute(brief_q)).scalar() or 0
    variant_count = (await db.execute(variant_q)).scalar() or 0
    brand_count = (await db.execute(brand_q)).scalar() or 0
    storage = (await db.execute(storage_q)).scalar() or 0

    return AdminStatsResponse(
        is_platform_admin=platform,
        clients=int(client_count),
        users=int(user_count),
        users_today=int(users_today),
        users_this_week=int(users_week),
        briefs=int(brief_count),
        variants=int(variant_count),
        brands=int(brand_count),
        storage_bytes=int(storage),
        storage_mb=round(int(storage) / 1_048_576, 2),
    )


@router.get("/usage")
async def admin_usage(current_user=Depends(_require_admin)):
    """Tokens, credits, and estimated USD spend across connected APIs."""
    platform = _is_platform_admin(current_user)
    return await usage_summary(
        tenant_id=current_user.tenant_id,
        platform=platform,
    )
