"""
Extract verified business facts from a website for ad generation.

Business rule: ads may only claim what the brand's site actually states.
Anything missing stays blank — the LLM must use soft, non-numeric language.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# Hard cap — keep LLM context lean and focused on claimable facts.
_MAX_MARKDOWN_CHARS = 12_000

BrandFacts = dict[str, Any]


def empty_brand_facts() -> BrandFacts:
    return {
        "services": [],
        "products": [],
        "service_areas": [],
        "locations": [],
        "offers": [],
        "rates_or_pricing": [],
        "reviews": {
            "rating": None,
            "count": None,
            "source": None,
            "highlights": [],
        },
        "credentials": [],
        "years_in_business": None,
        "phone": None,
        "cta_phrases": [],
        "unique_selling_points": [],
        "do_not_claim": [],
        "source_summary": "",
        "confidence": "low",
    }


def format_brand_facts_for_llm(facts: BrandFacts | None) -> str:
    """Human-readable block injected into ICP / variant prompts."""
    if not facts or not isinstance(facts, dict):
        return ""
    lines: list[str] = [
        "VERIFIED BRAND FACTS (from the business website — ACCC whitelist):",
        "Use ONLY these facts for specific numbers, rates, review counts, service names, and locations.",
        "If a field is empty / null → do NOT invent it. Use soft language instead.",
        "",
    ]
    services = [str(s).strip() for s in (facts.get("services") or []) if str(s).strip()]
    products = _normalize_product_names(facts.get("products") or [])
    areas = [str(s).strip() for s in (facts.get("service_areas") or []) if str(s).strip()]
    locations = [str(s).strip() for s in (facts.get("locations") or []) if str(s).strip()]
    offers = [str(s).strip() for s in (facts.get("offers") or []) if str(s).strip()]
    rates = [str(s).strip() for s in (facts.get("rates_or_pricing") or []) if str(s).strip()]
    creds = [str(s).strip() for s in (facts.get("credentials") or []) if str(s).strip()]
    usps = [str(s).strip() for s in (facts.get("unique_selling_points") or []) if str(s).strip()]
    ctas = [str(s).strip() for s in (facts.get("cta_phrases") or []) if str(s).strip()]
    do_not = [str(s).strip() for s in (facts.get("do_not_claim") or []) if str(s).strip()]

    reviews = facts.get("reviews") if isinstance(facts.get("reviews"), dict) else {}
    rating = reviews.get("rating")
    count = reviews.get("count")
    source = reviews.get("source")
    highlights = [str(h).strip() for h in (reviews.get("highlights") or []) if str(h).strip()]

    lines.append(f"- Services offered: {', '.join(services) if services else '(not found on site)'}")
    lines.append(
        f"- Products / models on site: {', '.join(products[:12]) if products else '(not found on site)'}"
    )
    lines.append(f"- Service areas: {', '.join(areas) if areas else '(not found on site)'}")
    lines.append(f"- Business locations / suburbs: {', '.join(locations) if locations else '(not found on site)'}")
    lines.append(f"- Current offers / promos: {', '.join(offers) if offers else '(not found on site)'}")
    lines.append(f"- Rates / pricing stated on site: {', '.join(rates) if rates else '(none stated — do NOT invent rates)'}")
    if rating is not None or count is not None:
        bits = []
        if rating is not None:
            bits.append(f"{rating}★")
        if count is not None:
            bits.append(f"{count} reviews")
        if source:
            bits.append(f"on {source}")
        lines.append(f"- Reviews: {' '.join(bits)}")
    else:
        lines.append("- Reviews: (not found — do NOT invent customer counts or star ratings)")
    if highlights:
        lines.append(f"- Review highlights: {'; '.join(highlights[:3])}")
    lines.append(f"- Credentials / licences: {', '.join(creds) if creds else '(not found)'}")
    years = facts.get("years_in_business")
    lines.append(
        f"- Years in business: {years}"
        if years
        else "- Years in business: (not found — do NOT invent 'serving for X years')"
    )
    if facts.get("phone"):
        lines.append(f"- Phone: {facts.get('phone')}")
    if ctas:
        lines.append(f"- Site CTAs: {', '.join(ctas[:5])}")
    if usps:
        lines.append(f"- USPs stated on site: {'; '.join(usps[:6])}")
    if do_not:
        lines.append(f"- DO NOT CLAIM (missing or unverified): {'; '.join(do_not)}")
    summary = str(facts.get("source_summary") or "").strip()
    if summary:
        lines.append(f"- Site summary: {summary[:400]}")
    conf = str(facts.get("confidence") or "low")
    lines.append(f"- Extraction confidence: {conf}")
    return "\n".join(lines)


def brand_facts_whitelist_text(facts: BrandFacts | None) -> str:
    """Flatten all claimable strings for ACCC post-processor whitelist matching."""
    if not facts or not isinstance(facts, dict):
        return ""
    parts: list[str] = []
    for key in ("services", "products", "service_areas", "locations", "offers", "rates_or_pricing", "credentials", "unique_selling_points", "cta_phrases", "do_not_claim"):
        for item in facts.get(key) or []:
            parts.append(str(item))
    reviews = facts.get("reviews") if isinstance(facts.get("reviews"), dict) else {}
    if reviews.get("rating") is not None:
        parts.append(str(reviews.get("rating")))
    if reviews.get("count") is not None:
        parts.append(str(reviews.get("count")))
    for h in reviews.get("highlights") or []:
        parts.append(str(h))
    if facts.get("years_in_business"):
        parts.append(str(facts.get("years_in_business")))
    if facts.get("phone"):
        parts.append(str(facts.get("phone")))
    if facts.get("source_summary"):
        parts.append(str(facts.get("source_summary")))
    return " ".join(parts)


def _normalize_product_names(raw: Any) -> list[str]:
    """Flatten scraped product entries to display names."""
    names: list[str] = []
    if not raw:
        return names
    items = raw if isinstance(raw, list) else [raw]
    for item in items:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("title") or "").strip()
        else:
            name = str(item or "").strip()
        if name and name.lower() not in {"product", "products", "shop", "buy now"}:
            names.append(name[:120])
    return list(dict.fromkeys(names))[:20]


def _heuristic_extract_products(text: str) -> list[str]:
    """Best-effort product/model names from shop markdown."""
    names: list[str] = []
    for m in re.finditer(r"\[([^\]\n]{3,80})\]\([^)]+\)", text or ""):
        label = m.group(1).strip()
        if _looks_like_nav_or_category(label):
            continue
        if re.search(r"(?i)(add to cart|shop now|view|learn more|read more)$", label):
            continue
        names.append(label)
    for m in re.finditer(
        r"(?im)^(?:#{1,4}\s*|\*\*)\s*([A-Z0-9][\w\s+\-./]{2,60}?)\s*(?:\*\*)?\s*$",
        text or "",
    ):
        label = m.group(1).strip()
        if _looks_like_nav_or_category(label):
            continue
        if re.search(r"(?i)(collection|category|menu|footer|header|blog|about)", label):
            continue
        names.append(label)
    return list(dict.fromkeys(names))[:16]


def _looks_like_nav_or_category(name: str) -> bool:
    n = (name or "").strip()
    if not n or len(n) < 2:
        return True
    low = n.lower()
    if low in {"home", "about", "contact", "blog", "faq", "cart", "checkout", "account"}:
        return True
    return bool(_CATEGORY_LABEL_RE.search(n))


_CATEGORY_LABEL_RE = re.compile(
    r"(?i)^(shop|buy|browse|collections?|kids?|children|men|women|sale|new)\b|"
    r"^(bikes?|parts|accessories|services?)$"
)


def _heuristic_extract(markdown: str, *, brand_name: str = "") -> BrandFacts:
    """Cheap regex pass when LLM is unavailable — better than nothing for a businessman demo."""
    facts = empty_brand_facts()
    text = markdown or ""
    lower = text.lower()

    # Rates e.g. 5.89% p.a.
    rates = re.findall(
        r"\b\d{1,2}\.\d{1,2}\s*%\s*(?:p\.?\s*a\.?|per\s+(?:annum|year))?(?:\s*(?:comparison|variable|fixed))?",
        text,
        flags=re.I,
    )
    facts["rates_or_pricing"] = list(dict.fromkeys(r.strip() for r in rates))[:6]

    # Google / review snippets
    rating_m = re.search(r"(\d(?:\.\d)?)\s*(?:out of\s*5|/5)?\s*(?:stars?|★)", text, re.I)
    count_m = re.search(
        r"(\d{1,5})\s*(?:\+|plus)?\s*(?:google\s+)?(?:reviews?|ratings?)",
        text,
        re.I,
    )
    if rating_m:
        try:
            facts["reviews"]["rating"] = float(rating_m.group(1))
        except ValueError:
            pass
    if count_m:
        try:
            facts["reviews"]["count"] = int(count_m.group(1).replace(",", ""))
        except ValueError:
            pass
    if "google" in lower and (facts["reviews"]["rating"] or facts["reviews"]["count"]):
        facts["reviews"]["source"] = "Google"

    # AU service areas / cities
    city_hits = []
    for city in (
        "Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Hobart", "Canberra", "Darwin",
        "Gold Coast", "Sunshine Coast", "Newcastle", "Wollongong", "Geelong", "Cairns",
        "Townsville", "Mandurah", "Fremantle", "Parramatta", "Blacktown", "Penrith",
    ):
        if re.search(rf"\b{re.escape(city)}\b", text, re.I):
            city_hits.append(city)
    facts["service_areas"] = city_hits[:8]
    facts["locations"] = city_hits[:5]

    # Common trade / finance service keywords
    service_kw = [
        ("split system", "Split-system air conditioning"),
        ("ducted", "Ducted air conditioning"),
        ("air conditioning", "Air conditioning"),
        ("hvac", "HVAC"),
        ("plumbing", "Plumbing"),
        ("hot water", "Hot water systems"),
        ("electrical", "Electrical"),
        ("refinance", "Home loan refinance"),
        ("first home", "First home buyer loans"),
        ("investment loan", "Investment loans"),
        ("dental implant", "Dental implants"),
        ("root canal", "Root canal"),
        ("whitening", "Teeth whitening"),
    ]
    found_services = []
    for kw, label in service_kw:
        if kw in lower:
            found_services.append(label)
    facts["services"] = list(dict.fromkeys(found_services))[:10]
    facts["products"] = _heuristic_extract_products(text)

    # Offers
    offer_hits = re.findall(
        r"(?:free\s+(?:quote|consultation|assessment|call.?out)|no\s+call.?out\s+fee|"
        r"same.?day\s+(?:service|install)|%\s*off|discount\s+on\s+[\w\s]{3,30})",
        text,
        flags=re.I,
    )
    facts["offers"] = list(dict.fromkeys(o.strip() for o in offer_hits))[:6]

    years_m = re.search(
        r"(?:over|more than|serving|established|since)\s+(?:19|20)?(\d{2,4})\s*(?:years)?",
        text,
        re.I,
    )
    if years_m:
        raw = years_m.group(0)
        facts["years_in_business"] = raw.strip()[:40]

    phone_m = re.search(r"(?:\+?61\s*)?(?:\(0\d\)|0\d)\s*\d{4}\s*\d{4}", text)
    if phone_m:
        facts["phone"] = phone_m.group(0).strip()

    missing = []
    if not facts["rates_or_pricing"]:
        missing.append("specific interest rates or fixed prices")
    if not facts["reviews"]["count"] and not facts["reviews"]["rating"]:
        missing.append("review ratings or customer counts")
    if not facts["years_in_business"]:
        missing.append("years in business")
    facts["do_not_claim"] = missing
    facts["source_summary"] = (f"{brand_name}: " if brand_name else "") + text[:220].replace("\n", " ").strip()
    facts["confidence"] = "medium" if (facts["services"] or facts["rates_or_pricing"] or facts["reviews"]["count"]) else "low"
    return facts


def _merge_facts(base: BrandFacts, overlay: BrandFacts) -> BrandFacts:
    out = empty_brand_facts()
    out.update(base)
    for key in ("services", "products", "service_areas", "locations", "offers", "rates_or_pricing", "credentials", "unique_selling_points", "cta_phrases", "do_not_claim"):
        merged = list(dict.fromkeys(
            [*(str(x).strip() for x in (base.get(key) or []) if str(x).strip()),
             *(str(x).strip() for x in (overlay.get(key) or []) if str(x).strip())]
        ))
        out[key] = merged[:20 if key == "products" else 12]
    br = base.get("reviews") if isinstance(base.get("reviews"), dict) else {}
    orr = overlay.get("reviews") if isinstance(overlay.get("reviews"), dict) else {}
    out["reviews"] = {
        "rating": orr.get("rating") if orr.get("rating") is not None else br.get("rating"),
        "count": orr.get("count") if orr.get("count") is not None else br.get("count"),
        "source": orr.get("source") or br.get("source"),
        "highlights": list(dict.fromkeys(
            [*(str(h) for h in (br.get("highlights") or [])),
             *(str(h) for h in (orr.get("highlights") or []))]
        ))[:5],
    }
    out["years_in_business"] = overlay.get("years_in_business") or base.get("years_in_business")
    out["phone"] = overlay.get("phone") or base.get("phone")
    out["source_summary"] = overlay.get("source_summary") or base.get("source_summary")
    out["confidence"] = overlay.get("confidence") or base.get("confidence") or "low"
    return out


async def extract_brand_facts(
    *,
    markdown: str,
    brand_name: str = "",
    page_title: str = "",
    industry: str = "",
    niche: str = "",
) -> BrandFacts:
    """
    Extract claimable business facts from site markdown.

    Uses LLM when available; always merges heuristic catches (rates, review counts)
    so we don't miss numbers the model softens away.
    """
    md = (markdown or "").strip()
    if not md:
        return empty_brand_facts()
    clipped = md[:_MAX_MARKDOWN_CHARS]
    heuristic = _heuristic_extract(clipped, brand_name=brand_name)

    if not settings.OPENROUTER_API_KEY:
        return heuristic

    try:
        from app.services.image_prompt_service import _get_openrouter_client

        client = _get_openrouter_client()
        system = (
            "You extract VERIFIED advertising facts from an Australian business website. "
            "Return ONLY JSON. Rules:\n"
            "1. Only include facts clearly stated on the page — never invent.\n"
            "2. If a rate, review count, year count, or award is not explicit → leave null / empty.\n"
            "3. Prefer specific service names (e.g. 'Split-system installation') over vague marketing fluff.\n"
            "4. service_areas = suburbs/cities/regions they say they serve.\n"
            "5. products = specific product/model/SKU names listed on the page (e.g. bike models, jewellery pieces, SKUs). "
            "Use exact names from the site — never invent.\n"
            "6. rates_or_pricing = only numeric rates/prices written on the page.\n"
            "7. do_not_claim = list of claim types NOT supported by this page "
            "(e.g. 'customer volume', 'interest rate', 'years of experience').\n"
            "8. confidence = high|medium|low based on how much concrete commercial detail is present.\n"
            "JSON shape:\n"
            "{"
            '"services":[],"products":[],"service_areas":[],"locations":[],"offers":[],'
            '"rates_or_pricing":[],'
            '"reviews":{"rating":null,"count":null,"source":null,"highlights":[]},'
            '"credentials":[],"years_in_business":null,"phone":null,'
            '"cta_phrases":[],"unique_selling_points":[],"do_not_claim":[],'
            '"source_summary":"","confidence":"low"'
            "}"
        )
        user = (
            f"Brand: {brand_name or 'Unknown'}\n"
            f"Page title: {page_title or ''}\n"
            f"Industry hint: {industry or ''}\n"
            f"Niche hint: {niche or ''}\n\n"
            f"WEBSITE MARKDOWN:\n{clipped}"
        )
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL_CLAUDE or settings.OPENROUTER_MODEL_OPENAI,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=1200,
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        if not isinstance(data, dict):
            return heuristic
        llm_facts = empty_brand_facts()
        for key in (
            "services", "products", "service_areas", "locations", "offers", "rates_or_pricing",
            "credentials", "unique_selling_points", "cta_phrases", "do_not_claim",
        ):
            val = data.get(key)
            if isinstance(val, list):
                if key == "products":
                    llm_facts[key] = _normalize_product_names(val)
                else:
                    llm_facts[key] = [str(x).strip() for x in val if str(x).strip()][:12]
        rev = data.get("reviews") if isinstance(data.get("reviews"), dict) else {}
        llm_facts["reviews"] = {
            "rating": rev.get("rating"),
            "count": rev.get("count"),
            "source": rev.get("source"),
            "highlights": [str(h).strip() for h in (rev.get("highlights") or []) if str(h).strip()][:5],
        }
        llm_facts["years_in_business"] = data.get("years_in_business")
        llm_facts["phone"] = data.get("phone")
        llm_facts["source_summary"] = str(data.get("source_summary") or "")[:400]
        llm_facts["confidence"] = str(data.get("confidence") or "medium")
        return _merge_facts(heuristic, llm_facts)
    except Exception as exc:
        logger.warning("Brand facts LLM extract failed — using heuristics: %s", exc)
        return heuristic
