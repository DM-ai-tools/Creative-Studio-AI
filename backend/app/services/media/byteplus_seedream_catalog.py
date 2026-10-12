"""BytePlus ModelArk Seedream 5.0 image catalog for Creative Studio."""

from __future__ import annotations

from app.schemas.generation import GenerationModelOption
from app.services.media.byteplus_seedream_client import (
    seedream_50_flash_model,
    seedream_50_lite_model,
    seedream_50_pro_model,
    seedream_configured,
)


def byteplus_seedream_catalog_options() -> list[GenerationModelOption]:
    if not seedream_configured():
        return []
    return [
        GenerationModelOption(
            id="ark-seedream-5-0-lite",
            label="Seedream 5.0 Lite (BytePlus) — fast B-roll stills · same account as Seedance",
            provider_model=seedream_50_lite_model(),
            modality="image",
            provider="byteplus",
            cost_usd=0.03,
            cost_unit="image",
            estimated_seconds=12,
            credits=3,
        ),
        GenerationModelOption(
            id="ark-seedream-5-0-pro",
            label="Seedream 5.0 Pro (BytePlus) — sharper text & product fidelity",
            provider_model=seedream_50_pro_model(),
            modality="image",
            provider="byteplus",
            cost_usd=0.05,
            cost_unit="image",
            estimated_seconds=18,
            credits=5,
        ),
        GenerationModelOption(
            id="ark-seedream-5-0-flash",
            label="Seedream 5.0 Flash (BytePlus) — quickest drafts",
            provider_model=seedream_50_flash_model(),
            modality="image",
            provider="byteplus",
            cost_usd=0.02,
            cost_unit="image",
            estimated_seconds=8,
            credits=2,
        ),
    ]
