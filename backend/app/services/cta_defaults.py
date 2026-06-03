"""Industry-appropriate default CTAs for Meta ad creatives."""

from __future__ import annotations

from app.services.industries import resolve_target_industry

# Default CTA label when the brief leaves a retail-style CTA on a service vertical.
INDUSTRY_DEFAULT_CTA: dict[str, str] = {
    "healthcare": "Book Appointment",
    "fitness": "Book Now",
    "legal": "Book Consultation",
    "finance": "Get Free Quote",
    "property_management": "Book Free Appraisal",
    "real_estate": "Book Inspection",
    "hospitality": "Book Now",
    "education": "Enroll Now",
    "beauty": "Book Appointment",
    "construction": "Get Free Quote",
    "local": "Book Now",
    "pro_services": "Book Consultation",
    "automotive": "Book Test Drive",
    "food_beverage": "Order Now",
    "retail": "Shop Now",
    "dtc": "Shop Now",
    "digital_marketing": "Learn More",
    "general": "Learn More",
}

RETAIL_CTAS = frozenset({"shop now", "shop", "buy now", "add to cart"})


def suggested_cta_for_industry(industry_id: str) -> str:
    key = (industry_id or "general").strip().lower()
    return INDUSTRY_DEFAULT_CTA.get(key, "Learn More")


def resolve_campaign_cta(brief: dict) -> str:
    """Use brief CTA, but replace generic retail CTAs on service industries."""
    explicit = str(brief.get("cta") or "").strip()
    kb = brief.get("key_benefits") or {}
    if isinstance(kb, dict):
        kb_cta = str(kb.get("cta_text") or "").strip()
        if kb_cta:
            explicit = kb_cta

    industry_id, _ = resolve_target_industry(brief)
    suggested = suggested_cta_for_industry(industry_id)

    if not explicit:
        return suggested
    if explicit.lower() in RETAIL_CTAS and industry_id not in {"retail", "dtc"}:
        return suggested
    return explicit
