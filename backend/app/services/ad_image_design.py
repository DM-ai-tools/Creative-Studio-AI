"""A different, designed look for every ad image in a brief, in a short prompt.

Why: the brief's image path applied ONE campaign-wide on-image style to every variant (dark
lower-third gradient, white sans headline, CTA pill) and then stacked a long series of rule blocks on
the prompt (brand lock, text anchor, prop ban, copy rules, palette lock...). Every ad came out the same
and the prompt ran to ~4,000 characters. The landing-page image tab looks better because each creative
gets its own named design (medium, typography treatment, composition).

This does the same here, only when the campaign leaves both "on-image style" and "visual style" on
Auto and the variant's prompt is not an authoritative one the user (or the strategy file) wrote:
  * each variant gets a different design from a library (a shuffled rotation, so a brief never
    repeats one until the library is used up);
  * the prompt is rebuilt short: the scene the strategy/LLM wrote for that variant (its layout and
    typography sentences removed, since the design decides those), the design direction, the exact
    words to print, the brand colours and fonts, and the guardrails (no logo, no brand name);
  * the brand's name is removed (the real logo is placed afterwards, see ad_image_logo.py).
A strategy file's per-variant scene is respected: it is the scene. Without one, the prompt-writing AI's
scene is used. Anything else keeps working exactly as before.
"""

from __future__ import annotations

import hashlib
import random
import re
from typing import Any

from app.services.ad_image_brand import brand_style_line
from app.services.creative_studio_still import NO_LOGO_SHORT, scrub_brand_name

VARIED = "varied"
MAX_SCENE_CHARS = 700

# Each: what it looks like, how the type is treated. People-led and object-led looks are mixed so a
# batch is not all portraits and not all abstract metaphors.
DESIGN_LIBRARY: list[dict[str, str]] = [
    {
        "label": "editorial portrait on clean negative space",
        "visual": "A real, candid person in their genuine environment, framed with generous empty space for the type; natural light, shallow depth of field.",
        "typography": "Large bold editorial headline sitting in the empty space, one key word in the accent colour; small supporting line; compact button chip.",
    },
    {
        "label": "dark cinematic conceptual 3D",
        "visual": "A moody dark stage with glowing glass and one metaphor object that literalises the problem; dramatic rim light.",
        "typography": "Thick white display type on a subtle arc or glass panel; neon accent button.",
    },
    {
        "label": "clean isometric 3D scene",
        "visual": "Isometric objects, charts and folders with soft shadows on a high-key studio gradient; keynote clarity.",
        "typography": "Bold modern sans on floating 3D labels and tabs; button as a raised 3D tab.",
    },
    {
        "label": "floating hero object on a bold colour field",
        "visual": "One hero object lit like a product shot on a solid brand-colour backdrop, lots of air.",
        "typography": "Minimal sans floating beside the object; button as a round badge.",
    },
    {
        "label": "overhead flat-lay workspace",
        "visual": "Top-down desk with the tools of the trade, organised chaos, warm daylight.",
        "typography": "Short copy printed on cards and notes lying in the scene; no bottom banner; button as a sticker or tab.",
    },
    {
        "label": "split-screen before and after",
        "visual": "Two halves telling the pain-to-relief story with a clear visual contrast.",
        "typography": "Contrasting weights left versus right; button centred on the dividing line.",
    },
    {
        "label": "brutalist swiss poster",
        "visual": "Bold colour fields and an asymmetric grid; one hero image cropped hard; no stock-photo clichés.",
        "typography": "Huge Helvetica-style blocks of type, one accent colour bar; button as a solid rectangle.",
    },
    {
        "label": "neon sign practical effect",
        "visual": "A night scene where the headline is a real neon tube sign; brand colours as neon glow.",
        "typography": "Headline as neon letters, button as a smaller neon sub-sign.",
    },
    {
        "label": "UGC phone-native frame",
        "visual": "A handheld, phone-camera look in natural light; feels like a real feed post, not a studio ad.",
        "typography": "Caption-style headline like a social post overlay; system-UI font; button as a native UI button.",
    },
    {
        "label": "luxury glass and light refraction",
        "visual": "Premium refractions and caustics, a dark luxe background built from the brand primary.",
        "typography": "Elegant thin type on frosted glass; button as a jewel-tone pill.",
    },
    {
        "label": "macro tactile still",
        "visual": "Extreme close-up of materials with shallow depth of field; the hero object tells the story.",
        "typography": "Minimal condensed sans stamped or embossed into the scene; tiny button chip.",
    },
    {
        "label": "retro risograph poster",
        "visual": "Two-colour riso grain with a limited palette pulled from the brand colours.",
        "typography": "Chunky retro display type with slight misregistration; button as a print badge.",
    },
    {
        "label": "street poster wheatpaste wall",
        "visual": "Urban textured wall with layered paste-up posters; gritty and authentic.",
        "typography": "All-caps condensed paste-up headline; button as a peel-off sticker.",
    },
    {
        "label": "soft lifestyle in context",
        "visual": "A real environment (office, workshop, shop, clinic); story-first, warm and human.",
        "typography": "Friendly rounded sans on environmental signage or a screen in the scene; button as a simple pill.",
    },
    {
        "label": "paper-craft layered cut-out",
        "visual": "Layered cut paper with craft shadows; playful but premium.",
        "typography": "Cut-paper letterforms and a paper banner; button as a folded paper tab.",
    },
]

# Sentences in a written scene that decide layout, type or text. The design decides those instead.
_LAYOUT_SENTENCE = re.compile(
    r"(?i)lower[\s-]?third|upper[\s-]?third|gradient|overlay|on[\s-]image|burn(?:ed|t)?[\s-]?in|image_hook|"
    r"image_headline|\bcta\b|\bpill\b|\bbutton\b|typograph|\bfonts?\b|\btext\b|\bheadline\b|\bsubline\b|"
    r"\bcopy\b|palette|#[0-9a-f]{6}\b|brand identity|brand visual|\blogo\b|wordmark|\bbanner\b|"
    r"title case|all caps|sans-serif|serif|montserrat|kanit|\bsticker\b|caption"
)


SHORT_SCENE_CHARS = 240


def is_short_scene(prompt: Any) -> bool:
    """A few words describing a picture ("woman holding a ring in a boutique"), with nothing about text,
    typography, colours or layout. That is a scene to build on, not a finished prompt."""
    text = " ".join(str(prompt or "").split())
    return bool(text) and len(text) <= SHORT_SCENE_CHARS and not _LAYOUT_SENTENCE.search(text)


def scene_may_be_redesigned(slot: Any, verbatim_slot: bool) -> bool:
    """False only for a complete prompt a person wrote or pasted. These are built on and given their own
    design: a scene from the strategy file, one from the prompt-writing AI, and a SHORT typed prompt.
    A long prompt that already carries its own text, type and layout is sent as written."""
    if isinstance(slot, dict) and slot.get("brief_complete"):
        return False  # a designer brief is a finished layout: no recomposed look, no app-drawn caption on top
    if not verbatim_slot:
        return True
    if not isinstance(slot, dict):
        return False
    source = str(slot.get("prompt_source") or "").strip().lower()
    if source in {"strategy", "ai"}:
        return True
    # No recorded source but "Generate AI" stamped the slot (generated_at): the prompt is the AI's own
    # draft (older briefs, or a slot whose marker was lost on the way). A hand edit is marked "user".
    if not source and str(slot.get("generated_at") or "").strip():
        return True
    return is_short_scene(slot.get("prompt"))


_FOCUS_LINE = {
    "product_only": "The product itself is the hero, large in frame, with no people.",
    "with_person": "A real person is the main subject, with the product clearly visible.",
    "product_with_person": "The product is the hero, with a person adding lifestyle context.",
}


def _casting_line(audience: Any) -> str:
    """People in the image should fit the stated audience and place, not an invented cultural setting."""
    info = audience if isinstance(audience, dict) else {}
    who = " ".join(str(info.get(k) or "").strip() for k in ("audience_type", "age_range")).strip()
    where = str(info.get("geography") or "").strip()
    if not who and not where:
        return ""
    return (
        f"If people appear, cast them naturally for {who or 'the audience'}"
        + (f" in {where}" if where else "")
        + "; no culturally specific costume, accessories or setting unless the scene asks for it."
    )


def enabled(kb_models: dict | None, brief_dict: dict | None, on_image_style: str, visual_style: str) -> bool:
    """On only when asked for AND the campaign did not choose a specific style of its own."""
    setting = str((kb_models or {}).get("image_design_variety") or (brief_dict or {}).get("image_design_variety") or "")
    exact = str((kb_models or {}).get("image_text_mode") or (brief_dict or {}).get("image_text_mode") or "")
    # "Exact brand fonts" rebuilds the prompt too (a text-free picture), so it switches this on by itself.
    if setting.strip().lower() != VARIED and exact.strip().lower() != "exact":
        return False
    return (on_image_style or "auto").strip().lower() in {"", "auto"} and (visual_style or "auto").strip().lower() in {"", "auto"}


def _rng(seed: str) -> random.Random:
    return random.Random(int.from_bytes(hashlib.sha256(str(seed).encode("utf-8")).digest()[:8], "big"))


def style_for_variant(index: int, seed: str) -> dict[str, str]:
    """The Nth variant of a brief gets the Nth design of a shuffle seeded by the brief, so a batch is
    all different until the library is used up."""
    pool = list(DESIGN_LIBRARY)
    _rng(f"brief:{seed}").shuffle(pool)
    return pool[max(0, int(index)) % len(pool)]


def style_for_key(key: str) -> dict[str, str]:
    """A stable pick for one image (used when it is regenerated on its own)."""
    return DESIGN_LIBRARY[_rng(f"image:{key}").randrange(len(DESIGN_LIBRARY))]


def clean_scene(text: str, limit: int = MAX_SCENE_CHARS) -> str:
    """The picture's subject, setting, people and mood: the sentences that are not layout, type or text."""
    kept: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        sentence = sentence.strip()
        if not sentence or _LAYOUT_SENTENCE.search(sentence):
            continue
        kept.append(sentence)
    out = ""
    for sentence in kept:
        if len(out) + len(sentence) + 1 > limit:
            break
        out = f"{out} {sentence}".strip()
    return out


def _quoted(label: str, value: str) -> str:
    value = " ".join((value or "").split()).replace('"', "'")
    return f'{label} "{value}"' if value else ""


def compose(
    *,
    scene_source: str,
    fallback_source: str = "",
    seed: str,
    index: int | None,
    key: str = "",
    hook: str = "",
    headline: str = "",
    cta: str = "",
    primary: str = "",
    secondary: str = "",
    font_heading: str = "",
    font_body: str = "",
    photo_only: bool = False,
    brand_name: str = "",
    frame_note: str = "",
    audience: Any = None,
    focus: str = "",
    exact_text: bool = False,
    text_zone: str = "bottom",
) -> tuple[str, str]:
    """The short, designed prompt and the name of the design used.

    ``exact_text``: the app will draw the text itself in the brand's real fonts (ad_image_text.py), so the
    picture is asked for with no writing at all and a calm empty band at the top or bottom for it."""
    style = style_for_variant(index, seed) if index is not None else style_for_key(key or seed)
    scene = clean_scene(scene_source)
    if len(scene) < 40:
        scene = clean_scene(fallback_source) or scene
    scene, _ = scrub_brand_name(scene, brand_name)
    scene = scene or "A real, specific, well-lit scene that makes the offer's benefit obvious."

    lead = scene if re.search(r"(?i)\bads?\b", scene[:90]) else f"Static social ad. {scene}"
    parts = [lead, f"Design direction, {style['label']}: {style['visual']}"]
    if frame_note:
        parts.append(frame_note)
    if _FOCUS_LINE.get((focus or "").strip().lower()):  # the shot style chosen for this variant
        parts.append(_FOCUS_LINE[focus.strip().lower()])
    casting = _casting_line(audience)
    if casting:
        parts.append(casting)
    if exact_text and not photo_only:
        zone = "top" if text_zone == "top" else "bottom"
        parts.append(
            "No text, letters, numbers or buttons anywhere on the image. Keep the "
            f"{zone} 40% of the frame as calm, plain, uncluttered space (soft background, no faces, no props) "
            "because the headline and button are added there afterwards; the main subject sits in the rest of the frame."
        )
    elif photo_only:
        # (no word "logo" here: the guard drops any sentence that has it, and the no-logo rule covers it)
        parts.append("No text, letters or numbers anywhere on the image; a clean photo only.")
    else:
        lines = [x for x in (_quoted("headline", headline), _quoted("supporting line", hook), _quoted("button reading", cta)) if x]
        if lines:
            parts.append(
                f"Typography: {style['typography']} The only words on the image, spelled exactly as written: "
                + "; ".join(lines)
                + ". No other readable words, numbers or labels anywhere; screens, signs, notepads and devices show only "
                "abstract shapes, charts and blocks of colour."
            )
        else:
            parts.append("No text, letters or numbers anywhere on the image.")
        if not cta:
            parts.append("No button or call-to-action on this image.")
    # Colours with a plain colour word, fonts described by what they look like (see ad_image_brand.py).
    # In exact mode the model draws no type, so only the colours matter to it (the app draws the fonts).
    no_type = photo_only or exact_text
    brand_line = brand_style_line(primary, secondary, font_heading, font_body, photo_only=no_type)
    if brand_line:
        parts.append(brand_line)
    parts.append(
        "Sharp, scroll-stopping, professionally art-directed."
        + ("" if no_type else " Text large, high-contrast and fully inside the frame.")
    )
    prompt = " ".join(parts) + NO_LOGO_SHORT
    return prompt, style["label"]


def info(label: str, prompt: str) -> dict[str, Any]:
    return {"design_style": label, "design_prompt_chars": len(prompt)}
