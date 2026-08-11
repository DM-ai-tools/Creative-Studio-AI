import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse


def _slugify_company(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:80]
    return slug or "workspace"


async def _user_response(db: AsyncSession, user: User, **extra) -> UserResponse:
    if "tenant_name" in extra:
        tenant_name = extra.pop("tenant_name")
    elif user.tenant_id:
        result = await db.execute(select(Tenant.name).where(Tenant.id == user.tenant_id))
        tenant_name = result.scalar_one_or_none()
    else:
        tenant_name = None
    data = UserResponse.model_validate(user)
    return data.model_copy(update={"tenant_name": tenant_name, **extra})


async def _build_token_response(db: AsyncSession, user: User) -> TokenResponse:
    payload = {"sub": str(user.id), "tenant_id": str(user.tenant_id), "role": user.role}
    return TokenResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token(payload),
        user=await _user_response(db, user),
    )


def _resolve_login_email(identifier: str) -> str:
    if "@" in identifier:
        return identifier.strip().lower()
    if identifier.strip().lower() == "admin":
        return settings.ADMIN_EMAIL.lower()
    return identifier.strip().lower()


class AuthService:
    @staticmethod
    async def _default_workspace(db: AsyncSession) -> Tenant:
        """Platform admin workspace only — not used for self-serve client signups."""
        result = await db.execute(select(Tenant).where(Tenant.slug == "admin"))
        tenant = result.scalar_one_or_none()
        if tenant:
            return tenant
        tenant = Tenant(name="CreativeStudio Workspace", slug="admin")
        db.add(tenant)
        await db.flush()
        return tenant

    @staticmethod
    async def _workspace_for_company(db: AsyncSession, company_name: str) -> Tenant:
        """Each client company gets its own tenant. Same company name joins the same workspace."""
        name = (company_name or "").strip() or "New workspace"
        base = _slugify_company(name)
        if base == "admin":
            base = "client-admin"

        result = await db.execute(select(Tenant).where(Tenant.slug == base))
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        slug = base
        n = 2
        while True:
            taken = await db.execute(select(Tenant.id).where(Tenant.slug == slug))
            if taken.scalar_one_or_none() is None:
                break
            slug = f"{base}-{n}"
            n += 1

        tenant = Tenant(name=name, slug=slug)
        db.add(tenant)
        await db.flush()
        return tenant

    @staticmethod
    async def register(db: AsyncSession, data: RegisterRequest) -> TokenResponse:
        email = data.email.strip().lower()
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        if email == settings.ADMIN_EMAIL.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email is reserved for the platform admin. Please sign in instead.",
            )

        tenant = await AuthService._workspace_for_company(db, data.tenant_name)
        user = User(
            tenant_id=tenant.id,
            email=email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            role="member",
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        return await _build_token_response(db, user)

    @staticmethod
    async def login(db: AsyncSession, data: LoginRequest) -> TokenResponse:
        email = _resolve_login_email(data.email)
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")
        user.last_login_at = datetime.now(timezone.utc)
        await db.flush()
        return await _build_token_response(db, user)

    @staticmethod
    async def refresh(db: AsyncSession, refresh_token: str) -> TokenResponse:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        result = await db.execute(select(User).where(User.id == UUID(payload["sub"])))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return await _build_token_response(db, user)

    @staticmethod
    async def get_me(db: AsyncSession, user_id: UUID) -> UserResponse:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return await _user_response(db, user)
