"""Runway API model options exposed in the generation catalog (text_to_image / image_to_video)."""

from __future__ import annotations

from app.schemas.generation import GenerationModelOption

# Runway bills ~$0.01 per credit (developer API).
_CREDIT_USD = 0.01

# (catalog_id, label, runway_api_model, credits_per_image, est_seconds)
# Credits from https://docs.dev.runwayml.com/guides/pricing/ (typical defaults we use).
RUNWAY_IMAGE_MODELS: list[tuple[str, str, str, int, int]] = [
    ("nano-banana-2", "Nano Banana 2 — Gemini 3.1 Flash", "gemini_image3.1_flash", 7, 25),
    ("nano-banana", "Nano Banana — Gemini 2.5 Flash", "gemini_2.5_flash", 5, 20),
    ("nano-banana-pro", "Nano Banana Pro — Gemini 3 Pro", "gemini_image3_pro", 20, 45),
    ("gen4-image", "Gen-4 Image", "gen4_image", 8, 35),
    ("gen4-image-turbo", "Gen-4 Image Turbo", "gen4_image_turbo", 2, 15),
    # GPT Image 2 high quality @ 1K/2K (we request 1920:1920) = 20 credits
    ("gpt-image-2", "GPT Image 2", "gpt_image_2", 20, 40),
]

# (catalog_id, label, runway_api_model, credits_per_second, est_seconds_default)
RUNWAY_VIDEO_MODELS: list[tuple[str, str, str, int, int]] = [
    ("veo-3.1", "Veo 3.1", "veo3.1", 40, 90),
    ("veo-3.1-fast", "Veo 3.1 Fast", "veo3.1.fast", 15, 60),
    ("veo-3", "Veo 3", "veo3", 40, 90),
    ("gen4-5", "Gen-4.5", "gen4.5", 12, 75),
    ("gen4-turbo", "Gen-4 Turbo (image required)", "gen4_turbo", 5, 45),
    ("gen3a-turbo", "Gen-3 Alpha Turbo (image required)", "gen3a_turbo", 5, 40),
    ("seedance-2", "Seedance 2", "seedance2", 8, 60),
]


def runway_image_catalog_options() -> list[GenerationModelOption]:
    return [
        GenerationModelOption(
            id=catalog_id,
            label=label,
            provider_model=api_model,
            modality="image",
            provider="runway",
            cost_usd=round(credits * _CREDIT_USD, 4),
            cost_unit="image",
            estimated_seconds=est_seconds,
        )
        for catalog_id, label, api_model, credits, est_seconds in RUNWAY_IMAGE_MODELS
    ]


def runway_video_catalog_options() -> list[GenerationModelOption]:
    return [
        GenerationModelOption(
            id=catalog_id,
            label=label,
            provider_model=api_model,
            modality="video",
            provider="runway",
            cost_usd=round(credits_per_sec * _CREDIT_USD, 4),
            cost_unit="second",
            estimated_seconds=est_seconds,
        )
        for catalog_id, label, api_model, credits_per_sec, est_seconds in RUNWAY_VIDEO_MODELS
    ]
