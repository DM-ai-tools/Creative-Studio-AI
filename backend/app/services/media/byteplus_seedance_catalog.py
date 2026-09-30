"""BytePlus ModelArk Seedance catalog entries for Creative Studio."""

from __future__ import annotations

from app.schemas.generation import GenerationModelOption
from app.services.media.byteplus_seedance_client import (
    ark_configured,
    ark_seedance_25_model,
    ark_seedance_model,
)


def byteplus_seedance_video_catalog_options() -> list[GenerationModelOption]:
    if not ark_configured():
        return []
    return [
        GenerationModelOption(
            id="ark-seedance-2-0",
            label="Seedance 2.0 (BytePlus / Dreamina) — up to 15s per clip · 1080p ✓ default",
            provider_model=ark_seedance_model(),
            modality="video",
            provider="byteplus",
            cost_usd=0.08,
            cost_unit="second",
            estimated_seconds=15,
            credits=8,
            max_duration_seconds=15,
        ),
        GenerationModelOption(
            id="ark-seedance-2-5",
            label="Seedance 2.5 (BytePlus / Dreamina) — up to 30s per clip · 1080p max",
            provider_model=ark_seedance_25_model(),
            modality="video",
            provider="byteplus",
            cost_usd=0.08,
            cost_unit="second",
            estimated_seconds=30,
            credits=8,
            max_duration_seconds=30,
        ),
    ]
