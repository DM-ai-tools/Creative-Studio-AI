"""Gemini Omni 1.1 Flash catalog entry for Creative Studio."""

from __future__ import annotations

from app.schemas.generation import GenerationModelOption


GEMINI_OMNI_MODEL_ID = "gemini-omni-1.1-flash"


def gemini_omni_video_catalog_options() -> list[GenerationModelOption]:
    # Keep the option visible before the key is supplied. Generation performs a
    # strict configuration preflight and never sends a paid request without it.
    return [
        GenerationModelOption(
            id=GEMINI_OMNI_MODEL_ID,
            label="Gemini Omni 1.1 Flash — 3–10s chapters · native audio · up to 4K",
            provider_model=GEMINI_OMNI_MODEL_ID,
            modality="video",
            provider="google",
            cost_usd=0.10,
            cost_unit="second",
            estimated_seconds=10,
            credits=0,
            max_duration_seconds=10,
        )
    ]

