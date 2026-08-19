"""SociaVault API client — fetch public social profiles and posts."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.sociavault.com"
_INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com"}
_FACEBOOK_HOSTS = {"facebook.com", "www.facebook.com", "fb.com", "www.fb.com"}


def _api_key() -> str:
    key = (settings.SOCIAVAULT_API_KEY or "").strip()
    if not key:
        raise ValueError(
            "SOCIAVAULT_API_KEY is not configured — add it to backend/.env and restart the server."
        )
    return key


def parse_social_input(
    *,
    platform: str = "",
    handle_or_url: str = "",
) -> tuple[str, str]:
    """
    Return (platform, handle_or_url_for_api).
    platform: instagram | facebook
    """
    raw = (handle_or_url or "").strip()
    if not raw:
        raise ValueError("Enter an Instagram or Facebook profile URL or handle.")

    plat = (platform or "").strip().lower()
    if raw.startswith("@") and not raw.startswith("http"):
        raw = raw.lstrip("@").strip()
        if not plat:
            plat = "instagram"
        return plat, raw

    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        host = (parsed.netloc or "").lower()
        path = (parsed.path or "").strip("/")
        segments = [s for s in path.split("/") if s and s not in {"p", "reel", "reels", "stories"}]
        if any(h in host for h in _INSTAGRAM_HOSTS):
            handle = segments[0] if segments else ""
            if not handle:
                raise ValueError("Could not read Instagram handle from URL.")
            return "instagram", handle
        if any(h in host for h in _FACEBOOK_HOSTS):
            handle = segments[0] if segments else ""
            if not handle:
                raise ValueError("Could not read Facebook page name from URL.")
            return "facebook", handle
        raise ValueError("URL must be an Instagram or Facebook profile link.")

    handle = re.sub(r"^@+", "", raw).strip()
    if not handle:
        raise ValueError("Invalid social handle.")
    if not plat:
        plat = "instagram"
    return plat, handle


async def _get(path: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
    base = (settings.SOCIAVAULT_BASE_URL or _BASE).rstrip("/")
    headers = {"X-API-Key": _api_key()}
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(f"{base}{path}", headers=headers, params=params or {})
        if response.status_code >= 400:
            body = response.text[:600]
            logger.warning("SociaVault %s failed (%s): %s", path, response.status_code, body)
            raise ValueError(f"SociaVault API error {response.status_code}: {body}")
        body = response.json()
        if not isinstance(body, dict):
            return {"success": True, "data": body}
        return body


def _unwrap_data(payload: dict[str, Any]) -> Any:
    if payload.get("success") is False:
        raise ValueError(str(payload.get("error") or payload.get("message") or "SociaVault request failed"))
    if "data" in payload:
        return payload["data"]
    return payload


def _extract_post_batch(data: Any) -> tuple[list[dict[str, Any]], str]:
    """Normalize SociaVault post payloads (list or numeric-key dict)."""
    batch: list[dict[str, Any]] = []
    next_cursor = ""
    if isinstance(data, list):
        batch = [item for item in data if isinstance(item, dict)]
    elif isinstance(data, dict):
        next_cursor = str(
            data.get("cursor") or data.get("next_cursor") or data.get("next_page_id") or ""
        ).strip()
        for key in ("posts", "items", "data", "edges"):
            val = data.get(key)
            if isinstance(val, list):
                batch = [item for item in val if isinstance(item, dict)]
                break
            if isinstance(val, dict):
                batch = [item for item in val.values() if isinstance(item, dict)]
                break
    return batch, next_cursor


async def fetch_instagram_profile(handle: str) -> dict[str, Any]:
    data = _unwrap_data(await _get("/v1/scrape/instagram/profile", params={"handle": handle}))
    return data if isinstance(data, dict) else {"raw": data}


async def fetch_instagram_posts(handle: str, *, max_pages: int = 2) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    cursor = ""
    for _ in range(max(1, max_pages)):
        params: dict[str, str] = {"handle": handle}
        if cursor:
            params["cursor"] = cursor
        data = _unwrap_data(await _get("/v1/scrape/instagram/posts", params=params))
        batch, next_cursor = _extract_post_batch(data)
        for item in batch:
            posts.append(item)
        if not next_cursor or not batch:
            break
        cursor = next_cursor
    return posts


async def fetch_facebook_profile(url_or_id: str) -> dict[str, Any]:
    if url_or_id.startswith("http"):
        params = {"url": url_or_id}
    else:
        params = {"url": f"https://www.facebook.com/{url_or_id.lstrip('/')}"}
    data = _unwrap_data(await _get("/v1/scrape/facebook/profile", params=params))
    return data if isinstance(data, dict) else {"raw": data}


async def fetch_facebook_posts(
    url_or_id: str,
    *,
    page_id: str = "",
    max_pages: int = 3,
) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    cursor = ""
    resolved_page_id = (page_id or "").strip()
    profile_url = ""
    if url_or_id.startswith("http"):
        profile_url = url_or_id
    elif url_or_id:
        profile_url = f"https://www.facebook.com/{url_or_id.lstrip('/')}"

    for _ in range(max(1, max_pages)):
        params: dict[str, str] = {}
        if resolved_page_id:
            params["pageId"] = resolved_page_id
        elif profile_url:
            params["url"] = profile_url
        else:
            break
        if cursor:
            params["cursor"] = cursor
        data = _unwrap_data(await _get("/v1/scrape/facebook/profile/posts", params=params))
        batch, next_cursor = _extract_post_batch(data)
        if isinstance(data, dict) and not resolved_page_id:
            resolved_page_id = str(data.get("pageId") or data.get("id") or "").strip()
        for item in batch:
            posts.append(item)
        if not next_cursor or not batch:
            break
        cursor = next_cursor
    return posts
