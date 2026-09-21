"""Suggest competitor social accounts from client context — discovery only, no post analysis."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.services.competitor_social_service import _competitor_key, normalize_competitor_insights
from app.services.image_prompt_service import _get_openrouter_client
from app.services.sociavault_client import (
    fetch_facebook_profile,
    fetch_instagram_profile,
    parse_social_input,
)
from app.services.social_style_service import _first_str

logger = logging.getLogger(__name__)

_MAX_CANDIDATES = 8

# AU state → neighbouring states/territories (competitor search radius).
_NEARBY_AU_STATES: dict[str, list[str]] = {
    "VIC": ["VIC", "NSW", "SA", "TAS"],
    "NSW": ["NSW", "VIC", "QLD", "ACT"],
    "QLD": ["QLD", "NSW", "NT"],
    "WA": ["WA", "SA", "NT"],
    "SA": ["SA", "VIC", "WA", "NSW"],
    "TAS": ["TAS", "VIC"],
    "ACT": ["ACT", "NSW", "VIC"],
    "NT": ["NT", "QLD", "WA", "SA"],
}

_AU_STATE_ABBREV: dict[str, str] = {
    "western australia": "WA",
    "wa": "WA",
    "northern territory": "NT",
    "nt": "NT",
    "queensland": "QLD",
    "qld": "QLD",
    "new south wales": "NSW",
    "nsw": "NSW",
    "victoria": "VIC",
    "vic": "VIC",
    "south australia": "SA",
    "sa": "SA",
    "tasmania": "TAS",
    "tas": "TAS",
    "act": "ACT",
    "australian capital territory": "ACT",
    "perth": "WA",
    "darwin": "NT",
    "brisbane": "QLD",
    "gold coast": "QLD",
    "sunshine coast": "QLD",
    "cairns": "QLD",
    "townsville": "QLD",
    "toowoomba": "QLD",
    "sydney": "NSW",
    "newcastle": "NSW",
    "wollongong": "NSW",
    "central coast": "NSW",
    "hunter valley": "NSW",
    "melbourne": "VIC",
    "geelong": "VIC",
    "ballarat": "VIC",
    "bendigo": "VIC",
    "mornington peninsula": "VIC",
    "adelaide": "SA",
    "hobart": "TAS",
    "launceston": "TAS",
    "canberra": "ACT",
    "fremantle": "WA",
    "mandurah": "WA",
}

# Obvious non-local signals — skip profiles that look international when AU geo is set.
_FOREIGN_LOCATION_MARKERS = (
    "united states",
    "usa",
    "new york",
    "los angeles",
    "united kingdom",
    "london uk",
    " dubai",
    " singapore",
    " hong kong",
    " india",
    " canada",
    " worldwide shipping",
    " global brand",
)


def resolve_geography_scope(geography: str) -> dict[str, Any]:
    """
    Turn brief Service Location into a local competitor search radius.
    Example: Melbourne VIC → city Melbourne, state VIC, nearby NSW/SA/TAS.
    """
    raw = (geography or "").strip()
    if not raw:
        return {"has_scope": False, "raw": "", "scope_text": ""}

    low = raw.lower()
    if low in {"australia", "au", "nationwide", "national", "worldwide", "global"}:
        return {"has_scope": False, "raw": raw, "scope_text": ""}

    state = ""
    city = ""

    abbrev_match = re.search(r"\b(VIC|NSW|QLD|WA|SA|TAS|ACT|NT)\b", raw, flags=re.I)
    if abbrev_match:
        state = abbrev_match.group(1).upper()

    for place, st in sorted(_AU_STATE_ABBREV.items(), key=lambda x: -len(x[0])):
        if len(place) <= 3 and place.upper() == place:
            continue
        if place in low:
            city = place.title()
            if not state:
                state = st
            break

    if not state:
        for token in re.split(r"[\s,]+", low):
            st = _AU_STATE_ABBREV.get(token.strip())
            if st and len(token.strip()) <= 3:
                state = st
                break

    if not state and not city:
        return {
            "has_scope": True,
            "raw": raw,
            "city": "",
            "state": "",
            "allowed_states": [],
            "scope_text": (
                f"PRIMARY service area: {raw}, Australia.\n"
                "Suggest ONLY competitors that clearly serve this local area — "
                "no international or unrelated nationwide brands."
            ),
        }

    allowed_states = _NEARBY_AU_STATES.get(state, [state] if state else [])
    state_labels = ", ".join(allowed_states) if allowed_states else state

    if city and state:
        primary = f"{city}, {state}"
    elif state:
        primary = f"{state}, Australia"
    else:
        primary = raw

    scope_text = (
        f"PRIMARY service area: {primary}\n"
        f"ALLOWED regions ONLY: {state_labels} (Australia) — same state plus neighbouring states only.\n"
        f"Prefer competitors with a physical presence or clear service area in {city or state or raw}.\n"
        "STRICT: Do NOT suggest international brands, US/UK pages, or unrelated cities "
        f"(e.g. if market is Melbourne VIC, exclude Perth, Brisbane, London, New York competitors unless "
        f"they have a dedicated {city or state} local page)."
    )

    return {
        "has_scope": True,
        "raw": raw,
        "city": city,
        "state": state,
        "allowed_states": allowed_states,
        "scope_text": scope_text,
    }


def _profile_text_blob(profile: dict[str, Any]) -> str:
    parts = [
        _first_str(profile.get("name"), profile.get("full_name"), profile.get("username")),
        _first_str(
            profile.get("biography"),
            profile.get("bio"),
            profile.get("about"),
            profile.get("description"),
            profile.get("category"),
        ),
    ]
    loc = profile.get("location")
    if isinstance(loc, dict):
        parts.append(_first_str(loc.get("city"), loc.get("state"), loc.get("country"), loc.get("name")))
    elif isinstance(loc, str):
        parts.append(loc)
    return " ".join(p for p in parts if p).lower()


def _profile_likely_in_scope(profile: dict[str, Any], scope: dict[str, Any]) -> bool:
    """Lightweight filter — drop obvious international pages when AU geo is set."""
    if not scope.get("has_scope"):
        return True
    blob = _profile_text_blob(profile)
    if not blob:
        return True
    return not any(marker.strip() in blob for marker in _FOREIGN_LOCATION_MARKERS)


def empty_competitor_candidate() -> dict[str, Any]:
    return {
        "name": "",
        "platform": "",
        "handle": "",
        "profile_url": "",
        "reason": "",
        "confidence": "",
        "discovered_at": "",
        "source": "llm_discovery",
    }


def normalize_competitor_candidates(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, dict):
        return [raw] if raw.get("handle") or raw.get("name") else []
    if isinstance(raw, list):
        return [
            item
            for item in raw
            if isinstance(item, dict) and (item.get("handle") or item.get("name"))
        ]
    return []


def _slug_handle(value: str) -> str:
    raw = re.sub(r"^@+", "", (value or "").strip())
    raw = raw.split("/")[-1].split("?")[0].strip()
    return re.sub(r"[^a-zA-Z0-9._-]", "", raw)


async def _validate_social_page(
    *,
    platform: str,
    handle: str,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    plat = (platform or "facebook").strip().lower()
    handle_clean = _slug_handle(handle)
    if not handle_clean or len(handle_clean) < 2:
        return None
    try:
        if plat == "instagram":
            profile = await fetch_instagram_profile(handle_clean)
            if not isinstance(profile, dict):
                return None
            if scope and not _profile_likely_in_scope(profile, scope):
                return None
            name = _first_str(profile.get("full_name"), profile.get("username"), handle_clean)
            return {
                "name": name,
                "platform": "instagram",
                "handle": handle_clean,
                "profile_url": f"https://www.instagram.com/{handle_clean}/",
            }
        profile = await fetch_facebook_profile(handle_clean)
        if not isinstance(profile, dict):
            return None
        if scope and not _profile_likely_in_scope(profile, scope):
            return None
        name = _first_str(profile.get("name"), handle_clean)
        page_id = _first_str(profile.get("id"))
        profile_url = f"https://www.facebook.com/{handle_clean}/"
        if page_id:
            profile_url = f"https://www.facebook.com/{handle_clean}/"
        return {
            "name": name,
            "platform": "facebook",
            "handle": handle_clean,
            "profile_url": profile_url,
        }
    except Exception:
        logger.debug("Could not validate social page %s @%s", plat, handle_clean, exc_info=True)
        return None


async def _suggest_competitors_with_llm(
    *,
    brand_name: str,
    industry: str = "",
    niche: str = "",
    geography: str = "",
    client_platform: str = "",
    client_handle: str = "",
    client_bio: str = "",
    geo_scope: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not settings.OPENROUTER_API_KEY:
        return []

    scope = geo_scope or {}
    geo_rules = ""
    if scope.get("has_scope") and scope.get("scope_text"):
        geo_rules = (
            "\n\nGEOGRAPHY RESTRICTION (mandatory):\n"
            f"{scope['scope_text']}\n"
            "Every competitor MUST operate in the allowed regions above. "
            "Exclude worldwide, US, UK, or unrelated-AU-city brands."
        )

    system = (
        "You suggest REAL competitor social media pages for a client's ad strategy research. "
        "Return ONLY valid JSON:\n"
        '{"competitors":[{"name":"Brand Name","platform":"facebook|instagram","handle":"PageSlug",'
        '"reason":"why they compete IN THE SAME LOCAL AREA","confidence":"high|medium"}]}\n'
        "Rules:\n"
        "- Suggest 5-8 direct LOCAL competitors in the same niche/market\n"
        "- Use real public page slugs/handles (no spaces in handle)\n"
        "- Prefer the same platform as the client when possible\n"
        "- Do NOT include the client's own page\n"
        "- Handles must be plausible Facebook page names or Instagram usernames"
        f"{geo_rules}"
    )
    user = (
        f"Client brand: {brand_name}\n"
        f"Industry: {industry or 'general'}\n"
        f"Niche / campaign: {niche or 'not specified'}\n"
        f"Service location (authoritative): {scope.get('raw') or geography or 'not specified'}\n"
        f"Client social: {client_platform} @{client_handle}\n"
        f"Client bio/page context: {client_bio or '—'}\n"
    )

    try:
        client = _get_openrouter_client()
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL_CLAUDE or settings.OPENROUTER_MODEL_CLAUDE_SCRIPT,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.4,
            max_tokens=1200,
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        items = data.get("competitors") if isinstance(data, dict) else []
        if not isinstance(items, list):
            return []
        out: list[dict[str, Any]] = []
        for item in items[: _MAX_CANDIDATES + 4]:
            if not isinstance(item, dict):
                continue
            handle = _slug_handle(str(item.get("handle") or item.get("facebook_handle") or ""))
            if not handle:
                continue
            plat = str(item.get("platform") or client_platform or "facebook").strip().lower()
            if plat not in {"facebook", "instagram"}:
                plat = "facebook"
            out.append(
                {
                    "name": str(item.get("name") or handle).strip(),
                    "platform": plat,
                    "handle": handle,
                    "reason": str(item.get("reason") or "").strip(),
                    "confidence": str(item.get("confidence") or "medium").strip(),
                }
            )
        return out
    except Exception:
        logger.exception("Competitor discovery LLM failed")
        return []


async def discover_competitor_candidates(
    *,
    brand_name: str,
    industry: str = "",
    niche: str = "",
    geography: str = "",
    client_handle_or_url: str = "",
    client_platform: str = "",
    existing_insights: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Suggest competitor social pages from client context.
    Validates handles via SociaVault profile lookup — does NOT fetch posts.
    """
    geo_scope = resolve_geography_scope(geography)
    if not geo_scope.get("has_scope"):
        raise ValueError(
            "Set Service Location on the brief (e.g. Melbourne VIC) before fetching competitors — "
            "suggestions are limited to your city, state, and nearby states only."
        )

    client_plat = (client_platform or "").strip().lower()
    client_handle = ""
    client_bio = ""

    if (client_handle_or_url or "").strip():
        try:
            client_plat, client_handle = parse_social_input(
                platform=client_platform,
                handle_or_url=client_handle_or_url.strip(),
            )
        except ValueError:
            client_handle = _slug_handle(client_handle_or_url)

    if client_handle:
        try:
            if client_plat == "instagram":
                prof = await fetch_instagram_profile(client_handle)
            else:
                prof = await fetch_facebook_profile(
                    client_handle_or_url if client_handle_or_url.startswith("http") else client_handle
                )
            if isinstance(prof, dict):
                client_bio = _first_str(
                    prof.get("biography"),
                    prof.get("bio"),
                    prof.get("about"),
                    prof.get("description"),
                    prof.get("category"),
                )
                brand_name = brand_name or _first_str(prof.get("name"), prof.get("full_name"))
        except Exception:
            logger.debug("Client profile lookup for discovery context failed", exc_info=True)

    client_key = _competitor_key(client_plat, client_handle) if client_handle else ""
    analyzed_keys = {
        _competitor_key(str(i.get("platform") or ""), str(i.get("handle") or ""))
        for i in normalize_competitor_insights(existing_insights)
    }

    suggestions = await _suggest_competitors_with_llm(
        brand_name=brand_name,
        industry=industry,
        niche=niche,
        geography=geography,
        client_platform=client_plat,
        client_handle=client_handle,
        client_bio=client_bio,
        geo_scope=geo_scope,
    )

    if not suggestions:
        raise ValueError(
            "Could not suggest local competitors — ensure OPENROUTER_API_KEY is set and Service Location is set."
        )

    now = datetime.now(timezone.utc).isoformat()
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    service_area = geo_scope.get("raw") or geography

    for item in suggestions:
        plat = str(item.get("platform") or "facebook").lower()
        handle = _slug_handle(str(item.get("handle") or ""))
        if not handle:
            continue
        key = _competitor_key(plat, handle)
        if key in seen or key == client_key or key in analyzed_keys:
            continue
        seen.add(key)

        resolved = await _validate_social_page(platform=plat, handle=handle, scope=geo_scope)
        if not resolved:
            continue

        candidate = empty_competitor_candidate()
        candidate.update(resolved)
        candidate["reason"] = str(item.get("reason") or "").strip()
        candidate["confidence"] = str(item.get("confidence") or "medium").strip()
        candidate["discovered_at"] = now
        candidate["service_area"] = service_area
        validated.append(candidate)
        if len(validated) >= _MAX_CANDIDATES:
            break

    if not validated:
        raise ValueError(
            f"No local competitor pages found for {service_area} — try a broader nearby state or add manually."
        )
    return validated
