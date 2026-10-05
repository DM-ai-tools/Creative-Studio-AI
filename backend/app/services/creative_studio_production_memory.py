"""Immutable production bible and chapter ledger for staged Creative Studio films.

The browser chat is not a reliable production database.  This module freezes the
authored timeline, reference set, audio identity and style once, persists them with
the tenant, and compiles every paid chapter from that same package.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.creative_studio_timeline import explicit_shot_windows, segment_motion_prompt


VERSION = 1
_SESSION_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _memory_path(tenant_id: str, session_id: str) -> Path:
    safe = _SESSION_SAFE.sub("-", str(session_id or "").strip())[:80].strip("-")
    if not safe:
        safe = "production-" + _digest(session_id)[:16]
    root = Path(settings.UPLOAD_DIR).resolve() / tenant_id / "creative-studio-productions"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{safe}.json"


def normalized_reference_lock(
    reference_assets: list[dict[str, Any]] | None,
    *,
    product_reference_url: str | None,
    logo_reference_url: str | None,
) -> list[dict[str, str]]:
    by_url: dict[str, str] = {}
    priority = {"character": 0, "product": 1, "scene": 2, "logo": 3, "reference": 4}

    def add(url: Any, role: str) -> None:
        value = str(url or "").strip()
        if not value:
            return
        existing = by_url.get(value)
        if existing is None or priority.get(role, 99) < priority.get(existing, 99):
            by_url[value] = role

    for asset in reference_assets or []:
        if not isinstance(asset, dict):
            continue
        role = str(asset.get("role") or "reference").strip().lower()
        if role not in priority:
            role = "reference"
        add(asset.get("url"), role)
    add(product_reference_url, "product")
    add(logo_reference_url, "logo")
    return [
        {"url": url, "role": role}
        for url, role in sorted(by_url.items(), key=lambda item: (priority[item[1]], item[0]))
    ]


def _chapter_windows(
    prompt: str, duration: int, clip_cap: int, *, storyboard_count: int = 0
) -> list[tuple[float, float]]:
    authored = explicit_shot_windows(prompt, total=duration)
    if not authored:
        return [
            (float(start), float(min(duration, start + clip_cap)))
            for start in range(0, duration, clip_cap)
        ]
    # A complete approved storyboard is one explicit image per authored scene.
    # Preserve those exact boundaries so each image anchors only its own scene.
    if storyboard_count and storyboard_count == len(authored):
        return authored
    chapters: list[tuple[float, float]] = []
    start, end = authored[0]
    for shot_start, shot_end in authored[1:]:
        if shot_end - start <= clip_cap + 0.05:
            end = shot_end
        else:
            chapters.append((start, end))
            start, end = shot_start, shot_end
    chapters.append((start, end))
    return chapters


def create_production_memory(
    *,
    tenant_id: str,
    session_id: str,
    prompt: str,
    duration_seconds: int,
    clip_cap: int,
    aspect: str,
    resolution: str,
    model: str,
    brand_name: str,
    product_name: str,
    voice_events: list[tuple[float, float, str]],
    references: list[dict[str, str]],
    storyboard_count: int = 0,
) -> dict[str, Any]:
    canonical = str(prompt or "").strip()
    chapters = _chapter_windows(
        canonical,
        int(duration_seconds),
        int(clip_cap),
        storyboard_count=int(storyboard_count),
    )
    prompt_hash = _digest(canonical)
    reference_hash = _digest(references)
    production_id = _digest([tenant_id, session_id, prompt_hash, reference_hash])[:24]
    lower_prompt = canonical.lower()
    female_requested = bool(re.search(r"\b(?:female voice|female presenter|woman presenter)\b", lower_prompt))
    male_requested = bool(re.search(r"\b(?:male voice|male presenter|man presenter)\b", lower_prompt))
    voice = "cedar" if male_requested and not female_requested else "marin"
    return {
        "version": VERSION,
        "production_id": production_id,
        "session_id": session_id,
        "created_at": _now(),
        "updated_at": _now(),
        "status": "active",
        "canonical_prompt": canonical,
        "canonical_prompt_sha256": prompt_hash,
        "duration_seconds": int(duration_seconds),
        "model": model,
        "style_guide": {
            "aspect": aspect,
            "resolution": resolution,
            "fps": 24,
            "colour_grade": "one warm-neutral commercial grade across every chapter",
            "lighting": "one consistent office lighting language and colour temperature",
            "camera": "controlled moves; preserve axis and movement direction across handoffs",
            "audio": "one post-produced master narration; provider speech disabled",
        },
        "voice_lock": {
            "provider": "openai",
            "model": "gpt-4o-mini-tts",
            "voice": voice,
            "accent": "Australian English" if "australian" in canonical.lower() else "brief-defined",
            "mode": "off_camera_master_narration",
            "target_lufs": -16.0,
            "native_provider_speech": False,
        },
        "brand_name": brand_name,
        "product_name": product_name,
        "reference_lock": references,
        "reference_lock_sha256": reference_hash,
        "script": [
            {"start": float(a), "end": float(b), "text": str(text)}
            for a, b, text in voice_events
        ],
        "shot_list": [
            {"chapter": index + 1, "start": a, "end": b}
            for index, (a, b) in enumerate(chapters)
        ],
        "chapter_log": [],
    }


def load_production_memory(tenant_id: str, session_id: str) -> dict[str, Any] | None:
    path = _memory_path(tenant_id, session_id)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def save_production_memory(tenant_id: str, memory: dict[str, Any]) -> None:
    session_id = str(memory.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("Production memory requires a Creative Studio session id")
    memory["updated_at"] = _now()
    path = _memory_path(tenant_id, session_id)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def ensure_production_memory(
    *,
    tenant_id: str,
    session_id: str,
    prompt: str,
    duration_seconds: int,
    clip_cap: int,
    aspect: str,
    resolution: str,
    model: str,
    brand_name: str,
    product_name: str,
    voice_events: list[tuple[float, float, str]],
    references: list[dict[str, str]],
    storyboard_count: int = 0,
) -> dict[str, Any]:
    existing = load_production_memory(tenant_id, session_id)
    prompt_hash = _digest(str(prompt or "").strip())
    refs_hash = _digest(references)
    if existing and existing.get("status") == "active" and existing.get("chapter_log"):
        if existing.get("canonical_prompt_sha256") != prompt_hash:
            # Button labels and short follow-up prompts must never replace the film bible.
            # A new chat creates a new session id and therefore a new production.
            prompt = str(existing.get("canonical_prompt") or prompt)
        if existing.get("reference_lock_sha256") != refs_hash:
            raise ValueError(
                "Production references are already locked. Keep the same character, product, "
                "scene and logo assets for every chapter, or start a new Creative Studio chat."
            )
        return existing
    memory = create_production_memory(
        tenant_id=tenant_id,
        session_id=session_id,
        prompt=prompt,
        duration_seconds=duration_seconds,
        clip_cap=clip_cap,
        aspect=aspect,
        resolution=resolution,
        model=model,
        brand_name=brand_name,
        product_name=product_name,
        voice_events=voice_events,
        references=references,
        storyboard_count=storyboard_count,
    )
    save_production_memory(tenant_id, memory)
    return memory


def compile_locked_chapter_prompt(memory: dict[str, Any], *, chapter_index: int) -> str:
    shots = list(memory.get("shot_list") or [])
    if chapter_index < 0 or chapter_index >= len(shots):
        raise ValueError("Requested chapter is outside the locked production timeline")
    shot = shots[chapter_index]
    start, end = float(shot["start"]), float(shot["end"])
    canonical = str(memory.get("canonical_prompt") or "")
    local = segment_motion_prompt(
        canonical,
        start=start,
        end=end,
        total=float(memory.get("duration_seconds") or end),
    )
    references = ", ".join(
        f"{asset.get('role')}={_digest(asset.get('url'))[:10]}"
        for asset in memory.get("reference_lock") or []
    ) or "none"
    cues = []
    for event in memory.get("script") or []:
        a, b = float(event["start"]), float(event["end"])
        if a < end and b > start:
            cues.append(
                f"local {max(a, start)-start:g}-{min(b, end)-start:g}s: {event['text']}"
            )
    previous = (memory.get("chapter_log") or [])[-1:] or []
    previous_line = (
        f"Previous accepted chapter ended on continuity frame {previous[0].get('continuity_frame_url')} "
        f"with QA status {previous[0].get('qa_status')}."
        if previous else "This is the first chapter. Establish the locked world once."
    )
    return (
        "LOCKED PRODUCTION PACKAGE — NEVER RECAST, RESTYLE OR REWRITE.\n"
        f"Production {memory.get('production_id')}; chapter {chapter_index + 1}/{len(shots)}; "
        f"global {start:g}-{end:g}s.\n"
        f"Reference manifest: {references}. The exact same assets are authoritative in every chapter.\n"
        "IDENTITY LOCK: preserve the accepted fictional presenter's face, age, skin tone, hair, "
        "navy/charcoal wardrobe and proportions. Preserve all product colours, logos, props and office architecture.\n"
        "STYLE LOCK: 24fps, one warm-neutral grade, identical white balance and restrained green/blue accents.\n"
        "AUDIO/ACTING LOCK: provider speech is disabled. Narration is an off-camera master track. "
        "Visible people must not speak, mouth words, or perform lip-sync; use natural closed-mouth reactions.\n"
        "B-ROLL LOCK: every visual must illustrate the narration cue at that exact local time. "
        "No generic walking, random dashboards, filler shots or repeated action.\n"
        f"HANDOFF: {previous_line} Start from the attached exact continuity frame when present.\n"
        + ("NARRATION CUES FOR VISUAL ALIGNMENT ONLY — DO NOT SPEAK THEM:\n" + "\n".join(cues) + "\n" if cues else "")
        + "\n"
        + local
    )


def append_chapter_log(
    tenant_id: str,
    memory: dict[str, Any],
    *,
    chapter_index: int,
    video_url: str,
    video_path: str,
    duration_seconds: float,
    continuity_frame_url: str | None,
    qa: dict[str, Any],
    provider_task_id: str | None,
) -> None:
    log = list(memory.get("chapter_log") or [])
    entry = {
        "chapter": chapter_index + 1,
        "accepted_at": _now(),
        "video_url": video_url,
        "video_path": video_path,
        "duration_seconds": round(float(duration_seconds), 3),
        "continuity_frame_url": continuity_frame_url,
        "qa_status": qa.get("status"),
        "qa": qa,
        "provider_task_id": provider_task_id,
        "reference_lock_sha256": memory.get("reference_lock_sha256"),
    }
    log = [item for item in log if int(item.get("chapter") or 0) != chapter_index + 1]
    log.append(entry)
    log.sort(key=lambda item: int(item.get("chapter") or 0))
    memory["chapter_log"] = log
    if len(log) >= len(memory.get("shot_list") or []):
        memory["status"] = "complete"
    save_production_memory(tenant_id, memory)


def public_production_report(memory: dict[str, Any]) -> dict[str, Any]:
    """Compact UI-safe proof that every chapter used the same frozen package."""
    return {
        "production_id": memory.get("production_id"),
        "status": memory.get("status"),
        "canonical_prompt_sha256": memory.get("canonical_prompt_sha256"),
        "reference_lock_sha256": memory.get("reference_lock_sha256"),
        "reference_count": len(memory.get("reference_lock") or []),
        "chapter_count": len(memory.get("shot_list") or []),
        "accepted_chapters": len(memory.get("chapter_log") or []),
        "voice_lock": memory.get("voice_lock"),
        "style_guide": memory.get("style_guide"),
        "chapter_log": memory.get("chapter_log") or [],
    }

