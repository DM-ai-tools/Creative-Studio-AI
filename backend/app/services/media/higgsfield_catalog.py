"""Higgsfield models for the generation catalog UI."""

from __future__ import annotations

from app.schemas.generation import GenerationModelOption
from app.services.media.higgsfield_models import (
    HIGGSFIELD_IMAGE_SPECS,
    HIGGSFIELD_VIDEO_SPECS,
    SEEDANCE_JOB_TYPES,
    higgsfield_configured,
    single_clip_max_seconds,
)


def _catalog_id(job_set_type: str) -> str:
    return f"hf-{job_set_type.replace('_', '-')}"


# Approximate Higgsfield-platform credits (UI estimate — actual bill is on their cloud).
_HF_IMAGE_CREDITS: dict[str, float] = {
    "nano_banana": 5,
    "nano_banana_flash": 7,
    "nano_banana_2": 10,
    "gpt_image_2": 20,
    "text2image_soul_v2": 12,
    "cinematic_studio_2_5": 15,
    "soul_cinematic": 12,
    "marketing_studio_image": 15,
}
_HF_IMAGE_COST = {
    "gpt_image_2": 0.20,
    "nano_banana": 0.05,
    "nano_banana_2": 0.07,
    "soul": 0.08,
}

# Credits per second of requested duration (Cinema Studio ~10/s → 150 for 15s).
_HF_VIDEO_CREDITS_PER_SEC: dict[str, float] = {
    "cinematic_studio_4_0": 12,
    "cinematic_studio_3_5": 10,
    "cinematic_studio_3_0": 10,
    "cinematic_studio_video": 10,
    "cinematic_studio_video_v2": 11,
    "seedance_2_0": 8,
    "seedance1_5": 8,
    "veo3_1": 12,
    "veo3_1_lite": 8,
    "veo3": 11,
    "kling3_0": 10,
    "kling2_6": 9,
    "marketing_studio_video": 10,
    "soul_cast": 9,
}


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
            cost_usd=_HF_IMAGE_COST.get(spec.job_set_type, 0.10),
            cost_unit="image",
            estimated_seconds=30,
            credits=_HF_IMAGE_CREDITS.get(spec.job_set_type, 10),
        )
        for spec in HIGGSFIELD_IMAGE_SPECS
    ]


def _video_label(spec) -> str:
    job = spec.job_set_type
    mx = single_clip_max_seconds(job)
    if job.startswith("cinematic_studio") or job == "soul_cast":
        suffix = " — ~5s only (use Kling for 10s)"
    elif job.startswith("kling"):
        suffix = " — one video up to 10s ✓ recommended"
    elif job in SEEDANCE_JOB_TYPES:
        suffix = f" — up to {mx}s (enable in Higgsfield cloud if disabled)"
    elif job == "marketing_studio_video":
        suffix = " — one video up to 30s, native audio"
    else:
        suffix = f" — one video up to {mx}s (no stitch)"
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
            cost_usd=round(
                0.01 * _HF_VIDEO_CREDITS_PER_SEC.get(spec.job_set_type, 10),
                4,
            ),
            cost_unit="second",
            estimated_seconds=single_clip_max_seconds(spec.job_set_type),
            credits=_HF_VIDEO_CREDITS_PER_SEC.get(spec.job_set_type, 10),
            max_duration_seconds=single_clip_max_seconds(spec.job_set_type),
        )
        for spec in HIGGSFIELD_VIDEO_SPECS
    ]
