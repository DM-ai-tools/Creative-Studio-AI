"""Runway API model options exposed in the generation catalog (text_to_image / image_to_video)."""

from __future__ import annotations

from app.schemas.generation import GenerationModelOption

# (catalog_id, label, runway_api_model)
RUNWAY_IMAGE_MODELS: list[tuple[str, str, str]] = [
    ("nano-banana-2", "Nano Banana 2 — Gemini 3.1 Flash", "gemini_image3.1_flash"),
    ("nano-banana", "Nano Banana — Gemini 2.5 Flash", "gemini_2.5_flash"),
    ("nano-banana-pro", "Nano Banana Pro — Gemini 3 Pro", "gemini_image3_pro"),
    ("gen4-image", "Gen-4 Image", "gen4_image"),
    ("gen4-image-turbo", "Gen-4 Image Turbo", "gen4_image_turbo"),
    ("gpt-image-2", "GPT Image 2", "gpt_image_2"),
]

# image_to_video models supported by our pipeline (POST /v1/image_to_video)
RUNWAY_VIDEO_MODELS: list[tuple[str, str, str]] = [
    ("veo-3.1", "Veo 3.1", "veo3.1"),
    ("veo-3.1-fast", "Veo 3.1 Fast", "veo3.1.fast"),
    ("veo-3", "Veo 3", "veo3"),
    ("gen4-5", "Gen-4.5", "gen4.5"),
    ("gen4-turbo", "Gen-4 Turbo (image required)", "gen4_turbo"),
    ("gen3a-turbo", "Gen-3 Alpha Turbo (image required)", "gen3a_turbo"),
    ("seedance-2", "Seedance 2", "seedance2"),
]


def runway_image_catalog_options() -> list[GenerationModelOption]:
    return [
        GenerationModelOption(
            id=catalog_id,
            label=label,
            provider_model=api_model,
            modality="image",
            provider="runway",
        )
        for catalog_id, label, api_model in RUNWAY_IMAGE_MODELS
    ]


def runway_video_catalog_options() -> list[GenerationModelOption]:
    return [
        GenerationModelOption(
            id=catalog_id,
            label=label,
            provider_model=api_model,
            modality="video",
            provider="runway",
        )
        for catalog_id, label, api_model in RUNWAY_VIDEO_MODELS
    ]
