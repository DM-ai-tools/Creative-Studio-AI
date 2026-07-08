"""Upload local images to HeyGen Assets API for Video Agent file attachments."""

from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path

import httpx

from app.services.brand_logo import logo_local_path
from app.services.http_retry import async_request_with_retry

logger = logging.getLogger(__name__)

_MAX_BASE64_BYTES = 4 * 1024 * 1024  # prefer asset upload above this


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    if mime and mime.startswith("image/"):
        return mime
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


async def upload_image_to_heygen(
    client: httpx.AsyncClient,
    base: str,
    headers: dict[str, str],
    image_path: Path,
) -> str | None:
    """POST /v3/assets — returns asset_id or None on failure."""
    if not image_path.is_file():
        return None
    mime = _guess_mime(image_path)
    try:
        with image_path.open("rb") as fh:
            resp = await async_request_with_retry(
                client,
                "POST",
                f"{base.rstrip('/')}/v3/assets",
                headers=headers,
                files={"file": (image_path.name, fh, mime)},
                label="HeyGen asset upload",
            )
        if resp.status_code >= 400:
            logger.warning(
                "HeyGen asset upload failed (%s): %s",
                resp.status_code,
                resp.text[:300],
            )
            return None
        data = (resp.json() or {}).get("data") or {}
        asset_id = str(data.get("asset_id") or "").strip()
        if asset_id:
            logger.info("HeyGen asset uploaded: %s (%s)", asset_id[:24], image_path.name)
        return asset_id or None
    except Exception:
        logger.exception("HeyGen asset upload error for %s", image_path.name)
        return None


def _base64_file_entry(image_path: Path) -> dict | None:
    if not image_path.is_file():
        return None
    raw = image_path.read_bytes()
    if len(raw) > 32 * 1024 * 1024:
        logger.warning("Stats image too large for HeyGen base64 (%s bytes)", len(raw))
        return None
    return {
        "type": "base64",
        "media_type": _guess_mime(image_path),
        "data": base64.b64encode(raw).decode("ascii"),
    }


async def build_heygen_file_attachment(
    client: httpx.AsyncClient,
    base: str,
    headers: dict[str, str],
    image_url: str | None,
) -> dict | None:
    """
    Resolve a /files/ or http(s) URL to a HeyGen files[] entry.
    Prefers asset_id upload; falls back to base64 for small local files.
    """
    if not image_url or not str(image_url).strip():
        return None

    local = logo_local_path(str(image_url).strip())
    if not local or not local.is_file():
        logger.warning("Stats image not found on disk: %s", str(image_url)[:120])
        return None

    asset_id = await upload_image_to_heygen(client, base, headers, local)
    if asset_id:
        return {"type": "asset_id", "asset_id": asset_id}

    if local.stat().st_size <= _MAX_BASE64_BYTES:
        entry = _base64_file_entry(local)
        if entry:
            logger.info("HeyGen stats image attached via base64 (%s)", local.name)
            return entry

    return None


async def build_heygen_file_attachments(
    client: httpx.AsyncClient,
    base: str,
    headers: dict[str, str],
    image_urls: list[str],
) -> list[dict]:
    """Resolve multiple image URLs to HeyGen files[] entries."""
    entries: list[dict] = []
    seen: set[str] = set()
    for url in image_urls:
        u = str(url or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        entry = await build_heygen_file_attachment(client, base, headers, u)
        if entry:
            entries.append(entry)
    return entries
