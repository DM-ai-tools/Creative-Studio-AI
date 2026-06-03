from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(current_user=Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    current_user=Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.tenant_id == current_user.tenant_id).order_by(User.created_at.desc())
    )
    return [UserResponse.model_validate(u) for u in result.scalars().all()]


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: UUID,
    role: str,
    current_user=Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    if role not in ("admin", "member", "viewer"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == current_user.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.role = role
    await db.flush()
    return UserResponse.model_validate(user)


@router.delete("/users/{user_id}", status_code=204)
async def deactivate_user(
    user_id: UUID,
    current_user=Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate yourself")
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == current_user.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = False
    await db.flush()


@router.get("/stats")
async def admin_stats(
    current_user=Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.models.brief import Brief
    from app.models.variant import Variant
    from app.models.asset import Asset

    user_count = (await db.execute(select(func.count()).where(User.tenant_id == current_user.tenant_id))).scalar()
    brief_count = (await db.execute(select(func.count()).where(Brief.tenant_id == current_user.tenant_id))).scalar()
    variant_count = (await db.execute(select(func.count()).where(Variant.tenant_id == current_user.tenant_id))).scalar()
    storage = (await db.execute(select(func.coalesce(func.sum(Asset.file_size), 0)).where(Asset.tenant_id == current_user.tenant_id))).scalar()

    return {
        "users": user_count,
        "briefs": brief_count,
        "variants": variant_count,
        "storage_bytes": int(storage),
        "storage_mb": round(int(storage) / 1_048_576, 2),
    }
