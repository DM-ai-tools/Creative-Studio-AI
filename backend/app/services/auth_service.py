import re
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse


def _make_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:80]


async def _build_token_response(user: User) -> TokenResponse:
    payload = {"sub": str(user.id), "tenant_id": str(user.tenant_id), "role": user.role}
    return TokenResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token(payload),
        user=UserResponse.model_validate(user),
    )


def _resolve_login_email(identifier: str) -> str:
    if "@" in identifier:
        return identifier.strip().lower()
    if identifier.strip().lower() == "admin":
        return settings.ADMIN_EMAIL.lower()
    return identifier.strip().lower()


class AuthService:
    @staticmethod
    async def register(db: AsyncSession, data: RegisterRequest) -> TokenResponse:
        existing = await db.execute(select(User).where(User.email == data.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        slug = _make_slug(data.tenant_name)
        suffix = 0
        base_slug = slug
        while True:
            res = await db.execute(select(Tenant).where(Tenant.slug == slug))
            if not res.scalar_one_or_none():
                break
            suffix += 1
            slug = f"{base_slug}-{suffix}"

        tenant = Tenant(name=data.tenant_name, slug=slug)
        db.add(tenant)
        await db.flush()

        user = User(
            tenant_id=tenant.id,
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            role="admin",
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        return await _build_token_response(user)

    @staticmethod
    async def login(db: AsyncSession, data: LoginRequest) -> TokenResponse:
        email = _resolve_login_email(data.email)
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")
        return await _build_token_response(user)

    @staticmethod
    async def refresh(db: AsyncSession, refresh_token: str) -> TokenResponse:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        result = await db.execute(select(User).where(User.id == UUID(payload["sub"])))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return await _build_token_response(user)

    @staticmethod
    async def get_me(db: AsyncSession, user_id: UUID) -> UserResponse:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return UserResponse.model_validate(user)
