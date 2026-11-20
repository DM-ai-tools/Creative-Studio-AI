"""Draw one still image for a script shot that must show a screen, page or graphic.

Seedance draws writing badly, so shots that need readable content are made as pictures by an image
model (GPT Image 2 or Seedream), reviewed by the user, and then shown over the video for their few
seconds (see creative_studio_inserts.py). This follows the same provider path and usage recording
the app's own Creative Studio image jobs use.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_PROMPT_CHARS = 2500

# Text-in-image rules, in the spirit of the app's existing B-roll prompts: spelling must be right
# and generic sample content only.
STILL_PREFIX = (
    "Photoreal commercial still, framed to fill the whole picture. Any text, numbers or labels shown on a "
    "screen, page or sign must be real, correctly spelled English that is sharp and legible, kept short, "
    "using generic sample content and never real brand names. No gibberish, pseudo-text, malformed letters "
    "or random symbols, and no watermark. "
)


# Strict for every brand and every picture: the image model never draws a logo or the brand's name.
# The real logo is only ever placed afterwards from the uploaded file (creative_studio_still_logo.py).
# The brand's name is deliberately not mentioned here: naming it, even to forbid it, invites it.
NO_LOGO_RULE = (
    " STRICT: do not draw any logo, brand mark, wordmark, company or brand name, slogan, tagline, app icon "
    "or watermark anywhere in the picture, including on screens, signs, packaging, clothing, devices or "
    "walls, and no real-world company, product or website names or logos. Where a brand would appear, "
    "leave a plain blank or generic placeholder area."
)


# The same guardrail in one sentence, for prompts that must stay short (ad images in a brief).
NO_LOGO_SHORT = (
    " STRICT: do not draw the advertiser's logo, brand mark, wordmark, brand or company name, slogan or watermark "
    "anywhere (including on screens, signs, clothing and devices), and do not invent logos or brand names; leave a "
    "plain blank area instead. Software or product screens that the brief itself asks for are fine."
)


# Trailing words of a company name that people leave off ("Adoria Jewels" is just "Adoria").
_GENERIC_NAME_WORDS = {
    "jewels", "jewellery", "jewelry", "jewellers", "jewelers", "co", "company", "pty", "ltd", "limited", "inc",
    "llc", "group", "studio", "studios", "agency", "solutions", "services", "australia", "au", "the",
}


def scrub_brand_name(text: str, brand_name: str | None) -> tuple[str, bool]:
    """Take the active brand's name out of a picture prompt (the model would draw it as a wordmark).

    Catches the name as written, joined or hyphenated, as a possessive and as a web address. Single
    words of a multi-word name are left alone ("traffic" is also an ordinary word). Returns the new
    text and whether anything was removed.
    """
    import re

    name = " ".join((brand_name or "").split())
    if len(name) < 3:
        return text, False
    words = re.findall(r"\w+", name)  # unicode-aware: accented and non-Latin names count too
    if not words:
        return text, False
    separator = r"[\s\-_.&+]*"  # "Traffic Radius", "TrafficRadius", "Traffic-Radius", "Café Noir & Co"
    # The name as the Brand Kit has it ("Adoria Jewels") AND as people write it ("Adoria"): a strategy
    # file says "Adoria logo", not "Adoria Jewels logo". Only a trailing generic word is dropped, so
    # "Traffic Radius" never becomes the ordinary word "Traffic".
    spellings = [words]
    trimmed = list(words)
    while len(trimmed) > 1 and trimmed[-1].lower() in _GENERIC_NAME_WORDS:
        trimmed = trimmed[:-1]
        if len("".join(trimmed)) >= 5:  # a short alias would also hit ordinary words ("Blue Group" -> "blue")
            spellings.append(list(trimmed))
    alternatives = "|".join(
        separator.join(re.escape(w) for w in spelling) for spelling in sorted(spellings, key=lambda s: -len("".join(s)))
    )
    # name, then optional possessive / web-address ending ("Acme Co's", "acmeco.com.au", "www.acme.com")
    pattern = re.compile(
        rf"(?<!\w)(?:www\.)?(?:{alternatives})(?:\.(?:com|net|org|io|co|ai|app|in|au|uk)(?:\.[a-z]{{2}})?)?(?:['’]s)?(?!\w)",
        re.IGNORECASE,
    )
    # Deleted, not replaced by a stand-in phrase: any words left in the prompt can get printed on the
    # picture (a "the company" line once appeared under a CTA button).
    cleaned, count = pattern.subn("", text)
    if not count:
        return text, False
    cleaned = re.sub(r"""(["'“”‘’])\s*\1""", "", cleaned)  # quotes the name was alone inside
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip(), True


def format_for_aspect(aspect: str) -> str:
    """The provider's format name for a video aspect ratio (same mapping the job runner uses)."""
    value = (aspect or "9/16").replace(":", "/")
    if value in {"9/16", "1/4", "4/5"}:
        return "reel"
    if value == "16/9":
        return "video"
    if value == "4/3":
        return "carousel"
    return "static"


def is_still_model(model: str | None) -> bool:
    """Only the two image families the Creative Studio offers. Anything else is refused, because the
    provider lookup would otherwise quietly fall back to an unrelated service."""
    from app.services.media.byteplus_seedream_client import is_byteplus_seedream_model
    from app.services.media.openai_image_catalog import is_openai_image_model

    return bool(model) and (is_openai_image_model(model) or is_byteplus_seedream_model(model))


async def generate_still(
    *,
    tenant_id: str,
    prompt: str,
    model: str,
    aspect: str = "9/16",
    logo_corner: str | None = None,
    brand_name: str | None = None,
) -> dict[str, Any]:
    from app.services.creative_studio_still_logo import corner_prompt_rule

    text = " ".join((prompt or "").split())
    if not text:
        raise ValueError("Describe the picture to draw.")
    if len(text) > MAX_PROMPT_CHARS:
        raise ValueError(f"The picture description is too long ({MAX_PROMPT_CHARS} characters at most).")
    text, name_removed = scrub_brand_name(text, brand_name)
    # Ask the model to leave the chosen corner empty; the real logo is placed there afterwards.
    text += corner_prompt_rule(logo_corner) + NO_LOGO_RULE
    if not is_still_model(model):
        raise ValueError("Choose GPT Image 2 or a Seedream model to draw the still.")

    from app.services.file_service import file_service
    from app.services.media.registry import get_image_provider
    from app.services.usage_tracker import estimate_media_cost, record_media_generation

    # Providers can charge before returning bytes: prove the result can be saved first.
    file_service.assert_writable(tenant_id, "generated")
    provider = get_image_provider(model)
    result = await provider.generate(
        prompt=f"{STILL_PREFIX}{text}",
        tenant_id=tenant_id,
        model=model,
        format_type=format_for_aspect(aspect),
        reference_purpose="scene",
    )
    url = str((result or {}).get("url") or "").strip()
    ok = str((result or {}).get("status") or "") in {"done", "mock"} and bool(url)
    record_media_generation(
        provider=str((result or {}).get("provider") or "image"),
        model=model,
        operation="creative_studio_script_still",
        success=ok,
        error=str((result or {}).get("error") or "")[:2000] or None,
        extra={"media_type": "image", **({"output_urls": [url]} if url else {})},
        tenant_id=tenant_id,
    )
    if not ok:
        raise RuntimeError(str((result or {}).get("error") or "The image model did not return a picture. Try again."))
    _, credits = estimate_media_cost(provider=str(result.get("provider") or "image"), model=model)
    return {
        "url": url,
        "model": str(result.get("model") or model),
        "provider": result.get("provider"),
        "credits_estimate": credits or None,
        "note": " ".join(
            part
            for part in (
                result.get("note"),
                "The brand name was removed from the picture description so it is not drawn as a logo." if name_removed else "",
            )
            if part
        )
        or None,
    }
