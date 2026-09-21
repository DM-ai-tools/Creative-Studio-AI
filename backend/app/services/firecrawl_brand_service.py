"""Fetch brand identity from a website via Firecrawl (colors, logo, industry)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_HEX = re.compile(r"^#?[0-9A-Fa-f]{6}$")


def _pick_raster_logo_url(*candidates: Any) -> str:
    """Prefer PNG/JPG/WebP logo URLs over SVG when scraping a website."""
    raster: list[str] = []
    svg: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        raw = str(candidate).strip()
        if not raw or raw.lower() in {"none", "null", "undefined"}:
            continue
        lower = raw.lower()
        if lower.endswith(".svg") or "/svg" in lower or "image/svg" in lower:
            svg.append(raw)
        else:
            raster.append(raw)
    if raster:
        return raster[0]
    for candidate in svg:
        from app.services.brand_logo import resolve_downloadable_logo_url

        return resolve_downloadable_logo_url(candidate)
    return ""


def _clean_font_family(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or raw.lower() in {"none", "null", "undefined", "inherit", "system-ui"}:
        return ""
    # Strip CSS stacks — keep first named family.
    first = raw.split(",")[0].strip().strip("'\"")
    return first[:80] if first else ""


def _extract_fonts(branding: dict[str, Any]) -> tuple[str, str]:
    """Heading + body families from Firecrawl branding.typography / fonts."""
    typography = branding.get("typography") if isinstance(branding.get("typography"), dict) else {}
    families = typography.get("fontFamilies") if isinstance(typography.get("fontFamilies"), dict) else {}
    heading = _clean_font_family(families.get("heading") or families.get("display"))
    body = _clean_font_family(families.get("primary") or families.get("body"))
    fonts_list = branding.get("fonts") if isinstance(branding.get("fonts"), list) else []
    for item in fonts_list:
        if not isinstance(item, dict):
            continue
        family = _clean_font_family(item.get("family"))
        if not family:
            continue
        role = str(item.get("role") or "").strip().lower()
        if role in {"heading", "display", "title"} and not heading:
            heading = family
        elif role in {"body", "primary", "text", ""} and not body:
            body = family
    if heading and not body:
        body = heading
    if body and not heading:
        heading = body
    return heading, body


def _norm_hex(value: Any, fallback: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    if not raw.startswith("#"):
        raw = f"#{raw}"
    if _HEX.match(raw):
        return raw.upper()
    return fallback


def _normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        raise ValueError("Website URL is required")
    if not u.startswith(("http://", "https://")):
        u = f"https://{u}"
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Invalid website URL")
    return u


_CATEGORY_LABEL_RE = re.compile(
    r"(?i)^(shop|buy|browse|collections?|engagement|wedding|fine)\b|"
    r"^(diamonds?|jewellery|jewelry|rings?|earrings?|necklaces?|bracelets?)$|"
    r"^shop\s+diamonds?"
)


def _company_name_from_host(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    slug = host.split(".")[0].replace("-", " ").replace("_", " ").strip()
    if not slug:
        return host
    # adoriajewels → Adoria Jewels
    for suffix in ("jewels", "jewellery", "jewelry", "diamonds"):
        if slug.endswith(suffix) and len(slug) > len(suffix) + 2:
            prefix = slug[: -len(suffix)].strip()
            return f"{prefix.title()} {suffix.title()}"
    return slug.title()


def _looks_like_nav_or_category(name: str) -> bool:
    n = (name or "").strip()
    if not n or len(n) < 2:
        return True
    return bool(_CATEGORY_LABEL_RE.search(n))


def _guess_industry_from_text(text: str) -> str:
    hay = (text or "").lower()
    rules = [
        ("dental", "dental"),
        ("clinic", "healthcare"),
        ("legal", "pro_services"),
        ("law firm", "pro_services"),
        ("accountant", "pro_services"),
        ("saas", "saas"),
        ("software", "saas"),
        ("ecommerce", "ecommerce"),
        ("shopify", "ecommerce"),
        ("wholesale", "wholesale"),
        ("plumbing", "trade"),
        ("electrician", "trade"),
        ("construction", "trade"),
        ("hvac", "trade"),
        ("tradie", "trade"),
        ("trade services", "trade"),
        ("hipages", "trade"),
        ("marketing", "digital_marketing"),
        ("agency", "digital_marketing"),
        ("retail", "retail"),
        ("restaurant", "retail"),
        ("real estate", "pro_services"),
        ("mortgage", "pro_services"),
    ]
    for kw, industry in rules:
        if kw in hay:
            return industry
    return "general"


async def _infer_industry_llm(*, brand_name: str, page_title: str, markdown: str) -> tuple[str, str, str]:
    """Return (industry_id, niche, brand_name)."""
    if not settings.OPENROUTER_API_KEY:
        return (
            _guess_industry_from_text(f"{brand_name} {page_title} {markdown[:800]}"),
            "",
            brand_name,
        )
    try:
        from app.services.image_prompt_service import _get_openrouter_client

        client = _get_openrouter_client()
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL_CLAUDE or settings.OPENROUTER_MODEL_OPENAI,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify the business industry. Return ONLY JSON: "
                        '{"industry":"<id>","niche":"<short niche>","brand_name":"<name>"} '
                        "industry id must be one of: dental, healthcare, digital_marketing, "
                        "wholesale, trade, pro_services, retail, ecommerce, saas, general. "
                        "brand_name must be the COMPANY name (e.g. Adoria Jewellery), NEVER a "
                        "nav/category label like Shop Diamonds, Collections, or Engagement Rings."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Brand hint: {brand_name}\n"
                        f"Page title: {page_title}\n"
                        f"Content excerpt:\n{markdown[:2000]}"
                    ),
                },
            ],
            max_tokens=200,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        data = json.loads(raw)
        industry = str(data.get("industry") or "general").strip().lower()
        niche = str(data.get("niche") or "").strip()
        name = str(data.get("brand_name") or brand_name).strip() or brand_name
        allowed = {
            "dental",
            "healthcare",
            "digital_marketing",
            "wholesale",
            "trade",
            "pro_services",
            "retail",
            "ecommerce",
            "saas",
            "general",
        }
        if industry not in allowed:
            industry = "general"
        return industry, niche, name
    except Exception:
        logger.exception("Industry LLM inference failed")
        return (
            _guess_industry_from_text(f"{brand_name} {page_title} {markdown[:800]}"),
            "",
            brand_name,
        )


async def fetch_brand_from_website(url: str) -> dict[str, Any]:
    """
    Scrape a website and return brand identity for brief creation.
    Uses Firecrawl branding format when FIRECRAWL_API_KEY is set;
    otherwise falls back to simple HTML fetch + heuristics.
    """
    clean_url = _normalize_url(url)

    if settings.FIRECRAWL_API_KEY.strip():
        return await _fetch_via_firecrawl(clean_url)
    return await _fetch_via_fallback(clean_url)


async def _fetch_via_firecrawl(url: str) -> dict[str, Any]:
    """
    Official Firecrawl brand identity scrape:
      POST {FIRECRAWL_BASE_URL}/scrape
      body: { "url": "...", "formats": ["branding", "markdown"] }

    Docs: https://docs.firecrawl.dev/features/scrape#extract-brand-identity
    Base must be https://api.firecrawl.dev/v2  (not v1).
    """
    headers = {
        "Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }
    # Branding needs full-page CSS/assets — do NOT set onlyMainContent.
    # Combine branding + markdown so we can infer industry/niche from page text.
    payload = {
        "url": url,
        "formats": ["branding", "markdown"],
    }
    base = (settings.FIRECRAWL_BASE_URL or "https://api.firecrawl.dev/v2").rstrip("/")
    # Guard against stale v1 configs in Railway / local .env
    if base.endswith("/v1"):
        base = base[:-3] + "/v2"
        logger.warning("FIRECRAWL_BASE_URL was v1 — using v2 scrape endpoint instead")

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            f"{base}/scrape",
            headers=headers,
            json=payload,
        )
        if response.status_code >= 400:
            raise ValueError(f"Firecrawl failed ({response.status_code}): {response.text[:400]}")
        body = response.json()

    if isinstance(body, dict) and body.get("success") is False:
        err = body.get("error") or body.get("message") or body
        raise ValueError(f"Firecrawl scrape failed: {err}")

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        data = body if isinstance(body, dict) else {}

    branding = data.get("branding") if isinstance(data.get("branding"), dict) else {}
    colors = branding.get("colors") if isinstance(branding.get("colors"), dict) else {}
    images = branding.get("images") if isinstance(branding.get("images"), dict) else {}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    markdown = str(data.get("markdown") or "")[:4000]
    personality = branding.get("personality") if isinstance(branding.get("personality"), dict) else {}

    # Docs: branding.logo OR branding.images.logo / favicon / ogImage — prefer raster over SVG.
    logo_candidates = [
        branding.get("logo"),
        images.get("logo"),
        images.get("ogImage"),
        metadata.get("ogImage"),
        images.get("favicon"),
    ]
    logo_str = _pick_raster_logo_url(*logo_candidates)

    page_title = str(metadata.get("title") or metadata.get("ogTitle") or "").strip()
    brand_name = page_title.split("|")[0].split("-")[0].strip() or urlparse(url).netloc

    inferred = await _infer_industry_llm(
        brand_name=brand_name,
        page_title=page_title,
        markdown=markdown or str(personality.get("targetAudience") or ""),
    )
    industry, niche, brand_name = inferred
    host_name = _company_name_from_host(url)
    if _looks_like_nav_or_category(brand_name):
        brand_name = host_name or brand_name

    components = branding.get("components") if isinstance(branding.get("components"), dict) else {}
    button_primary = (
        components.get("buttonPrimary")
        if isinstance(components.get("buttonPrimary"), dict)
        else {}
    )
    primary = _norm_hex(
        colors.get("primary") or button_primary.get("background"),
        "#0F1B3D",
    )
    secondary = _norm_hex(
        colors.get("secondary")
        or colors.get("accent")
        or colors.get("link")
        or colors.get("textPrimary"),
        "#00C2A8",
    )
    font_heading, font_body = _extract_fonts(branding)

    if not branding:
        logger.warning("Firecrawl returned no branding object for %s — check API key / plan", url)

    brand_facts: dict[str, Any] = {}
    try:
        from app.services.brand_facts_service import extract_brand_facts

        brand_facts = await extract_brand_facts(
            markdown=markdown or str(personality.get("targetAudience") or ""),
            brand_name=brand_name or urlparse(url).netloc,
            page_title=page_title,
            industry=industry or "",
            niche=niche or "",
        )
    except Exception as exc:
        logger.warning("Brand facts extraction failed for %s: %s", url, exc)
        brand_facts = {}

    from app.services.usage_tracker import record_firecrawl

    record_firecrawl(success=True, url=url)
    return {
        "source_url": url,
        "brand_name": brand_name or urlparse(url).netloc,
        "industry": industry or "general",
        "niche": niche or str(personality.get("targetAudience") or "")[:80],
        "primary_color": primary,
        "secondary_color": secondary,
        "font_heading": font_heading or None,
        "font_body": font_body or None,
        "logo_url": logo_str or None,
        "page_title": page_title,
        "description": str(metadata.get("description") or metadata.get("ogDescription") or "")[:500],
        "provider": "firecrawl",
        "color_scheme": branding.get("colorScheme"),
        "brand_facts": brand_facts,
    }


async def _fetch_via_fallback(url: str) -> dict[str, Any]:
    """No Firecrawl key — basic HTML fetch + OpenRouter industry guess."""
    from app.services.website_script_service import fetch_website_content

    page = await fetch_website_content(url)
    brand_name = (page.get("title") or "").split("|")[0].split("-")[0].strip() or urlparse(url).netloc
    body = str(page.get("body") or "")
    inferred = await _infer_industry_llm(
        brand_name=brand_name,
        page_title=str(page.get("title") or ""),
        markdown=body,
    )
    industry, niche, brand_name = inferred
    host_name = _company_name_from_host(url)
    if _looks_like_nav_or_category(brand_name):
        brand_name = host_name or brand_name

    # Best-effort favicon
    parsed = urlparse(url)
    favicon = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"

    brand_facts: dict[str, Any] = {}
    try:
        from app.services.brand_facts_service import extract_brand_facts

        brand_facts = await extract_brand_facts(
            markdown=body,
            brand_name=brand_name,
            page_title=str(page.get("title") or ""),
            industry=industry or "",
            niche=niche or "",
        )
    except Exception as exc:
        logger.warning("Brand facts extraction failed (fallback) for %s: %s", url, exc)

    return {
        "source_url": url,
        "brand_name": brand_name,
        "industry": industry or "general",
        "niche": niche or "",
        "primary_color": "#0F1B3D",
        "secondary_color": "#00C2A8",
        "logo_url": favicon,
        "page_title": str(page.get("title") or ""),
        "description": str(page.get("description") or "")[:500],
        "provider": "fallback",
        "warning": "FIRECRAWL_API_KEY not set — colors/logo are estimated. Add Firecrawl for accurate brand extraction.",
        "brand_facts": brand_facts,
    }
