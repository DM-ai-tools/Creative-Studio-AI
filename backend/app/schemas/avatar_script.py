from typing import Literal

from pydantic import BaseModel, Field


class AvatarScriptLine(BaseModel):
    start: str
    end: str
    text: str


class AvatarScriptValidation(BaseModel):
    id: str
    label: str
    status: Literal["ok", "warn"]


class AvatarScriptRequest(BaseModel):
    script_prompt: str | None = None
    product_name: str = ""
    offer: str = ""
    brand_name: str = ""
    target_audience: str = ""
    ad_copy_tone: str = ""
    cta: str = ""
    notes: str = ""
    target_seconds: int = Field(default=30, ge=5, le=60)
    avatar_label: str = ""
    voice_label: str = ""
    forbidden_words: list[str] = Field(default_factory=list)
    variation: Literal["default", "different_hook"] = "default"
    purpose: Literal["avatar_script", "brief_notes", "visual_cues"] = "avatar_script"


class AvatarScriptResponse(BaseModel):
    lines: list[AvatarScriptLine]
    full_script: str
    word_count: int
    estimated_seconds: float
    words_per_second: float = 2.5
    model_id: str
    model_label: str
    validations: list[AvatarScriptValidation]
