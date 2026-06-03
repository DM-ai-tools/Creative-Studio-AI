"""Split campaign focus into separate themes for carousel panels (generic, not hardcoded)."""

from __future__ import annotations

import re
from typing import Any

# Split "Kitchen / Bathroom & Landscaping" or "A, B and C" into separate slide topics.
_THEME_SPLIT = re.compile(
    r"\s*/\s*|\s*\|\s*|,\s*(?=[A-Za-z0-9])|\s+&\s+|\s+\band\s+",
    re.IGNORECASE,
)


def parse_campaign_themes(campaign: str, brief: dict[str, Any] | None = None) -> list[str]:
    """
    Derive one or more slide topics from the brief campaign field.
    Uses slashes, commas, pipes, and "and" — no industry-specific rules.
    """
    sources: list[str] = []
    if campaign and str(campaign).strip():
        sources.append(str(campaign).strip())
    if brief:
        for key in ("carousel_themes", "slide_topics"):
            val = brief.get(key)
            if isinstance(val, list):
                sources.extend(str(v).strip() for v in val if str(v).strip())
        kb = brief.get("key_benefits")
        if isinstance(kb, dict):
            extra = kb.get("carousel_themes") or kb.get("slide_topics")
            if isinstance(extra, list):
                sources.extend(str(v).strip() for v in extra if str(v).strip())

    themes: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for part in _THEME_SPLIT.split(source):
            topic = re.sub(r"\s+", " ", part.strip())
            if len(topic) < 3:
                continue
            key = topic.lower()
            if key in seen:
                continue
            seen.add(key)
            themes.append(topic)

    if themes:
        return themes[:5]
    fallback = re.sub(r"\s+", " ", (campaign or "").strip())
    return [fallback] if fallback else ["our offer"]


def build_carousel_slides(
    themes: list[str],
    *,
    offer: str,
    cta: str,
    vertical_label: str,
) -> list[dict[str, str]]:
    """Per-panel copy; each slide headline matches only that panel's topic."""
    slides: list[dict[str, str]] = []
    shared_offer = offer.strip()
    for theme in themes:
        hook = shared_offer if shared_offer else f"Trusted {vertical_label} — {theme}"
        slides.append(
            {
                "theme": theme,
                "headline": theme,
                "hook": hook,
                "cta": cta,
            }
        )
    return slides
