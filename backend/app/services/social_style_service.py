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


def _guidance_is_stale_gold_template(text: str) -> bool:
    """Detect generic gold/jewellery guidance wrongly saved for non-jewellery brands."""
    lower = (text or "").lower()
    if not lower:
        return False
    gold_hints = (
        "metallic gold",
        "gold serif",
        "champagne-gold",
        "gold pill",
        "solid black",
        "gold on black",
        "gold headlines",
        "dark charcoal backgrounds with metallic gold",
    )
    jewellery_hints = (
        "jewel",
        "jewellery",
        "jewelry",
        "diamond",
        "ring",
        "pendant",
        "engagement",
        "pedestal",
    )
    return any(h in lower for h in gold_hints) and not any(h in lower for h in jewellery_hints)


def social_style_applies_color_override(
    profile: dict[str, Any] | None,
    *,
    brand_primary: str = "",
    brand_secondary: str = "",
) -> bool:
    """
    Social feed colours may override Brand Kit ONLY for confirmed gold-led feeds
    on brands whose Brand Kit is also gold/dark (jewellery). Non-gold Brand Kit always wins.
    """
    kit_primary = _parse_color_token(brand_primary)
    if kit_primary and not _is_gold_hex(kit_primary):
        return False
    if not isinstance(profile, dict) or not profile.get("fetched_at"):
        return False
    mode = social_style_aesthetic_mode(profile)
    social_primary, _social_secondary = social_style_color_overrides(profile)
    return mode in {"gold_on_dark", "gold_on_white"} and _is_gold_hex(social_primary)


def resolve_effective_brand_colors(
    *,
    primary_color: str = "",
    secondary_color: str = "",
    social_style_profile: dict | None = None,
) -> tuple[str, str]:
    """
    Brand Kit colours are the default for every industry.
    Social feed colours override ONLY when the brand's Kit is gold-compatible AND
    the saved social profile is a confirmed gold-led feed (jewellery/luxury black+gold).
    """
    kit_primary = _parse_color_token(primary_color)

    if not isinstance(social_style_profile, dict) or not social_style_profile.get("fetched_at"):
        return primary_color, secondary_color

    # Explicit Brand Kit palette (red, green, coral, blue, etc.) — never replace with gold social styling.
    if kit_primary and not _is_gold_hex(kit_primary):
        return primary_color, secondary_color

    if not social_style_applies_color_override(
        social_style_profile,
        brand_primary=primary_color,
        brand_secondary=secondary_color,
    ):
        return primary_color, secondary_color

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
    primary, secondary = social_style_color_overrides(profile)
    stored = str(profile.get("aesthetic_mode") or "").strip().lower()
    if stored in {"gold_on_dark", "gold_on_white"}:
        # Ignore stale gold mode when feed colours are not actually gold-led.
        if not _is_gold_hex(primary):
            stored = ""
        else:
            return stored
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
    brand_primary: str = "",
    brand_secondary: str = "",
) -> str:
    """Hard visual rules appended to image prompts — match THIS brand's feed only."""
    if not isinstance(profile, dict):
        return ""
    use_social_colours = social_style_applies_color_override(
        profile,
        brand_primary=brand_primary,
        brand_secondary=brand_secondary,
    )
    mode = social_style_aesthetic_mode(profile) if use_social_colours else ""
    primary, secondary = social_style_color_overrides(profile)
    themes = profile.get("visual_themes") if isinstance(profile.get("visual_themes"), dict) else {}
    typography = str(themes.get("typography_style") or "").strip()
    cta_style = str(themes.get("cta_style") or "").strip()
    mood = str(themes.get("mood") or "").strip()
    composition = str(themes.get("image_composition") or "").strip()
    avoid = themes.get("avoid") if isinstance(themes.get("avoid"), list) else []
    avoid_bits = [str(a).strip() for a in avoid if str(a).strip()][:6]

    if not use_social_colours:
        if not typography and not themes.get("layout_patterns") and not composition and not lifestyle_scene:
            return ""
        if lifestyle_scene:
            type_note = typography or "match headline/CTA typography from their social posts"
            return (
                f"SOCIAL FEED STYLE: {type_note}. Keep the lifestyle photograph — do NOT replace "
                "with product-only pedestal or black studio catalog. "
                "Use Brand Kit primary/secondary for ALL on-image text and CTA colours — NOT gold unless Brand Kit uses gold."
            )
        lines = [
            "SOCIAL FEED STYLE (composition + typography — Brand Kit colours for CTA/headline):",
        ]
        if typography:
            lines.append(f"Typography: {typography}.")
        if cta_style:
            lines.append(f"CTA style: {cta_style}.")
        if composition:
            lines.append(f"Composition: {composition}.")
        if themes.get("layout_patterns"):
            lines.append(f"Layouts: {', '.join(themes['layout_patterns'][:6])}.")
        if mood:
            lines.append(f"Mood: {mood}.")
        lines.append(
            "Use Brand Kit primary/secondary hex for headline accent and CTA pill — "
            "do NOT default to metallic gold serif or black jewellery-studio layouts."
        )
        if avoid_bits:
            lines.append("AVOID: " + "; ".join(avoid_bits[:8]) + ".")
        return " ".join(lines)

    if not mode and not primary and not typography and not lifestyle_scene:
        return ""

    if lifestyle_scene:
        if mode in {"gold_on_dark", "gold_on_white"} or _is_gold_hex(primary):
            return (
                "SOCIAL FEED TYPOGRAPHY LOCK: apply feed accent "
                f"({primary or '#C9A962'}) to headline/CTA text only + white sans sublines. "
                "Keep the lifestyle scene — do NOT replace with product-only pedestal or "
                "full-frame black studio catalog."
            )
        accent = primary or "brand accent from their feed"
        type_note = typography or "bold sans-serif or brand headline style from their posts"
        return (
            f"SOCIAL FEED TYPOGRAPHY LOCK: match their feed — {type_note}. "
            f"Headline/CTA accent {accent}. Keep the lifestyle photograph intact. "
            "Do NOT substitute generic gold serif jewellery styling unless their feed uses it."
        )

    if mode == "gold_on_dark":
        lines = [
            "SOCIAL FEED SCENE LOCK (gold-on-dark — match this jeweller/luxury feed):",
            (
                f"Solid matte BLACK or dark charcoal background ({secondary or '#0A0A0A'}) — "
                "NOT a gold-to-cream gradient, NOT a diagonal split panel. "
                f"Headlines in metallic gold luxury serif ({primary or '#C9A962'}). "
                f"CTA pill: solid gold ({primary or '#C9A962'}) with white text. "
                "Product hero on dark pedestal with dramatic studio lighting."
            ),
        ]
    elif mode == "gold_on_white":
        lines = [
            "SOCIAL FEED SCENE LOCK (gold-on-white — match this feed):",
            (
                f"Clean white or soft off-white studio background ({secondary or '#FFFFFF'}). "
                f"Headlines in metallic gold serif ({primary or '#C9A962'}). "
                f"CTA pill in solid gold ({primary or '#C9A962'}) with white bold text."
            ),
        ]
    else:
        lines = [
            "SOCIAL FEED SCENE LOCK (match this client's actual posts — not generic gold serif):",
        ]
        if secondary:
            lines.append(f"Background/frame: {secondary}.")
        if primary:
            lines.append(f"CTA pill + headline accent: {primary}.")
        if typography:
            lines.append(f"Typography: {typography}.")
        if cta_style:
            lines.append(f"CTA style: {cta_style}.")
        if composition:
            lines.append(f"Composition: {composition}.")
        if mood:
            lines.append(f"Mood: {mood}.")
        lines.append(
            "Use ONLY colours and type styles from this feed profile. "
            "Do NOT default to metallic gold serif on black unless listed above."
        )

    default_avoid = [
        "off-brand colour palettes",
        "generic stock-photo look",
        "borrowed luxury jeweller gold foil from other brands",
    ]
    if mode in {"gold_on_dark", "gold_on_white"}:
        default_avoid = [
            "blue CTAs or navy headlines",
            "gold-to-cream gradient split cards",
            "generic lifestyle desk/office stress scenes",
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


def format_social_style_for_llm(
    profile: dict[str, Any] | None,
    *,
    brand_primary: str = "",
    brand_secondary: str = "",
) -> str:
    """Inject stored social style into image-plan LLM prompts."""
    if not isinstance(profile, dict):
        return ""

    themes = profile.get("visual_themes") if isinstance(profile.get("visual_themes"), dict) else {}
    guidance = str(profile.get("prompt_guidance") or "").strip()
    if guidance and _guidance_is_stale_gold_template(guidance) and not social_style_applies_color_override(
        profile, brand_primary=brand_primary, brand_secondary=brand_secondary
    ):
        guidance = ""
    social_primary, social_secondary = social_style_color_overrides(profile)
    use_social_colours = social_style_applies_color_override(
        profile, brand_primary=brand_primary, brand_secondary=brand_secondary
    )

    if not guidance and not themes and not (use_social_colours and social_primary):
        return ""

    lines = [
        "CLIENT SOCIAL MEDIA VISUAL STYLE (from their live feed — match layout/typography; Brand Kit owns colours unless gold jewellery feed):",
    ]
    if guidance:
        lines.append(guidance)
    if use_social_colours and (social_primary or social_secondary):
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
    elif brand_primary or brand_secondary:
        kit_bits = []
        if brand_primary:
            kit_bits.append(f"Brand Kit primary {brand_primary} for CTA + headline accent")
        if brand_secondary:
            kit_bits.append(f"Brand Kit secondary {brand_secondary} for backgrounds/highlights")
        if kit_bits:
            lines.append(
                "COLOURS: " + "; ".join(kit_bits) + ". Do NOT substitute gold serif or jewellery styling."
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
    scene_lock = format_social_style_scene_lock(
        profile,
        brand_primary=brand_primary,
        brand_secondary=brand_secondary,
    )
    if scene_lock:
        lines.append(scene_lock)
    if use_social_colours:
        lines.append(
            "When writing image prompts, mirror this client's gold + dark OR gold + white feed aesthetic — "
            "do NOT invent blue, navy, or gradient split layouts."
        )
    else:
        lines.append(
            "When writing image prompts, mirror THIS client's feed composition and typography. "
            "Always use Brand Kit colours for CTA/headline — never default to gold serif unless Brand Kit uses gold."
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
        "Focus on: colors (include hex codes in color_palette when visible), layout, product vs lifestyle mix, "
        "typography on images, CTA pill style, backgrounds, mood, and what to avoid. "
        "Describe what you ACTUALLY see — supplements may use bold sans-serif on bright photos; "
        "medical brands may use green/white; only jewellery feeds use gold serif on black. "
        "Do NOT assume gold unless feed images clearly use gold type or accents. "
        'avoid MUST NOT force gold on feeds that use other brand colours. '
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
    caption_sample = " ".join(
        str(p.get("caption") or "")[:120] for p in posts[:6]
    ).lower()
    is_jewellery_hint = any(
        k in caption_sample for k in ("jewel", "diamond", "ring", "pendant", "engagement")
    )
    if is_jewellery_hint:
        palette = ["#0A0A0A", "#C9A962", "#FFFFFF"]
        typography = "metallic gold luxury serif headlines, white thin sans sublines"
        cta = "gold pill button with white text on dark background"
        guidance = (
            f"Match {brand_name or handle}'s {platform} feed (@{handle}): "
            "solid black/dark backgrounds with gold serif headlines when seen in feed posts."
        )
    else:
        palette = []
        typography = "match on-image type from feed — bold sans-serif, clean modern headlines as observed"
        cta = "match CTA pill style and colour from feed posts"
        guidance = (
            f"Match {brand_name or handle}'s {platform} feed (@{handle}): "
            "use the same on-image colours, typography, photo style, and CTA treatment as their posts. "
            "Do NOT default to gold serif on black unless their feed clearly uses that look."
        )
    return {
        "visual_themes": {
            "color_palette": palette,
            "layout_patterns": ["match native layouts from analyzed posts"],
            "typography_style": typography,
            "image_composition": "match product vs lifestyle mix from feed",
            "cta_style": cta,
            "mood": "match feed mood and energy",
            "recurring_elements": [],
            "avoid": [
                "generic gold serif jewellery styling when feed does not use gold",
                "off-brand colour palettes",
            ],
        },
        "caption_tone": "match feed captions",
        "content_mix": {"product": int(image_ratio * 100), "promo": 20, "lifestyle": 10, "other": 0},
        "prompt_guidance": guidance,
        "post_summaries": [f"{p.get('kind')}: {(p.get('caption') or '')[:80]}" for p in posts[:8]],
    }


async def fetch_social_feed_posts(
    *,
    platform: str,
    handle_or_url: str,
    brand_name: str = "",
) -> tuple[str, str, str, list[dict[str, Any]], dict[str, Any]]:
    """SociaVault fetch — returns (platform, handle, profile_url, normalized_posts, raw_profile)."""
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
    return plat, handle, profile_url, posts, profile if isinstance(profile, dict) else {}


async def fetch_and_analyze_social_style(
    *,
    platform: str,
    handle_or_url: str,
    brand_name: str = "",
) -> dict[str, Any]:
    """One-time SociaVault fetch + LLM style profile for storage on Brand."""
    plat, handle, profile_url, posts, profile = await fetch_social_feed_posts(
        platform=platform,
        handle_or_url=handle_or_url,
        brand_name=brand_name,
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
    mode = social_style_aesthetic_mode(out)
    if mode in {"gold_on_dark", "gold_on_white"} and _is_gold_hex(effective_primary):
        if effective_primary:
            out["effective_primary_color"] = effective_primary
        if effective_secondary:
            out["effective_secondary_color"] = effective_secondary
        out["aesthetic_mode"] = mode
    elif effective_primary and not _is_gold_hex(effective_primary):
        out["effective_primary_color"] = effective_primary
        if effective_secondary:
            out["effective_secondary_color"] = effective_secondary
    return out
