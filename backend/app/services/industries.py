"""Client vertical labels for brief-level target industry (not agency brand industry)."""

CLIENT_INDUSTRY_LABELS: dict[str, str] = {
    "real_estate": "Real Estate",
    "property_management": "Property Management",
    "hospitality": "Hospitality & Tourism",
    "healthcare": "Healthcare",
    "retail": "Retail & E-commerce",
    "dtc": "DTC E-commerce",
    "saas": "SaaS / B2B Tech",
    "local": "Local / Trades",
    "pro_services": "Professional Services",
    "automotive": "Automotive",
    "education": "Education",
    "fitness": "Fitness & Wellness",
    "finance": "Finance & Insurance",
    "legal": "Legal",
    "food_beverage": "Food & Beverage",
    "beauty": "Beauty & Personal Care",
    "construction": "Construction & Home Services",
    "digital_marketing": "Digital Marketing",
    "general": "General",
}


def resolve_target_industry(brief_dict: dict) -> tuple[str, str]:
    """Return (id, human label) for the client vertical this campaign promotes."""
    kb = brief_dict.get("key_benefits") or {}
    if not isinstance(kb, dict):
        kb = {}
    raw = (
        brief_dict.get("target_industry_id")
        or brief_dict.get("target_industry")
        or kb.get("target_industry_id")
        or kb.get("target_industry")
    )
    if not raw:
        return "general", CLIENT_INDUSTRY_LABELS["general"]
    key = str(raw).strip().lower()
    label = CLIENT_INDUSTRY_LABELS.get(key, key.replace("_", " ").title())
    return key, label
