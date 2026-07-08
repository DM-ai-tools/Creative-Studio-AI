"""Resolve Runway video clip length from brief settings or generate request."""

from __future__ import annotations

from app.core.config import settings

# Single Runway image_to_video clip lengths.
ALLOWED_VIDEO_DURATIONS: tuple[int, ...] = (5, 6, 8, 10, 12, 15)

# UI value: selecting 30s enables master script (4 clips totalling 30s), not one 30s Runway call.
MASTER_VIDEO_DURATION_SECONDS = 30

# HeyGen / long-form UI durations (up to 4 minutes).
EXTENDED_VIDEO_DURATIONS: tuple[int, ...] = (60, 90, 120, 180, 240)
MAX_VIDEO_DURATION_SECONDS = 240


def is_master_30_duration(seconds: int | str | None) -> bool:
    try:
        return int(seconds) == MASTER_VIDEO_DURATION_SECONDS
    except (TypeError, ValueError):
        return False


def is_extended_duration(seconds: int | str | None) -> bool:
    try:
        return int(seconds) in EXTENDED_VIDEO_DURATIONS
    except (TypeError, ValueError):
        return False


def is_allowed_ui_duration(seconds: int | str | None) -> bool:
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return False
    return (
        value in ALLOWED_VIDEO_DURATIONS
        or is_master_30_duration(value)
        or is_extended_duration(value)
    )


def master_video_requested(brief: dict | None) -> bool:
    if not isinstance(brief, dict):
        return False
    kb = brief.get("key_benefits") or {}
    if not isinstance(kb, dict):
        kb = {}
    if kb.get("video_master_30s") is True:
        return True
    if is_master_30_duration(kb.get("video_duration_seconds")):
        return True
    return str(kb.get("video_production_mode", "")).lower() in {"master_30s", "master", "30s"}


def clamp_video_duration(seconds: int | None, *, default: int | None = None) -> int:
    if is_master_30_duration(seconds):
        return 8
    if is_extended_duration(seconds):
        return 15
    fallback = default if default is not None else settings.RUNWAYML_VIDEO_DURATION
    try:
        value = int(seconds) if seconds is not None else fallback
    except (TypeError, ValueError):
        value = fallback
    if value in ALLOWED_VIDEO_DURATIONS:
        return value
    return clamp_video_duration(fallback, default=8)


def apply_video_settings_to_brief(
    brief_dict: dict,
    *,
    duration_override: int | None = None,
) -> dict:
    """Merge generate-request duration into brief key_benefits (master vs single clip)."""
    kb = brief_dict.get("key_benefits")
    if not isinstance(kb, dict):
        kb = {}
    else:
        kb = dict(kb)
    if duration_override is not None:
        kb["video_duration_seconds"] = int(duration_override)
        kb["video_master_30s"] = is_master_30_duration(duration_override)
        if is_master_30_duration(duration_override):
            kb["video_production_mode"] = "master_30s"
    return {**brief_dict, "key_benefits": kb}


def requested_video_duration_seconds(
    brief: dict | None = None,
    *,
    override: int | None = None,
) -> int:
    """User-facing duration (30 for master mode, not per-clip 8)."""
    if override is not None:
        value = int(override)
        if is_allowed_ui_duration(value):
            return value
        return clamp_video_duration(value)
    if isinstance(brief, dict):
        kb = brief.get("key_benefits")
        if isinstance(kb, dict) and kb.get("video_duration_seconds") is not None:
            value = int(kb["video_duration_seconds"])
            if is_allowed_ui_duration(value):
                return value
            return clamp_video_duration(value)
    return settings.RUNWAYML_VIDEO_DURATION


def resolve_video_duration_seconds(
    brief: dict | None = None,
    *,
    override: int | None = None,
) -> int:
    if override is not None and is_master_30_duration(override):
        return 8
    if override is not None:
        return clamp_video_duration(override)
    if isinstance(brief, dict):
        kb = brief.get("key_benefits")
        if isinstance(kb, dict) and kb.get("video_duration_seconds") is not None:
            return clamp_video_duration(kb.get("video_duration_seconds"))
    return clamp_video_duration(settings.RUNWAYML_VIDEO_DURATION)
