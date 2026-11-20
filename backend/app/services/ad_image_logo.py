"""Logo placement for the brief's ad images (static ads and carousel cards).

Modes, chosen per campaign with an optional per-variant override:
  ""        the long-standing behaviour (white header strip, logo composited by the provider). Untouched.
  "auto"    the prompt leaves room in a corner the text does not use; after drawing, the app measures
            all four corners of the real picture and puts the logo in the cleanest one.
  corner    "top_left" | "top_right" | "bottom_left" | "bottom_right" | "top_center" | "bottom_center" | "center":
            the user's choice (Auto uses a corner, or a top/bottom centre strip when every corner is busy).
  "none"    no logo on the picture.

In every mode except "" the image model is told never to draw a logo or the brand's name, the brand's
name is taken out of the prompt, and the real logo file is placed afterwards (so it is never redrawn,
never misspelled, and never lands on the text). The light or dark version is chosen from the picture.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any

from app.services.creative_studio_still import NO_LOGO_RULE, NO_LOGO_SHORT, scrub_brand_name
from app.services.creative_studio_still_logo import (
    AUTO_ORDER,
    CORNER_LABELS,
    CORNERS,
    POSITIONS,
    corner_prompt_rule,
    place_logo_in_corner,
)

logger = logging.getLogger(__name__)

LEGACY, AUTO, NONE = "", "auto", "none"

_CORNER_RE = r"(top|upper|bottom|lower)[\s-]*(left|right)"
_TEXT_WORDS = r"(?:headline|hook|cta|call[\s-]to[\s-]action|button|offer|price|text|copy|title|badge|tagline|caption)"
_SENTENCE_SPLIT = re.compile(r"[.;\n]")


def normalize_mode(value: Any) -> str:
    """'' (old behaviour), 'auto', 'none', or one of the four corners. Anything unknown is ''."""
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_").replace("centre", "center")
    if text in {"auto", "none"}:
        return text
    if text in {"off", "no_logo"}:
        return NONE
    return text if text in POSITIONS else LEGACY


def resolve_mode(slot: Any, kb_models: dict | None, brief_dict: dict | None) -> str:
    """A variant's own choice wins; otherwise the campaign's. Reels and videos never use this
    (their logo is burned on the video later), so the caller only asks for still formats."""
    own = normalize_mode(slot.get("logo_corner")) if isinstance(slot, dict) else LEGACY
    if own:
        return own
    return normalize_mode((kb_models or {}).get("image_logo_corner") or (brief_dict or {}).get("image_logo_corner"))


def _corner_from_match(match: re.Match[str]) -> str:
    vertical = "top" if match.group(1).lower() in {"top", "upper"} else "bottom"
    return f"{vertical}_{match.group(2).lower()}"


def requested_corner(prompt: str) -> str:
    """A corner the prompt itself asks the logo to be in ("logo bottom right")."""
    for sentence in _SENTENCE_SPLIT.split(prompt or ""):
        if not re.search(r"(?i)\blogo\b", sentence):
            continue
        match = re.search(rf"(?i)\blogo\b[^,]{{0,60}}?\b{_CORNER_RE}\b", sentence) or re.search(
            rf"(?i)\b{_CORNER_RE}\b[^,]{{0,30}}?\blogo\b", sentence
        )
        if match:
            return _corner_from_match(match)
    return ""


def occupied_corners(prompt: str) -> set[str]:
    """Corners the prompt says carry text (headline, offer, CTA...). A sentence about the logo never counts."""
    taken: set[str] = set()
    for sentence in _SENTENCE_SPLIT.split(prompt or ""):
        if re.search(r"(?i)\blogo\b", sentence) or not re.search(rf"(?i)\b{_TEXT_WORDS}\b", sentence):
            continue
        found = False
        for match in re.finditer(rf"(?i)\b{_CORNER_RE}\b", sentence):
            taken.add(_corner_from_match(match))
            found = True
        if found:
            continue
        for edge in re.findall(r"(?i)\b(top|upper|bottom|lower)(?:\s+(?:third|edge|strip|bar|banner|area|half))?\b", sentence):
            vertical = "top" if edge.lower() in {"top", "upper"} else "bottom"
            taken.update({f"{vertical}_left", f"{vertical}_right"})
    return taken


# Every picture keeps a little breathing room at the top, so a headline never runs to the very edge and a
# logo can sit there when the user wants it at the top.
TOP_MARGIN_RULE = (
    " Layout margin: leave a slim blank band, about 6% of the picture's height, along the very top edge, "
    "with no text, numbers or artwork cut off in it. The headline and every other line start below that band, "
    "and nothing touches or is cropped by any edge."
)

_DESIGNER_SPOTS = ("top_left", "top_right", "top_center", "bottom_left", "bottom_right", "bottom_center")


def suggest_corner(prompt: str, seed: str = "", index: int = 0) -> str:
    """Where to keep room for the logo: the spot the prompt names, else a free one.

    Without a ``seed`` it is the first free corner (the old, fixed behaviour). With a seed (the campaign's
    id) each creative gets a different free spot, rotating through the corners and the top / bottom centre,
    the way a designer varies the logo from one piece to the next. A centre strip is only offered when the
    prompt puts no text on that edge, and the layout is then drawn around the chosen spot."""
    asked = requested_corner(prompt)
    if asked:
        return asked
    taken = occupied_corners(prompt)
    if seed:
        free = [
            spot
            for spot in _DESIGNER_SPOTS
            if (
                (spot.endswith("center") and not ({f"{spot.split('_')[0]}_left", f"{spot.split('_')[0]}_right"} & taken))
                or (not spot.endswith("center") and spot not in taken)
            )
        ]
        if free:
            start = int(hashlib.sha1(str(seed).encode("utf-8")).hexdigest()[:8], 16)
            return free[(start + int(index)) % len(free)]
    for corner in AUTO_ORDER:
        if corner not in taken:
            return corner
    return AUTO_ORDER[0]


_STRIP_SENTENCE = re.compile(r"[^.]*\bwhite\s+(?:header\s+|top\s+)?(?:strip|band)\b[^.]*\.?", re.IGNORECASE)
_BRAND_LOCK = re.compile(
    r"\s*BRAND IDENTITY LOCK:.*?(?:never appear as the store name\.|$)", re.IGNORECASE | re.DOTALL
)


_COPY_LINE = re.compile(
    r"(?im)^[ \t]*(?:main headline|subheadline|supporting text|benefit callouts|message|cta button):.*$"
)
_LOGO_SENTENCE = re.compile(r"(?i)\b(?:logos?|wordmarks?|brand[\s-]?marks?|branding|watermarks?)\b")


def _without_guard_text(text: str) -> str:
    """The prompt with our own guard sentences taken out, so they are added exactly once at the end."""
    for rule in (NO_LOGO_RULE, NO_LOGO_SHORT):
        text = text.replace(rule, " ").replace(rule.strip(), " ")
    return text


def guard_body(prompt: str, brand_name: str | None) -> str:
    """The prompt with everything removed that would make the model draw a logo or the brand's name.

    * the existing "BRAND IDENTITY LOCK", which asks for the brand's name to be lettered on the picture;
    * any sentence that mentions a logo, wordmark, brand mark, branding or watermark: a strategy file
      writes "Adoria logo bottom right", and the model obeys it. The real logo is placed afterwards
      from the Brand Kit, in the position chosen;
    * the brand's name, as the Brand Kit has it and as people shorten it.
    """
    text = _without_guard_text(prompt or "")
    # The user's own copy lines (headline, subheadline, callouts, message, CTA) are printed word for word,
    # even when a line contains the brand's name ("DISCOVER WATERUPS WICKING SYSTEMS"). Only the logo and a
    # stand-alone brand name are kept off the picture.
    kept: list[str] = []

    def _keep(match: re.Match[str]) -> str:
        kept.append(match.group(0).strip())
        return f" COPYLINE{len(kept) - 1}X "

    text = _COPY_LINE.sub(_keep, text)
    text = _BRAND_LOCK.sub(" ", text)
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    text = " ".join(s.strip() for s in sentences if s.strip() and not _LOGO_SENTENCE.search(s))
    text, _ = scrub_brand_name(text, brand_name)
    text = re.sub(r"\s{2,}", " ", text).strip()
    for index, line in enumerate(kept):
        text = text.replace(f"COPYLINE{index}X", line)
    return text


def guard_prompt(prompt: str, brand_name: str | None) -> str:
    """guard_body plus the one-line rule. For the old white-strip mode and every other mode alike."""
    return f"{guard_body(prompt, brand_name)}{NO_LOGO_SHORT}"


def prepare_prompt(
    prompt: str, mode: str, brand_name: str | None, seed: str = "", index: int = 0
) -> tuple[str, str]:
    """Final prompt for a mode other than the old one, plus the corner kept clear ('' for none).

    Also removes the white-strip instruction (the logo is no longer in a strip) on top of guard_body.
    """
    text = _STRIP_SENTENCE.sub("", _without_guard_text(prompt or ""))
    corner = ""
    if mode == AUTO:
        corner = suggest_corner(text, seed, index)
    elif mode in POSITIONS:
        corner = mode
    body = guard_body(text, brand_name)
    rule = corner_prompt_rule(corner) if corner else ""
    return f"{body}{TOP_MARGIN_RULE}{rule}{NO_LOGO_SHORT}", corner


async def apply_mode(
    image_result: Any,
    *,
    mode: str,
    suggested: str,
    tenant_id: str,
    logo_url: str | None,
    logo_on_light_url: str | None,
) -> Any:
    """Put the real logo on the finished picture (or note that none was wanted). Never fails the
    image: if the logo cannot be placed, the plain picture is kept and the reason is recorded."""
    if mode == LEGACY or not isinstance(image_result, dict):
        return image_result
    result = image_result
    if mode == NONE:
        return {**result, "logo_applied": False, "logo_corner": NONE}
    url = str(result.get("url") or "")
    if result.get("status") not in {"done", "mock"} or not url.startswith("/files/"):
        return result
    if not logo_url:
        logger.warning("Ad image logo: no usable Brand Kit logo, picture left without one")
        return {**result, "logo_applied": False, "warnings": [*(result.get("warnings") or []), "No Brand Kit logo found, so none was added. Upload a PNG or JPG logo in the Brand Kit."]}
    try:
        placed = await asyncio.to_thread(
            place_logo_in_corner,
            image_url=url,
            corner=AUTO if mode == AUTO else mode,
            tenant_id=tenant_id,
            logo_url=logo_url,
            logo_on_light_url=logo_on_light_url,
            suggested=suggested or None,
            avoid_text=False,  # a spot the user chose is used exactly; only Auto picks by itself
        )
    except Exception as exc:  # noqa: BLE001 - a logo problem must not lose a paid picture
        logger.exception("Ad image logo placement failed")
        return {**result, "logo_applied": False, "warnings": [*(result.get("warnings") or []), f"The logo could not be added: {exc}"]}
    return {
        **result,
        "url": placed["url"],
        "url_without_logo": url,
        "logo_applied": True,
        "logo_corner": placed["corner"],
        "logo_corner_label": CORNER_LABELS[placed["corner"]],
        "logo_auto": placed["auto"],
        "logo_background": placed["background"],
        "logo_version": placed["logo_version"],
        "warnings": [*(result.get("warnings") or []), *placed["warnings"]],
    }
