"""ICP-driven image variant planning from campaign name (+ brand / industry)."""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.services.australian_copy import AUSTRALIAN_ENGLISH_BRIEF_RULES
from app.services.image_prompt_service import (
    _SELECTOR_FALLBACK_USE_CASES,
    _USE_CASE_CATALOGUE,
    _USE_CASE_DESCRIPTIONS,
    _get_openrouter_client,
)

logger = logging.getLogger(__name__)

# Agency brand types (Brand Kit) — visuals should match the SERVICE sold (ads, leads, targeting),
# not random client-vertical stock scenes (e.g. warehouse for a Meta ads campaign).
_AGENCY_BRAND_INDUSTRIES = frozenset({
    "digital_marketing",
    "marketing",
    "general",  # generic agency default
    "pro_services",  # marketing / pro services agency in Brand Kit
})

# Scene pools — suggestions for variety, not hard bans. Laptop/coffee/notebook are fine when they fit.
_INDUSTRY_SCENE_POOLS: dict[str, list[str]] = {
    "digital_marketing": [
        "Marketing manager reviewing Meta Ads Manager on screen, frustrated by wasted spend, modern AU office",
        "Business owner scrolling Facebook feed on phone, noticing competitor ads, candid documentary moment",
        "Agency strategist and client at screen reviewing ad targeting map / audience breakdown",
        "Split focus: poor-performing ads dashboard vs relieved owner after fix — same person, different mood",
        "Creative director reviewing ad mockups on large monitor, performance metrics visible, team in background",
        "Small business owner on laptop in real workplace (warehouse office, shop back room, or home studio) checking lead form results — workplace matches ICP, screen shows ads/leads context",
    ],
    "wholesale": [
        "Wholesale warehouse aisle: ops manager with handheld scanner beside pallet racking, industrial daylight",
        "Loading dock: delivery truck check-off, clipboard and hi-vis vest",
        "Distribution centre: worker at pick slot while forklift moves in background",
        "Distributor back-office reviewing stock reports at desk with warehouse visible through window",
    ],
    "trade": [
        "Residential job site: tradie on ladder, tool belt and van visible",
        "Driveway service call: plumber under sink with client watching, natural daylight",
        "Commercial fit-out: electrician at switchboard, industrial interior",
        "Tradie between jobs in van checking phone for next lead, suburban AU street",
    ],
    "pro_services": [
        "Glass meeting room: advisor presenting strategy deck to clients, city view soft blur",
        "Professional at desk with client consultation, warm corporate light",
        "Whiteboard strategy session: framework sketched, collaborative mood",
        "Reception greeting client, trust and authority",
    ],
    "retail": [
        "Boutique shop floor: owner preparing display before weekend rush, warm pendant lights",
        "Saturday trade: staff at counter, customers browsing",
        "Manager carrying stock from back room to floor, energetic mood",
        "Shop window: passer-by pausing at display, inviting interior glow",
    ],
    "ecommerce": [
        "Home packing bench: branded boxes, shipping labels, hands packing order",
        "Garage studio: product samples and ring light, authentic DTC setup",
        "Founder at laptop reviewing online orders and ad performance side by side",
        "Courier pickup at front door: founder handing parcel to driver",
    ],
    "general": [
        "Documentary portrait: person in their real workplace solving the ICP pain — vary setting each variant",
        "Team huddle in authentic small-business workspace, candid AU commercial",
        "Over-shoulder whiteboard session circling one priority problem",
        "Environmental wide shot: subject small in frame, workplace context tells the story",
        "Morning light office: focused work moment with tools that fit the ICP (laptop, phone, or industry props as needed)",
    ],
}

_INDUSTRY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "digital_marketing": (
        "meta ads", "facebook ads", "instagram ads", "google ads", "ad targeting", "ad spend",
        "ppc", "paid social", "lead gen", "leads", "roas", "cac", "traffic", "digital marketing",
        "marketing agency", "ads audit", "campaign",
    ),
    "wholesale": ("wholesale", "distributor", "distribution", "dead stock", "inventory", "margin", "warehouse"),
    "trade": ("trade", "tradie", "plumb", "electric", "hvac", "builder", "roof", "construction"),
    "pro_services": ("consult", "account", "legal", "advisory", "dental", "clinic", "law firm"),
    "retail": ("retail", "store", "shop", "boutique", "foot traffic", "brick and mortar"),
    "ecommerce": ("ecommerce", "e-commerce", "dtc", "online store", "shopify", "unboxing"),
}

_VARIETY_GUIDANCE = """
- Vary scene, environment, props, lighting, and camera angle across variants — do NOT repeat the same setup.
- Do NOT use the exact same laptop + coffee + notebook composition in every variant; rotate settings.
- Laptop, coffee, notebook, and desk scenes ARE allowed when they genuinely fit the ICP and campaign.
- Pick visuals that match what is being SOLD: e.g. a digital marketing agency → ads, targeting, leads, performance.
- Client industry (wholesale, trade, etc.) informs WHO is in the scene; the brand service informs WHAT problem is shown.
""".strip()

_INDUSTRY_REFERENCE_ICPS = """
WHOLESALE — Margin Guardian:
Ops/purchasing manager, mid-size AU distributor. Pain: dead stock, missed fills, thin margins.
Visual: warehouse aisle, pallet racking, clipboard/tablet, industrial daylight.

TRADE — Booked-Out Tradie:
Owner-operator plumber/electric/HVAC, 1–8 staff. Pain: feast-or-famine leads, admin after hours.
Visual: residential job site, van with tools, tradie in workwear, golden-hour outdoor AU.

PROFESSIONAL SERVICES — Trust Builder:
Managing Partner (CPA) at a mid-tier accounting/advisory firm in Melbourne CBD with a satellite in Geelong. Decision power on marketing spend and partner alignment for a 6-month horizon.
Pain: referrals drying up, internal partner buy-in politics, competitors with stronger SEO/content and clearer Google Ads presence, plus fear of non-compliant or overly-salesy regulated marketing.
They need partner-ready proof (ROI, milestones, cost-per-client clarity) and an agency workflow that upskills the marketing coordinator instead of sidelining her.
Visual: modern Australian office, glass meeting room in warm morning light; managing partner presenting a partner-ready 90-day digital growth plan on a laptop/tablet; subtle blurred compliance/governance notes; monitor shows generic (non-readable) leads/pipeline/ROI charts; authentic tailored professional mood.

RETAIL — Floor Manager:
Specialty retail owner/manager. Pain: uneven foot traffic, discount dependency.
Visual: boutique floor, styled shelves, warm pendant lights, customer at counter.

ECOMMERCE — Cart Chaser:
DTC founder/marketing lead. Pain: creative fatigue, rising CAC.
Visual: home-studio unboxing, lifestyle product-in-use, crisp ecommerce aesthetic.

DIGITAL MARKETING AGENCY — Growth Partner:
Marketing manager or SMB owner. Pain: wasted ad spend, wrong targeting, leads going to competitors.
Visual: Meta/social ads context, dashboards, phone feed, targeting — NOT unrelated warehouse ops unless ads are the subject.
""".strip()

_ICP_FROM_CAMPAIGN_SYSTEM = f"""
You are an expert ICP strategist for AUSTRALIAN businesses.
Infer the ideal customer profile from the CAMPAIGN NAME and brand context only.
Do NOT require product, offer, or audience fields — infer from the campaign name.

Output plain text in this exact format (no markdown):

AVATAR NAME: <FirstName LastName — "Archetype Nickname">
IDENTITY: <2-3 sentences: role, company size, AU location, decision power>
CURRENT REALITY: <2-3 sentences: what is happening in their world right now>
CORE PAIN: <1-2 sentences: deepest frustration>
DESIRED OUTCOME: <1-2 sentences: what they want after the solution>
KEY OBJECTION: <1 sentence>
BUYING TRIGGER: <1 sentence>
LANGUAGE THEY USE: <3-5 short Australian phrases>

Match wholesale/trade/pro services/retail/ecommerce archetypes when the campaign name implies them.
Use Brand Kit industry as backup when the campaign name is vague.
{AUSTRALIAN_ENGLISH_BRIEF_RULES}
Plain text only — no bullets, no extra sections.
""".strip()

_VARIANTS_SYSTEM = """
You are a senior performance creative director for Australian digital ads.
Given an ICP profile and campaign context, produce DISTINCT image ad variants.

HALO framework per variant:
- Hook: scroll-stopping pain question or pattern interrupt (on-image hook text)
- Agitate: implied in the visual mood / scene
- Lift: solution world — calm control, proof, better state
- Offer: caption follow-up (NOT burned into the image) that sounds like your best copywriter (2–3 sentences)
- CTA: short on-image button text for THIS variant only (2–4 words)

Output ONLY valid JSON:
{
  "variants": [
    {
      "use_cases": ["id1"],
      "hook": "short on-image hook, max 12 words",
      "message": "on-image headline, max 14 words",
      "cta": "2-4 word button text unique to this variant",
      "offer": "caption follow-up in 2–3 sentences (what they’re thinking), do not include it in the image",
      "prompt": "full ad creative image prompt, one paragraph 120-260 words",
      "reasoning": "one sentence"
    }
  ]
}

Rules:
- Each variant MUST differ in scene, angle, hook, message, CTA, use cases, environment, props, and lighting.
- When AD STYLES / HOOK FRAMEWORKS are provided, they are MANDATORY — hooks AND visuals must clearly match them.
- If pattern_interrupt is selected: NEVER produce generic stock meeting/laptop huddle scenes; the image must feel unexpected and scroll-stopping; do NOT use the phrase "professional stock photography".
- use_cases: 1-3 ids from the catalogue only.
- prompt MUST describe: background photo, exact hook text placement, headline text placement, and CTA button with the variant's own CTA text.
- prompt MUST mention the selected ad style by name when frameworks are provided (e.g. "pattern interrupt stop-the-scroll commercial").
- IMPORTANT: DO NOT include the caption `offer` text in the image prompt. The image prompt should only burn hook + headline + the CTA button text.
- CTA RULES (critical):
  - Every variant MUST include its own `cta` field.
  - Prefer action CTAs matched to the campaign + ICP (e.g. Book Consultation, Get Free Audit, Claim Free Review, Start 90-Day Pilot, Book Free Quote).
  - Do NOT use "Learn More" unless the campaign is pure awareness with no conversion action.
  - If a CTA HINT is provided, treat it as optional guidance — still vary CTAs across variants when it improves the angle.
  - Never repeat the exact same CTA across all variants in one batch.
- Human subjects: sharp visible faces, Australian context.
- Single full-bleed photo — NO collage, NO split panels, NO watermarks.
- Australian English spelling in on-image text.
- Never use the ICP persona's first name on the image.

UNIQUENESS (critical):
- Follow the REQUIRED SCENE MANDATE for each variant as a starting point, then make it specific to the ICP.
- Match the visual to what the BRAND SELLS and who the ICP is — service context beats random industry stock imagery.
- Vary camera angle, time of day, interior vs exterior, and subject action across variants.
- Avoid repeating the same scene/prop combo across variants in one batch (e.g. do not generate three café-laptop shots).
- Laptop, coffee, notebook, and desk setups are fine when they fit the story — just do not use them every time by default.
""".strip()


@dataclass
class IcpImageVariantPlan:
    use_cases: list[str]
    hook: str
    message: str
    cta: str
    offer: str
    prompt: str
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "use_cases": self.use_cases,
            "hook": self.hook,
            "message": self.message,
            "cta": self.cta,
            "offer": self.offer,
            "prompt": self.prompt,
            "reasoning": self.reasoning,
        }


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, AttributeError):
        return None


def _clamp_prompt(prompt: str, max_len: int = 4000) -> str:
    prompt = (prompt or "").strip()
    if len(prompt) > max_len:
        return prompt[: max_len - 1] + "…"
    return prompt


def _valid_use_cases(ids: list[Any]) -> list[str]:
    return [uc for uc in (ids or []) if isinstance(uc, str) and uc in _USE_CASE_DESCRIPTIONS] or list(
        _SELECTOR_FALLBACK_USE_CASES
    )


def _derive_industry_bucket(*, campaign_name: str, industry: str, icp_text: str = "") -> str:
    """Map brand industry + campaign + ICP to a scene pool key."""
    ind = (industry or "").lower().strip()

    # Agency / digital marketing brand → visuals about ads, leads, targeting (the service sold).
    if ind in _AGENCY_BRAND_INDUSTRIES or "digital_marketing" in ind:
        return "digital_marketing"

    # Product / client brands: infer vertical from campaign + ICP text.
    haystack = f"{campaign_name} {icp_text}".lower()
    scores: dict[str, int] = {k: 0 for k in _INDUSTRY_SCENE_POOLS if k != "digital_marketing"}
    for bucket, keywords in _INDUSTRY_KEYWORDS.items():
        if bucket == "digital_marketing":
            continue
        for kw in keywords:
            if kw in haystack:
                scores[bucket] = scores.get(bucket, 0) + 1

    # Campaign explicitly about ads/traffic for any brand
    dm_score = sum(1 for kw in _INDUSTRY_KEYWORDS["digital_marketing"] if kw in haystack)
    if dm_score >= 2:
        return "digital_marketing"

    best = max(scores, key=lambda k: scores[k])
    if scores[best] > 0:
        return best

    if "retail" in ind or ind == "dtc":
        return "ecommerce" if "dtc" in ind else "retail"
    if "local" in ind or "construction" in ind:
        return "trade"
    if "saas" in ind:
        return "pro_services"
    return "general"


def _pick_scene_mandates(
    *,
    count: int,
    campaign_name: str,
    industry: str,
    icp_text: str = "",
    avoid_snippets: list[str] | None = None,
    hook_frameworks: list[str] | None = None,
) -> list[str]:
    """Pick distinct scene mandates; prefer industry pool, light backfill for variety."""
    frameworks = [f.lower().strip() for f in (hook_frameworks or []) if f]
    if "pattern_interrupt" in frameworks:
        pool = list(_PATTERN_INTERRUPT_SCENES) + list(
            _INDUSTRY_SCENE_POOLS.get("digital_marketing", _INDUSTRY_SCENE_POOLS["general"])
        )
        random.shuffle(pool)
        chosen: list[str] = []
        avoid = " ".join((avoid_snippets or [])).lower()
        for scene in pool:
            if len(chosen) >= count:
                break
            if scene.lower()[:48] in avoid or scene in chosen:
                continue
            chosen.append(f"PATTERN INTERRUPT: {scene}")
        while len(chosen) < count:
            extra = random.choice(_PATTERN_INTERRUPT_SCENES)
            chosen.append(f"PATTERN INTERRUPT: {extra} (distinct angle from prior)")
        return chosen[:count]

    bucket = _derive_industry_bucket(
        campaign_name=campaign_name,
        industry=industry,
        icp_text=icp_text,
    )
    primary = list(_INDUSTRY_SCENE_POOLS.get(bucket, _INDUSTRY_SCENE_POOLS["general"]))
    if bucket == "digital_marketing":
        secondary = list(_INDUSTRY_SCENE_POOLS["general"])
    else:
        secondary = [
            s
            for b, scenes in _INDUSTRY_SCENE_POOLS.items()
            if b not in (bucket, "digital_marketing")
            for s in scenes
        ]
    pool = primary + secondary
    random.shuffle(pool)

    avoid = " ".join((avoid_snippets or [])).lower()
    chosen: list[str] = []
    for scene in pool:
        if len(chosen) >= count:
            break
        scene_key = scene.lower()[:48]
        if scene_key in avoid:
            continue
        if scene in chosen:
            continue
        chosen.append(scene)

    while len(chosen) < count:
        extra = random.choice(_INDUSTRY_SCENE_POOLS.get(bucket, _INDUSTRY_SCENE_POOLS["general"]))
        if extra not in chosen:
            chosen.append(extra)
        else:
            chosen.append(
                f"Variant {len(chosen) + 1}: documentary AU commercial scene — "
                f"{extra} (distinct angle and props from prior variants)"
            )
    return chosen[:count]


async def build_icp_from_campaign(
    *,
    campaign_name: str,
    brand_name: str = "",
    industry: str = "",
) -> str:
    """Build ICP text from campaign name + brand (+ industry backup)."""
    if not settings.OPENROUTER_API_KEY:
        return (
            f'AVATAR NAME: Target Buyer — "The {campaign_name[:40]} Prospect"\n'
            f"IDENTITY: Australian business decision-maker evaluating {campaign_name}. "
            f"Brand context: {brand_name or 'local business'}.\n"
            f"CURRENT REALITY: Comparing options and looking for proof before committing.\n"
            f"CORE PAIN: Wasted spend and uncertainty about what will actually work.\n"
            f"DESIRED OUTCOME: A clear, trustworthy path to measurable results.\n"
            f'KEY OBJECTION: "I\'ve seen this before — show me it works for businesses like mine."\n'
            f"BUYING TRIGGER: A compelling ad that speaks directly to their current frustration.\n"
            f'LANGUAGE THEY USE: "Is this worth it?" | "Show me proof" | "How fast can we start?"'
        )

    user_content = "\n".join([
        f"CAMPAIGN NAME: {campaign_name}",
        f"BRAND: {brand_name or 'Not specified'}",
        f"BRAND KIT INDUSTRY (backup if name is vague): {industry or 'Not specified'}",
        "",
        "INDUSTRY REFERENCE ARCHETYPES (use when campaign name maps to one):",
        _INDUSTRY_REFERENCE_ICPS,
    ])

    try:
        client = _get_openrouter_client()
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL_CLAUDE_SCRIPT,
            messages=[
                {"role": "system", "content": _ICP_FROM_CAMPAIGN_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            max_tokens=900,
        )
        icp_text = (response.choices[0].message.content or "").strip()
        if len(icp_text) < 100:
            raise ValueError("ICP response too short")
        return icp_text
    except Exception:
        logger.exception("ICP-from-campaign failed — using fallback")
        return (
            f'AVATAR NAME: Buyer — "The Motivated Customer"\n'
            f"IDENTITY: Australian buyer interested in {campaign_name}. Brand: {brand_name}.\n"
            f"CURRENT REALITY: Actively comparing options.\n"
            f"CORE PAIN: Time and money wasted on solutions that underdeliver.\n"
            f"DESIRED OUTCOME: Fast, trustworthy results.\n"
            f'KEY OBJECTION: "Not sure this is the right fit."\n'
            f"BUYING TRIGGER: Cost of inaction becomes obvious.\n"
            f'LANGUAGE THEY USE: "Show me proof" | "How long does it take?"'
        )


def _fallback_cta_options(*, industry: str, cta_hint: str) -> list[str]:
    """Distinct action CTAs for fallback plans — avoid Learn More by default."""
    from app.services.cta_defaults import suggested_cta_for_industry

    hint = (cta_hint or "").strip()
    primary = hint if hint and hint.lower() not in {"learn more", "learnmore"} else suggested_cta_for_industry(
        industry or "general"
    )
    if primary.lower() in {"learn more", "learnmore"}:
        primary = "Get Free Quote"
    pool = [
        primary,
        "Book Consultation",
        "Get Free Audit",
        "Claim Free Review",
        "Start Free Pilot",
        "Book Free Quote",
        "Request Strategy Call",
        "Get Partner-Ready Plan",
    ]
    # Preserve order, drop duplicates (case-insensitive).
    seen: set[str] = set()
    out: list[str] = []
    for item in pool:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _fallback_variants(
    *,
    campaign_name: str,
    brand_name: str,
    industry: str,
    cta: str,
    offer_hint: str,
    image_aspect_ratio: str,
    variant_count: int,
    existing_hooks: list[str],
    scene_mandates: list[str] | None = None,
) -> list[IcpImageVariantPlan]:
    """Template variants when no API key."""
    brand = brand_name or "your brand"
    cta_options = _fallback_cta_options(industry=industry, cta_hint=cta)
    offer_base = offer_hint.strip() or f"{brand} — free review this week"
    variants: list[IcpImageVariantPlan] = []
    mandates = scene_mandates or _pick_scene_mandates(
        count=variant_count,
        campaign_name=campaign_name,
        industry=industry,
    )

    for i in range(variant_count):
        scene = mandates[i % len(mandates)]
        hook = f"Still struggling with {campaign_name[:30]}?"
        if hook in existing_hooks:
            hook = f"Is {campaign_name[:25]} costing you?"
        message = f"{brand} shows you exactly"
        cta_text = cta_options[i % len(cta_options)]
        offer = (
            f"{offer_base}. "
            f"You get clarity without the guesswork, so you can act with confidence — claim the next step now."
        )
        prompt = _clamp_prompt(
            f"Photoreal Australian commercial ad, {image_aspect_ratio}. "
            f"SCENE MANDATE: {scene}. Subject matches buyer for campaign '{campaign_name}'. "
            f'Bold hook text upper third: "{hook}". '
            f'Headline below: "{message}". '
            f'CTA button lower third: "{cta_text}". '
            f"Documentary commercial lighting, authentic non-stock feel, sharp visible faces."
        )
        variants.append(
            IcpImageVariantPlan(
                use_cases=["bs_real_life", "bs_emotional_appeal"][: 1 + (i % 2)],
                hook=hook,
                message=message,
                cta=cta_text,
                offer=offer,
                prompt=prompt,
                reasoning=f"Fallback variant {i + 1} from campaign name (no API key).",
            )
        )
    return variants


_HOOK_FRAMEWORK_GUIDANCE = {
    "problem_agitate_solve": (
        "Open on visible pain, heighten urgency in the scene mood, then imply the calm solution. "
        "Hook is a sharp pain question; visual shows the stuck reality."
    ),
    "ugc_style": (
        "Candid phone-camera / documentary feel — slight grain, imperfect framing, authentic workplace. "
        "NOT polished studio stock. Subject feels real, mid-action."
    ),
    "pattern_interrupt": (
        "STOP-THE-SCROLL creative. The visual MUST be unexpected for this industry — not a normal meeting, "
        "not a smiling stock huddle, not a polite laptop desk shot. Use one strong interrupt device: "
        "odd camera angle, surprising prop metaphor, empty chair / missing lead visual, crossed-out competitor ad, "
        "phone blowing up with notifications, broken pipeline metaphor, or a bold confrontation with the viewer. "
        "Hook must be a pattern-breaking question or shocking claim (max 12 words). "
        "NEVER write 'professional stock photography' — prefer bold commercial, high-contrast, scroll-stopping."
    ),
    "social_proof": (
        "Credibility on screen: peers reacting, results vibe, trusted professional context (no fake logos). "
        "Hook references proof, demand, or what others are already doing."
    ),
    "founder_led": (
        "Authority / expert energy — confident subject, direct eye contact or decisive workplace leadership. "
        "Hook sounds like a founder calling out the problem."
    ),
    "before_after": (
        "Contrast stuck-old-way vs improved-new-way in mood, props, or expression within ONE full-bleed frame "
        "(no split collage panels)."
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
}

_PATTERN_INTERRUPT_SCENES = [
    "Extreme close-up of a broker's phone exploding with competitor lead notifications — startled reaction, harsh phone glow",
    "Empty client chair in a mortgage office with a 'LOST LEAD' sticky note — cold daylight, unsettling quiet",
    "Over-shoulder shot of Facebook/Google ads for rival brokers filling the screen while subject looks defeated",
    "Dutch-tilt (tilted camera) of a broker mid-scroll, frozen by a shocking ad claim — high contrast, urgent mood",
    "Metaphor visual: leaking pipeline / funnel of leads spilling onto the floor of a modern AU office",
    "Subject staring straight into camera with a bold confronting expression — almost uncomfortable intimacy, scroll-stop",
]


def _style_enforcement_block(frameworks: list[str]) -> str:
    if not frameworks:
        return ""
    lines = [
        "STYLE ENFORCEMENT (mandatory — selected frameworks override generic stock scenes):",
    ]
    for fid in frameworks:
        tip = _HOOK_FRAMEWORK_GUIDANCE.get(fid)
        if tip:
            lines.append(f"- {fid.upper().replace('_', ' ')}: {tip}")
    if "pattern_interrupt" in frameworks:
        lines.extend(
            [
                "- BAN for pattern_interrupt: 'professional stock photography', smiling team huddle, "
                "generic glass meeting room with polite laptop review, soft corporate brochure lighting.",
                "- REQUIRE for pattern_interrupt: unusual angle OR unexpected prop/metaphor OR confrontational "
                "viewer stare OR competitive threat visible in-frame; hook must feel like a scroll-stop.",
                "- In each prompt, explicitly say the creative approach is pattern interrupt / stop-the-scroll "
                "(not stock photography).",
            ]
        )
    return "\n".join(lines)


async def generate_icp_image_plan(
    *,
    campaign_name: str,
    brand_name: str = "",
    industry: str = "",
    objective_id: str = "",
    cta: str = "",
    offer: str = "",
    image_aspect_ratio: str = "1:1",
    hook_frameworks: list[str] | None = None,
    variant_count: int = 1,
    existing_hooks: list[str] | None = None,
    existing_prompts: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build ICP from campaign name, then produce N distinct image variant plans.
    Returns { icp_text, variants: [{ use_cases, hook, message, prompt, reasoning }] }.
    """
    count = max(1, min(20, int(variant_count or 1)))
    hooks_avoid = [h.strip() for h in (existing_hooks or []) if h and h.strip()]
    prompts_avoid = [p.strip() for p in (existing_prompts or []) if p and p.strip()]
    frameworks = [f.strip() for f in (hook_frameworks or []) if f and str(f).strip()]
    framework_lines = []
    for fid in frameworks:
        tip = _HOOK_FRAMEWORK_GUIDANCE.get(fid, "Apply this marketing angle clearly in hook + scene.")
        framework_lines.append(f"- {fid}: {tip}")
    framework_block = (
        "\n".join(framework_lines)
        if framework_lines
        else "- (none selected) — vary styles naturally across variants using PAS, pattern interrupt, and social proof."
    )

    icp_text = await build_icp_from_campaign(
        campaign_name=campaign_name,
        brand_name=brand_name,
        industry=industry,
    )

    scene_mandates = _pick_scene_mandates(
        count=count,
        campaign_name=campaign_name,
        industry=industry,
        icp_text=icp_text,
        avoid_snippets=prompts_avoid,
        hook_frameworks=frameworks,
    )

    if not settings.OPENROUTER_API_KEY:
        variants = _fallback_variants(
            campaign_name=campaign_name,
            brand_name=brand_name,
            industry=industry,
            cta=cta,
            offer_hint=offer,
            image_aspect_ratio=image_aspect_ratio,
            variant_count=count,
            existing_hooks=hooks_avoid,
            scene_mandates=scene_mandates,
        )
        return {"icp_text": icp_text, "variants": [v.to_dict() for v in variants]}

    style_block = _style_enforcement_block(frameworks)
    user_msg = "\n".join([
        _USE_CASE_CATALOGUE,
        "",
        "---",
        f"CAMPAIGN NAME: {campaign_name}",
        f"BRAND: {brand_name or 'Unknown'}",
        f"BRAND KIT INDUSTRY: {industry or 'general'}",
        f"SCENE POOL: {_derive_industry_bucket(campaign_name=campaign_name, industry=industry, icp_text=icp_text)}",
        f"OBJECTIVE: {objective_id or 'conversions'}",
        f"CTA HINT (optional shared guidance — still invent a distinct CTA per variant): {cta or 'none — invent action CTAs from campaign + ICP'}",
        f"OFFER HINT (caption only — do NOT put in image): {offer or 'infer from ICP and campaign'}",
        f"ASPECT RATIO: {image_aspect_ratio}",
        f"VARIANT COUNT: {count}",
        "",
        "SELECTED AD STYLES / HOOK FRAMEWORKS (apply across the batch; rotate if multiple):",
        framework_block,
        "",
        *( [style_block, ""] if style_block else [] ),
        "VARIETY GUIDANCE:",
        _VARIETY_GUIDANCE,
        "",
        "ICP PROFILE:",
        icp_text,
        "",
        "SCENE STARTING POINT (one per variant — adapt to ICP; vary props and setting across variants):",
        *[f"  Variant {i + 1}: {scene_mandates[i]}" for i in range(count)],
        "",
        *(f"AVOID THESE HOOKS (already used): {h}" for h in hooks_avoid),
        *(f"AVOID REPEATING SCENES SIMILAR TO: {p[:120]}…" for p in prompts_avoid[:5]),
        "",
        f"Produce exactly {count} variant(s). Each must use HALO aligned to the ICP.",
        "Each variant needs its own action CTA on the image button — do not default every variant to Learn More.",
        "If pattern_interrupt is selected, every prompt must feel like a stop-the-scroll Pattern Interrupt — not stock photography.",
        "Mention brand naturally in headline where appropriate.",
    ])

    try:
        client = _get_openrouter_client()
        model = settings.OPENROUTER_MODEL_CLAUDE or settings.OPENROUTER_MODEL_CLAUDE_SCRIPT
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _VARIANTS_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=2800,
            temperature=0.97,
        )
        raw = (response.choices[0].message.content or "").strip()
        data = _parse_json_object(raw)
        raw_variants = (data or {}).get("variants") if data else None

        if isinstance(raw_variants, list) and raw_variants:
            variants: list[IcpImageVariantPlan] = []
            cta_fallbacks = _fallback_cta_options(industry=industry, cta_hint=cta)
            used_ctas: set[str] = set()
            for i, item in enumerate(raw_variants[:count]):
                if not isinstance(item, dict):
                    continue
                hook = str(item.get("hook") or "").strip()
                message = str(item.get("message") or "").strip()
                cta_line = str(item.get("cta") or "").strip()
                if not cta_line or cta_line.lower() in used_ctas:
                    for candidate in cta_fallbacks:
                        if candidate.lower() not in used_ctas:
                            cta_line = candidate
                            break
                    if not cta_line:
                        cta_line = cta_fallbacks[i % len(cta_fallbacks)]
                used_ctas.add(cta_line.lower())
                offer_line = str(item.get("offer") or offer or cta or "").strip()
                prompt = _clamp_prompt(str(item.get("prompt") or ""))
                if not hook or not message or not prompt:
                    continue
                # Ensure the prompt burns this variant's CTA (not a stale Learn More).
                if cta_line and cta_line.lower() not in prompt.lower():
                    prompt = _clamp_prompt(
                        f'{prompt.rstrip()} CTA button text must read exactly: "{cta_line}".'
                    )
                variants.append(
                    IcpImageVariantPlan(
                        use_cases=_valid_use_cases(item.get("use_cases")),
                        hook=hook,
                        message=message,
                        cta=cta_line,
                        offer=offer_line,
                        prompt=prompt,
                        reasoning=str(item.get("reasoning") or "").strip()
                        or f"ICP-driven variant {i + 1} for {campaign_name}.",
                    )
                )
            if variants:
                while len(variants) < count:
                    fb = _fallback_variants(
                        campaign_name=campaign_name,
                        brand_name=brand_name,
                        industry=industry,
                        cta=cta,
                        offer_hint=offer,
                        image_aspect_ratio=image_aspect_ratio,
                        variant_count=1,
                        existing_hooks=hooks_avoid + [v.hook for v in variants],
                        scene_mandates=[scene_mandates[len(variants) % len(scene_mandates)]],
                    )
                    variants.append(fb[0])
                return {
                    "icp_text": icp_text,
                    "variants": [v.to_dict() for v in variants[:count]],
                }

        logger.warning("ICP image plan LLM returned invalid JSON; using fallback variants")
    except Exception:
        logger.exception("generate_icp_image_plan LLM failed")

    variants = _fallback_variants(
        campaign_name=campaign_name,
        brand_name=brand_name,
        industry=industry,
        cta=cta,
        offer_hint=offer,
        image_aspect_ratio=image_aspect_ratio,
        variant_count=count,
        existing_hooks=hooks_avoid,
        scene_mandates=scene_mandates,
    )
    return {"icp_text": icp_text, "variants": [v.to_dict() for v in variants]}
