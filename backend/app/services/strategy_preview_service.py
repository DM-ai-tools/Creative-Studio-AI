"""Build a manager-ready creative strategy preview: ICP, HALO, hooks, body, competitors."""

from __future__ import annotations

import json
import logging
import re

from app.core.config import settings
from app.schemas.avatar_script import IcpScriptRequest
from app.services.avatar_script_service import _strip_json_fence
from app.services.icp_service import build_icp_profile
from app.services.website_script_service import choose_framework

logger = logging.getLogger(__name__)

HOOK_FRAMEWORK_LABELS: dict[str, str] = {
    "problem_agitate_solve": "Problem-Agitate-Solve",
    "ugc_style": "UGC-Style",
    "pattern_interrupt": "Pattern Interrupt",
    "social_proof": "Social Proof",
    "founder_led": "Founder-Led",
}


def _parse_icp_fields(icp_text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current_key = None
    buf: list[str] = []
    for line in icp_text.splitlines():
        if ":" in line and line.split(":", 1)[0].strip().isupper():
            if current_key:
                fields[current_key] = " ".join(buf).strip()
            current_key = line.split(":", 1)[0].strip()
            buf = [line.split(":", 1)[1].strip()]
        elif current_key:
            buf.append(line.strip())
    if current_key:
        fields[current_key] = " ".join(buf).strip()
    return fields


def _fallback_strategy(
    *,
    icp_text: str,
    framework: dict,
    brand_name: str,
    offer: str,
    hook_frameworks: list[str],
    competitors: list[str],
) -> dict:
    fw_labels = [HOOK_FRAMEWORK_LABELS.get(h, h) for h in hook_frameworks]
    comp_line = (
        f"Position {brand_name} as the clearer, faster alternative to "
        f"{', '.join(competitors[:3])} — proof-led and outcome-focused."
        if competitors
        else f"Differentiate {brand_name} with a specific, measurable outcome vs generic {offer or 'solutions'}."
    )
    return {
        "hook_options": [
            f"Still invisible online while competitors take your customers?",
            offer or f"What if {brand_name} could change that this week?",
            f"Here's why {brand_name} is different — and why it matters now.",
        ],
        "body_outline": [
            {"section": step, "duration_hint": "", "talking_points": ""}
            for step in framework.get("structure", [])
        ],
        "halo_strategy": {
            "hook": "Open with a pattern-interrupt question tied to core pain.",
            "agitate": "Deepen cost of inaction using ICP language.",
            "lift": f"Introduce {brand_name} as the credible path with proof.",
            "offer": offer or "Clear CTA with low-friction next step.",
        },
        "competitor_positioning": comp_line,
        "differentiation_points": [
            f"Outcome-focused vs feature-led competitors",
            f"Built for the ICP's buying trigger",
            f"Tone: {', '.join(fw_labels) if fw_labels else 'direct response'}",
        ],
    }


async def generate_strategy_preview(
    *,
    campaign_name: str,
    brand_name: str,
    product_name: str,
    offer: str,
    target_audience: str,
    ad_copy_tone: str,
    cta: str,
    target_seconds: int,
    hook_frameworks: list[str],
    competitors: list[str],
    objective: str,
    placements: list[str],
    formats: list[str],
    website_url: str = "",
) -> dict:
    """Return structured strategy preview for UI + Excel export."""
    framework = choose_framework(target_seconds)
    fw_labels = [HOOK_FRAMEWORK_LABELS.get(h, h) for h in hook_frameworks if h]

    icp_req = IcpScriptRequest(
        target_audience=target_audience,
        offer=offer,
        product_name=product_name,
        brand_name=brand_name,
        ad_copy_tone=ad_copy_tone,
        cta=cta,
        target_seconds=target_seconds,
    )
    icp_text = await build_icp_profile(icp_req)
    icp_fields = _parse_icp_fields(icp_text)

    strategy_data = _fallback_strategy(
        icp_text=icp_text,
        framework=framework,
        brand_name=brand_name,
        offer=offer,
        hook_frameworks=hook_frameworks,
        competitors=competitors,
    )

    if settings.OPENROUTER_API_KEY:
        from app.services.ai_service import ai_service

        system = """You are a senior performance creative strategist.
Return ONLY valid JSON with these exact keys:
{
  "hook_options": ["hook line 1", "hook line 2", "hook line 3"],
  "body_outline": [
    {"section": "SECTION NAME", "duration_hint": "0:00-0:30", "talking_points": "2-3 bullet ideas as one string"}
  ],
  "halo_strategy": {
    "hook": "H — attention grabber (1-2 sentences)",
    "agitate": "A — agitate pain using ICP language (1-2 sentences)",
    "lift": "L — lift / solution + brand differentiation (1-2 sentences)",
    "offer": "O — offer + CTA urgency (1-2 sentences)"
  },
  "competitor_positioning": "1 paragraph on how to position vs competitors",
  "differentiation_points": ["point 1", "point 2", "point 3"]
}
Rules:
- hook_options: 3 distinct scroll-stopping spoken hooks (max 20 words each)
- body_outline: one entry per framework section provided; talking_points must be specific to ICP
- halo_strategy: HALO = Hook, Agitate, Lift, Offer — align with ICP pain/desire
- competitor_positioning: if no competitors listed, position vs category/status quo
- Mention brand name naturally in lift and offer
- Never use the ICP persona's first name to address the viewer
- Plain strings only, no markdown"""

        user_bits = [
            f"Campaign: {campaign_name}",
            f"Brand: {brand_name}",
            f"Product: {product_name}",
            f"Offer: {offer}",
            f"Audience: {target_audience}",
            f"Tone: {ad_copy_tone}",
            f"CTA: {cta}",
            f"Objective: {objective}",
            f"Duration: {target_seconds}s",
            f"Script framework: {framework['name']} — sections: {', '.join(framework['structure'])}",
            f"Selected hook frameworks: {', '.join(fw_labels) if fw_labels else 'auto'}",
            f"Competitors: {', '.join(competitors) if competitors else 'not specified — use category'}",
            f"Placements: {', '.join(placements)}",
            f"Formats: {', '.join(formats)}",
            f"Website URL: {website_url or 'n/a'}",
            "",
            "ICP PROFILE:",
            icp_text,
        ]

        try:
            client = ai_service._get_client()
            response = client.chat.completions.create(
                model=settings.OPENROUTER_MODEL_CLAUDE_SCRIPT,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": "\n".join(user_bits)},
                ],
                max_tokens=2000,
            )
            raw = _strip_json_fence(response.choices[0].message.content or "")
            parsed = json.loads(raw)
            for key in ("hook_options", "body_outline", "halo_strategy", "competitor_positioning", "differentiation_points"):
                if parsed.get(key):
                    strategy_data[key] = parsed[key]
        except Exception:
            logger.exception("Strategy preview LLM failed — using fallback")

    halo = strategy_data.get("halo_strategy") or {}
    if isinstance(halo, dict):
        strategy_data["halo_strategy"] = {
            "hook": str(halo.get("hook", "")),
            "agitate": str(halo.get("agitate", "")),
            "lift": str(halo.get("lift", "")),
            "offer": str(halo.get("offer", "")),
        }

    outline = strategy_data.get("body_outline") or []
    normalized_outline = []
    for item in outline:
        if isinstance(item, dict):
            normalized_outline.append({
                "section": str(item.get("section", "")),
                "duration_hint": str(item.get("duration_hint", "")),
                "talking_points": str(item.get("talking_points", "")),
            })
    strategy_data["body_outline"] = normalized_outline

    strategy_data["hook_options"] = [str(h) for h in (strategy_data.get("hook_options") or [])[:3]]
    strategy_data["differentiation_points"] = [
        str(p) for p in (strategy_data.get("differentiation_points") or [])
    ]

    return {
        "campaign_name": campaign_name,
        "brand_name": brand_name,
        "product_name": product_name,
        "offer": offer,
        "target_audience": target_audience,
        "ad_copy_tone": ad_copy_tone,
        "cta": cta,
        "target_seconds": target_seconds,
        "objective": objective,
        "hook_frameworks": fw_labels,
        "competitors": competitors,
        "website_url": website_url,
        "framework_name": framework["name"],
        "framework_description": framework["description"],
        "framework_structure": framework["structure"],
        "icp_text": icp_text,
        "icp_fields": icp_fields,
        **strategy_data,
    }
