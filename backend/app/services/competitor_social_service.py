"""Fetch competitor social posts (SociaVault) and extract posting STRATEGY for image prompts.

Competitor insights are stored separately from the client's social_style_profile.
They inform content structure, hooks, and formats — never competitor brand colors/logos.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.services.image_prompt_service import _get_openrouter_client
from app.services.social_style_service import (
    _first_str,
    fetch_social_feed_posts,
)
from app.services.sociavault_client import parse_social_input

logger = logging.getLogger(__name__)


def empty_competitor_insight() -> dict[str, Any]:
    return {
        "platform": "",
        "handle": "",
        "profile_url": "",
        "fetched_at": "",
        "provider": "sociavault",
        "post_count_analyzed": 0,
        "content_mix": {},
        "hook_patterns": [],
        "format_patterns": [],
        "posting_logic": "",
        "caption_tone": "",
        "prompt_guidance": "",
        "post_summaries": [],
    }


def _competitor_key(platform: str, handle: str) -> str:
    return f"{(platform or '').strip().lower()}:{(handle or '').strip().lower().lstrip('@')}"


def normalize_competitor_insights(raw: Any) -> list[dict[str, Any]]:
    """Coerce stored value to a list of insight dicts."""
    if not raw:
        return []
    if isinstance(raw, dict):
        return [raw] if raw.get("handle") or raw.get("platform") else []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict) and (item.get("handle") or item.get("platform"))]
    return []


async def _analyze_competitor_posts_with_llm(
    *,
    platform: str,
    handle: str,
    posts: list[dict[str, Any]],
    profile: dict[str, Any],
    industry: str = "",
    niche: str = "",
) -> dict[str, Any]:
    """LLM extracts posting STRATEGY — not visual brand identity."""
    if not settings.OPENROUTER_API_KEY:
        return _heuristic_competitor_insight(posts, platform=platform, handle=handle)

    bio = _first_str(
        profile.get("biography"),
        profile.get("bio"),
        profile.get("about"),
        profile.get("description"),
    )
    summaries = []
    for i, p in enumerate(posts[:24], start=1):
        summaries.append(
            f"Post {i} ({p.get('kind')}): caption={(p.get('caption') or '')[:350]} | "
            f"likes={p.get('likes') or '?'}"
        )

    system = (
        "You analyze a COMPETITOR's public social media feed to guide OUR client's ad image planning. "
        "Extract POSTING STRATEGY only — NOT their brand colors, fonts, logos, or visual identity. "
        "Return ONLY valid JSON:\n"
        "{"
        '"content_mix": {"product": 0, "lifestyle": 0, "promo": 0, "testimonial": 0, "educational": 0, "other": 0},'
        '"hook_patterns": ["pain_led", "before_after", "social_proof", "offer_led", "..."],'
        '"format_patterns": ["static_hero", "carousel_story", "quote_card", "..."],'
        '"posting_logic": "1-2 sentences describing their story arc across posts",'
        '"caption_tone": "short description of caption voice",'
        '"prompt_guidance": "2-4 sentences telling how OUR ads should borrow their CONTENT STRUCTURE '
        '(angles, hooks, proof beats, carousel flow) while using OUR brand look — never copy their colors/logo",'
        '"post_summaries": ["short pattern note per post"]'
        "}"
    )
    user = (
        f"Competitor: @{handle} on {platform}\n"
        f"Industry context: {industry or 'general'} / {niche or 'not specified'}\n"
        f"Bio: {bio or '—'}\n\n"
        f"POSTS ({len(posts)}):\n" + "\n".join(summaries)
    )

    try:
        client = _get_openrouter_client()
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL_CLAUDE or settings.OPENROUTER_MODEL_CLAUDE_SCRIPT,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.35,
            max_tokens=1600,
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("LLM returned non-object JSON")
        return data
    except Exception:
        logger.exception("Competitor social LLM analysis failed — using heuristic")
        return _heuristic_competitor_insight(posts, platform=platform, handle=handle)


def _heuristic_competitor_insight(
    posts: list[dict[str, Any]],
    *,
    platform: str,
    handle: str,
) -> dict[str, Any]:
    kinds = [str(p.get("kind") or "") for p in posts]
    carousel_ratio = sum(1 for k in kinds if "carousel" in k) / max(1, len(posts))
    return {
        "content_mix": {
            "product": 40,
            "lifestyle": 25,
            "promo": 20,
            "testimonial": 10,
            "educational": 5,
        },
        "hook_patterns": ["pain_led", "social_proof", "offer_led"],
        "format_patterns": ["carousel_story" if carousel_ratio > 0.3 else "static_hero"],
        "posting_logic": "Problem or hook opener → proof or lifestyle → CTA or offer on closer posts.",
        "caption_tone": "Direct, benefit-led captions with occasional promo codes.",
        "prompt_guidance": (
            f"Borrow @{handle}'s content rhythm on {platform}: open with a scroll-stopping pain or hook, "
            "show proof or product-in-use mid-frame, close with a clear CTA. "
            "Use OUR brand colors, fonts, and logo — never competitor visual identity."
        ),
        "post_summaries": [f"{p.get('kind')}: {(p.get('caption') or '')[:80]}" for p in posts[:8]],
    }


async def fetch_and_analyze_competitor_social(
    *,
    platform: str,
    handle_or_url: str,
    industry: str = "",
    niche: str = "",
) -> dict[str, Any]:
    """SociaVault fetch + strategy-only LLM analysis for one competitor."""
    _, handle_hint = parse_social_input(platform=platform, handle_or_url=handle_or_url)
    plat, handle, profile_url, posts, profile = await fetch_social_feed_posts(
        platform=platform,
        handle_or_url=handle_or_url,
        brand_name=handle_hint,
    )
    analysis = await _analyze_competitor_posts_with_llm(
        platform=plat,
        handle=handle,
        posts=posts,
        profile=profile,
        industry=industry,
        niche=niche,
    )
    out = empty_competitor_insight()
    out.update({
        "platform": plat,
        "handle": handle,
        "profile_url": profile_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "post_count_analyzed": len(posts),
        "content_mix": analysis.get("content_mix") if isinstance(analysis.get("content_mix"), dict) else {},
        "hook_patterns": analysis.get("hook_patterns") if isinstance(analysis.get("hook_patterns"), list) else [],
        "format_patterns": analysis.get("format_patterns") if isinstance(analysis.get("format_patterns"), list) else [],
        "posting_logic": str(analysis.get("posting_logic") or "").strip(),
        "caption_tone": str(analysis.get("caption_tone") or "").strip(),
        "prompt_guidance": str(analysis.get("prompt_guidance") or "").strip(),
        "post_summaries": analysis.get("post_summaries") if isinstance(analysis.get("post_summaries"), list) else [],
    })
    return out


def format_competitor_insights_for_llm(insights: list[dict[str, Any]] | None) -> str:
    """Inject stored competitor strategy into image-plan LLM prompts."""
    items = normalize_competitor_insights(insights)
    if not items:
        return ""

    lines = [
        "COMPETITOR POSTING LOGIC (reference only — apply their CONTENT STRUCTURE to OUR product/campaign):",
        "CRITICAL: Keep OUR brand colors, fonts, logo, and social_style_profile unchanged.",
        "Never show competitor name, logo, or visual identity on the ad.",
        "",
    ]
    for i, item in enumerate(items[:5], start=1):
        plat = str(item.get("platform") or "social").strip()
        handle = str(item.get("handle") or "").strip().lstrip("@")
        label = f"@{handle}" if handle else f"Competitor {i}"
        lines.append(f"--- Competitor {i}: {plat} {label} ---")
        if item.get("posting_logic"):
            lines.append(f"Story arc: {item['posting_logic']}")
        if item.get("hook_patterns"):
            hooks = item["hook_patterns"]
            if isinstance(hooks, list):
                lines.append(f"Hook patterns they use: {', '.join(str(h) for h in hooks[:8])}")
        if item.get("format_patterns"):
            fmts = item["format_patterns"]
            if isinstance(fmts, list):
                lines.append(f"Format patterns: {', '.join(str(f) for f in fmts[:6])}")
        mix = item.get("content_mix")
        if isinstance(mix, dict) and mix:
            mix_str = ", ".join(f"{k} {v}%" for k, v in list(mix.items())[:6])
            lines.append(f"Content mix: {mix_str}")
        if item.get("caption_tone"):
            lines.append(f"Caption tone: {item['caption_tone']}")
        if item.get("prompt_guidance"):
            lines.append(f"Apply to our ads: {item['prompt_guidance']}")
        lines.append("")

    lines.append(
        "Use competitor insights for angles, hooks, carousel beats, and proof structure only. "
        "Visual style must match OUR brand social feed / Brand Kit — not the competitor's look."
    )
    return "\n".join(lines)


def upsert_competitor_insight(
    existing: list[dict[str, Any]] | None,
    new_insight: dict[str, Any],
) -> list[dict[str, Any]]:
    """Replace same platform+handle or append."""
    items = normalize_competitor_insights(existing)
    key = _competitor_key(str(new_insight.get("platform") or ""), str(new_insight.get("handle") or ""))
    if not key or key == ":":
        items.append(new_insight)
        return items
    out: list[dict[str, Any]] = []
    replaced = False
    for item in items:
        item_key = _competitor_key(str(item.get("platform") or ""), str(item.get("handle") or ""))
        if item_key == key:
            out.append(new_insight)
            replaced = True
        else:
            out.append(item)
    if not replaced:
        out.append(new_insight)
    return out[:10]


def remove_competitor_insight(
    existing: list[dict[str, Any]] | None,
    *,
    platform: str,
    handle: str,
) -> list[dict[str, Any]]:
    key = _competitor_key(platform, handle)
    return [
        item
        for item in normalize_competitor_insights(existing)
        if _competitor_key(str(item.get("platform") or ""), str(item.get("handle") or "")) != key
    ]
