from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class BriefCreate(BaseModel):
    brand_id: UUID
    title: str
    objective: str = ""
    target_audience: str = ""
    formats: List[str] = []
    ad_copy_tone: str = "Professional"
    cta: str = "Shop Now"
    product_name: str = ""
    key_benefits: Dict[str, Any] = {}


class BriefUpdate(BaseModel):
    title: Optional[str] = None
    objective: Optional[str] = None
    target_audience: Optional[str] = None
    formats: Optional[List[str]] = None
    ad_copy_tone: Optional[str] = None
    cta: Optional[str] = None
    product_name: Optional[str] = None
    key_benefits: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class VariantSummary(BaseModel):
    id: UUID
    format: str
    hook: str
    status: str
    compliance_status: str
    performance_score: Optional[float]

    model_config = {"from_attributes": True}


class BriefResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    brand_id: UUID
    created_by: Optional[UUID]
    title: str
    objective: str
    target_audience: str
    formats: List[str]
    ad_copy_tone: str
    cta: str
    product_name: str
    key_benefits: Dict[str, Any]
    status: str
    variant_count: int
    completed_variants: int
    variants: List[VariantSummary] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenerationRequest(BaseModel):
    formats: Optional[List[str]] = None
    count_per_format: int = 2
    ai_model: str = "claude"
    image_model: Optional[str] = None
    video_model: Optional[str] = None
    video_duration_seconds: Optional[int] = None
    heygen_avatar_id: Optional[str] = None
    heygen_voice_id: Optional[str] = None
    higgsfield_voice_preset: Optional[str] = None
    avatar_script: Optional[str] = None
    heygen_settings: Optional[Dict[str, Any]] = None
