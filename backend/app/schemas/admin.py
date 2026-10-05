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


class SeedanceModelCheck(BaseModel):
    catalog_id: str
    label: str
    api_model: str
    billing_status: str
    message: str
    probe_task_id: Optional[str] = None


class SeedanceTaskHistory(BaseModel):
    total_tasks: int
    recent_succeeded: int
    recent_failed: int
    recent_billing_failures: int


class SeedanceCreditsCheckResponse(BaseModel):
    checked_at: datetime
    configured: bool
    status: str
    message: str
    task_history: Optional[SeedanceTaskHistory] = None
    models: list[SeedanceModelCheck] = []
    probe_note: Optional[str] = None
