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
]

VALID_ANGLE_IDS = frozenset(a[0] for a in AD_ANGLE_CATALOG)

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
        "Open on visible pain, heighten urgency in scene mood, then imply the calm solution. "
        "Hook is a sharp pain question; visual shows the stuck reality."
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
        "Hook references proof, demand, or what others are already doing."
    ),
    "founder_led": (
        "Authority / expert energy — confident subject, direct eye contact or decisive leadership. "
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
    "curiosity_hook": (
        "Withhold the answer on purpose. Hook creates an open loop. "
        "Image shows partially obscured/teased element — mid-reveal, not satisfying."
    ),
    "pain_led": (
        "State the pain flatly without softening. Rawest literal form — frustrated subject, declining graph, "
        "overwhelming workspace. NO resolution or solution hint in this image."
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
}

_ANGLE_SELECTION_SYSTEM = """
You are an expert performance creative strategist for Australian digital ads.
Given campaign context and an ICP profile, recommend which ad angles (hook frameworks) to test.

Rules:
- Pick 2–5 angles from the ALLOWED LIST only (by id).
- Match angles to the specific INDUSTRY + NICHE first, then objective and ICP.
- Prefer variety — angles should test different psychological approaches.
- For finance / mortgage / home-loan / lead-gen niches: prefer pain_led, problem_agitate_solve,
  social_proof, educational, myth_busting, fear_loss_aversion, testimonial.
  Avoid fomo_scarcity and hard offer_urgency unless there is a real time-bound offer.
- For conversion/lead campaigns with acute pain, include pain_led or problem_agitate_solve.
- For awareness, prefer educational, curiosity_hook, pattern_interrupt, myth_busting, contrarian.
- Never pick angles that contradict the ICP (e.g. fomo_scarcity without a real offer).
- In reasoning, explicitly mention the niche and WHY each angle fits that niche.

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
    (
        ("dental", "clinic", "patient", "dentist"),
        ["pain_led", "social_proof", "before_after", "testimonial", "educational"],
    ),
    (
        ("legal", "lawyer", "law firm", "solicitor"),
        ["fear_loss_aversion", "social_proof", "educational", "founder_led", "pain_led"],
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


def _niche_preferred_angles(industry: str, niche: str, campaign_name: str) -> list[str]:
    hay = f"{industry} {niche} {campaign_name}".lower()
    for keywords, angles in _NICHE_ANGLE_PACKS:
        if any(kw in hay for kw in keywords):
            return list(angles)
    return []


def catalog_options() -> list[dict[str, str]]:
    return [{"id": aid, "label": label} for aid, label, _ in AD_ANGLE_CATALOG]


def label_for(angle_id: str) -> str:
    for aid, label, _ in AD_ANGLE_CATALOG:
        if aid == angle_id:
            return label
    return angle_id.replace("_", " ").title()


def default_angles_for_objective(objective_id: str, count: int) -> list[str]:
    """Rule-based defaults when user selects no angles."""
    key = (objective_id or "conversions").lower().strip()
    pool = OBJECTIVE_ANGLE_PRIORITY.get(key, OBJECTIVE_ANGLE_PRIORITY["conversions"])
    n = max(1, min(20, count))
    if len(pool) >= n:
        return pool[:n]
    extra = [a[0] for a in AD_ANGLE_CATALOG if a[0] not in pool]
    combined = pool + extra
    return [combined[i % len(combined)] for i in range(n)]


def assign_angles_to_variants(
    selected: list[str] | None,
    variant_count: int,
    objective_id: str = "",
) -> list[str]:
    """One angle per variant — rotate through selected angles; auto-pick if none selected."""
    count = max(1, min(20, int(variant_count or 1)))
    valid = [a for a in (selected or []) if a in VALID_ANGLE_IDS]
    pool = valid if valid else default_angles_for_objective(objective_id, count)
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
    """Niche-aware fallback suggestions without LLM."""
    n = max(2, min(5, variant_count, 5))
    key = (objective_id or "conversions").lower().strip()
    hay = f"{industry} {niche} {campaign_name}".lower()
    # Mortgage / home-loan lead gen is lead_generation even if UI left Conversions selected.
    if key == "conversions" and any(
        w in hay for w in ("lead", "mortgage", "broker", "home loan", "enquiry", "appointment")
    ):
        key = "lead_generation"

    niche_pool = _niche_preferred_angles(industry, niche, campaign_name)
    obj_pool = list(OBJECTIVE_ANGLE_PRIORITY.get(key, OBJECTIVE_ANGLE_PRIORITY["conversions"]))
    pool = niche_pool + [a for a in obj_pool if a not in niche_pool]

    signals = _icp_signals(icp_text)
    hay_full = f"{hay} {icp_text}".lower()

    if signals["acute_pain"] and "pain_led" not in pool:
        pool.insert(0, "pain_led")
    if signals["trust_issue"] and "social_proof" not in pool[:n]:
        pool.insert(1, "social_proof")
    if signals["awareness"] and "educational" not in pool[:n]:
        pool.insert(0, "educational")
    if signals["urgency"] or "free" in hay_full or "audit" in hay_full:
        if "offer_urgency" not in pool[:n]:
            pool.insert(0, "offer_urgency")

    # Soft-demote FOMO for regulated / high-trust niches
    if any(w in hay for w in ("mortgage", "loan", "broker", "legal", "dental", "clinic")):
        pool = [a for a in pool if a != "fomo_scarcity"] + (
            ["fomo_scarcity"] if "fomo_scarcity" in pool else []
        )

    seen: list[str] = []
    for aid in pool:
        if aid in VALID_ANGLE_IDS and aid not in seen:
            seen.append(aid)
        if len(seen) >= n:
            break
    while len(seen) < n:
        for aid, _, _ in AD_ANGLE_CATALOG:
            if aid not in seen:
                seen.append(aid)
                break
        if len(seen) >= n:
            break

    labels = [label_for(a) for a in seen[:n]]
    niche_label = (niche or campaign_name or industry or "this campaign").strip()
    return {
        "suggested_angles": seen[:n],
        "reasoning": (
            f"For {niche_label} ({key.replace('_', ' ')}), "
            f"these angles fit the niche: {', '.join(labels)}. "
            "Pain, trust, and proof outperform FOMO for home-loan / lead-gen creatives."
            if niche_pool
            else (
                f"For a {key.replace('_', ' ')} campaign targeting this ICP, "
                f"these angles test different hooks: {', '.join(labels)}. "
                "Each variant will use one angle so you can compare what resonates."
            )
        ),
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
    niche_hint_line = (
        f"NICHE-FIT HINT (prefer these if they match): {', '.join(niche_hint)}"
        if niche_hint
        else "NICHE-FIT HINT: none — infer from industry + niche text"
    )

    allowed = "\n".join(
        f"- {aid}: {label} — {use_when}"
        for aid, label, use_when in AD_ANGLE_CATALOG
    )
    user_msg = "\n".join([
        f"CAMPAIGN: {campaign_name}",
        f"BRAND: {brand_name or 'Unknown'}",
        f"INDUSTRY: {industry or 'general'}",
        f"NICHE: {niche or '(not provided — infer from campaign)'}",
        f"OBJECTIVE: {objective_id or 'conversions'}",
        f"VARIANT COUNT: {variant_count}",
        niche_hint_line,
        "",
        "ALLOWED ANGLES (pick ids from this list only):",
        allowed,
        "",
        "ICP PROFILE:",
        icp,
        "",
        "Explain in reasoning how each angle fits this exact niche "
        f"({niche or campaign_name}).",
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
            if isinstance(a, str) and a in VALID_ANGLE_IDS
        ]
        if angles:
            return {
                "suggested_angles": angles[:5],
                "reasoning": str(data.get("reasoning") or fallback["reasoning"]).strip(),
                "icp_text": icp,
                "source": "ai",
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
