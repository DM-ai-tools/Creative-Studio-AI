from pydantic import BaseModel


class GenerationModelOption(BaseModel):
    id: str
    label: str
    provider_model: str
    modality: str
    provider: str | None = None  # runway | heygen — for grouped UI selects


class CatalogOption(BaseModel):
    id: str
    label: str
    gender: str | None = None  # male / female when known (HeyGen avatars)


class GenerationEstimate(BaseModel):
    cost_per_variant_usd: float
    seconds_per_variant: int


class GenerationCatalogResponse(BaseModel):
    copy_models: list[GenerationModelOption]
    image_models: list[GenerationModelOption]
    video_models: list[GenerationModelOption]
    heygen_avatar_options: list[CatalogOption] = []
    """Standalone public looks (e.g. Vespri) — not Sofia/Florin pose libraries."""
    heygen_avatar_featured: list[CatalogOption] = []
    heygen_voice_options: list[CatalogOption] = []
    higgsfield_voice_options: list[CatalogOption] = []
    objectives: list[CatalogOption]
    placements: list[CatalogOption]
    creative_formats: list[CatalogOption]
    hook_frameworks: list[CatalogOption]
    cta_options: list[CatalogOption]
    tone_options: list[CatalogOption]
    pipeline_steps: list[str]
    estimate: GenerationEstimate
