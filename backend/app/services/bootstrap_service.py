from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.tenant import Tenant
from app.models.user import User


async def ensure_default_admin(db: AsyncSession) -> None:
    if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        return

    admin_email = settings.ADMIN_EMAIL.strip().lower()
    existing = await db.execute(select(User).where(User.email == admin_email))
    user = existing.scalar_one_or_none()
    if user:
        # Keep DB password in sync with backend/.env (dev convenience).
        if not verify_password(settings.ADMIN_PASSWORD, user.hashed_password):
            user.hashed_password = hash_password(settings.ADMIN_PASSWORD)
            user.is_active = True
            await db.commit()
        return

    tenant_result = await db.execute(select(Tenant).where(Tenant.slug == "admin"))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        tenant = Tenant(name="Admin Workspace", slug="admin")
        db.add(tenant)
        await db.flush()

    db.add(
        User(
            tenant_id=tenant.id,
            email=admin_email,
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            full_name="Admin",
            role="admin",
            is_verified=True,
        )
    )
    await db.commit()
