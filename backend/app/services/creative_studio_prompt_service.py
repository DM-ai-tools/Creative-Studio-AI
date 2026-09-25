"""LLM prompt builder for Creative Studio — Seedance-optimized multi-clip prompts."""

from __future__ import annotations

import logging
import re

from app.core.config import settings

logger = logging.getLogger(__name__)

CREATIVE_STUDIO_NICHES: list[dict[str, str]] = [
    {"id": "energy_drink", "label": "Energy drink / beverage"},
    {"id": "supplements", "label": "Supplements / gummies"},
    {"id": "fitness", "label": "Fitness / gym / sports"},
    {"id": "headphones", "label": "Headphones / consumer electronics"},
    {"id": "fashion", "label": "Fashion / apparel"},
    {"id": "shoes", "label": "Shoes / footwear"},
    {"id": "beauty", "label": "Beauty / skincare"},
    {"id": "dental", "label": "Dental / oral care"},
    {"id": "hvac", "label": "HVAC / air conditioning"},
    {"id": "trade", "label": "Trade / construction / tradie"},
    {"id": "pet", "label": "Pet products"},
    {"id": "food", "label": "Food / restaurant"},
    {"id": "saas", "label": "SaaS / software"},
    {"id": "real_estate", "label": "Real estate"},
    {"id": "jewellery", "label": "Jewellery / luxury"},
    {"id": "other", "label": "Other (describe below)"},
]

# Seedance prompts need room for continuity + CLIP 1/2/3 + negatives
_PROMPT_MAX = 5000

_STRICT_NEGATIVES = """
STRICT NEGATIVE REQUIREMENTS
NO on-screen text.
NO captions.
NO subtitles.
NO title cards.
NO promotional graphics.
NO UI elements.
NO watermarks.
NO readable logos or brand names.
NO floating product labels.
NO split screen, collage, or stacked panels.
NO change of talent between clips.
NO wardrobe changes between clips.
NO different location between clips.
NO unrealistic body transformation.
NO exaggerated facial expressions.
NO morphing between scenes — use clear cuts only.
""".strip()


def sanitize_visual_prompt(prompt: str) -> str:
    """Strip overlay/caption instructions; keep Seedance structure intact."""
    text = (prompt or "").strip()
    if not text:
        return text
    # Only strip explicit overlay *instructions*, not the whole prompt body
    text = re.sub(
        r"(?i)\b(?:text overlay|on[- ]screen text|burn[- ]in text|title card)\b[^.\n]*[.\n]?",
        " ",
        text,
    )
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if "STRICT NEGATIVE" not in text.upper() and "NO on-screen text" not in text:
        text = f"{text.rstrip()}\n\n{_STRICT_NEGATIVES}"
    return text[:_PROMPT_MAX]


def seed_frame_prompt(prompt: str) -> str:
    """First-frame still from CLIP 1 / opening beat only."""
    visual = (prompt or "").strip()
    m = re.search(
        r"(?is)\bCLIP\s*1\s*(?:\([^)]*\))?\s*:?\s*(.+?)(?=\bCLIP\s*2\b|\bSTRICT\b|$)",
        visual,
    )
    if m:
        opening = re.sub(r"\s+", " ", m.group(1)).strip()[:700]
    else:
        cut = re.split(r"(?i)\bCLIP\s*2\b|\bHOOK\b|\bBODY\b", visual, maxsplit=1)[0].strip()
        opening = cut[:700] if len(cut) >= 40 else visual[:700]
    return (
        f"{opening} "
        "Single photoreal still — opening frame of CLIP 1 only. "
        "FULL FRAME one composition — no collage, no split screen, no stacked panels, "
        "no picture-in-picture, no text of any kind."
    )[:1600]


def build_spoken_voiceover(prompt: str, *, duration_seconds: int = 15) -> str:
    """Only explicitly labelled narration is eligible for speech synthesis."""
    from app.services.creative_studio_video_finishing import extract_voiceover_events

    return " ".join(
        line for _, _, line in extract_voiceover_events(
            prompt, duration_seconds=duration_seconds
        )
    )


def _clip_windows(duration_seconds: int) -> list[tuple[int, int]]:
    """Split duration into ~equal CLIP windows (prefer 3 beats for 12–30s)."""
    d = max(5, int(duration_seconds))
    if d <= 6:
        return [(0, d)]
    if d <= 10:
        mid = d // 2
        return [(0, mid), (mid, d)]
    # 3 beats
    a = max(3, d // 3)
    b = max(3, d // 3)
    c = d - a - b
    if c < 3:
        c = 3
        b = d - a - c
    t0, t1, t2, t3 = 0, a, a + b, d
    return [(t0, t1), (t1, t2), (t2, t3)]


def _fallback_prompt(
    *,
    niche: str,
    media_mode: str,
    duration_seconds: int,
    style: str,
    genre: str,
    camera: str,
    aspect: str,
    product_name: str,
    brand_name: str,
    notes: str,
) -> str:
    niche_l = niche or "product"
    product = product_name or niche_l
    brand = brand_name or "the brand"
    style_l = style if style and style != "auto" else "realistic premium UGC"
    genre_l = genre if genre and genre != "general" else "authentic commercial"
    cam = camera if camera and camera != "auto" else "smooth handheld smartphone / gimbal"
    aspect_l = (aspect or "9/16").replace("/", ":")
    orient = "vertical 9:16" if "9" in aspect_l and aspect_l.startswith("9") else f"{aspect_l} frame"

    if (media_mode or "video").lower() == "image":
        return sanitize_visual_prompt(
            f"Scroll-stopping {style_l} Meta ad still for {brand} — {product} ({niche_l}). "
            f"Genre: {genre_l}. {orient}. Clear product hero in authentic niche environment. "
            f"Single full-frame composition. {notes}".strip()
        )

    windows = _clip_windows(duration_seconds)
    if len(windows) == 1:
        clips = (
            f"CLIP 1 — {windows[0][0]}–{windows[0][1]} SECONDS: Establishing action with {product} "
            f"in the niche setting. Camera: {cam}."
        )
    elif len(windows) == 2:
        clips = (
            f"CLIP 1 — {windows[0][0]}–{windows[0][1]} SECONDS: Setup / problem / activity without product yet.\n\n"
            f"CLIP 2 — {windows[1][0]}–{windows[1][1]} SECONDS: Product reveal, use, satisfied reaction."
        )
    else:
        clips = (
            f"CLIP 1 — {windows[0][0]}–{windows[0][1]} SECONDS: WORKOUT / SETUP\n"
            f"Establish the same talent in the niche environment. Macro or close start, then pull back. "
            f"Do not show the product yet. Camera: {cam}.\n\n"
            f"CLIP 2 — {windows[1][0]}–{windows[1][1]} SECONDS: PRODUCT DISCOVERY / USE\n"
            f"Hard cut. Same person, same clothes, same location. Hands interact with {product} — "
            f"clearly visible for ~1 second, realistic size, then natural use and a subtle satisfied reaction.\n\n"
            f"CLIP 3 — {windows[2][0]}–{windows[2][1]} SECONDS: RETURN TO PERFORMANCE / PAYOFF\n"
            f"Hard cut. Same talent back in action with renewed confidence. Strong final beat, brief hold, fade to black."
        )

    return sanitize_visual_prompt(
        f"{duration_seconds}-SECOND UGC {niche_l.upper()} PRODUCT VIDEO — SINGLE CONTINUOUS STORY\n\n"
        f"Create a realistic, premium-but-authentic {genre_l} advertisement for {brand} — {product}. "
        f"Style: {style_l}. Aspect: {orient}. "
        f"The video follows one same adult throughout all clips. Maintain the exact same person, "
        f"clothing, hairstyle, body type, environment, lighting direction, and visual style "
        f"across the entire {duration_seconds} seconds.\n\n"
        f"SUBJECT CONTINUITY:\n"
        f"One adult matching the {niche_l} audience. Same person in every clip — "
        f"do not change clothes, hairstyle, physique, age, or appearance between shots.\n\n"
        f"ENVIRONMENT:\n"
        f"Authentic {niche_l} setting with niche-correct props. Real working environment, not a fake studio set. "
        f"Background extras only if soft and unidentifiable.\n\n"
        f"PRODUCT:\n"
        f"{product} must look like a real physical product, correctly sized, clearly visible in the product beat, "
        f"never oversized or floating.\n\n"
        f"{clips}\n\n"
        f"VISUAL STYLE\n"
        f"{style_l}. Smartphone/social aesthetic with premium image quality. Natural skin texture. "
        f"Believable human motion. No superhero effects, no glow, no exaggerated transformation.\n\n"
        f"EDITING / TIMING\n"
        f"Use clear cuts between clips. Do not morph between scenes. "
        f"Total length {duration_seconds}s; if the provider has a shorter per-request limit, "
        "preserve this full timeline through continuous chapter segments and final assembly.\n\n"
        f"{notes}".strip()
    )


_SEEDANCE_SYSTEM = """You write Seedance-optimized VISUAL prompts for Higgsfield video ads.
Output ONLY the prompt text — no markdown fences, no preamble, no quotes around the whole prompt.

The prompt MUST follow this structure (adapt content to the niche/product; keep the section headers):

1) One-line title: "{N}-SECOND UGC … — SINGLE CONTINUOUS STORY" where N MUST equal the requested duration exactly (never write 20s when asked for 10s or 15s).
2) Opening paragraph: realistic premium-but-authentic ad; ONE same person across ALL clips; lock clothing, hair, body, location, lighting, style.
3) SUBJECT CONTINUITY: specific age range, build, wardrobe, sweat/effort cues; "same person in Clips 1..N".
4) ENVIRONMENT: niche-correct real location + props + lighting (daylight/gym/bathroom/kitchen/etc.). Soft out-of-focus extras only if needed.
5) PRODUCT: physical description, realistic size, when it appears (usually mid clip), never oversized.
6) TIMING BEATS (CLIP 1 / CLIP 2 / CLIP 3 labels as guides inside ONE continuous video — not separate files):
   - For ≤10s: usually TWO beats. For 12–15s: THREE beats.
   - CLIP 1: setup / activity — usually NO product yet; camera move described.
   - CLIP 2: product discovery + use + subtle genuine reaction (not influencer overacting).
   - CLIP 3 (if needed): payoff / confidence; brief hold; fade to black if fits.
7) VISUAL STYLE: UGC + quality; natural motion; ban cinematic excess / VFX.
8) EDITING / TIMING: Cover the full requested duration with a deliberate opening, escalation, product reveal, multiple motivated product views, and a resolved ending/CTA. If the provider requires short chapters, each chapter must hand off cleanly to the next and preserve the same continuity bible.
9) STRICT NEGATIVE REQUIREMENTS: no random text, UI, watermarks, unreadable logos, split-screen, wardrobe changes or location changes. Preserve and render exact campaign overlays when the brief supplies them.

Rules for Seedance quality:
- Write like a shot list a real DP would follow (camera, hands, face, props).
- Continuity language must be repeated (same athlete / same clothes / same gym).
- FULL FRAME single composition — never ask for split screen or collage.
- Never invent readable brand typography on packaging unless the product name is given — prefer generic physical product look without readable words.
- Do not collapse a long requested runtime into a 15s summary.
- Max ~4800 characters. Be specific, not fluffy.
"""


async def generate_creative_studio_prompt(
    *,
    niche: str,
    media_mode: str = "video",
    duration_seconds: int = 15,
    style: str = "auto",
    genre: str = "general",
    camera: str = "auto",
    aspect: str = "9/16",
    product_name: str = "",
    brand_name: str = "",
    notes: str = "",
) -> str:
    niche = (niche or "").strip()
    if not niche:
        raise ValueError("Niche is required to auto-generate a prompt")

    notes = (notes or "").strip()
    media_mode = (media_mode or "video").strip().lower()
    duration_seconds = max(5, min(60, int(duration_seconds or 15)))
    windows = _clip_windows(duration_seconds)
    window_hint = " | ".join(f"CLIP {i+1} {a}–{b}s" for i, (a, b) in enumerate(windows))

    fallback_kwargs = dict(
        niche=niche,
        media_mode=media_mode,
        duration_seconds=duration_seconds,
        style=style,
        genre=genre,
        camera=camera,
        aspect=aspect,
        product_name=product_name,
        brand_name=brand_name,
        notes=notes,
    )

    if not settings.OPENROUTER_API_KEY:
        return _fallback_prompt(**fallback_kwargs)

    from app.services.image_prompt_service import _get_openrouter_client

    user = (
        f"NICHE / INDUSTRY: {niche}\n"
        f"MEDIA: {media_mode}\n"
        f"DURATION: {duration_seconds}s\n"
        f"CLIP WINDOWS: {window_hint}\n"
        f"ASPECT RATIO: {aspect}\n"
        f"STYLE: {style or 'auto'}\n"
        f"GENRE: {genre or 'general'}\n"
        f"CAMERA PREFERENCE: {camera or 'auto'}\n"
        f"BRAND: {brand_name or '(infer lightly; do not force readable logos)'}\n"
        f"PRODUCT: {product_name or '(infer a concrete physical product from the niche)'}\n"
        f"EXTRA NOTES: {notes or '(none)'}\n\n"
        "Write one Seedance-optimized prompt in the required structure. "
        f"Title MUST start with exactly '{duration_seconds}-SECOND' (never invent a different length). "
        "Any industry / any product / any style — but always continuity + timed beats + strict negatives. "
        "Do NOT include spoken dialogue or a narrator reading the prompt."
    )

    try:
        client = _get_openrouter_client()
        model = settings.OPENROUTER_MODEL_CLAUDE or "anthropic/claude-haiku-4.5"
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SEEDANCE_SYSTEM},
                {"role": "user", "content": user},
            ],
            max_tokens=2200,
            temperature=0.75,
        )
        raw = (response.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:\w+)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()
        raw = raw.strip('"').strip("'").strip()
        if len(raw) < 120:
            raise ValueError("LLM returned an empty prompt")
        # Soft sanitize — do not crush CLIP structure
        return sanitize_visual_prompt(raw[:_PROMPT_MAX])
    except Exception as exc:
        logger.warning("Creative Studio prompt LLM failed: %s", exc)
        return _fallback_prompt(**fallback_kwargs)
