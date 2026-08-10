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

    tenant_result = await db.execute(select(Tenant).where(Tenant.slug == "admin"))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        tenant = Tenant(name="Admin Workspace", slug="admin")
        db.add(tenant)
        await db.flush()

    if user:
        # Keep DB password in sync with backend/.env (dev convenience).
        changed = False
        if not verify_password(settings.ADMIN_PASSWORD, user.hashed_password):
            user.hashed_password = hash_password(settings.ADMIN_PASSWORD)
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if user.role != "admin":
            user.role = "admin"
            changed = True
        if user.tenant_id != tenant.id:
            user.tenant_id = tenant.id
            changed = True
        if changed:
            await db.commit()
    else:
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

    # Self-serve signups used to create their own tenant + admin role.
    # Demote those accounts to members and move them into the shared workspace
    # so they appear in the Admin → Team Members list.
    await _normalize_member_accounts(db, admin_email=admin_email, workspace_id=tenant.id)


async def _normalize_member_accounts(
    db: AsyncSession,
    *,
    admin_email: str,
    workspace_id,
) -> None:
    result = await db.execute(select(User).where(User.email != admin_email))
    users = list(result.scalars().all())
    changed = False
    for u in users:
        if u.role == "admin":
            u.role = "member"
            changed = True
        if u.tenant_id != workspace_id:
            u.tenant_id = workspace_id
            changed = True
    if changed:
        await db.commit()
