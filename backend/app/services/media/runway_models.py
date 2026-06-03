"""Map UI catalog model ids to Runway API model names and valid request payloads."""

from __future__ import annotations

from app.core.config import settings

# Runway API ids (see POST /v1/text_to_image validation errors).
NANO_BANANA_2 = "gemini_image3.1_flash"
NANO_BANANA = "gemini_2.5_flash"
NANO_BANANA_PRO = "gemini_image3_pro"

IMAGE_MODEL_ALIASES: dict[str, str] = {
    "nano-banana-2": NANO_BANANA_2,
    "nano-banana": NANO_BANANA,
    "nano-banana-pro": NANO_BANANA_PRO,
    "gen4-image": "gen4_image",
    "gen4-image-turbo": "gen4_image_turbo",
    "gpt-image-2": "gpt_image_2",
    "gemini_image3.1_flash": NANO_BANANA_2,
    "gemini_2.5_flash": NANO_BANANA,
    "gemini_image3_pro": NANO_BANANA_PRO,
    "gen4_image": "gen4_image",
    "gen4_image_turbo": "gen4_image_turbo",
    "gpt_image_2": "gpt_image_2",
}

VIDEO_MODEL_ALIASES: dict[str, str] = {
    "veo-3.1": "veo3.1",
    "veo-3.1-fast": "veo3.1.fast",
    "veo-3": "veo3",
    "gen4-5": "gen4.5",
    "gen4-turbo": "gen4_turbo",
    "gen3a-turbo": "gen3a_turbo",
    "seedance-2": "seedance2",
    "veo3.1": "veo3.1",
    "veo3.1.fast": "veo3.1.fast",
    "veo3.1_fast": "veo3.1.fast",
    "veo3": "veo3",
    "gen4.5": "gen4.5",
    "gen4_turbo": "gen4_turbo",
    "gen3a_turbo": "gen3a_turbo",
    "seedance2": "seedance2",
}

# image_to_video models that always need promptImage (normalized ids)
VIDEO_MODELS_REQUIRING_IMAGE: frozenset[str] = frozenset({"gen4.turbo", "gen3a.turbo"})

# gemini_image3.1_flash (Nano Banana 2) uses pixel ratios like 768:1344 — not 9:16 + imageSize.
GEMINI_PIXEL_MODELS = {NANO_BANANA_2, NANO_BANANA, NANO_BANANA_PRO}

_PIXEL_RATIO_BY_FORMAT = {
    "static": "1024:1024",
    "carousel": "1344:768",
    "reel": "768:1344",
    "video": "768:1344",
}


def resolve_image_model(catalog_or_runway_id: str | None) -> str:
    if not catalog_or_runway_id or catalog_or_runway_id == "default":
        return settings.RUNWAYML_MODEL_IMAGE
    return IMAGE_MODEL_ALIASES.get(catalog_or_runway_id, catalog_or_runway_id)


def resolve_video_model(catalog_or_runway_id: str | None) -> str:
    if not catalog_or_runway_id or catalog_or_runway_id == "default":
        return settings.RUNWAYML_MODEL_VIDEO
    key = catalog_or_runway_id.strip()
    return VIDEO_MODEL_ALIASES.get(key, VIDEO_MODEL_ALIASES.get(key.lower(), key))


def normalize_runway_video_model_id(provider_model: str) -> str:
    """Canonical dotted id for duration/ratio helpers."""
    return (provider_model or "").strip().lower().replace("_", ".")


def build_text_to_image_payload(*, model: str, prompt: str, format_type: str) -> dict:
    """Build a Runway /text_to_image body that passes API validation for the model."""
    if model in GEMINI_PIXEL_MODELS:
        return {
            "model": model,
            "promptText": prompt,
            "ratio": _PIXEL_RATIO_BY_FORMAT.get(format_type, "1024:1024"),
        }

    # gen4_image / gen4_image_turbo use pixel dimensions
    if format_type in {"reel", "video"}:
        ratio = "1080:1920"
    elif format_type == "carousel":
        ratio = "1920:1080"
    else:
        ratio = settings.RUNWAYML_IMAGE_RATIO or "1080:1080"

    return {
        "model": model,
        "promptText": prompt,
        "ratio": ratio,
    }
