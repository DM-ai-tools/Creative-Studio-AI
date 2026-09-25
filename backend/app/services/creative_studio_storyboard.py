"""Parse multi-scene Creative Studio briefs into a Higgsfield-style storyboard."""

from __future__ import annotations

import re
from typing import Any
from app.services.creative_studio_timeline import SHOT_HEADER
from app.services.creative_studio_picture import (
    extract_brand_terms,
    natural_capture_directive,
    sanitize_visual_direction,
)


_SCENE_HEADER = re.compile(
    r"(?is)^\s*(?:Scene|SCENE|CLIP)\s*(\d+)\s*[—\-:.]*\s*([^\n]*)"
)

_OVERLAY_BLOCK = re.compile(
    r"(?is)Video\s*text\s*overlay\s*:?\s*"
)


def looks_like_multi_scene_brief(text: str) -> bool:
    return len(list(SHOT_HEADER.finditer(text or ""))) >= 2


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
    # Common production-brief layout: only VISUAL DIRECTION is sent to the
    # image/video model. VO and copy remain available to deterministic finishers.
    visual_heading = re.search(r"(?im)^\s*VISUAL\s+DIRECTION\s*:\s*$", block)
    if visual_heading:
        after = block[visual_heading.end():]
        stop = re.search(
            r"(?im)^\s*(?:VOICEOVER|VO|NARRATION|(?:FINAL\s+)?ON-SCREEN\s+TEXT|"
            r"TEXT\s+REQUIREMENTS|BRANDING\s+REQUIREMENTS)\s*:\s*$",
            after,
        )
        cleaned = after[:stop.start()] if stop else after

    for copy_match in re.finditer(
        r"(?ims)^\s*(?:FINAL\s+)?ON-SCREEN\s+TEXT\s*:\s*(.*?)(?=^\s*[A-Z][A-Z /+-]{2,}\s*:\s*$|^\s*[-=]{4,}\s*$|\Z)",
        block,
    ):
        section = copy_match.group(1)
        quoted = re.findall(r"[“\"]([^”\"\n]+)[”\"]", section)
        overlays.extend(item.strip() for item in quoted if item.strip())

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
    product_visual_markers = (
        "product box",
        "holding box",
        "package",
        "unbox",
        "unboxing",
        "product photo",
        "product hero",
        "close-up",
        "close up",
        "detail",
        "feature",
        "reveal",
        "shop now",
        "cta",
        "brand finish",
    )
    problem_markers = (
        "problem",
        "manual routine",
        "basic wooden",
        "weathered wooden",
        "old coop",
        "dirty egg",
        "soiled egg",
        "avoidable",
        "checking the chicken coop every",
        "opening the coop",
        "scooping feed",
        "plastic water",
    )
    if any(m in blob for m in product_markers):
        return True
    if any(m in blob for m in product_visual_markers):
        return True
    if any(m in blob for m in problem_markers):
        return False
    # Unspecified scenes may contain the product; never invent a "before" scene.
    return True


def parse_storyboard_scenes(
    brief: str,
    *,
    max_scenes: int = 40,
    product_name: str = "",
) -> list[dict[str, Any]]:
    """
    Split a Scene 1 / Scene 2 … brief into storyboard frames.
    Image prompts are visual-only (no burned-in text); overlays kept for video.
    """
    text = (brief or "").strip()
    if not text:
        return []

    # Only line-start headings delimit scenes; references to "Scene 2" inside a
    # direction are content, not a new scene.
    text = re.sub(r"(?m)^\s*#{1,6}\s*(?=(?:Scene|CLIP)\s*\d+)", "", text, flags=re.I)
    starts = list(SHOT_HEADER.finditer(text))
    parts = [
        text[match.start():starts[i + 1].start() if i + 1 < len(starts) else len(text)].strip()
        for i, match in enumerate(starts)
    ]

    product_label = (product_name or "the product").strip() or "the product"
    scenes: list[dict[str, Any]] = []
    for part in parts[: max_scenes + 2]:
        header = SHOT_HEADER.match(part)
        if not header:
            continue
        numbered = _SCENE_HEADER.match(part)
        num = int(numbered.group(1)) if numbered else len(scenes) + 1
        title = (numbered.group(2) if numbered else header.group()).strip(" —-:") or f"Scene {num}"
        body = part[header.end() :].strip()
        visual, overlays = _extract_overlays(body or title)
        visual = re.sub(
            r"\s+", " ",
            sanitize_visual_direction(visual, brand_terms=extract_brand_terms(text)),
        ).strip()
        if len(visual) < 8:
            visual = f"{title}: {visual}".strip(": ")
        if len(visual) < 6:
            continue

        wants_product = scene_wants_product(title=title, visual=visual, index=num)
        image_prompt = (
            f"{visual} "
            "Single live-action documentary frame — this scene only, one composition. "
            "FULL FRAME. No collage, no split screen, no on-image text, captions, "
            "subtitles, logos, brand names, signage, labels, watermarks, UI chrome, or "
            "placeholder tokens like [BRAND] or [website]. Keep screens, uniforms and "
            "packaging clean and unbranded. Brand graphics are added in post."
            f" {natural_capture_directive(text)}"
        )
        if wants_product:
            image_prompt += (
                f" Show {product_label} matching the attached product photo exactly "
                "(shape, colour stripe, proportions)."
            )
        else:
            # Explicit ban — stop model from pasting the product into problem beats
            image_prompt += (
                f" Do NOT show {product_label} in this explicitly described problem beat. "
                "Use only the setting, objects and actions specified in the brief."
            )

        scenes.append(
            {
                "id": f"scene-{num}",
                "index": num,
                "title": title[:80],
                "image_prompt": image_prompt[:2200],
                "overlays": overlays[:6],
                "raw": part,
                "visual": visual,
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
                    f"{(visual or text)[:1800]} Single live-action documentary frame. "
                    f"No on-image text or captions. {natural_capture_directive(text)}"
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
        timing = re.search(
            r"(\d+(?:\.\d+)?)\s*[–—-]\s*(\d+(?:\.\d+)?)\s*(?:s|seconds?)\b",
            str(scene.get("title") or ""), re.I,
        )
        a, b = (float(timing.group(1)), float(timing.group(2))) if timing else (edges[i], edges[i + 1])
        if b <= a:
            b = a + 1
        title = str(scene.get("title") or f"Scene {i + 1}")
        visual = str(scene.get("visual") or scene.get("raw") or scene.get("image_prompt") or "")
        visual = re.sub(
            r"(?i)\s*Single photoreal still[^.]*\.",
            "",
            visual,
        ).strip()
        overlays = scene.get("overlays") or []
        overlay_line = ""
        if overlays:
            overlay_line = (
                " Reserve clean negative space for the approved campaign copy, which is "
                "composited after generation. Do not render letters, logos or symbols."
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
        "AUDIO: Native ambient sound and foley appropriate to the specified scene. Not silent."
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
        "CHARACTER CONTINUITY: Preserve the subjects, appearance, wardrobe, location "
        "and lighting specified in the brief unless a beat explicitly changes them. "
        "Do not invent people, animals, settings or actions.\n\n"
        + "\n\n".join(clips)
        + f"\n\n{audio}\n"
        "TEXT RULE: Generate clean footage only. Do not render campaign copy, logos, labels, "
        "websites or unrelated text; approved graphics are composited in post-production. "
        "PRODUCT RULE: Product beats must match the supplied product reference exactly. "
        "PRODUCT COVERAGE: Use motivated cinematic views across product beats — hero wide, "
        "three-quarter, side/profile, close detail of defining hardware/stripe/door, "
        "slow tracking or orbit, practical usage view, and a final hero composition. "
        "Each view must describe the same physical product, never a generic substitute. "
        "MOTION RULE: natural human hand/weight/eye movement, physically plausible action, "
        "realistic camera exposure and focus pulls; avoid plastic faces, warped hands, floaty "
        "objects, impossible cuts and glossy AI-looking motion."
    )


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
