"""Parse multi-scene Creative Studio briefs into a Higgsfield-style storyboard."""

from __future__ import annotations

import re
from typing import Any


_SCENE_HEADER = re.compile(
    r"(?is)^\s*(?:Scene|SCENE|CLIP)\s*(\d+)\s*[—\-:.]*\s*([^\n]*)"
)

_OVERLAY_BLOCK = re.compile(
    r"(?is)Video\s*text\s*overlay\s*:?\s*"
)


def looks_like_multi_scene_brief(text: str) -> bool:
    raw = text or ""
    return len(re.findall(r"(?i)\bScene\s*\d+\b", raw)) >= 2 or len(
        re.findall(r"(?i)\bCLIP\s*\d+\b", raw)
    ) >= 2


def _extract_overlays(block: str) -> tuple[str, list[str]]:
    overlays: list[str] = []
    cleaned = block
    m = _OVERLAY_BLOCK.search(block)
    if m:
        after = block[m.end() :]
        # Until next Scene/CLIP header or end
        stop = re.search(r"(?i)\n\s*(?:Scene|CLIP)\s*\d+\b", after)
        chunk = after[: stop.start()] if stop else after
        for line in re.split(r"[\n|/]+", chunk):
            line = line.strip().strip('"').strip("'")
            line = re.sub(r"\s*[❌✓]\s*$", "", line).strip()
            if line and len(line) > 1 and not line.lower().startswith("scene"):
                overlays.append(line[:120])
        # Remove overlay section from visual
        end_idx = m.start()
        cleaned = block[:end_idx]
        if stop:
            cleaned += after[stop.start() :]
    cleaned = re.sub(r"(?im)^\s*Video\s*text\s*overlay\s*:?\s*.*$", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, overlays


def scene_wants_product(*, title: str, visual: str, index: int = 1) -> bool:
    """
    True only for product-reveal beats.
    Problem/hook/manual scenes must NOT get the product photo reference.
    """
    blob = f"{title} {visual}".lower()
    product_markers = (
        "the turn",
        "easier way",
        "chicken caravan",
        " cc10",
        "cc10 ",
        "product feature",
        "product close",
        "product reveal",
        "feature reveal",
        "full cc10",
        "orbit the",
        "push-in on the front",
    )
    problem_markers = (
        "problem",
        "manual routine",
        "hook",
        "basic wooden",
        "weathered wooden",
        "old coop",
        "dirty egg",
        "soiled egg",
        "tired",
        "avoidable",
        "checking the chicken coop every",
        "opening the coop",
        "scooping feed",
        "plastic water",
    )
    if any(m in blob for m in product_markers):
        return True
    if any(m in blob for m in problem_markers):
        return False
    # Scene 1–2 default to problem world unless explicitly product
    if int(index or 1) <= 2:
        return False
    # Scene 3+ default to product if not clearly a problem beat
    return True


def parse_storyboard_scenes(
    brief: str,
    *,
    max_scenes: int = 6,
    product_name: str = "",
) -> list[dict[str, Any]]:
    """
    Split a Scene 1 / Scene 2 … brief into storyboard frames.
    Image prompts are visual-only (no burned-in text); overlays kept for video.
    """
    text = (brief or "").strip()
    if not text:
        return []

    parts = [p.strip() for p in re.split(r"(?i)(?=\bScene\s*\d+\b)", text) if p.strip()]
    if len(parts) < 2:
        parts = [p.strip() for p in re.split(r"(?i)(?=\bCLIP\s*\d+\b)", text) if p.strip()]

    product_label = (product_name or "the product").strip() or "the product"
    scenes: list[dict[str, Any]] = []
    for part in parts[: max_scenes + 2]:
        header = _SCENE_HEADER.match(part)
        if not header:
            continue
        num = int(header.group(1))
        title = (header.group(2) or "").strip(" —-:") or f"Scene {num}"
        body = part[header.end() :].strip()
        visual, overlays = _extract_overlays(body)
        visual = re.sub(r"\s+", " ", visual).strip()
        if len(visual) < 8:
            visual = f"{title}: {visual}".strip(": ")
        if len(visual) < 6:
            continue

        wants_product = scene_wants_product(title=title, visual=visual, index=num)
        image_prompt = (
            f"{visual} "
            "Single photoreal still — this scene only, one composition. "
            "FULL FRAME. No collage, no split screen, no on-image text, captions, "
            "subtitles, watermarks, or UI chrome."
        )
        if wants_product:
            image_prompt += (
                f" Show {product_label} matching the attached product photo exactly "
                "(shape, colour stripe, proportions)."
            )
        else:
            # Explicit ban — stop model from pasting the product into problem beats
            image_prompt += (
                f" CRITICAL: Do NOT show {product_label}, any modern white trailer coop, "
                "or any branded mobile caravan. This is the BEFORE / problem state — "
                "only a basic weathered wooden chicken coop and manual chores."
            )

        scenes.append(
            {
                "id": f"scene-{num}",
                "index": num,
                "title": title[:80],
                "image_prompt": image_prompt[:2200],
                "overlays": overlays[:6],
                "raw": part[:2000],
                "wants_product": wants_product,
            }
        )

    by_idx: dict[int, dict[str, Any]] = {}
    for s in scenes:
        by_idx[int(s["index"])] = s
    ordered = [by_idx[k] for k in sorted(by_idx.keys())][:max_scenes]

    if not ordered and text:
        visual, overlays = _extract_overlays(text)
        ordered = [
            {
                "id": "scene-1",
                "index": 1,
                "title": "Opening",
                "image_prompt": (
                    f"{(visual or text)[:1800]} Single photoreal still. "
                    "No on-image text or captions."
                ),
                "overlays": overlays[:4],
                "raw": text[:2000],
                "wants_product": False,
            }
        ]
    return ordered


def build_storyboard_video_prompt(
    scenes: list[dict[str, Any]],
    *,
    duration_seconds: int = 15,
    sound_on: bool = True,
    product_name: str = "",
) -> str:
    """Timed Seedance prompt that walks every storyboard scene + overlay copy."""
    secs = max(5, min(600, int(duration_seconds or 15)))
    n = max(1, len(scenes))
    edges = [round(i * secs / n) for i in range(n + 1)]
    edges[-1] = secs

    clips: list[str] = []
    for i, scene in enumerate(scenes):
        a, b = edges[i], edges[i + 1]
        if b <= a:
            b = a + 1
        title = str(scene.get("title") or f"Scene {i + 1}")
        visual = str(scene.get("image_prompt") or scene.get("raw") or "")[:700]
        visual = re.sub(
            r"(?i)\s*Single photoreal still[^.]*\.",
            "",
            visual,
        ).strip()
        overlays = scene.get("overlays") or []
        overlay_line = ""
        if overlays:
            joined = " | ".join(str(o) for o in overlays[:4])
            overlay_line = (
                f" ON-SCREEN TEXT — render these exact words legibly in the video, "
                f"without paraphrasing or inventing text: {joined}. "
                "Use clean high-contrast advertising typography, placed safely inside frame."
            )
        clips.append(
            f"CLIP {i + 1} — {a}–{b} SECONDS ({title}): {visual}.{overlay_line}"
        )

    product_line = (
        f"PRODUCT LOCK: {product_name} must match the attached product photo in every product beat.\n"
        if product_name
        else ""
    )
    audio = (
        "AUDIO: Native diegetic sound — ambient farm/yard, foley, soft natural presence. Not silent."
        if sound_on
        else "AUDIO: Silent — no speech, no music."
    )
    return (
        f"{secs}-SECOND MULTI-SCENE COMMERCIAL — follow EVERY clip below in order. "
        "Use the full requested runtime; do not compress the story into one opening shot. "
        "Begin with a deliberate establishing image, build through the problem, reveal and "
        "product demonstration, then finish with a clear visual ending/CTA. "
        "Hard cuts between scenes are OK inside one continuous generation. "
        "Do NOT freeze on a single opening frame.\n\n"
        f"{product_line}"
        "CHARACTER CONTINUITY: The same adult woman must appear in every scene: same face, "
        "age, hairstyle, body type, wardrobe and colour palette. Preserve her identity across "
        "cuts; do not replace her with a different person. Keep the same farm/yard geography "
        "and natural morning-light progression unless a beat explicitly changes it.\n\n"
        + "\n\n".join(clips)
        + f"\n\n{audio}\n"
        "TEXT RULE: Every listed overlay is intentional campaign copy. Render it exactly and "
        "legibly; do not omit, rewrite, misspell or add unrelated text. "
        "PRODUCT RULE: Product beats must match the supplied product reference exactly. "
        "PRODUCT COVERAGE: Use motivated cinematic views across product beats — hero wide, "
        "three-quarter, side/profile, close detail of defining hardware/stripe/door, "
        "slow tracking or orbit, practical usage view, and a final hero composition. "
        "Each view must describe the same physical product, never a generic substitute. "
        "MOTION RULE: natural human hand/weight/eye movement, physically plausible chickens, "
        "realistic camera exposure and focus pulls; avoid plastic faces, warped hands, floaty "
        "objects, impossible cuts and glossy AI-looking motion."
    )[:4800]


def opening_still_prompt(scenes: list[dict[str, Any]]) -> str:
    if not scenes:
        return ""
    return str(scenes[0].get("image_prompt") or "")


def product_hero_scene(scenes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for s in scenes:
        blob = f"{s.get('title','')} {s.get('image_prompt','')}".lower()
        if any(k in blob for k in ("reveal", "feature", "caravan", "product close", "cc10")):
            return s
    return scenes[-1] if scenes else None
