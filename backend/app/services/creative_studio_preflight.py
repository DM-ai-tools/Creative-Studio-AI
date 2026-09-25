"""Deterministic checks that run before any paid Creative Studio video call."""

from __future__ import annotations

from typing import Any

from app.services.creative_studio_timeline import SHOT_HEADER, explicit_shot_windows, validate_video_prompt


def validate_video_preflight(
    *, prompt: str, duration_seconds: int,
    storyboard_image_urls: list[str] | None, seed_image_url: str | None,
    sound_on: bool, voice_events: list[tuple[float, float, str]] | None,
    reference_assets: list[dict[str, Any]] | None,
    product_reference_url: str | None, logo_reference_url: str | None,
) -> dict[str, Any]:
    """Build a reviewable asset/shot lock and block structurally invalid jobs."""
    validate_video_prompt(prompt)
    duration = int(duration_seconds)
    if duration < 5 or duration > 120:
        raise ValueError("Creative Studio video duration must be between 5 and 120 seconds.")
    boards = [str(url).strip() for url in (storyboard_image_urls or []) if str(url).strip()]
    assets = [asset for asset in (reference_assets or []) if isinstance(asset, dict)]
    windows = explicit_shot_windows(prompt, total=duration)
    scene_count = len(list(SHOT_HEADER.finditer(prompt)))
    errors: list[str] = []
    warnings: list[str] = []
    if duration > 15 and scene_count < 2:
        errors.append("Long Seedance videos require an explicit timed multi-scene plan.")
    if scene_count >= 2 and not windows:
        errors.append("Scene timings are missing, overlapping, or do not cover the full duration.")
    if boards and scene_count and len(boards) > scene_count:
        errors.append(
            f"Storyboard coverage mismatch: {scene_count} timed scenes but {len(boards)} "
            "selected images. Remove stale images that do not belong to the current plan."
        )
    if boards and scene_count and len(boards) < scene_count:
        warnings.append(
            f"{len(boards)} approved storyboard images cover {scene_count} timed scenes; "
            "unanchored beats will continue inside the same natural Seedance chapter."
        )
    if duration > 15 and not boards:
        warnings.append("No per-scene storyboard images are selected; later scenes are prompt-guided.")
    if not seed_image_url and not boards:
        warnings.append("No approved opening image is attached; the first scene is text-guided.")
    voices = list(voice_events or []) if sound_on else []
    spoken = sum(max(0.0, min(float(b), duration) - max(0.0, float(a)))
                 for a, b, text in voices if str(text).strip())
    words = sum(len(str(text).split()) for _, _, text in voices)
    if sound_on and not voices:
        warnings.append("Sound is enabled but the brief contains no extractable narration lines.")
    elif voices and spoken / duration < 0.25:
        warnings.append("Narration covers less than 25% of the timeline; ambience is needed between lines.")
    if errors:
        raise ValueError("Video preflight failed: " + " ".join(errors))
    return {
        "status": "passed", "duration_seconds": duration,
        "scene_count": scene_count or len(windows),
        "shot_windows": [{"start": a, "end": b} for a, b in windows],
        "storyboard_count": len(boards),
        "provider_image_mode": "approved first frame per Seedance chapter" if boards else "continuity/text guided",
        "asset_lock": {
            "opening_frame": bool(seed_image_url or boards),
            "character_references": sum(1 for asset in assets if str(asset.get("role") or "").lower() == "character"),
            "product_reference": bool(product_reference_url),
            "logo_master": bool(logo_reference_url),
            "logo_rendering": "post-production composite only" if logo_reference_url else "none",
        },
        "audio_plan": {
            "sound_on": bool(sound_on), "narration_lines": len(voices),
            "narration_words": words, "spoken_window_seconds": round(spoken, 3),
            "single_voice_bed": bool(voices),
        },
        "warnings": warnings,
    }
