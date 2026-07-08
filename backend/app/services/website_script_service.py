"""Fetch a webpage, extract its content, choose a script framework by duration,
and generate a timed avatar script with Claude."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.schemas.avatar_script import AvatarScriptRequest, AvatarScriptResponse
from app.services.avatar_script_service import WPS, generate_avatar_script

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Duration-based framework selection
# ---------------------------------------------------------------------------

FRAMEWORKS: dict[str, dict] = {
    "hook_cta": {
        "name": "Hook + CTA",
        "seconds": (5, 20),
        "description": "One punchy hook line then immediately the offer and CTA. No filler.",
        "structure": ["HOOK (one line)", "OFFER (one line)", "CTA (one line)"],
    },
    "hook_benefit_cta": {
        "name": "Hook → Benefit → CTA",
        "seconds": (20, 45),
        "description": "Open with a hook, state the single biggest benefit, close with CTA.",
        "structure": ["HOOK", "KEY BENEFIT", "CTA"],
    },
    "problem_solution_cta": {
        "name": "Problem → Solution → CTA",
        "seconds": (45, 90),
        "description": "Identify the viewer's pain point, present the product as the solution, CTA.",
        "structure": ["PROBLEM (relatable)", "SOLUTION (product)", "CTA"],
    },
    "pas": {
        "name": "Problem → Agitate → Solution → CTA",
        "seconds": (90, 150),
        "description": "Surface the problem, intensify the pain, reveal the solution, CTA.",
        "structure": ["PROBLEM", "AGITATE (deepen pain)", "SOLUTION", "CTA"],
    },
    "story_arc": {
        "name": "Story Arc (Before → Struggle → Discovery → After)",
        "seconds": (150, 300),
        "description": (
            "Tell a mini-story: life before the product, the struggle/frustration, "
            "discovering the product, life after with social proof, CTA."
        ),
        "structure": [
            "BEFORE (relatable status quo)",
            "STRUGGLE (pain points)",
            "DISCOVERY (product/brand introduction)",
            "AFTER (results / proof)",
            "CTA",
        ],
    },
}


def choose_framework(target_seconds: int) -> dict:
    """Return the most appropriate script framework for the given duration."""
    for fw in FRAMEWORKS.values():
        lo, hi = fw["seconds"]
        if lo <= target_seconds < hi:
            return fw
    # Default to story arc for very long videos
    return FRAMEWORKS["story_arc"]


# ---------------------------------------------------------------------------
# Website content extraction
# ---------------------------------------------------------------------------

_STRIP_TAGS = re.compile(r"<[^>]+>")
_COLLAPSE_WS = re.compile(r"\s{2,}")
_SCRIPT_STYLE = re.compile(
    r"<(script|style|noscript|nav|footer|header|aside)[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
_META_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_DESC = re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', re.IGNORECASE)
_OG_TITLE = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', re.IGNORECASE)
_OG_DESC = re.compile(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']', re.IGNORECASE)
_HEADING = re.compile(r"<h[1-3][^>]*>(.*?)</h[1-3]>", re.IGNORECASE | re.DOTALL)


def _extract_page_content(html: str, max_chars: int = 3000) -> dict:
    """Return a structured dict of the most useful text from the page."""
    title = (_OG_TITLE.search(html) or _META_TITLE.search(html))
    title = _STRIP_TAGS.sub("", title.group(1)).strip() if title else ""

    desc = (_OG_DESC.search(html) or _META_DESC.search(html))
    desc = desc.group(1).strip() if desc else ""

    headings = [_STRIP_TAGS.sub("", h).strip() for h in _HEADING.findall(html)][:10]

    # Strip noisy tags then get body text
    clean = _SCRIPT_STYLE.sub(" ", html)
    clean = _STRIP_TAGS.sub(" ", clean)
    clean = _COLLAPSE_WS.sub(" ", clean).strip()

    return {
        "title": title,
        "description": desc,
        "headings": headings,
        "body": clean[:max_chars],
    }


async def fetch_website_content(url: str) -> dict:
    """Fetch a URL and return extracted page content. Raises on network/parse error."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme: {parsed.scheme}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        html = response.text

    return _extract_page_content(html)


# ---------------------------------------------------------------------------
# Script generation from website content
# ---------------------------------------------------------------------------

async def generate_website_script(
    *,
    url: str,
    target_seconds: int,
    brand_name: str,
    product_name: str,
    offer: str,
    ad_copy_tone: str,
    cta: str,
    target_audience: str,
    avatar_label: str,
    voice_label: str,
    forbidden_words: list[str],
    variation: str = "default",
    performance_stats=None,
) -> tuple[AvatarScriptResponse, dict, dict]:
    """
    Fetch the page, pick a framework, generate the script.
    Returns (script_response, page_content, framework).
    """
    # 1. Fetch & extract
    page = await fetch_website_content(url)

    # 2. Pick framework
    framework = choose_framework(target_seconds)

    # 3. Build rich prompt for avatar script service
    page_summary = "\n".join(filter(None, [
        f"Page title: {page['title']}",
        f"Meta description: {page['description']}",
        f"Key headings: {' | '.join(page['headings'][:6])}",
        f"Page body (excerpt): {page['body'][:1500]}",
    ]))

    structure_steps = "\n".join(
        f"  {i+1}. {step}" for i, step in enumerate(framework["structure"])
    )

    script_prompt = (
        f"SCRIPT FRAMEWORK: {framework['name']}\n"
        f"Framework description: {framework['description']}\n"
        f"Structure to follow:\n{structure_steps}\n\n"
        f"WEBSITE CONTENT (use this as your source of truth for facts, benefits, and language):\n"
        f"{page_summary}\n\n"
        f"BRAND: {brand_name} — mention '{brand_name}' at least twice in the dialogue.\n"
        f"Never address the viewer by a personal name — always use 'you' / 'your business'.\n"
        f"Follow the framework structure strictly but make it sound natural, not templated.\n"
        f"AUSTRALIAN ENGLISH ONLY: warm Aussie accent, Australian spelling, local idioms — not American English."
    )

    if performance_stats:
        from app.services.stats_image_service import format_performance_stats_for_script

        stats_text = format_performance_stats_for_script(performance_stats)
        if stats_text.strip():
            script_prompt += (
                f"\n\nVERIFIED PERFORMANCE STATS (from uploaded dashboard — cite these exact "
                f"figures in proof/results beats):\n{stats_text}"
            )

    req = AvatarScriptRequest(
        purpose="avatar_script",
        product_name=product_name or page["title"],
        offer=offer or page["description"],
        brand_name=brand_name,
        target_audience=target_audience,
        ad_copy_tone=ad_copy_tone,
        cta=cta,
        target_seconds=target_seconds,
        avatar_label=avatar_label,
        voice_label=voice_label,
        forbidden_words=forbidden_words,
        variation=variation,
        script_prompt=script_prompt,
        performance_stats=performance_stats,
    )

    script = await generate_avatar_script(req)
    return script, page, framework
