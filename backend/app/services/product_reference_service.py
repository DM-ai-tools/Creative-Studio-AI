"""Resolve ecommerce product URLs/slugs into tenant-owned image references."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.services.media_content import image_suffix_and_type

_MAX_HTML_BYTES = 4_000_000
_MAX_IMAGE_BYTES = 12_000_000
_IMAGE_RE = re.compile(r"""<meta[^>]+(?:property|name)=["'](?:og:image|twitter:image)["'][^>]+content=["']([^"']+)["']""", re.I)
_LINK_IMAGE_RE = re.compile(r"""<link[^>]+rel=["'][^"']*image_src[^"']*["'][^>]+href=["']([^"']+)["']""", re.I)


def _safe_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Product URL or slug is required")
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a valid public product URL or slug")
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Private product URLs are not allowed")
    try:
        for result in socket.getaddrinfo(host, None):
            address = ipaddress.ip_address(result[4][0])
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                raise ValueError("Private product URLs are not allowed")
    except socket.gaierror as exc:
        raise ValueError("Could not resolve the product website") from exc
    return raw


def _jsonld_images(html: str, page_url: str) -> list[str]:
    found: list[str] = []
    for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S):
        try:
            data: Any = json.loads(unescape(raw).strip())
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop(0)
            if not isinstance(item, dict):
                continue
            image = item.get("image")
            values = image if isinstance(image, list) else [image]
            for value in values:
                if isinstance(value, dict):
                    value = value.get("url") or value.get("contentUrl")
                if isinstance(value, str) and value.strip():
                    found.append(urljoin(page_url, value.strip()))
            stack.extend(item.get("@graph") or [])
    return found


async def resolve_product_reference(source: str) -> dict[str, Any]:
    page_url = _safe_url(source)
    headers = {"User-Agent": "CreativeStudioAI Product Reference/1.0"}
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
        response = await client.get(page_url)
        response.raise_for_status()
        html = response.content[:_MAX_HTML_BYTES].decode(response.encoding or "utf-8", errors="ignore")
        final_url = str(response.url)

        candidates: list[str] = []
        candidates.extend(_jsonld_images(html, final_url))
        candidates.extend(
            urljoin(final_url, value)
            for value in _IMAGE_RE.findall(html) + _LINK_IMAGE_RE.findall(html)
        )
        candidates.extend(
            urljoin(final_url, value)
            for value in re.findall(r'<img[^>]+(?:src|data-src)=["\']([^"\']+)["\']', html, re.I)
        )
        seen: set[str] = set()
        for image_url in candidates:
            if image_url in seen:
                continue
            seen.add(image_url)
            try:
                image_response = await client.get(image_url)
                image_response.raise_for_status()
                raw = image_response.content
                if len(raw) > _MAX_IMAGE_BYTES:
                    continue
                suffix, mime = image_suffix_and_type(raw)
                return {
                    "source_url": page_url,
                    "final_url": final_url,
                    "image_url": image_url,
                    "image_bytes": raw,
                    "suffix": suffix,
                    "mime_type": mime,
                    "slug": urlparse(final_url).path.rstrip("/").split("/")[-1],
                }
            except Exception:
                continue
    raise ValueError("No usable product image was found on that page")
