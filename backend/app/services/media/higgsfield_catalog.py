"""Higgsfield models for the generation catalog UI."""

from __future__ import annotations

from app.core.config import settings
from app.schemas.generation import GenerationModelOption
from app.services.media.higgsfield_models import (
    HIGGSFIELD_IMAGE_SPECS,
    HIGGSFIELD_VIDEO_SPECS,
    higgsfield_configured,
)


def _catalog_id(job_set_type: str) -> str:
    return f"hf-{job_set_type.replace('_', '-')}"


def higgsfield_image_catalog_options() -> list[GenerationModelOption]:
    if not higgsfield_configured():
        return []
    return [
        GenerationModelOption(
            id=_catalog_id(spec.job_set_type),
            label=spec.label,
            provider_model=spec.platform_path,
            modality="image",
            provider="higgsfield",
        )
        for spec in HIGGSFIELD_IMAGE_SPECS
    ]


def _video_label(spec) -> str:
    from app.services.media.higgsfield_models import (
        higgsfield_supports_native_audio,
        resolve_higgsfield_video_duration,
    )

    _, warn = resolve_higgsfield_video_duration(spec.job_set_type, 30)
    suffix = ""
    if warn and "5s" in warn:
        suffix = " — max 5s clip"
    elif spec.job_set_type.startswith("kling"):
        suffix = " — up to 10s, native audio"
    elif spec.job_set_type == "marketing_studio_video":
        suffix = " — up to 30s, native audio"
    elif "dop" in spec.platform_path or spec.job_set_type.startswith("veo"):
        suffix = " — motion only; voiceover added after"
    return f"{spec.label}{suffix}"


def higgsfield_video_catalog_options() -> list[GenerationModelOption]:
    if not higgsfield_configured():
        return []
    return [
        GenerationModelOption(
            id=_catalog_id(spec.job_set_type),
            label=_video_label(spec),
            provider_model=spec.platform_path,
            modality="video",
            provider="higgsfield",
        )
        for spec in HIGGSFIELD_VIDEO_SPECS
    ]
