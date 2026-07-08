from typing import Literal

from pydantic import BaseModel, Field


class PerformanceMetricItem(BaseModel):
    label: str = ""
    value: str = ""


class PerformanceStatsContext(BaseModel):
    """Stats extracted from a performance dashboard image — used in script generation."""
    industry: str = ""
    campaign_type: str = ""
    headline_stat: str = ""
    roas: str = ""
    roi: str = ""
    conversions: str = ""
    clicks: str = ""
    purchases_sales: str = ""
    revenue: str = ""
    conversion_value: str = ""
    cost: str = ""
    cost_per_conversion: str = ""
    conv_value_per_cost: str = ""
    lead_forms: str = ""
    timeline: str = ""
    growth_story: str = ""
    metrics: list[PerformanceMetricItem] = Field(default_factory=list)
    script_proof_lines: list[str] = Field(default_factory=list)
    summary_for_script: str = ""


class StatsImageExtractionResponse(BaseModel):
    stats: PerformanceStatsContext
    filename: str = ""


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
    target_seconds: int = Field(default=30, ge=5, le=240)
    avatar_label: str = ""
    voice_label: str = ""
    forbidden_words: list[str] = Field(default_factory=list)
    variation: Literal["default", "different_hook"] = "default"
    purpose: Literal["avatar_script", "brief_notes", "visual_cues", "scene_broll"] = "avatar_script"
    icp_context: str | None = None
    performance_stats: PerformanceStatsContext | None = None
    performance_stats_per_image: list[PerformanceStatsContext] = Field(
        default_factory=list,
        description="OCR stats per uploaded dashboard image — each pairs with [INSERT STAT IMAGE N].",
    )
    stats_image_count: int = Field(
        default=0,
        description="Number of stats images uploaded. When > 0, the script writer embeds [INSERT STAT IMAGE N] markers at proof-beat lines.",
    )
    approved_script: str | None = Field(
        default=None,
        description="Timed approved voice script — required for scene_broll / visual_cues so scenes match spoken lines.",
    )
    scene_label: str = Field(
        default="",
        description="HeyGen scene preset label — used for B-roll presenter background.",
    )
    scene_custom: str = Field(
        default="",
        description="Custom HeyGen scene description — overrides scene_label for B-roll.",
    )
    source_script: str | None = Field(
        default=None,
        description="Full written script (Hook/Problem/Proof/CTA) converted to timed spoken dialogue.",
    )


class AvatarScriptResponse(BaseModel):
    lines: list[AvatarScriptLine]
    full_script: str
    word_count: int
    estimated_seconds: float
    words_per_second: float = 2.5
    model_id: str
    model_label: str
    validations: list[AvatarScriptValidation]


class IcpScriptRequest(BaseModel):
    """Generate an ICP profile first, then use it to write a spoken avatar script."""
    target_audience: str = ""
    offer: str = ""
    product_name: str = ""
    brand_name: str = ""
    ad_copy_tone: str = ""
    cta: str = ""
    target_seconds: int = Field(default=30, ge=5, le=240)
    avatar_label: str = ""
    voice_label: str = ""
    forbidden_words: list[str] = Field(default_factory=list)
    variation: Literal["default", "different_hook"] = "default"
    performance_stats: PerformanceStatsContext | None = None
    source_script: str | None = None


class IcpScriptResponse(BaseModel):
    """Full ICP text + the resulting avatar script."""
    icp_text: str
    script: AvatarScriptResponse


class WebsiteScriptRequest(BaseModel):
    """Generate a script by scraping a website URL."""
    url: str
    target_seconds: int = Field(default=30, ge=5, le=240)
    brand_name: str = ""
    product_name: str = ""
    offer: str = ""
    ad_copy_tone: str = ""
    cta: str = ""
    target_audience: str = ""
    avatar_label: str = ""
    voice_label: str = ""
    forbidden_words: list[str] = Field(default_factory=list)
    variation: Literal["default", "different_hook"] = "default"
    performance_stats: PerformanceStatsContext | None = None


class WebsiteScriptResponse(BaseModel):
    """Script + metadata about what was fetched and which framework was used."""
    script: AvatarScriptResponse
    page_title: str
    page_description: str
    framework_name: str
    framework_description: str
    url: str


class BodyOutlineSection(BaseModel):
    section: str
    duration_hint: str = ""
    talking_points: str = ""


class HaloStrategy(BaseModel):
    hook: str
    agitate: str
    lift: str
    offer: str


class StrategyPreviewRequest(BaseModel):
    campaign_name: str = ""
    brand_name: str = ""
    product_name: str = ""
    offer: str = ""
    target_audience: str = ""
    ad_copy_tone: str = ""
    cta: str = ""
    target_seconds: int = Field(default=30, ge=5, le=240)
    hook_frameworks: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    objective: str = ""
    placements: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)
    website_url: str = ""


class StrategyPreviewResponse(BaseModel):
    campaign_name: str
    brand_name: str
    product_name: str
    offer: str
    target_audience: str
    ad_copy_tone: str
    cta: str
    target_seconds: int
    objective: str
    hook_frameworks: list[str]
    competitors: list[str]
    website_url: str
    framework_name: str
    framework_description: str
    framework_structure: list[str]
    icp_text: str
    icp_fields: dict[str, str]
    hook_options: list[str]
    body_outline: list[BodyOutlineSection]
    halo_strategy: HaloStrategy
    competitor_positioning: str
    differentiation_points: list[str]


class MasterScriptBeat(BaseModel):
    start: str
    end: str
    spoken: str
    visual: str
    stat_image: str | None = None
    stat_headline: str | None = None
    stat_warning: str | None = None


class MasterScriptPreviewRequest(BaseModel):
    avatar_script: str = ""
    scene_broll_directions: str = ""
    target_seconds: int = Field(default=60, ge=5, le=240)
    performance_stats_per_image: list[PerformanceStatsContext] = Field(default_factory=list)


class MasterScriptPreviewResponse(BaseModel):
    beats: list[MasterScriptBeat]
    warnings: list[str] = Field(default_factory=list)
    ready: bool = False
