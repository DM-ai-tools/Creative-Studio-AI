"""Ad angle library — psychological approaches for image ad variants.

Based on the standalone ad-angle-library module. Used for catalog options,
ICP-driven variant planning, and AI angle suggestions.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# (id, label, use_when summary)
AD_ANGLE_CATALOG: list[tuple[str, str, str]] = [
    ("problem_agitate_solve", "Problem-Agitate-Solve", "ICP has clear frustration; leads/conversion"),
    ("ugc_style", "UGC-Style", "Low-trust category, younger audience, Reels/Stories"),
    ("pattern_interrupt", "Pattern Interrupt", "Crowded feed, stop the scroll, awareness"),
    ("social_proof", "Social Proof", "Consideration stage, risk-averse ICP"),
    ("founder_led", "Founder-Led", "Authenticity over polish; challenger brand"),
    ("before_after", "Before / After", "Visually demonstrable transformation"),
    ("testimonial", "Testimonial / Review", "Trust is the main objection"),
    ("offer_urgency", "Offer / Urgency", "Bottom-funnel; time-bound offer"),
    ("educational", "Educational / How-to", "Awareness; ICP doesn't know the problem yet"),
    ("myth_busting", "Myth Busting", "ICP holds a misconception blocking purchase"),
    ("curiosity_hook", "Curiosity Hook", "Cold audience; open loop only a click resolves"),
    ("pain_led", "Pain-Led Hook", "ICP actively suffering the problem right now"),
    ("fear_loss_aversion", "Fear / Loss Aversion", "Real consequence of inaction"),
    ("fomo_scarcity", "FOMO / Scarcity", "Genuine limitation; social exclusion angle"),
    ("contrarian", "Contrarian / Unpopular Opinion", "Saturated category; sophisticated ICP"),
    ("product_hero", "Product Hero / Catalog", "Product-alone retail; model name + bold headline on brand colors"),
]

VALID_ANGLE_IDS = frozenset(a[0] for a in AD_ANGLE_CATALOG)

# Alias map — external / UI ids → catalog ids
_ANGLE_ID_ALIASES: dict[str, str] = {
    "educational_howto": "educational",
    "testimonial_review": "testimonial",
    "pain_led_hook": "pain_led",
}


def normalize_angle_id(angle_id: str) -> str:
    """Map external angle ids onto catalog ids."""
    raw = (angle_id or "").strip().lower()
    if not raw:
        return ""
    mapped = _ANGLE_ID_ALIASES.get(raw, raw)
    return mapped if mapped in VALID_ANGLE_IDS else ""


def _normalize_angle_list(ids: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for aid in ids:
        nid = normalize_angle_id(aid)
        if nid and nid not in seen:
            seen.add(nid)
            out.append(nid)
    return out


# Industry → primary / secondary / blocked angle pools.
# Primary = preferred first. Secondary = fill only. Blocked = never suggest / assign.
INDUSTRY_ANGLE_POOLS: dict[str, dict[str, list[str]]] = {
    "professional_services": {
        "primary": _normalize_angle_list([
            "problem_agitate_solve", "social_proof", "educational_howto", "testimonial_review",
            "founder_led", "myth_busting", "pain_led_hook", "contrarian",
        ]),
        "secondary": _normalize_angle_list(["curiosity_hook", "fear_loss_aversion"]),
        "blocked": _normalize_angle_list([
            "fomo_scarcity", "ugc_style", "pattern_interrupt", "offer_urgency",
        ]),
    },
    "healthcare": {
        "primary": _normalize_angle_list([
            "educational_howto", "myth_busting", "problem_agitate_solve", "founder_led",
        ]),
        "secondary": _normalize_angle_list([
            "pain_led_hook", "social_proof", "curiosity_hook",
        ]),
        # AHPRA National Law s133 — testimonials and before/after restricted.
        "blocked": _normalize_angle_list([
            "before_after", "testimonial_review", "fear_loss_aversion", "fomo_scarcity",
            "offer_urgency", "ugc_style", "pattern_interrupt", "contrarian",
        ]),
    },
    "trade_services": {
        "primary": _normalize_angle_list([
            "before_after", "problem_agitate_solve", "pain_led_hook", "social_proof",
            "testimonial_review", "founder_led",
        ]),
        "secondary": _normalize_angle_list([
            "offer_urgency", "educational_howto", "ugc_style", "pattern_interrupt",
            "curiosity_hook", "myth_busting",
        ]),
        "blocked": _normalize_angle_list(["contrarian", "fomo_scarcity"]),
    },
    "ecommerce": {
        "primary": _normalize_angle_list([
            "before_after", "ugc_style", "social_proof", "offer_urgency", "fomo_scarcity",
            "curiosity_hook", "pattern_interrupt", "testimonial_review",
        ]),
        "secondary": _normalize_angle_list([
            "problem_agitate_solve", "educational_howto", "founder_led", "pain_led_hook",
        ]),
        "blocked": _normalize_angle_list(["contrarian", "fear_loss_aversion"]),
    },
    "wholesale": {
        "primary": _normalize_angle_list(["problem_agitate_solve", "social_proof"]),
        "secondary": _normalize_angle_list([
            "testimonial_review", "founder_led", "educational_howto", "offer_urgency",
            "pain_led_hook", "contrarian", "myth_busting", "fomo_scarcity",
        ]),
        "blocked": _normalize_angle_list([
            "ugc_style", "pattern_interrupt", "before_after", "curiosity_hook",
            "fear_loss_aversion",
        ]),
    },
    "retail": {
        "primary": _normalize_angle_list([
            "offer_urgency", "fomo_scarcity", "ugc_style", "social_proof",
        ]),
        "secondary": _normalize_angle_list([
            "before_after", "testimonial_review", "founder_led", "curiosity_hook",
            "pattern_interrupt",
        ]),
        "blocked": _normalize_angle_list([
            "contrarian", "fear_loss_aversion", "problem_agitate_solve",
            "educational_howto", "myth_busting",
        ]),
    },
    "fashion_retail": {
        "primary": _normalize_angle_list([
            "offer_urgency", "fomo_scarcity", "ugc_style", "social_proof",
        ]),
        "secondary": _normalize_angle_list([
            "pattern_interrupt", "curiosity_hook", "testimonial_review",
            "founder_led", "before_after",
        ]),
        "blocked": _normalize_angle_list([
            "contrarian", "fear_loss_aversion", "problem_agitate_solve",
            "educational_howto", "myth_busting",
        ]),
    },
}

_INDUSTRY_POOL_NOTES: dict[str, str] = {
    "healthcare": (
        "AHPRA National Law s133 — testimonials and before/after restricted; "
        "requires human approval gate. Never suggest blocked healthcare angles."
    ),
}


def resolve_industry_angle_key(*, industry: str = "", niche: str = "", campaign_name: str = "") -> str | None:
    """Map free-text industry/niche to an INDUSTRY_ANGLE_POOLS key."""
    hay = f"{industry} {niche} {campaign_name}".lower()

    # Healthcare / dental first (compliance-critical).
    if any(
        k in hay
        for k in (
            "healthcare", "health care", "dental", "dentist", "clinic", "medical",
            "orthodont", "physiotherap", "chiropract", "gp ", "doctor", "hospital",
            "ahpra", "allied health",
        )
    ):
        return "healthcare"

    if any(
        k in hay
        for k in (
            "trade", "tradie", "hvac", "air con", "aircon", "plumb", "electric",
            "builder", "building", "roof", "landscap", "garden", "lawn", "turf",
            "construction", "home improvement", "renovation", "heating", "cooling",
            "local / trades", "trade services",
        )
    ):
        return "trade_services"

    if any(k in hay for k in ("wholesale", "distributor", "distribution", "b2b supply")):
        return "wholesale"

    if any(k in hay for k in ("ecommerce", "e-commerce", "dtc", "online store", "shopify")):
        return "ecommerce"

    if any(k in hay for k in ("retail", "store", "shop", "boutique", "brick and mortar")):
        return "retail"

    if any(
        k in hay
        for k in (
            "fashion", "apparel", "clothing", "denim", "knitwear", "runway",
            "arrivals", "wardrobe", "jeans", "new season", "editorial fashion",
        )
    ):
        return "fashion_retail"

    if any(
        k in hay
        for k in (
            "professional", "pro services", "consult", "account", "legal", "lawyer",
            "solicitor", "advisory", "mortgage", "broker", "finance", "agency",
            "marketing", "saas", "software",
        )
    ):
        return "professional_services"

    return None


def industry_angle_pool(*, industry: str = "", niche: str = "", campaign_name: str = "") -> dict[str, Any] | None:
    key = resolve_industry_angle_key(industry=industry, niche=niche, campaign_name=campaign_name)
    if not key:
        return None
    pool = INDUSTRY_ANGLE_POOLS.get(key)
    if not pool:
        return None
    return {
        "primary": list(pool.get("primary") or []),
        "secondary": list(pool.get("secondary") or []),
        "blocked": list(pool.get("blocked") or []),
        "key": key,
        "note": _INDUSTRY_POOL_NOTES.get(key, ""),
    }


def filter_angles_by_industry(
    angles: list[str],
    *,
    industry: str = "",
    niche: str = "",
    campaign_name: str = "",
) -> list[str]:
    """Drop blocked industry angles; keep order otherwise."""
    pool = industry_angle_pool(industry=industry, niche=niche, campaign_name=campaign_name)
    blocked = set((pool or {}).get("blocked") or [])
    out: list[str] = []
    for aid in angles:
        nid = normalize_angle_id(aid) or aid
        if nid in VALID_ANGLE_IDS and nid not in blocked and nid not in out:
            out.append(nid)
    return out


def angles_from_industry_pool(
    *,
    industry: str = "",
    niche: str = "",
    campaign_name: str = "",
    count: int = 3,
) -> list[str]:
    """Prefer primary, then secondary — never blocked. Pads from catalog if needed."""
    n = max(1, min(20, count))
    pool = industry_angle_pool(industry=industry, niche=niche, campaign_name=campaign_name)
    if not pool:
        return []
    blocked = set(pool.get("blocked") or [])
    ordered = [a for a in (pool.get("primary") or []) if a not in blocked]
    for a in pool.get("secondary") or []:
        if a not in blocked and a not in ordered:
            ordered.append(a)
    if len(ordered) >= n:
        return ordered[:n]
    for aid, _, _ in AD_ANGLE_CATALOG:
        if aid not in blocked and aid not in ordered:
            ordered.append(aid)
        if len(ordered) >= n:
            break
    return ordered[:n]


OBJECTIVE_ANGLE_PRIORITY: dict[str, list[str]] = {
    "awareness": [
        "educational",
        "pattern_interrupt",
        "curiosity_hook",
        "myth_busting",
        "contrarian",
    ],
    "traffic": ["curiosity_hook", "pattern_interrupt", "educational", "pain_led"],
    "lead_generation": [
        "problem_agitate_solve",
        "pain_led",
        "social_proof",
        "founder_led",
        "fear_loss_aversion",
    ],
    "conversions": [
        "offer_urgency",
        "fomo_scarcity",
        "problem_agitate_solve",
        "pain_led",
        "testimonial",
    ],
    "add_to_cart": ["offer_urgency", "fomo_scarcity", "before_after", "social_proof"],
    "retention": ["social_proof", "founder_led", "testimonial"],
}

ANGLE_GUIDANCE: dict[str, str] = {
    "problem_agitate_solve": (
        "ONE full-bleed frame must carry all three beats with PROPS (not copy alone): "
        "(1) PROBLEM — the broken/painful niche object large in frame; "
        "(2) AGITATE — a second cue that makes inaction hurt (heat, cost, failed attempt, dodgy quotes); "
        "(3) SOLVE — the brand path arriving (honest quote, technician explaining, clear fix) — calm is secondary. "
        "Hook = sharp pain question. On-image: image_hook = problem/agitate; image_headline = solve. "
        "BANNED: solve-only scenes (calm person reading a clean quote with tiny niche object in the background)."
    ),
    "ugc_style": (
        "Candid phone-camera / documentary feel — slight grain, imperfect framing, authentic workplace. "
        "NOT polished studio stock. Subject feels real, mid-action."
    ),
    "pattern_interrupt": (
        "STOP-THE-SCROLL creative. Unexpected for this industry — not a normal meeting or smiling stock huddle. "
        "Odd camera angle, surprising prop metaphor, or confrontational viewer stare. "
        "Hook must be pattern-breaking (max 12 words). NEVER 'professional stock photography'."
    ),
    "social_proof": (
        "Credibility on screen: peers reacting, results vibe, trusted professional context (no fake logos). "
        "Hook references proof, demand, or what others are already doing. "
        "On-image copy + CTA must match: trust/results language → Book Free Quote / Book Free Consultation — "
        "never waitlist CTAs like Join the List."
    ),
    "founder_led": (
        "Authority / expert energy — confident subject, direct eye contact or decisive leadership. "
        "Hook sounds like a founder calling out the problem."
    ),
    "before_after": (
        "DENTAL-RESULTS STYLE comparison (any industry): SIDE-BY-SIDE dual state in ONE ad image. "
        "LEFT = BEFORE / problem (concerned expression + broken/neglected/painful props). "
        "RIGHT = AFTER / result (confident smile + transformed/solved props). "
        "Same person or same place. Stranger must read the transformation with text removed. "
        "Examples: braces model vs clear aligner; overgrown yard vs lush garden; hot failing AC vs cool new unit. "
        "BANNED: after-only lifestyle shot; tiny far-background 'before whisper'; pure social-proof peers."
    ),
    "testimonial": (
        "Word-of-mouth energy — someone recommending from lived experience; warm, believable, not staged pitch."
    ),
    "offer_urgency": (
        "Time-sensitive action energy — decisive posture, clear next step, urgency without spammy clutter."
    ),
    "educational": (
        "Teaching moment — whiteboard, checklist, explainer posture, helpful clarity; hook teaches one insight."
    ),
    "myth_busting": (
        "Call out a common false belief in the hook, then show the corrected reality in the scene."
    ),
    "curiosity_hook": (
        "Withhold the answer on purpose. Hook creates an open loop. "
        "Image shows partially obscured/teased element — mid-reveal, not satisfying."
    ),
    "pain_led": (
        "State the pain flatly without softening. Show the EXACT physical or situational pain "
        "for THIS niche — not generic worry, sadness, or office stress. For dental/medical: "
        "jaw wince, tooth sensitivity, x-ray, swollen cheek, clinic chair — stranger must name "
        "the treatment category from visuals alone. NO resolution or solution hint in this image."
    ),
    "fear_loss_aversion": (
        "Name what's at risk if nothing changes. Concrete consequence — real number, declining line, deadline. "
        "Warning tone, not melodrama."
    ),
    "fomo_scarcity": (
        "Social exclusion — others already acting, filling seats, group moving forward without viewer. "
        "Emotional center is 'you'll be left out', not just ticking clock."
    ),
    "contrarian": (
        "Take a stance against common category belief. Visual tension between accepted approach and brand approach. "
        "Crossed-out conventional wisdom or subject breaking from the group."
    ),
    "product_hero": (
        "PRODUCT-ALONE CATALOG AD (mandatory when product_focus=product_only): "
        "Simple premium retail layout like a bike/jewellery catalog ad — NO people, NO pain-story, NO before/after. "
        "Product fills 50–70% of frame on clean studio background with diagonal brand-color blocks (primary + white). "
        "Stacked bold headline in brand colors (2–3 short words per line, e.g. RIDE / WITH / STYLE). "
        "Product model name as a lower label bar in white bold sans on brand primary (e.g. NORCO SCENE VLT 2025). "
        "image_hook = product model name; image_headline = short feature or stacked headline line; offer/CTA optional pill. "
        "Brand Kit logo is composited in a white header strip in post — do not draw a fake wordmark. "
        "Use brand website colors and fonts — not random gold or generic stock."
    ),
}

_ANGLE_SELECTION_SYSTEM = """
You are an expert performance creative strategist for Australian digital ads.
Given campaign context and an ICP profile, recommend which ad angles (hook frameworks) to test.

Rules:
- Pick exactly VARIANT COUNT angles (or 2–5 if count unclear) from the ALLOWED LIST only (by id).
- Match angles to THIS exact INDUSTRY + NICHE + ICP — never industry alone.
- All industries use Australian English creative voice (catchy Aussie billboard — not flat US corporate).
- Trade Services is NOT one business: HVAC ≠ plumbing ≠ roofing ≠ artificial turf ≠ general landscaping.
  Pick different angle mixes for different niches. Do NOT default every trade niche to the same two angles.
- If an INDUSTRY ANGLE POOL is provided: stay inside PRIMARY + SECONDARY. NEVER pick BLOCKED.
  Within that pool, CHOICE is yours based on the niche story — niche hint packs are optional guidance only.
- Prefer variety — angles should test different psychological approaches for THIS niche.
- For finance / mortgage / home-loan niches: prefer pain_led, problem_agitate_solve,
  social_proof, educational, myth_busting, fear_loss_aversion, testimonial when allowed.
- For healthcare / dental: obey AHPRA constraints — never pick blocked angles.
- For conversion/lead campaigns with acute pain, include pain_led or problem_agitate_solve when they fit THIS niche.
- Never pick angles that contradict the ICP (e.g. fomo_scarcity without a real offer).
- In reasoning, name the niche and WHY each angle fits that niche (not generic "trade services").

Output ONLY valid JSON:
{
  "suggested_angles": ["angle_id_1", "angle_id_2"],
  "reasoning": "2-3 sentences explaining why these fit THIS industry + niche and ICP"
}
""".strip()


# Niche keyword packs → preferred angles (ordered). Used when LLM fails / for rules.
_NICHE_ANGLE_PACKS: list[tuple[tuple[str, ...], list[str]]] = [
    (
        (
            "mortgage",
            "home loan",
            "broker",
            "refinance",
            "first home",
            "property investor",
            "homebuyer",
            "lending",
            "loan approval",
        ),
        [
            "pain_led",
            "problem_agitate_solve",
            "social_proof",
            "educational",
            "myth_busting",
            "fear_loss_aversion",
            "testimonial",
        ],
    ),
    (
        ("lead gen", "lead generation", "leads", "appointment", "enquiry", "quote"),
        [
            "pain_led",
            "problem_agitate_solve",
            "social_proof",
            "offer_urgency",
            "fear_loss_aversion",
        ],
    ),
    # Specific dental niches BEFORE general dental.
    (
        ("root canal", "endodontic", "tooth pain", "toothache"),
        ["pain_led", "problem_agitate_solve", "educational", "myth_busting", "social_proof"],
    ),
    (
        ("dental implant", "dental implants", "implants", "missing tooth", "missing teeth"),
        ["pain_led", "problem_agitate_solve", "educational", "myth_busting", "social_proof", "founder_led"],
    ),
    (
        ("whitening", "teeth whitening", "bleaching"),
        ["myth_busting", "educational", "social_proof", "pain_led", "founder_led"],
    ),
    (
        (
            "dental",
            "dentist",
            "tooth",
            "teeth",
            "molar",
            "crown",
            "filling",
            "gum",
            "oral",
            "orthodont",
            "invisalign",
            "extraction",
        ),
        # Healthcare-safe defaults (before_after / testimonial blocked by AHPRA pool).
        ["educational", "myth_busting", "problem_agitate_solve", "pain_led", "social_proof", "founder_led"],
    ),
    (
        ("legal", "lawyer", "law firm", "solicitor"),
        ["fear_loss_aversion", "social_proof", "educational", "founder_led", "pain_led"],
    ),
    # --- Trade niches (specific BEFORE generic "trade") ---
    # Artificial turf BEFORE general landscaping (otherwise "turf"/"lawn" steal the wrong pack).
    (
        (
            "artificial turf",
            "synthetic turf",
            "fake grass",
            "artificial grass",
            "synthetic grass",
            "turf installation",
            "artificial lawn",
            "pet turf",
            "sports turf",
        ),
        [
            "before_after",
            "pain_led",
            "problem_agitate_solve",
            "social_proof",
            "myth_busting",
            "testimonial",
            "offer_urgency",
        ],
    ),
    (
        (
            "landscap", "landscape", "gardening", "garden design", "garden",
            "lawn", "turf", "backyard", "outdoor living", "entertaining area",
            "paving", "retaining wall", "mulch", "planting",
        ),
        [
            "before_after",
            "pain_led",
            "problem_agitate_solve",
            "social_proof",
            "testimonial",
            "founder_led",
            "offer_urgency",
        ],
    ),
    (
        (
            "hvac",
            "air con",
            "aircon",
            "air conditioning",
            "air conditioner",
            "split system",
            "ducted",
            "heating and cooling",
        ),
        [
            "before_after",
            "pain_led",
            "problem_agitate_solve",
            "social_proof",
            "testimonial",
            "offer_urgency",
        ],
    ),
    (
        ("roof", "roofing", "roofer", "skylight", "roof restoration", "re-roof"),
        [
            "before_after",
            "pain_led",
            "problem_agitate_solve",
            "social_proof",
            "testimonial",
            "founder_led",
        ],
    ),
    (
        ("plumb", "plumber", "blocked drain", "hot water", "burst pipe"),
        [
            "pain_led",
            "problem_agitate_solve",
            "social_proof",
            "testimonial",
            "before_after",
            "offer_urgency",
        ],
    ),
    (
        ("electric", "electrician", "switchboard", "electrical"),
        [
            "pain_led",
            "problem_agitate_solve",
            "social_proof",
            "testimonial",
            "founder_led",
            "offer_urgency",
        ],
    ),
    (
        (
            "trade",
            "tradie",
            "builder",
            "building",
            "hipages",
            "local / trades",
            "construction",
            "home improvement",
            "renovation",
        ),
        [
            "before_after",
            "pain_led",
            "problem_agitate_solve",
            "social_proof",
            "testimonial",
            "founder_led",
            "offer_urgency",
        ],
    ),
    (
        ("saas", "software", "b2b", "agency", "meta ads", "marketing"),
        [
            "problem_agitate_solve",
            "pain_led",
            "pattern_interrupt",
            "myth_busting",
            "social_proof",
            "contrarian",
        ],
    ),
]


def _match_niche_angle_pack(industry: str, niche: str, campaign_name: str) -> list[str]:
    """Return niche-specific preferred angles (ordered). Niche text weighted over industry."""
    # Prefer niche string alone first so "Landscaping" wins over generic "Trade services".
    niche_hay = f"{niche} {campaign_name}".lower().strip()
    industry_hay = f"{industry}".lower().strip()
    full_hay = f"{niche} {industry} {campaign_name}".lower()

    # Pass 1: match against niche / campaign only (most specific).
    if niche_hay:
        for keywords, angles in _NICHE_ANGLE_PACKS:
            if any(kw in niche_hay for kw in keywords):
                return list(angles)

    # Pass 2: full haystack (industry + niche).
    for keywords, angles in _NICHE_ANGLE_PACKS:
        if any(kw in full_hay for kw in keywords):
            return list(angles)

    # Pass 3: industry-only last resort.
    if industry_hay:
        for keywords, angles in _NICHE_ANGLE_PACKS:
            if any(kw in industry_hay for kw in keywords):
                return list(angles)
    return []


def ensure_must_have_niche_angles(
    angles: list[str],
    *,
    industry: str = "",
    niche: str = "",
    campaign_name: str = "",
) -> list[str]:
    """
    Soft cleanup only — NEVER hard-pin the same angles for every trade niche.

    Industry blocked list is the only hard rail. Niche-specific order comes from
    the LLM (or niche hint packs as fallback), not forced before_after/pain_led.
    """
    ind_pool = industry_angle_pool(industry=industry, niche=niche, campaign_name=campaign_name)
    blocked = set((ind_pool or {}).get("blocked") or [])

    out = [normalize_angle_id(a) or a for a in angles if (normalize_angle_id(a) or a) in VALID_ANGLE_IDS]
    out = [a for a in out if a not in blocked]
    seen: list[str] = []
    for a in out:
        if a not in seen:
            seen.append(a)
    return seen


def blend_industry_and_niche_angles(
    *,
    industry: str = "",
    niche: str = "",
    campaign_name: str = "",
    count: int = 5,
) -> list[str]:
    """
    Industry = hard rails (primary / secondary / blocked).
    Niche packs = soft reorder hint for rule fallback only (LLM decides when available).

    Different niches under the same industry MUST be able to surface different angles
    (turf ≠ HVAC ≠ plumbing). Do not hardcode the same two for all Trade Services.
    """
    n = max(1, min(20, count))
    ind = industry_angle_pool(industry=industry, niche=niche, campaign_name=campaign_name)
    niche_prefs = _match_niche_angle_pack(industry, niche, campaign_name)

    blocked: set[str] = set((ind or {}).get("blocked") or [])
    primary = [a for a in ((ind or {}).get("primary") or []) if a not in blocked]
    secondary = [a for a in ((ind or {}).get("secondary") or []) if a not in blocked]
    allowed = set(primary) | set(secondary)

    ordered: list[str] = []

    # 1) Niche prefs that are allowed by industry.
    for aid in niche_prefs:
        nid = normalize_angle_id(aid) or aid
        if nid in blocked:
            continue
        if ind and nid not in allowed:
            continue
        if nid in VALID_ANGLE_IDS and nid not in ordered:
            ordered.append(nid)

    # 2) Remaining industry primary / secondary (fill only — not forced first).
    for aid in primary + secondary:
        if aid not in ordered:
            ordered.append(aid)

    # 3) No industry pool → niche prefs + catalog.
    if not ind:
        for aid in niche_prefs:
            nid = normalize_angle_id(aid) or aid
            if nid in VALID_ANGLE_IDS and nid not in ordered:
                ordered.append(nid)
        for aid, _, _ in AD_ANGLE_CATALOG:
            if aid not in ordered:
                ordered.append(aid)
            if len(ordered) >= n:
                break

    # Soft cleanup (blocked only) — do NOT pin before_after/pain_led for every niche.
    return ensure_must_have_niche_angles(
        ordered[: max(n, 3)],
        industry=industry,
        niche=niche,
        campaign_name=campaign_name,
    )[:n]


def _niche_preferred_angles(industry: str, niche: str, campaign_name: str) -> list[str]:
    """Industry rails + niche reorder — never industry-alone."""
    blended = blend_industry_and_niche_angles(
        industry=industry, niche=niche, campaign_name=campaign_name, count=8
    )
    if blended:
        return blended
    return filter_angles_by_industry(
        _match_niche_angle_pack(industry, niche, campaign_name),
        industry=industry,
        niche=niche,
        campaign_name=campaign_name,
    )


def catalog_options() -> list[dict[str, str]]:
    return [{"id": aid, "label": label} for aid, label, _ in AD_ANGLE_CATALOG]


def label_for(angle_id: str) -> str:
    for aid, label, _ in AD_ANGLE_CATALOG:
        if aid == angle_id:
            return label
    return angle_id.replace("_", " ").title()


def default_angles_for_objective(
    objective_id: str,
    count: int,
    *,
    industry: str = "",
    niche: str = "",
    campaign_name: str = "",
) -> list[str]:
    """Rule-based defaults — industry rails + niche reorder, then objective fill."""
    n = max(1, min(20, count))
    blended = blend_industry_and_niche_angles(
        industry=industry, niche=niche, campaign_name=campaign_name, count=n
    )
    if blended:
        return blended[:n]

    key = (objective_id or "conversions").lower().strip()
    pool = OBJECTIVE_ANGLE_PRIORITY.get(key, OBJECTIVE_ANGLE_PRIORITY["conversions"])
    pool = filter_angles_by_industry(
        pool, industry=industry, niche=niche, campaign_name=campaign_name
    )
    if len(pool) >= n:
        return pool[:n]
    blocked = set(
        (industry_angle_pool(industry=industry, niche=niche, campaign_name=campaign_name) or {}).get(
            "blocked"
        )
        or []
    )
    extra = [a[0] for a in AD_ANGLE_CATALOG if a[0] not in pool and a[0] not in blocked]
    combined = pool + extra
    if not combined:
        combined = [a[0] for a in AD_ANGLE_CATALOG]
    return [combined[i % len(combined)] for i in range(n)]


def assign_angles_to_variants(
    selected: list[str] | None,
    variant_count: int,
    objective_id: str = "",
    *,
    industry: str = "",
    niche: str = "",
    campaign_name: str = "",
    product_focus: str = "",
) -> list[str]:
    """
    One angle per variant.

    If the user selected angles, those win 1:1 (no industry reshuffle).
    Example: 2 variants + [before_after, pain_led] → exactly those two slots.

    Product-alone catalog shots always use product_hero — no pain-led defaults.
    """
    # Keep angle assignments aligned with the app's variant cap.
    # If we cap at 20 here, carousel briefs with >20 cards will leave the
    # last cards without locked angles (LLM fills them), causing mixed results.
    count = max(1, min(100, int(variant_count or 1)))
    focus = (product_focus or "").strip().lower().replace("-", "_")
    if focus in {"product_only", "product_alone", "product_hero", "catalog", "solo"}:
        return ["product_hero"] * count
    # Preserve user order; normalize aliases; drop blocked only.
    raw = [normalize_angle_id(a) or a for a in (selected or []) if a]
    valid = filter_angles_by_industry(
        [a for a in raw if a in VALID_ANGLE_IDS],
        industry=industry,
        niche=niche,
        campaign_name=campaign_name,
    )
    if valid:
        # User picked angles — lock them to slots.
        # If fewer angles than variants, pad with complementary angles so each variant
        # gets a DIFFERENT visual framework (no "pain_led, pain_led, pain_led" repeats).
        if len(valid) < count:
            complement_pool = default_angles_for_objective(
                objective_id,
                count,
                industry=industry,
                niche=niche,
                campaign_name=campaign_name,
            )
            # Keep user choices first, then fill with non-repeating complements
            used = set(valid)
            extras = [a for a in complement_pool if a not in used]
            padded = valid + extras
            return [padded[i % len(padded)] for i in range(count)]
        return [valid[i % len(valid)] for i in range(count)]

    pool = default_angles_for_objective(
        objective_id,
        count,
        industry=industry,
        niche=niche,
        campaign_name=campaign_name,
    )
    return [pool[i % len(pool)] for i in range(count)]


def _icp_signals(icp_text: str) -> dict[str, bool]:
    hay = (icp_text or "").lower()
    return {
        "acute_pain": any(
            w in hay
            for w in (
                "frustrat",
                "pain",
                "leaking",
                "losing",
                "wasted",
                "overwhelm",
                "stuck",
                "struggling",
            )
        ),
        "trust_issue": any(w in hay for w in ("trust", "skeptic", "proof", "referral", "risk")),
        "awareness": any(w in hay for w in ("don't know", "unaware", "learning", "discover")),
        "urgency": any(w in hay for w in ("deadline", "limited", "this week", "running out")),
    }


def suggest_ad_angles_rule_based(
    *,
    objective_id: str = "",
    icp_text: str = "",
    campaign_name: str = "",
    industry: str = "",
    niche: str = "",
    variant_count: int = 2,
) -> dict[str, Any]:
    """Industry-pool + niche-aware fallback suggestions without LLM."""
    n = max(2, min(5, variant_count, 5))
    key = (objective_id or "conversions").lower().strip()
    hay = f"{industry} {niche} {campaign_name}".lower()
    # Mortgage / home-loan lead gen is lead_generation even if UI left Conversions selected.
    if key == "conversions" and any(
        w in hay for w in ("lead", "mortgage", "broker", "home loan", "enquiry", "appointment")
    ):
        key = "lead_generation"

    ind_pool = industry_angle_pool(industry=industry, niche=niche, campaign_name=campaign_name)
    blocked = set((ind_pool or {}).get("blocked") or [])
    niche_pool = _niche_preferred_angles(industry, niche, campaign_name)
    obj_pool = list(OBJECTIVE_ANGLE_PRIORITY.get(key, OBJECTIVE_ANGLE_PRIORITY["conversions"]))
    pool = niche_pool + [a for a in obj_pool if a not in niche_pool]
    pool = [a for a in pool if a not in blocked]

    signals = _icp_signals(icp_text)
    hay_full = f"{hay} {icp_text}".lower()

    def _can(aid: str) -> bool:
        return aid in VALID_ANGLE_IDS and aid not in blocked

    if signals["acute_pain"] and _can("pain_led") and "pain_led" not in pool:
        pool.insert(0, "pain_led")
    if signals["trust_issue"] and _can("social_proof") and "social_proof" not in pool[:n]:
        pool.insert(1, "social_proof")
    if signals["awareness"] and _can("educational") and "educational" not in pool[:n]:
        pool.insert(0, "educational")
    if signals["urgency"] or "free" in hay_full or "audit" in hay_full:
        if _can("offer_urgency") and "offer_urgency" not in pool[:n]:
            pool.insert(0, "offer_urgency")

    # Soft-demote FOMO for regulated / high-trust niches
    if any(w in hay for w in ("mortgage", "loan", "broker", "legal", "dental", "clinic")):
        pool = [a for a in pool if a != "fomo_scarcity"] + (
            ["fomo_scarcity"] if "fomo_scarcity" in pool and "fomo_scarcity" not in blocked else []
        )

    seen: list[str] = []
    for aid in pool:
        if aid in VALID_ANGLE_IDS and aid not in seen and aid not in blocked:
            seen.append(aid)
        if len(seen) >= n:
            break
    # Fill from industry secondary / primary if short.
    if len(seen) < n and ind_pool:
        for aid in (ind_pool.get("primary") or []) + (ind_pool.get("secondary") or []):
            if aid not in seen and aid not in blocked:
                seen.append(aid)
            if len(seen) >= n:
                break
    while len(seen) < n:
        for aid, _, _ in AD_ANGLE_CATALOG:
            if aid not in seen and aid not in blocked:
                seen.append(aid)
                break
        else:
            break
        if len(seen) >= n:
            break

    labels = [label_for(a) for a in seen[:n]]
    niche_label = (niche or campaign_name or industry or "this campaign").strip()
    industry_key = (ind_pool or {}).get("key") or "general"
    note = (ind_pool or {}).get("note") or ""
    reason_extra = f" {note}" if note else ""
    final = ensure_must_have_niche_angles(
        seen[:n],
        industry=industry,
        niche=niche,
        campaign_name=campaign_name,
    )[:n]
    labels = [label_for(a) for a in final]
    return {
        "suggested_angles": final,
        "reasoning": (
            f"For {niche_label} ({industry_key.replace('_', ' ')} / {key.replace('_', ' ')}), "
            f"these angles fit industry + niche: {', '.join(labels)}."
            f"{reason_extra}"
        ),
        "industry_pool_key": industry_key,
        "blocked_angles": sorted(blocked),
    }


def _parse_angle_json(raw: str) -> dict[str, Any] | None:
    """Parse LLM JSON even when wrapped in markdown or padded with prose."""
    text = (raw or "").strip()
    if not text:
        return None
    text = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


async def suggest_ad_angles(
    *,
    campaign_name: str,
    brand_name: str = "",
    industry: str = "",
    niche: str = "",
    objective_id: str = "",
    icp_text: str = "",
    variant_count: int = 2,
) -> dict[str, Any]:
    """AI-powered ad angle suggestions; falls back to niche-aware rules if LLM fails."""
    from app.services.icp_image_plan_service import build_icp_from_campaign

    # Prefer explicit industry+niche for ICP; campaign_name may already be "Industry — Niche".
    icp_seed = campaign_name
    if industry.strip() and niche.strip():
        icp_seed = f"{industry.strip()} — {niche.strip()}"
    elif niche.strip():
        icp_seed = niche.strip()

    icp = icp_text.strip() or await build_icp_from_campaign(
        campaign_name=icp_seed,
        brand_name=brand_name,
        industry=industry or niche,
        niche=niche,
        objective_id=objective_id,
    )

    fallback = suggest_ad_angles_rule_based(
        objective_id=objective_id,
        icp_text=icp,
        campaign_name=campaign_name,
        industry=industry,
        niche=niche,
        variant_count=variant_count,
    )
    fallback_out = {**fallback, "icp_text": icp, "source": "rules"}

    if not settings.OPENROUTER_API_KEY:
        return fallback_out

    niche_hint = _niche_preferred_angles(industry, niche, campaign_name)
    niche_only = _match_niche_angle_pack(industry, niche, campaign_name)
    niche_hint_line = (
        f"SOFT FALLBACK HINT (optional — do NOT copy blindly; judge THIS niche yourself): {', '.join(niche_hint)}"
        if niche_hint
        else "SOFT FALLBACK HINT: none — infer from industry + niche text"
    )
    niche_specific_line = (
        f"NICHE CONTEXT for '{niche or campaign_name}' (example angles that often fit, not mandatory): {', '.join(niche_only)}"
        if niche_only
        else f"NICHE CONTEXT: no pack for '{niche or '(blank)'}' — decide from niche text + ICP"
    )
    ind_pool = industry_angle_pool(industry=industry, niche=niche, campaign_name=campaign_name)
    if ind_pool:
        pool_lines = [
            f"INDUSTRY ANGLE POOL ({ind_pool.get('key')}) — hard rails only:",
            f"  ALLOWED PRIMARY: {', '.join(ind_pool.get('primary') or [])}",
            f"  ALLOWED SECONDARY: {', '.join(ind_pool.get('secondary') or [])}",
            f"  BLOCKED (never pick): {', '.join(ind_pool.get('blocked') or []) or '(none)'}",
            "RULE: Stay inside allowed angles. Pick the best mix for THIS niche — "
            "Trade Services niches differ (artificial turf ≠ HVAC ≠ plumbing ≠ roofing). "
            "Do NOT always return the same two angles for every trade niche.",
            f"Return exactly {max(2, min(5, int(variant_count or 2)))} angle ids.",
        ]
        if ind_pool.get("note"):
            pool_lines.append(f"  COMPLIANCE: {ind_pool['note']}")
        industry_pool_block = "\n".join(pool_lines)
        # Restrict ALLOWED list to non-blocked when we have a pool.
        blocked = set(ind_pool.get("blocked") or [])
        allowed_catalog = [
            (aid, label, use_when)
            for aid, label, use_when in AD_ANGLE_CATALOG
            if aid not in blocked
        ]
    else:
        industry_pool_block = "INDUSTRY ANGLE POOL: none mapped — use niche packs + full catalog carefully."
        allowed_catalog = list(AD_ANGLE_CATALOG)

    allowed = "\n".join(
        f"- {aid}: {label} — {use_when}"
        for aid, label, use_when in allowed_catalog
    )
    user_msg = "\n".join([
        f"CAMPAIGN: {campaign_name}",
        f"BRAND: {brand_name or 'Unknown'}",
        f"INDUSTRY: {industry or 'general'}",
        f"NICHE: {niche or '(not provided — infer from campaign)'}",
        f"OBJECTIVE: {objective_id or 'conversions'}",
        f"VARIANT COUNT: {variant_count}",
        niche_hint_line,
        niche_specific_line,
        "",
        industry_pool_block,
        "",
        "ALLOWED ANGLES (pick ids from this list only — blocked already removed):",
        allowed,
        "",
        "ICP PROFILE:",
        icp,
        "",
        "Explain in reasoning how each angle fits THIS exact niche "
        f"({niche or campaign_name}) inside industry ({industry or 'general'}).",
        'Return ONLY valid JSON: {"suggested_angles":["id1","id2"],"reasoning":"..."}',
    ])

    # Prefer script model (set in .env) — default haiku id is often empty/unavailable on OpenRouter.
    model = (
        settings.OPENROUTER_MODEL_CLAUDE_SCRIPT
        or settings.OPENROUTER_MODEL_CLAUDE
        or settings.OPENROUTER_MODEL_OPENAI
    )

    try:
        from app.services.image_prompt_service import _get_openrouter_client

        client = _get_openrouter_client()
        raw = ""
        for use_json_mode in (True, False):
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": _ANGLE_SELECTION_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                "max_tokens": 500,
                "temperature": 0.3,
            }
            if use_json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            try:
                response = client.chat.completions.create(**kwargs)
            except Exception as exc:
                logger.warning("suggest_ad_angles OpenRouter call failed (json_mode=%s): %s", use_json_mode, exc)
                continue
            choice = response.choices[0].message if response.choices else None
            raw = (getattr(choice, "content", None) or "").strip() if choice else ""
            if raw:
                break
            logger.warning(
                "suggest_ad_angles empty content from model=%s json_mode=%s finish=%s",
                model,
                use_json_mode,
                getattr(response.choices[0], "finish_reason", None) if response.choices else None,
            )

        data = _parse_angle_json(raw)
        if not data:
            logger.warning("suggest_ad_angles could not parse JSON (len=%s): %r", len(raw), raw[:200])
            return fallback_out

        angles = [
            a for a in (data.get("suggested_angles") or [])
            if isinstance(a, str) and (normalize_angle_id(a) or a in VALID_ANGLE_IDS)
        ]
        # Normalize aliases then strip industry-blocked.
        angles = filter_angles_by_industry(
            [normalize_angle_id(a) or a for a in angles],
            industry=industry,
            niche=niche,
            campaign_name=campaign_name,
        )
        # Niche must-haves (e.g. before_after for landscaping) — LLM cannot drop these.
        angles = ensure_must_have_niche_angles(
            angles,
            industry=industry,
            niche=niche,
            campaign_name=campaign_name,
        )
        if angles:
            return {
                "suggested_angles": angles[:5],
                "reasoning": str(data.get("reasoning") or fallback["reasoning"]).strip(),
                "icp_text": icp,
                "source": "ai",
                "industry_pool_key": (ind_pool or {}).get("key"),
                "blocked_angles": list((ind_pool or {}).get("blocked") or []),
            }
        logger.warning("suggest_ad_angles returned no valid angle ids: %s", data.get("suggested_angles"))
    except Exception:
        logger.exception("suggest_ad_angles LLM failed")

    return fallback_out


def angle_guidance_block(angle_id: str) -> str:
    tip = ANGLE_GUIDANCE.get(angle_id, "Apply this marketing angle clearly in hook + scene.")
    return f"{angle_id.upper().replace('_', ' ')}: {tip}"


def per_variant_angle_instructions(assignments: list[str]) -> str:
    if not assignments:
        return ""
    lines = ["VARIANT AD ANGLE ASSIGNMENTS (mandatory — one angle per variant):"]
    for i, aid in enumerate(assignments):
        lines.append(f"  Variant {i + 1}: {angle_guidance_block(aid)}")
    lines.append(
        "Each variant MUST use ONLY its assigned angle for hook voice and visual composition. "
        "Do not blend angles within a single variant."
    )
    return "\n".join(lines)
