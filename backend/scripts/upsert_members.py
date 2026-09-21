"""Create or reset named member accounts in the shared admin workspace."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User


async def upsert_members(specs: list[str]) -> int:
    async with AsyncSessionLocal() as db:
        tenant_result = await db.execute(select(Tenant).where(Tenant.slug == "admin"))
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            tenant = Tenant(name="Admin Workspace", slug="admin")
            db.add(tenant)
            await db.flush()

        for spec in specs:
            username, separator, password = spec.partition(":")
            username = username.strip().lower()
            if not separator or not username or not password:
                raise ValueError("Each member must use username:password")
            result = await db.execute(select(User).where(User.email == username))
            user = result.scalar_one_or_none()
            if user:
                user.hashed_password = hash_password(password)
                user.full_name = username.title()
                user.role = "member"
                user.tenant_id = tenant.id
                user.is_active = True
                user.is_verified = True
                print(f"Updated member: {username}")
            else:
                db.add(
                    User(
                        tenant_id=tenant.id,
                        email=username,
                        hashed_password=hash_password(password),
                        full_name=username.title(),
                        role="member",
                        is_active=True,
                        is_verified=True,
                    )
                )
                print(f"Created member: {username}")
        await db.commit()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--user",
        action="append",
        required=True,
        help="Member credentials in username:password form; repeat for each member.",
    )
    args = parser.parse_args()
    return asyncio.run(upsert_members(args.user))


if __name__ == "__main__":
    raise SystemExit(main())
