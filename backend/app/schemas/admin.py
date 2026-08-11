from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.schemas.auth import UserResponse


class AdminStatsResponse(BaseModel):
    is_platform_admin: bool
    clients: int
    users: int
    users_today: int
    users_this_week: int
    briefs: int
    variants: int
    brands: int
    storage_bytes: int
    storage_mb: float


class AdminClientResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    plan: str
    is_active: bool
    user_count: int
    brand_count: int
    brief_count: int
    variant_count: int
    created_at: datetime
    last_activity_at: Optional[datetime] = None


class AdminUsersResponse(BaseModel):
    users: list[UserResponse]
