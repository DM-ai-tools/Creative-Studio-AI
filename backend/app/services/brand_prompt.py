"""Build generation prompts from Brand + Brand Kit (name, colors, voice)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.campaign_themes import parse_campaign_themes
from app.services.copy_helpers import texts_duplicate
from app.services.cta_defaults import resolve_campaign_cta
from app.services.industries import resolve_target_industry

if TYPE_CHECKING:
    from app.models.brand import Brand, BrandKit

# Runway text_to_image promptText max length (API validation).
RUNWAY_IMAGE_PROMPT_MAX = 1000


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def clamp_runway_image_prompt(prompt: str, max_len: int = RUNWAY_IMAGE_PROMPT_MAX) -> str:
    """Ensure prompt fits Runway API limits."""
    return _clip(prompt, max_len)


def brand_snapshot(brand: "Brand", kit: "BrandKit | None" = None) -> dict[str, Any]:
    kit_colors: dict = {}
    if kit and isinstance(kit.colors, dict):
        kit_colors = kit.colors

    primary = brand.primary_color or kit_colors.get("primary") or "#0F1B3D"
    secondary = brand.secondary_color or kit_colors.get("secondary") or "#00C2A8"
    voice = ""
    if isinstance(brand.voice_rules, dict):
        voice = str(brand.voice_rules.get("description") or "")

    fonts: dict = {}
    logo_on_light = ""
    if kit and isinstance(kit.fonts, dict):
        fonts = kit.fonts
    if kit and isinstance(kit.logo_variations, dict):
        logo_on_light = str(kit.logo_variations.get("on_light") or "")

    # Also include full logo_variations so resolve_video_logo_urls can pick it up
    logo_variations: dict = {}
    if kit and isinstance(kit.logo_variations, dict):
        logo_variations = kit.logo_variations

    return {
        "brand_name": brand.name,
        "agency_industry": brand.industry,
        "language": brand.language,
        "primary_color": primary,
        "secondary_color": secondary,
        "voice": voice,
        "logo_url": brand.logo_url,
        "logo_on_light_url": logo_on_light or None,
        "logo_variations": logo_variations or None,
        "font_heading": fonts.get("heading", ""),
        "font_body": fonts.get("body", ""),
    }


def enrich_brief_with_brand(brief_dict: dict[str, Any], brand: "Brand", kit: "BrandKit | None" = None) -> dict[str, Any]:
    snap = brand_snapshot(brand, kit)
    target_id, target_label = resolve_target_industry(brief_dict)
    merged = {**brief_dict, **snap}
    merged["campaign_product"] = brief_dict.get("product_name") or brand.name
    merged["target_industry_id"] = target_id
    merged["target_industry_label"] = target_label
    return merged


def build_image_prompt(
    *,
    brand: dict[str, Any],
    brief: dict[str, Any],
    copy: dict[str, Any],
    format_type: str,
) -> str:
    brand_name = _clip(brand.get("brand_name") or brief.get("brand_name") or "Agency", 40)
    campaign = _clip(brief.get("campaign_product") or brief.get("product_name") or brand_name, 80)
    primary = brand.get("primary_color", "#0F1B3D")
    secondary = brand.get("secondary_color", "#00C2A8")
    target_industry = _clip(brief.get("target_industry_label") or "client industry", 50)
    tone = _clip(brief.get("ad_copy_tone", "professional"), 24)
    hook = _clip(copy.get("hook", ""), 120)
    headline = _clip(copy.get("headline", ""), 80)
    cta = _clip(copy.get("cta", brief.get("cta", "Learn More")), 40)
    offer = ""
    benefits = brief.get("key_benefits")
    if isinstance(benefits, dict):
        offer = _clip(str(benefits.get("offer") or ""), 80)

    has_logo = bool(brand.get("logo_url"))
    prompt = (
        f"Professional Meta {format_type} ad for {target_industry}. "
        "Natural, realistic photography or clean modern layout — true-to-life colors, "
        "not a heavy color filter or monochromatic tint over the whole image. "
    )
    prompt += (
        f"Brand accent colors (use sparingly): {primary} for CTA button only, "
        f"{secondary} for one small highlight at most. "
        "White or dark neutral backgrounds; avoid thick colored borders or frames. "
        "Do not orange-wash, duotone, or recolor the entire photo. "
    )
    if has_logo and format_type not in {"carousel", "reel", "video"}:
        prompt += "Leave top-left corner empty (logo added later). No drawn logos or wordmarks. "

    themes = parse_campaign_themes(
        brief.get("campaign_product") or brief.get("product_name") or "",
        brief,
    )
    slides = copy.get("carousel_slides")
    if format_type == "carousel" and isinstance(slides, list) and len(slides) > 1:
        n = len(slides)
        prompt += (
            f"Meta carousel: {n} equal panels in a row below a top header margin "
            "(empty light band ~12% height for logo — panels must not extend into header). "
        )
        for i, slide in enumerate(slides[:5]):
            if not isinstance(slide, dict):
                continue
            theme = _clip(str(slide.get("theme") or slide.get("headline") or ""), 50)
            slide_hook = _clip(str(slide.get("hook") or offer), 60)
            prompt += (
                f'Panel {i + 1}: realistic photo of {theme}; '
                f'headline text ONLY "{theme}" — do not mention other services on this panel. '
            )
            if slide_hook and not texts_duplicate(slide_hook, theme):
                prompt += f'Subtext: "{slide_hook}". '
        if offer:
            prompt += f'Shared offer line (small): "{offer}". '
        prompt += f'Shared CTA button: "{cta}". '
    elif format_type in {"reel", "video"}:
        prompt += (
            "Vertical 9:16 full-bleed portrait — subject and scene fill the entire frame edge to edge. "
            "No letterboxing, no empty white or black bars at top or bottom, no cinematic widescreen bars. "
            "Logo added in post — do not draw a logo or a large empty header strip. "
            "One headline in the upper third only (single placement). "
            "Do NOT repeat the headline at the bottom. "
            "Bottom third: one CTA button only. "
        )
        prompt += f'Headline once: "{headline}". '
        if offer and not texts_duplicate(offer, headline):
            prompt += f'Small offer line under headline only: "{offer}". '
        prompt += (
            f'CTA button text must read exactly: "{cta}". '
            "Do not use Shop Now, Buy Now, or other retail CTAs. "
        )
    else:
        if offer and not texts_duplicate(offer, headline):
            prompt += f"Offer: {offer}. "
        prompt += f'One headline only: "{headline}".'
        if hook and not texts_duplicate(hook, headline) and not texts_duplicate(hook, campaign):
            prompt += f' Subtext: "{hook}".'
        prompt += f' CTA button text must read exactly: "{cta}". '
        prompt += "Do not repeat the headline in multiple banners. "

    prompt += f"{tone} tone, high-end Facebook Instagram ad, natural and trustworthy."
    return clamp_runway_image_prompt(prompt)
