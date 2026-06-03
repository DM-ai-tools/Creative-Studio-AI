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
        ),
        GenerationModelOption(
            id="heygen-avatar-v2",
            label="Avatar (v2) — talking head on solid background",
            provider_model="heygen-avatar-v2",
            modality="video",
            provider="heygen",
        ),
    ]
