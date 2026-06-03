"""Reset the default admin password to match backend/.env (ADMIN_EMAIL / ADMIN_PASSWORD)."""

import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User


async def main() -> int:
    email = settings.ADMIN_EMAIL.strip().lower()
    password = settings.ADMIN_PASSWORD
    if not email or not password:
        print("Set ADMIN_EMAIL and ADMIN_PASSWORD in backend/.env")
        return 1

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            tenant_result = await db.execute(select(Tenant).where(Tenant.slug == "admin"))
            tenant = tenant_result.scalar_one_or_none()
            if not tenant:
                tenant = Tenant(name="Admin Workspace", slug="admin")
                db.add(tenant)
                await db.flush()
            user = User(
                tenant_id=tenant.id,
                email=email,
                hashed_password=hash_password(password),
                full_name="Admin",
                role="admin",
                is_verified=True,
                is_active=True,
            )
            db.add(user)
            print(f"Created admin user: {email}")
        else:
            user.hashed_password = hash_password(password)
            user.is_active = True
            print(f"Reset password for: {email}")

        await db.commit()

    print("Done. Sign in with ADMIN_EMAIL and ADMIN_PASSWORD from backend/.env")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
