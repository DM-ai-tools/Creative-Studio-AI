from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


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
    generation_params: Dict[str, Any] = Field(default_factory=dict)
    status: str
    compliance_status: str
    compliance_notes: Dict[str, Any] = Field(default_factory=dict)
    performance_score: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def slim_generation_params_for_list(params: Dict[str, Any] | None) -> Dict[str, Any]:
    """Keep preview media URLs; drop huge image prompts from list payloads."""
    if not isinstance(params, dict):
        return {}
    pipeline = params.get("pipeline")
    slim_pipeline: Dict[str, Any] = {}
    if isinstance(pipeline, dict):
        for step in ("image", "video", "copy", "compliance"):
            step_data = pipeline.get(step)
            if not isinstance(step_data, dict):
                continue
            slim_pipeline[step] = {
                k: step_data[k]
                for k in ("status", "url", "model", "error", "source", "reason")
                if k in step_data
            }
    out: Dict[str, Any] = {}
    if slim_pipeline:
        out["pipeline"] = slim_pipeline
    for key in ("format", "tone", "models", "hook_framework"):
        if key in params:
            out[key] = params[key]
    # List views: keep hook/cta for History grid; full prompt only on get-by-id / export.
    image_plan = params.get("image_plan")
    if isinstance(image_plan, dict):
        out["image_plan"] = {
            k: image_plan[k]
            for k in (
                "use_cases",
                "variant_index",
                "hook",
                "message",
                "cta",
                "ad_angle",
            )
            if k in image_plan
        }
    return out


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
