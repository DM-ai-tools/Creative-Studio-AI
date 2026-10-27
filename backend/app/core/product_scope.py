"""Per-user product access (optional). Default / empty = full Creative Studio."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.models.user import User
from app.services.media.byteplus_seedance_client import (
    DEFAULT_SEEDANCE_25_MODEL,
    is_seedance_25_model,
)

# Creative Studio AI tab only; video capped to Seedance 2.5; image + chat enabled inside CS.
PRODUCT_SCOPE_CREATIVE_STUDIO_SEEDANCE25 = "creative_studio_seedance25"

DEFAULT_CS25_VIDEO_CATALOG_ID = "ark-seedance-2-5"

CS25_ALLOWED_BRIEF_MEDIA = frozenset({"creative_studio"})


def product_scope(user: User | None) -> str | None:
    if user is None:
        return None
    raw = getattr(user, "product_scope", None)
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def is_creative_studio_seedance25_only(user: User | None) -> bool:
    return product_scope(user) == PRODUCT_SCOPE_CREATIVE_STUDIO_SEEDANCE25


def require_full_studio_access(user: User) -> None:
    if is_creative_studio_seedance25_only(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This account is limited to the Creative Studio tab with Seedance 2.5. "
                "Image ads, HeyGen video, and other generation routes are not available."
            ),
        )


def require_brief_media_type(user: User, media_type: str | None) -> None:
    if not is_creative_studio_seedance25_only(user):
        return
    mt = (media_type or "").strip().lower()
    if mt and mt not in CS25_ALLOWED_BRIEF_MEDIA:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account can only create Creative Studio (Seedance 2.5) projects.",
        )


def coerce_creative_studio_video_model(user: User, model: str | None) -> str:
    if not is_creative_studio_seedance25_only(user):
        return (model or DEFAULT_CS25_VIDEO_CATALOG_ID).strip() or DEFAULT_CS25_VIDEO_CATALOG_ID
    chosen = (model or DEFAULT_CS25_VIDEO_CATALOG_ID).strip() or DEFAULT_CS25_VIDEO_CATALOG_ID
    if not is_seedance_25_model(chosen):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account may only use Seedance 2.5 for video generation.",
        )
    return chosen


def filter_video_catalog_for_user(user: User, options: list) -> list:
    if not is_creative_studio_seedance25_only(user):
        return options
    filtered = []
    for opt in options:
        oid = opt.id if hasattr(opt, "id") else (opt.get("id") if isinstance(opt, dict) else "")
        if is_seedance_25_model(str(oid)):
            filtered.append(opt)
    return filtered


def default_video_model_for_user(user: User, default: str) -> str:
    if is_creative_studio_seedance25_only(user):
        return DEFAULT_CS25_VIDEO_CATALOG_ID
    return default


def resolved_seedance25_provider_model() -> str:
    return DEFAULT_SEEDANCE_25_MODEL
