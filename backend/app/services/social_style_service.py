"""Fetch client social posts (SociaVault) and build a stored visual-style profile for image prompts."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.services.sociavault_client import (
    fetch_facebook_posts,
    fetch_facebook_profile,
    fetch_instagram_posts,
    fetch_instagram_profile,
    parse_social_input,
)

logger = logging.getLogger(__name__)

_MAX_POSTS = 24
_MAX_CAPTION = 400

_NAMED_COLOR_HEX: dict[str, str] = {
    "black": "#0A0A0A",
    "dark": "#0A0A0A",
    "charcoal": "#1A1A1A",
    "gold": "#C9A962",
    "golden": "#C9A962",
    "champagne": "#D4AF37",
    "bronze": "#B8860B",
    "white": "#FFFFFF",
    "cream": "#F5F0E8",
    "navy": "#0F1B3D",
    "blue": "#2563EB",
    "rose gold": "#B76E79",
    "rosegold": "#B76E79",
}

_GOLD_HEX = {"#C9A962", "#D4AF37", "#B8860B", "#FFD700", "#E6BE8A"}
_DARK_HEX = {"#0A0A0A", "#000000", "#1A1A1A", "#111111", "#0F0F0F", "#0F1B3D"}


def _parse_color_token(token: str) -> str:
    raw = str(token or "").strip()
    if not raw:
        return ""
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", raw):
        return raw.upper()
    match = re.search(r"#[0-9A-Fa-f]{6}", raw)
    if match:
        return match.group(0).upper()
    lower = raw.lower()
    for name, hex_val in _NAMED_COLOR_HEX.items():
        if name in lower:
            return hex_val
    return ""


def _is_dark_hex(value: str) -> bool:
    hex_val = _parse_color_token(value)
    if not hex_val or hex_val in _DARK_HEX:
        return bool(hex_val)
    try:
        r = int(hex_val[1:3], 16)
        g = int(hex_val[3:5], 16)
        b = int(hex_val[5:7], 16)
        return (0.299 * r + 0.587 * g + 0.114 * b) < 70
    except ValueError:
        return False


def _is_gold_hex(value: str) -> bool:
    hex_val = _parse_color_token(value)
    if hex_val in _GOLD_HEX:
        return True
    lower = str(value or "").lower()
    return any(k in lower for k in ("gold", "champagne", "bronze", "gilded"))


def social_style_color_overrides(profile: dict[str, Any] | None) -> tuple[str, str]:
    """
    Derive primary/secondary hex from stored social feed analysis.
    Primary = accent for CTA + headline type (often gold).
    Secondary = background / frame (often black).
    """
    if not isinstance(profile, dict):
        return "", ""

    stored_primary = _parse_color_token(str(profile.get("effective_primary_color") or ""))
    stored_secondary = _parse_color_token(str(profile.get("effective_secondary_color") or ""))
    if stored_primary or stored_secondary:
        return stored_primary, stored_secondary

    themes = profile.get("visual_themes") if isinstance(profile.get("visual_themes"), dict) else {}
    palette_raw = themes.get("color_palette") if isinstance(themes.get("color_palette"), list) else []
    parsed = [_parse_color_token(str(item)) for item in palette_raw]
    parsed = [c for c in parsed if c]

    guidance = " ".join(
        [
            str(profile.get("prompt_guidance") or ""),
            str(themes.get("typography_style") or ""),
            str(themes.get("cta_style") or ""),
            str(themes.get("mood") or ""),
            " ".join(str(x) for x in palette_raw),
        ]
    ).lower()

    primary = ""
    secondary = ""

    if any(k in guidance for k in ("black and gold", "black & gold", "gold on black", "black background")):
        primary = primary or "#C9A962"
        secondary = secondary or "#0A0A0A"

    if any(k in guidance for k in ("gold and white", "gold & white", "white and gold", "gold on white")):
        primary = primary or "#C9A962"
        if not secondary or not _is_dark_hex(secondary):
            secondary = secondary or "#FFFFFF"

    # Luxury jewellery feeds without explicit palette: default gold accent + dark studio bg.
    if not primary and not secondary:
        if any(k in guidance for k in ("jewel", "diamond", "ring", "luxury", "bespoke")):
            primary = "#C9A962"
            secondary = "#0A0A0A"

    for color in parsed:
        if _is_gold_hex(color):
            primary = primary or color
        elif _is_dark_hex(color):
            secondary = secondary or color
        elif color == "#FFFFFF":
            continue
        elif not primary:
            primary = color
        elif not secondary:
            secondary = color

    if not primary:
        for color in parsed:
            if not _is_dark_hex(color) and color != "#FFFFFF":
                primary = color
                break

    if not secondary:
        for color in parsed:
            if _is_dark_hex(color):
                secondary = color
                break

    return primary, secondary


def resolve_effective_brand_colors(
    *,
    primary_color: str = "",
    secondary_color: str = "",
    social_style_profile: dict | None = None,
) -> tuple[str, str]:
    """
    When a social style profile exists, its feed palette overrides website Brand Kit
    colours for image prompts (CTA pill, headline type, backgrounds).
    """
    social_primary, social_secondary = social_style_color_overrides(social_style_profile)
    if social_primary:
        primary_color = social_primary
    if social_secondary:
        secondary_color = social_secondary
    return primary_color, secondary_color


def social_style_aesthetic_mode(profile: dict[str, Any] | None) -> str:
    """gold_on_dark | gold_on_white | empty"""
    if not isinstance(profile, dict):
        return ""
    stored = str(profile.get("aesthetic_mode") or "").strip().lower()
    if stored in {"gold_on_dark", "gold_on_white"}:
        return stored
    primary, secondary = social_style_color_overrides(profile)
    if _is_gold_hex(primary) and _is_dark_hex(secondary):
        return "gold_on_dark"
    if _is_gold_hex(primary) and secondary == "#FFFFFF":
        return "gold_on_white"
    if _is_gold_hex(primary):
        return "gold_on_dark"
    return ""


def format_social_style_scene_lock(
    profile: dict[str, Any] | None,
    *,
    lifestyle_scene: bool = False,
) -> str:
    """Hard visual rules appended to image prompts — prevents gradient/blue drift."""
    if not isinstance(profile, dict):
        return ""
    mode = social_style_aesthetic_mode(profile)
    primary, secondary = social_style_color_overrides(profile)
    if not mode and not primary and not lifestyle_scene:
        return ""

    if lifestyle_scene:
        return (
            "SOCIAL FEED TYPOGRAPHY LOCK: apply gold "
            f"({primary or '#C9A962'}) serif headlines + white sans sublines to TEXT ONLY. "
            "Keep the lifestyle boutique/consultation scene — do NOT replace with product-only "
            "pedestal or full-frame black studio catalog. NO blue/navy tones."
        )

    themes = profile.get("visual_themes") if isinstance(profile.get("visual_themes"), dict) else {}
    avoid = themes.get("avoid") if isinstance(themes.get("avoid"), list) else []
    avoid_bits = [str(a).strip() for a in avoid if str(a).strip()][:6]

    lines = [
        "SOCIAL FEED SCENE LOCK (non-negotiable — match how this client posts on Facebook/Instagram):",
    ]
    if mode == "gold_on_white":
        lines.append(
            f"Clean white or soft off-white studio background ({secondary or '#FFFFFF'}). "
            f"Headlines in metallic gold serif ({primary or '#C9A962'}). "
            f"CTA pill in solid gold ({primary or '#C9A962'}) with white bold text. "
            "Product hero on white/light surface — catalogue studio shot."
        )
    else:
        lines.append(
            f"Solid matte BLACK or dark charcoal background ({secondary or '#0A0A0A'}) — "
            "NOT a gold-to-cream gradient, NOT a diagonal split panel, NOT blue/navy tones. "
            f"Headlines in metallic gold luxury serif ({primary or '#C9A962'}) with subtle foil sheen. "
            "Subline in clean WHITE thin sans-serif when needed. "
            f"CTA pill: solid gold ({primary or '#C9A962'}) with white text — NEVER blue. "
            "Product hero: ring/jewellery on dark grey pedestal or black reflective surface, "
            "dramatic studio lighting exactly like their social posts."
        )

    default_avoid = [
        "blue CTAs or navy headlines",
        "gold-to-cream gradient split cards",
        "generic lifestyle desk/office stress scenes",
        "orange-washed or duotone colour filters",
    ]
    merged_avoid = list(dict.fromkeys([*avoid_bits, *default_avoid]))
    lines.append("AVOID: " + "; ".join(merged_avoid[:8]) + ".")
    return " ".join(lines)


def empty_social_style_profile() -> dict[str, Any]:
    return {
        "platform": "",
        "handle": "",
        "profile_url": "",
        "fetched_at": "",
        "provider": "sociavault",
        "post_count_analyzed": 0,
        "sample_image_urls": [],
        "visual_themes": {},
        "caption_tone": "",
        "content_mix": {},
        "prompt_guidance": "",
        "post_summaries": [],
    }


def _first_str(*values: Any) -> str:
    for v in values:
        s = str(v or "").strip()
        if s:
            return s
    return ""


def _normalize_post(item: dict[str, Any], *, platform: str) -> dict[str, Any]:
    caption = _first_str(
        item.get("caption"),
        item.get("text"),
        item.get("description"),
        item.get("message"),
        (item.get("edge_media_to_caption") or {}).get("edges", [{}])[0]
        if isinstance(item.get("edge_media_to_caption"), dict)
        else "",
    )
    if isinstance(item.get("edge_media_to_caption"), dict):
        edges = item["edge_media_to_caption"].get("edges") or []
        if edges and isinstance(edges[0], dict):
            node = edges[0].get("node") or {}
            caption = caption or _first_str(node.get("text"))

    media_type = _first_str(
        item.get("media_type"),
        item.get("product_type"),
        item.get("type"),
        item.get("__typename"),
    ).lower()
    if "video" in media_type or item.get("is_video"):
        kind = "video"
    elif "carousel" in media_type or "sidecar" in media_type:
        kind = "carousel"
    else:
        kind = "image"

    image_url = _first_str(
        item.get("display_url"),
        item.get("thumbnail_url"),
        item.get("image_url"),
        item.get("thumbnail"),
        item.get("image") if isinstance(item.get("image"), str) else "",
        (item.get("image") or {}).get("uri") if isinstance(item.get("image"), dict) else "",
        (item.get("videoDetails") or {}).get("thumbnailUrl")
        if isinstance(item.get("videoDetails"), dict)
        else "",
    )
    if not image_url and isinstance(item.get("thumbnail_resources"), list):
        thumbs = [t for t in item["thumbnail_resources"] if isinstance(t, dict)]
        if thumbs:
            image_url = _first_str(thumbs[-1].get("src"), thumbs[0].get("src"))

    likes = item.get("like_count") or item.get("likes") or item.get("reaction_count")
    comments = item.get("comment_count") or item.get("comments")
    short_url = _first_str(item.get("url"), item.get("permalink"), item.get("shortcode"))

    return {
        "platform": platform,
        "kind": kind,
        "caption": (caption or "")[:_MAX_CAPTION],
        "image_url": image_url,
        "likes": likes,
        "comments": comments,
        "url": short_url,
    }


def format_social_style_for_llm(profile: dict[str, Any] | None) -> str:
    """Inject stored social style into image-plan LLM prompts."""
    if not isinstance(profile, dict):
        return ""

    themes = profile.get("visual_themes") if isinstance(profile.get("visual_themes"), dict) else {}
    guidance = str(profile.get("prompt_guidance") or "").strip()
    social_primary, social_secondary = social_style_color_overrides(profile)

    if not guidance and not themes and not social_primary:
        return ""

    lines = [
        "CLIENT SOCIAL MEDIA VISUAL STYLE (from their live feed — match this look in generated ad images):",
    ]
    if guidance:
        lines.append(guidance)
    if social_primary or social_secondary:
        colour_bits = []
        if social_primary:
            colour_bits.append(f"accent/CTA/headline {social_primary}")
        if social_secondary:
            colour_bits.append(f"background/frame {social_secondary}")
        lines.append(
            "SOCIAL FEED COLOURS OVERRIDE Brand Kit when they differ — use: "
            + ", ".join(colour_bits)
            + ". Do NOT default to generic blue CTAs or navy headlines if the feed is black/gold."
        )
    if themes.get("color_palette"):
        lines.append(f"Palette: {', '.join(themes['color_palette'][:8])}")
    if themes.get("layout_patterns"):
        lines.append(f"Layouts: {', '.join(themes['layout_patterns'][:6])}")
    if themes.get("typography_style"):
        lines.append(f"Type: {themes['typography_style']}")
    if themes.get("cta_style"):
        lines.append(f"CTA style: {themes['cta_style']}")
    if themes.get("recurring_elements"):
        lines.append(f"Recurring: {', '.join(themes['recurring_elements'][:6])}")
    if themes.get("avoid"):
        lines.append(f"Avoid: {', '.join(themes['avoid'][:6])}")
    scene_lock = format_social_style_scene_lock(profile)
    if scene_lock:
        lines.append(scene_lock)
    lines.append(
        "When writing image prompts, mirror this client's existing social ad aesthetic — "
        "gold + dark OR gold + white only; do NOT invent blue, navy, or gradient split layouts."
    )
    return "\n".join(lines)


async def _analyze_posts_with_llm(
    *,
    brand_name: str,
    platform: str,
    handle: str,
    posts: list[dict[str, Any]],
    profile: dict[str, Any],
) -> dict[str, Any]:
    if not settings.OPENROUTER_API_KEY:
        return _heuristic_style(posts, brand_name=brand_name, platform=platform, handle=handle)

    from app.services.image_prompt_service import _get_openrouter_client

    bio = _first_str(
        profile.get("biography"),
        profile.get("bio"),
        profile.get("about"),
        profile.get("description"),
    )
    summaries = []
    for i, p in enumerate(posts[:_MAX_POSTS], start=1):
        summaries.append(
            f"Post {i} ({p.get('kind')}): caption={p.get('caption') or '—'} | "
            f"likes={p.get('likes') or '?'} | has_image={bool(p.get('image_url'))}"
        )
    sample_urls = [p["image_url"] for p in posts if p.get("image_url")][:4]

    system = (
        "You analyze a brand's public social media feed to guide AI ad image generation. "
        "Return ONLY valid JSON describing their VISUAL style (not copy strategy). "
        "Focus on: colors (include hex codes in color_palette), layout, product vs lifestyle mix, typography on images, "
        "CTA pill style, backgrounds, mood, and what to avoid. "
        "For luxury/jewellery feeds with black backgrounds and gold type, color_palette MUST include "
        '"#0A0A0A", "#C9A962", and "#FFFFFF". '
        "layout_patterns should describe: product on dark pedestal, gold serif headline on black, "
        "studio jewellery hero — NOT gradient split cards. "
        'avoid MUST include: "blue CTAs", "gold gradient split", "lifestyle desk scenes". '
        "JSON shape:\n"
        "{"
        '"visual_themes": {'
        '"color_palette": [], "layout_patterns": [], "typography_style": "", '
        '"image_composition": "", "cta_style": "", "mood": "", '
        '"recurring_elements": [], "avoid": []'
        "},"
        '"caption_tone": "",'
        '"content_mix": {"product": 0, "promo": 0, "lifestyle": 0, "other": 0},'
        '"prompt_guidance": "2-4 sentences telling an image model exactly how to match this brand feed",'
        '"post_summaries": ["short note per post pattern"]'
        "}"
    )
    user = (
        f"Brand: {brand_name or handle}\n"
        f"Platform: {platform}\n"
        f"Handle: {handle}\n"
        f"Bio: {bio or '—'}\n\n"
        f"POSTS ({len(posts)}):\n" + "\n".join(summaries)
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if sample_urls and settings.OPENROUTER_MODEL_VISION:
        content: list[dict[str, Any]] = [{"type": "text", "text": user + "\n\nSample post images attached."}]
        for url in sample_urls[:3]:
            content.append({"type": "image_url", "image_url": {"url": url}})
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]

    try:
        client = _get_openrouter_client()
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL_VISION or settings.OPENROUTER_MODEL_CLAUDE,
            messages=messages,
            temperature=0.2,
            max_tokens=1400,
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
        logger.exception("Social style LLM analysis failed — using heuristic")
        return _heuristic_style(posts, brand_name=brand_name, platform=platform, handle=handle)


def _heuristic_style(
    posts: list[dict[str, Any]],
    *,
    brand_name: str,
    platform: str,
    handle: str,
) -> dict[str, Any]:
    kinds = [p.get("kind") for p in posts]
    image_ratio = sum(1 for k in kinds if k == "image") / max(1, len(posts))
    return {
        "visual_themes": {
            "color_palette": ["#0A0A0A", "#C9A962", "#FFFFFF"],
            "layout_patterns": [
                "product hero on dark grey pedestal",
                "gold serif headline on solid black background",
                "studio jewellery close-up with dramatic lighting",
            ],
            "typography_style": "metallic gold luxury serif headlines, white thin sans sublines",
            "image_composition": "product-forward studio shots on dark backgrounds",
            "cta_style": "gold pill button with white text on dark background",
            "mood": "luxury, elegant, high-end",
            "recurring_elements": ["dark backgrounds", "gold typography", "pedestal product shots"],
            "avoid": [
                "blue CTAs or navy headlines",
                "gold-to-cream gradient split cards",
                "lifestyle desk stress scenes",
            ],
        },
        "caption_tone": "match feed captions",
        "content_mix": {"product": int(image_ratio * 100), "promo": 20, "lifestyle": 10, "other": 0},
        "prompt_guidance": (
            f"Match {brand_name or handle}'s {platform} feed (@{handle}): "
            "solid BLACK or dark charcoal backgrounds with metallic GOLD serif headlines and white sublines; "
            "OR clean white studio backgrounds with gold type. "
            "Product hero shots on dark pedestals with dramatic studio lighting. "
            "Never blue/navy CTAs, never gold-to-cream gradient split cards, never generic desk lifestyle scenes."
        ),
        "post_summaries": [f"{p.get('kind')}: {(p.get('caption') or '')[:80]}" for p in posts[:8]],
    }


async def fetch_and_analyze_social_style(
    *,
    platform: str,
    handle_or_url: str,
    brand_name: str = "",
) -> dict[str, Any]:
    """One-time SociaVault fetch + LLM style profile for storage on Brand."""
    plat, handle = parse_social_input(platform=platform, handle_or_url=handle_or_url)
    profile: dict[str, Any] = {}
    raw_posts: list[dict[str, Any]] = []

    if plat == "instagram":
        profile = await fetch_instagram_profile(handle)
        raw_posts = await fetch_instagram_posts(handle, max_pages=2)
        profile_url = f"https://www.instagram.com/{handle}/"
    else:
        fb_target = handle_or_url if handle_or_url.startswith("http") else handle
        profile = await fetch_facebook_profile(fb_target)
        page_id = _first_str(
            profile.get("id"),
            (profile.get("adLibrary") or {}).get("pageId")
            if isinstance(profile.get("adLibrary"), dict)
            else "",
        )
        raw_posts = await fetch_facebook_posts(
            fb_target,
            page_id=page_id,
            max_pages=8,
        )
        profile_url = handle_or_url if handle_or_url.startswith("http") else f"https://www.facebook.com/{handle}/"

    if plat == "facebook" and isinstance(profile, dict):
        page_name = _first_str(profile.get("name"), brand_name).lower()
        page_id = _first_str(
            profile.get("id"),
            (profile.get("adLibrary") or {}).get("pageId")
            if isinstance(profile.get("adLibrary"), dict)
            else "",
        )
        if page_name or page_id:
            owned_raw: list[dict[str, Any]] = []
            for item in raw_posts:
                if not isinstance(item, dict):
                    continue
                author = item.get("author") if isinstance(item.get("author"), dict) else {}
                author_name = str(author.get("name") or author.get("short_name") or "").lower()
                author_id = str(author.get("id") or "")
                if (page_name and author_name == page_name) or (page_id and author_id == page_id):
                    owned_raw.append(item)
            if owned_raw:
                raw_posts = owned_raw

    posts = [_normalize_post(p, platform=plat) for p in raw_posts if isinstance(p, dict)]
    posts = [p for p in posts if p.get("caption") or p.get("image_url")][:_MAX_POSTS]

    if not posts:
        raise ValueError(
            f"No public posts found for {plat} @{handle}. Check the handle/URL is correct and the profile is public."
        )

    analysis = await _analyze_posts_with_llm(
        brand_name=brand_name,
        platform=plat,
        handle=handle,
        posts=posts,
        profile=profile if isinstance(profile, dict) else {},
    )

    sample_images = [p["image_url"] for p in posts if p.get("image_url")][:12]
    out = empty_social_style_profile()
    out.update({
        "platform": plat,
        "handle": handle,
        "profile_url": profile_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "post_count_analyzed": len(posts),
        "sample_image_urls": sample_images,
        "visual_themes": analysis.get("visual_themes") if isinstance(analysis.get("visual_themes"), dict) else {},
        "caption_tone": str(analysis.get("caption_tone") or ""),
        "content_mix": analysis.get("content_mix") if isinstance(analysis.get("content_mix"), dict) else {},
        "prompt_guidance": str(analysis.get("prompt_guidance") or "").strip(),
        "post_summaries": analysis.get("post_summaries") if isinstance(analysis.get("post_summaries"), list) else [],
    })
    effective_primary, effective_secondary = social_style_color_overrides(out)
    if effective_primary:
        out["effective_primary_color"] = effective_primary
    if effective_secondary:
        out["effective_secondary_color"] = effective_secondary
    mode = social_style_aesthetic_mode(out)
    if mode:
        out["aesthetic_mode"] = mode
    return out
