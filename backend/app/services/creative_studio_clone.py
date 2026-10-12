"""Clone-image scene catalogue and compact GPT Image prompt compiler."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


_SCENE_FILE = Path(__file__).with_name("creative_studio_clone_scenes.json")


@lru_cache(maxsize=1)
def clone_scenes() -> list[dict[str, str]]:
    try:
        rows = json.loads(_SCENE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [
        {
            "id": str(row.get("id") or ""),
            "category": str(row.get("category") or "Other"),
            "title": str(row.get("title") or "Scene"),
            "description": str(row.get("description") or ""),
        }
        for row in rows
        if isinstance(row, dict) and row.get("id") and row.get("description")
    ]


def clone_scene(scene_id: str) -> dict[str, str] | None:
    wanted = str(scene_id or "").strip().lower()
    return next((row for row in clone_scenes() if row["id"] == wanted), None)


def compile_clone_prompt(
    *,
    user_prompt: str,
    scene_id: str,
    clone_count: int,
) -> str:
    """Build a short identity-led prompt; long prompts reduce face fidelity."""
    scene = clone_scene(scene_id)
    count = max(2, min(6, int(clone_count or 4)))
    direction = str(user_prompt or "").strip()
    scene_text = scene["description"] if scene else direction
    if scene and direction and direction.lower() not in scene_text.lower():
        scene_text = f"{scene_text} Additional direction: {direction}"
    if not scene_text:
        scene_text = "A premium modern advertising scene with coordinated action."
    return (
        "Create one photorealistic advertising image. "
        f"Scene: {scene_text} "
        f"Show exactly {count} separate copies of the one same person shown in the attached "
        "character reference photographs. Every copy must have the exact same facial identity, "
        "hair, age, skin tone and body build. Use coordinated scene-appropriate wardrobe and give "
        "each copy a distinct, physically believable action. Keep all important faces clear and "
        "recognisable; identity accuracy is more important than background complexity. Correct "
        "anatomy, natural hands, no fused bodies, no duplicate limbs, no extra people. "
        "No captions, logos, watermarks or readable text."
    )


def clone_scene_groups() -> dict[str, Any]:
    scenes = clone_scenes()
    labels = list(dict.fromkeys(row["category"] for row in scenes))
    return {
        "categories": [{"id": label, "label": label} for label in labels],
        "scenes": scenes,
    }
