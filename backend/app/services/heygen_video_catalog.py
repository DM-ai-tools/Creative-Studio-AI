"""HeyGen video provider options for the generation catalog."""

from __future__ import annotations

from app.core.config import settings
from app.schemas.generation import GenerationModelOption


def heygen_video_catalog_options() -> list[GenerationModelOption]:
    if not (settings.HEYGEN_API_KEY or "").strip():
        return []
    return [
        GenerationModelOption(
            id="heygen-video-agent",
            label="Video Agent (v3) — avatar, B-roll, scenes",
            provider_model="heygen-video-agent",
            modality="video",
            provider="heygen",
            # Approximate HeyGen API usage (not Runway credits).
            cost_usd=0.05,
            cost_unit="second",
            estimated_seconds=180,
        ),
        GenerationModelOption(
            id="heygen-avatar-v2",
            label="Avatar (v2) — talking head on solid background",
            provider_model="heygen-avatar-v2",
            modality="video",
            provider="heygen",
            cost_usd=0.04,
            cost_unit="second",
            estimated_seconds=120,
        ),
    ]
