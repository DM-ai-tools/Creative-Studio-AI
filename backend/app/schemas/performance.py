from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class MetricResponse(BaseModel):
    id: UUID
    variant_id: UUID
    date: date
    impressions: int
    clicks: int
    conversions: int
    spend: float
    revenue: float
    roas: float
    ctr: float
    cpm: float
    frequency: float
    reach: int
    meta_ad_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class RollupResponse(BaseModel):
    id: UUID
    variant_id: UUID
    roas_7d: float
    roas_personal_best: float
    roas_30d: float
    frequency_7d: float
    is_fatigued: bool
    status: str
    last_synced_at: Optional[datetime]
    updated_at: datetime

    model_config = {"from_attributes": True}


class DashboardStats(BaseModel):
    active_variants: int
    avg_roas_7d: float
    # Null when no compliance checks have been recorded yet (do not fake 100%).
    brand_safety_pass_rate: Optional[float] = None
    brand_safety_checks: int = 0
    fatigued_count: int


class AssetResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    variant_id: Optional[UUID]
    brand_id: Optional[UUID]
    file_name: str
    file_url: str
    file_type: str
    file_size: int
    asset_type: str
    width: Optional[int]
    height: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}
