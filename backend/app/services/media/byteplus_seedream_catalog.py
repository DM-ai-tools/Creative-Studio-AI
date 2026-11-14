"""BytePlus ModelArk Seedream 5.0 image catalog for Creative Studio."""

from __future__ import annotations

from app.schemas.generation import GenerationModelOption
from app.services.media.byteplus_seedream_client import (
    seedream_50_flash_model,
    seedream_50_lite_model,
    seedream_50_pro_model,
    seedream_configured,
)
from app.services.media.openai_image_catalog import (
    openai_configured,
    openai_image_catalog_options,
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
            label="Dola Seedream 5.0 Flash (BytePlus) — quick stills · same account as Seedance",
            provider_model=seedream_50_flash_model(),
            modality="image",
            provider="byteplus",
            cost_usd=0.02,
            cost_unit="image",
            estimated_seconds=8,
            credits=2,
        ),
    ]


def creative_studio_still_model_options() -> list[GenerationModelOption]:
    """Image-first Creative Studio: GPT Image 2 plus optional BytePlus Seedream 5.0 stills."""
    options: list[GenerationModelOption] = []
    if openai_configured():
        from app.services.media.openai_image_catalog import OPENAI_IMAGE_DEFAULT_CATALOG_ID

        primary = next(
            (o for o in openai_image_catalog_options() if o.id == OPENAI_IMAGE_DEFAULT_CATALOG_ID),
            None,
        )
        if primary:
            options.append(primary)
        else:
            options.append(
                GenerationModelOption(
                    id=OPENAI_IMAGE_DEFAULT_CATALOG_ID,
                    label="GPT Image 2.6 Sunburst",
                    provider_model="gpt-image-2.6-sunburst",
                    modality="image",
                    provider="openai",
                    cost_usd=0.05,
                    cost_unit="image",
                    estimated_seconds=18,
                )
            )
    options.extend(byteplus_seedream_catalog_options())
    return options
