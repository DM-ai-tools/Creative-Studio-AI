from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class BrandCreate(BaseModel):
    name: str
    industry: str = "general"
    language: str = "English"
    voice_rules: Dict[str, Any] = {}
    forbidden_words: List[str] = []
    primary_color: Optional[str] = "#0F1B3D"
    secondary_color: Optional[str] = "#00C2A8"


class BrandUpdate(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    language: Optional[str] = None
    voice_rules: Optional[Dict[str, Any]] = None
    forbidden_words: Optional[List[str]] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    logo_url: Optional[str] = None


class BrandResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    industry: str
    language: str
    voice_rules: Dict[str, Any]
    forbidden_words: List[str]
    logo_url: Optional[str]
    primary_color: Optional[str]
    secondary_color: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BrandKitCreate(BaseModel):
    name: str = "Default Kit"
    colors: Dict[str, Any] = {}
    fonts: Dict[str, Any] = {}
    logo_variations: Dict[str, Any] = {}
    guidelines_url: Optional[str] = None


class BrandKitResponse(BaseModel):
    id: UUID
    brand_id: UUID
    name: str
    colors: Dict[str, Any]
    fonts: Dict[str, Any]
    logo_variations: Dict[str, Any]
    guidelines_url: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
