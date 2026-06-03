"""Distinct hook/headline helpers so ad copy and image prompts do not repeat the same phrase."""

from __future__ import annotations

import re

# Benefit-style hooks when the campaign title would duplicate the headline.
VERTICAL_HOOK_TEMPLATES: dict[str, str] = {
    "beauty": "Achieve a radiant, confident smile",
    "healthcare": "Professional care you can trust",
    "fitness": "Reach your goals with expert support",
    "hospitality": "Experience more — book today",
    "real_estate": "Find your perfect place faster",
    "property_management": "Stress-free property care",
    "retail": "Shop smarter, save more",
    "dtc": "Limited-time offer inside",
    "finance": "Compare options in minutes",
    "legal": "Clear advice when you need it",
    "education": "Learn with confidence",
    "food_beverage": "Taste the difference today",
    "automotive": "Drive away happy",
    "local": "Trusted by your neighborhood",
    "saas": "Work smarter, not harder",
    "pro_services": "Results you can measure",
    "construction": "Quality work, done right",
    "general": "See why customers choose us",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def texts_duplicate(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # "Teeth Whitening" vs "Teeth Whitening — Beauty"
    return na in nb or nb in na


def distinct_hook(
    *,
    campaign: str,
    headline: str,
    offer: str,
    vertical_id: str,
    vertical_label: str,
) -> str:
    """Return a hook line that must not repeat the headline / campaign title."""
    if offer and not texts_duplicate(offer, headline) and not texts_duplicate(offer, campaign):
        return offer.strip()

    template = VERTICAL_HOOK_TEMPLATES.get(vertical_id) or VERTICAL_HOOK_TEMPLATES["general"]
    if not texts_duplicate(template, headline) and not texts_duplicate(template, campaign):
        return template

    fallback = f"Trusted {vertical_label} specialists"
    if texts_duplicate(fallback, headline):
        return "Book your appointment today"
    return fallback


def build_headline(
    *,
    campaign: str,
    tone: str,
    vertical_label: str,
    theme: str | None = None,
) -> str:
    """Single primary title — one theme, or full campaign string if not split."""
    if theme:
        return theme.strip()
    tone = (tone or "professional").lower()
    tone_headlines = {
        "bold": f"{campaign}",
        "urgent": campaign,
        "casual": campaign,
        "warm": campaign,
        "professional": campaign,
    }
    return tone_headlines.get(tone, campaign)
