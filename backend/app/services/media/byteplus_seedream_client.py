"""BytePlus ModelArk Seedream image generation (same account as Seedance)."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.core.config import settings
from app.services.media.byteplus_seedance_client import (
    ark_base_url,
    ark_configured,
    ark_headers,
    map_aspect_to_ratio,
)

logger = logging.getLogger(__name__)

DEFAULT_SEEDREAM_50_LITE = "seedream-5-0-260128"
DEFAULT_SEEDREAM_50_PRO = "dola-seedream-5-0-pro-260628"
DEFAULT_SEEDREAM_50_FLASH = "dola-seedream-5-0-flash-260915"

SEEDREAM_CATALOG_IDS = frozenset(
    {
        "ark-seedream-5-0-lite",
        "ark-seedream-5-0-pro",
        "ark-seedream-5-0-flash",
        "byteplus-seedream-5-0-lite",
        "byteplus-seedream-5-0-pro",
        "byteplus-seedream-5-0-flash",
        "seedream-5-0-lite",
        "seedream-5-0-pro",
        "seedream-5-0-flash",
    }
)

_BYTEPLUS_TOS_HOST = re.compile(
    r"^https://ark-acg-[^/]+\.tos-[^/]+\.volces\.com/",
    re.IGNORECASE,
)


def seedream_50_lite_model() -> str:
    return (settings.ARK_SEEDREAM_50_LITE_MODEL or DEFAULT_SEEDREAM_50_LITE).strip()


def seedream_50_pro_model() -> str:
    return (settings.ARK_SEEDREAM_50_PRO_MODEL or DEFAULT_SEEDREAM_50_PRO).strip()


def seedream_50_flash_model() -> str:
    return (settings.ARK_SEEDREAM_50_FLASH_MODEL or DEFAULT_SEEDREAM_50_FLASH).strip()


def is_byteplus_seedream_model(model: str | None) -> bool:
    mid = (model or "").strip().lower().replace("_", "-")
    if not mid:
        return False
    if mid in SEEDREAM_CATALOG_IDS:
        return True
    if mid.startswith("seedream-") or mid.startswith("dola-seedream-"):
        return True
    return "seedream-5-0" in mid or "seedream-5.0" in mid


def resolve_seedream_api_model(model: str | None) -> str:
    mid = (model or "").strip().lower().replace("_", "-")
    if mid.startswith("seedream-") or mid.startswith("dola-seedream-"):
        return (model or "").strip()
    if "flash" in mid:
        return seedream_50_flash_model()
    if "pro" in mid:
        return seedream_50_pro_model()
    return seedream_50_lite_model()


def is_byteplus_ark_media_url(url: str | None) -> bool:
    """True for BytePlus ModelArk TOS URLs — pass unchanged to Seedance (same-account trust)."""
    u = (url or "").strip()
    return bool(u and _BYTEPLUS_TOS_HOST.match(u))


def map_format_to_size(format_type: str | None, aspect: str | None = None) -> str:
    ratio = map_aspect_to_ratio(aspect, format_type)
    if ratio in {"16:9", "21:9"}:
        return "1536x1024"
    if ratio in {"9:16", "3:4", "4:5"}:
        return "1024x1536"
    if ratio in {"4:3", "5:4"}:
        return "1536x1152"
    return "1024x1024"


def extract_image_url(body: dict[str, Any]) -> str | None:
    data = body.get("data")
    if isinstance(data, list) and data:
        row = data[0]
        if isinstance(row, dict):
            url = row.get("url") or row.get("image_url")
            if url:
                return str(url)
    content = body.get("content")
    if isinstance(content, dict):
        url = content.get("image_url") or content.get("url")
        if url:
            return str(url)
    for key in ("image_url", "output_url", "url"):
        if body.get(key):
            return str(body[key])
    return None


async def generate_seedream_image(
    client: httpx.AsyncClient,
    *,
    prompt: str,
    model: str | None = None,
    size: str = "1024x1024",
    reference_image_url: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    POST /images/generations — returns (image_url, raw_response_body).
    Reference images use the optional ``image`` field (i2i).
    """
    api_model = resolve_seedream_api_model(model)
    payload: dict[str, Any] = {
        "model": api_model,
        "prompt": prompt,
        "size": size,
        "response_format": "url",
        "watermark": False,
    }
    ref = (reference_image_url or "").strip()
    if ref:
        payload["image"] = ref

    url = f"{ark_base_url()}/images/generations"
    response = await client.post(
        url,
        json=payload,
        headers=ark_headers(api_model),
        timeout=180.0,
    )
    if response.status_code >= 400:
        body = (response.text or "")[:800]
        raise RuntimeError(f"BytePlus Seedream failed ({response.status_code}): {body}")
    body = response.json() if response.content else {}
    image_url = extract_image_url(body)
    if not image_url:
        raise RuntimeError(f"BytePlus Seedream returned no image URL: {body!r}"[:400])
    return image_url, body


def seedream_configured() -> bool:
    return ark_configured()
