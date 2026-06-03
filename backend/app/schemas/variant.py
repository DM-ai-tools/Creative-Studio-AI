from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class VariantResponse(BaseModel):
    id: UUID
    brief_id: UUID
    brand_id: UUID
    tenant_id: UUID
    format: str
    hook: str
    headline: str
    body_copy: str
    cta: str
    hashtags: List[str]
    ai_model: str
    generation_params: Dict[str, Any] = {}
    status: str
    compliance_status: str
    compliance_notes: Dict[str, Any]
    performance_score: Optional[float]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VariantUpdate(BaseModel):
    hook: Optional[str] = None
    headline: Optional[str] = None
    body_copy: Optional[str] = None
    cta: Optional[str] = None
    hashtags: Optional[List[str]] = None
    status: Optional[str] = None
    compliance_status: Optional[str] = None
    compliance_notes: Optional[Dict[str, Any]] = None
    generation_params: Optional[Dict[str, Any]] = None
