import time
from threading import Lock

from app.core.config import settings
from app.schemas.generation import (
    CatalogOption,
    GenerationCatalogResponse,
    GenerationEstimate,
    GenerationModelOption,
)
from app.services.heygen_catalog import (
    get_heygen_avatar_featured,
    get_heygen_avatar_options,
    get_heygen_voice_options,
)
from app.services.heygen_video_catalog import heygen_video_catalog_options
from app.services.media.higgsfield_catalog import (
    higgsfield_image_catalog_options,
    higgsfield_video_catalog_options,
)
from app.services.media.runway_catalog import (
    runway_image_catalog_options,
    runway_video_catalog_options,
)


_CATALOG_CACHE: tuple[float, GenerationCatalogResponse] | None = None
_CATALOG_LOCK = Lock()
_CATALOG_TTL_SEC = 300


def get_generation_catalog() -> GenerationCatalogResponse:
    global _CATALOG_CACHE
    now = time.time()
    with _CATALOG_LOCK:
        if _CATALOG_CACHE and now - _CATALOG_CACHE[0] < _CATALOG_TTL_SEC:
            return _CATALOG_CACHE[1]

    image_models: list[GenerationModelOption] = []
    image_models.extend(runway_image_catalog_options())
    image_models.extend(higgsfield_image_catalog_options())

    video_models: list[GenerationModelOption] = []
    video_models.extend(heygen_video_catalog_options())
    video_models.extend(runway_video_catalog_options())
    video_models.extend(higgsfield_video_catalog_options())

    response = GenerationCatalogResponse(
        copy_models=[
            GenerationModelOption(
                id="claude",
                label="Claude copy",
                provider_model=settings.OPENROUTER_MODEL_CLAUDE,
                modality="copy",
            ),
            GenerationModelOption(
                id="openai",
                label="GPT copy",
                provider_model=settings.OPENROUTER_MODEL_OPENAI,
                modality="copy",
            ),
        ],
        image_models=image_models,
        video_models=video_models,
        heygen_avatar_options=get_heygen_avatar_options(),
        heygen_avatar_featured=get_heygen_avatar_featured(),
        heygen_voice_options=get_heygen_voice_options(),
        higgsfield_voice_options=[
            CatalogOption(id="serene_female", label="Serene (Female)", gender="female"),
            CatalogOption(id="deep_male", label="Deep (Male)", gender="male"),
            CatalogOption(id="clear_female", label="Clear (Female)", gender="female"),
            CatalogOption(id="warm_male", label="Warm (Male)", gender="male"),
        ],
        objectives=[
            CatalogOption(id="conversions", label="Conversions (Purchase)"),
            CatalogOption(id="add_to_cart", label="Add to Cart"),
            CatalogOption(id="lead_generation", label="Lead Generation"),
            CatalogOption(id="traffic", label="Traffic"),
            CatalogOption(id="awareness", label="Awareness"),
        ],
        placements=[
            CatalogOption(id="feed", label="Feed (1:1, 4:5)"),
            CatalogOption(id="landscape", label="Landscape (16:9)"),
            CatalogOption(id="reels", label="Portrait — Reels (9:16)"),
            CatalogOption(id="stories", label="Portrait — Stories (9:16)"),
            CatalogOption(id="marketplace", label="Marketplace (1:1)"),
        ],
        creative_formats=[
            CatalogOption(id="static", label="Static"),
            CatalogOption(id="video", label="Landscape"),
            CatalogOption(id="reel", label="Portrait"),
            CatalogOption(id="carousel", label="Carousel"),
        ],
        hook_frameworks=[
            CatalogOption(id="problem_agitate_solve", label="Problem-Agitate-Solve"),
            CatalogOption(id="ugc_style", label="UGC-Style"),
            CatalogOption(id="pattern_interrupt", label="Pattern Interrupt"),
            CatalogOption(id="social_proof", label="Social Proof"),
            CatalogOption(id="founder_led", label="Founder-Led"),
        ],
        cta_options=[
            CatalogOption(id="shop_now", label="Shop Now"),
            CatalogOption(id="get_offer", label="Get Offer"),
            CatalogOption(id="subscribe", label="Subscribe"),
            CatalogOption(id="learn_more", label="Learn More"),
        ],
        tone_options=[
            CatalogOption(id="professional", label="Professional"),
            CatalogOption(id="casual", label="Casual & Friendly"),
            CatalogOption(id="bold", label="Bold & Direct"),
            CatalogOption(id="urgent", label="Urgent & Compelling"),
            CatalogOption(id="warm", label="Warm & Empathetic"),
        ],
        pipeline_steps=[
            "Plan",
            "Hook Gen",
            "Copy Gen",
            "Image",
            "Video",
            "Caption",
            "Compose",
            "Compliance",
            "Persist",
        ],
        estimate=GenerationEstimate(cost_per_variant_usd=0.60, seconds_per_variant=90),
    )
    with _CATALOG_LOCK:
        _CATALOG_CACHE = (now, response)
    return response
