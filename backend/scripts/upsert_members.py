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
from app.core.product_scope import PRODUCT_SCOPE_CREATIVE_STUDIO_SEEDANCE25
from app.models.tenant import Tenant
from app.models.user import User
from app.services.auth_service import resolve_login_email


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


async def remove_members(emails: list[str]) -> int:
    async with AsyncSessionLocal() as db:
        for raw in emails:
            email = raw.strip().lower()
            if not email:
                continue
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user:
                print(f"No user to remove: {email}")
                continue
            if user.role == "admin":
                raise ValueError(f"Refusing to remove admin account: {email}")
            await db.delete(user)
            print(f"Removed member: {email}")
        await db.commit()
    return 0


async def upsert_members(specs: list[str], *, product_scope: str | None = None) -> int:
    async with AsyncSessionLocal() as db:
        for spec in specs:
            username, separator, password = spec.partition(":")
            username = username.strip().lower()
            if not separator or not username or not password:
                raise ValueError("Each member must use username:password")

            email = resolve_login_email(username)
            tenant = await _tenant_for_member(db, email)
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user and email != username:
                legacy = await db.execute(select(User).where(User.email == username))
                legacy_user = legacy.scalar_one_or_none()
                if legacy_user:
                    legacy_user.email = email
                    user = legacy_user
                    print(f"Migrated member email: {username} -> {email}")
            local_part = email.split("@", 1)[0]
            if local_part == "seedance_2.5":
                display = "Seedance 2.5"
            else:
                display = local_part.replace(".", " ").replace("_", " ").title()
            scope = product_scope
            if local_part == "seedance_2.5":
                scope = PRODUCT_SCOPE_CREATIVE_STUDIO_SEEDANCE25
            if user:
                user.hashed_password = hash_password(password)
                user.full_name = display
                user.role = "member"
                user.tenant_id = tenant.id
                user.is_active = True
                user.is_verified = True
                if scope:
                    user.product_scope = scope
                print(f"Updated member: {email} -> workspace {tenant.slug} scope={user.product_scope}")
            else:
                db.add(
                    User(
                        tenant_id=tenant.id,
                        email=email,
                        hashed_password=hash_password(password),
                        full_name=display,
                        role="member",
                        product_scope=scope,
                        is_active=True,
                        is_verified=True,
                    )
                )
                print(f"Created member: {email} -> workspace {tenant.slug} scope={scope}")
        await db.commit()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--user",
        action="append",
        default=[],
        help="Member credentials in username:password form; repeat for each member.",
    )
    parser.add_argument(
        "--remove",
        action="append",
        default=[],
        help="Remove a member account by email.",
    )
    parser.add_argument(
        "--product-scope",
        default=None,
        help="Optional product_scope for created/updated users (e.g. creative_studio_seedance25).",
    )
    args = parser.parse_args()
    if not args.user and not args.remove:
        parser.error("Provide --user and/or --remove.")
    if args.remove:
        asyncio.run(remove_members(args.remove))
    if args.user:
        return asyncio.run(upsert_members(args.user, product_scope=args.product_scope))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
