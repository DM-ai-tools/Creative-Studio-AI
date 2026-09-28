"""Create or reset named member accounts, each in their own private workspace."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")[:80]
    return slug or "workspace"


async def _tenant_for_member(db, email: str) -> Tenant:
    """One member → one tenant. Uploads and briefs stay isolated by tenant_id."""
    local = email.split("@", 1)[0].strip().lower() or "member"
    base = _slugify(local)
    if base in {"admin", "platform"}:
        base = f"member-{base}"

    result = await db.execute(select(Tenant).where(Tenant.slug == base))
    tenant = result.scalar_one_or_none()
    if tenant:
        return tenant

    slug = base
    n = 2
    while True:
        taken = await db.execute(select(Tenant.id).where(Tenant.slug == slug))
        if taken.scalar_one_or_none() is None:
            break
        slug = f"{base}-{n}"
        n += 1

    label = local.replace("-", " ").replace("_", " ").title()
    tenant = Tenant(name=f"{label} Workspace", slug=slug)
    db.add(tenant)
    await db.flush()
    return tenant


async def upsert_members(specs: list[str]) -> int:
    async with AsyncSessionLocal() as db:
        for spec in specs:
            username, separator, password = spec.partition(":")
            username = username.strip().lower()
            if not separator or not username or not password:
                raise ValueError("Each member must use username:password")

            tenant = await _tenant_for_member(db, username)
            result = await db.execute(select(User).where(User.email == username))
            user = result.scalar_one_or_none()
            display = username.split("@", 1)[0].replace(".", " ").title()
            if user:
                user.hashed_password = hash_password(password)
                user.full_name = display
                user.role = "member"
                user.tenant_id = tenant.id
                user.is_active = True
                user.is_verified = True
                print(f"Updated member: {username} -> workspace {tenant.slug}")
            else:
                db.add(
                    User(
                        tenant_id=tenant.id,
                        email=username,
                        hashed_password=hash_password(password),
                        full_name=display,
                        role="member",
                        is_active=True,
                        is_verified=True,
                    )
                )
                print(f"Created member: {username} -> workspace {tenant.slug}")
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
