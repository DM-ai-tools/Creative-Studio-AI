"""BytePlus ModelArk Seedance catalog entries for Creative Studio."""

from __future__ import annotations

from app.schemas.generation import GenerationModelOption
from app.services.media.byteplus_seedance_client import ark_configured, ark_seedance_model


def byteplus_seedance_video_catalog_options() -> list[GenerationModelOption]:
    if not ark_configured():
        return []
    api_model = ark_seedance_model()
    max_sec = 30 if "2-5" in api_model or "2.5" in api_model else 15
    return [
        GenerationModelOption(
            id="ark-seedance-2-0",
            label=f"Seedance 2.0 (BytePlus / Dreamina) — up to {max_sec}s ✓ recommended",
            provider_model=api_model,
            modality="video",
            provider="byteplus",
            cost_usd=0.08,
            cost_unit="second",
            estimated_seconds=max_sec,
            credits=8,
            max_duration_seconds=max_sec,
        )
    ]
