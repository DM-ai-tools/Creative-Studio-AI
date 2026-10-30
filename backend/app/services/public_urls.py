"""Absolute URLs for exports, emails, and admin UI (same origin as the web app + /files proxy)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.core.config import settings


def public_app_origin() -> str:
    """Site origin where nginx/Next serves the app and proxies ``/files/*`` to the API."""
    explicit = (getattr(settings, "PUBLIC_APP_URL", None) or "").strip().rstrip("/")
    if explicit.startswith("http://") or explicit.startswith("https://"):
        return explicit
    origins = settings.CORS_ORIGINS or []
    for origin in origins:
        raw = str(origin).strip().rstrip("/")
        if raw.startswith("https://"):
            return raw
    for origin in origins:
        raw = str(origin).strip().rstrip("/")
        if raw.startswith("http://"):
            return raw
    return "http://localhost:3000"


def normalize_stored_file_url(raw: str) -> str:
    """Return ``/files/...`` path as stored in DB, or empty."""
    u = (raw or "").strip()
    if not u:
        return ""
    if u.startswith("http://") or u.startswith("https://"):
        if "/files/" in u:
            return "/files/" + u.split("/files/", 1)[1].split("?", 1)[0]
        return ""
    path = u if u.startswith("/") else f"/{u}"
    if not path.startswith("/files/"):
        return ""
    return path.split("?", 1)[0]


def absolute_media_url(raw: str) -> str:
    """Turn ``/files/tenant/...`` or full URL into a browser-openable HTTPS link."""
    u = (raw or "").strip()
    if not u:
        return ""
    if u.startswith("http://") or u.startswith("https://"):
        return u.split("?", 1)[0] if "/files/" in u else u
    base = public_app_origin()
    if u.startswith("/"):
        return f"{base}{u.split('?', 1)[0]}"
    return f"{base}/{u.lstrip('/').split('?', 1)[0]}"


def variant_library_url(variant_id: str | None) -> str:
    vid = (variant_id or "").strip()
    if not vid:
        return ""
    base = public_app_origin()
    return f"{base}/variants?variant={quote(vid, safe='')}"


def server_disk_path(stored_file_url: str) -> str:
    """Absolute path on the machine where the backend stores uploads (for local / IT review)."""
    norm = normalize_stored_file_url(stored_file_url)
    if not norm:
        return ""
    rel = norm[len("/files/") :].replace("/", os.sep)
    try:
        return str((Path(settings.UPLOAD_DIR).resolve() / rel))
    except (OSError, ValueError):
        return str(Path(settings.UPLOAD_DIR) / rel.replace("\\", "/"))


_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg")
_VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov", ".m4v", ".mkv", ".avi")


def _url_looks_like_video(url: str) -> bool:
    low = (url or "").lower().split("?", 1)[0]
    return any(low.endswith(ext) for ext in _VIDEO_EXTENSIONS)


def _url_looks_like_image(url: str) -> bool:
    low = (url or "").lower().split("?", 1)[0]
    return any(low.endswith(ext) for ext in _IMAGE_EXTENSIONS)


def pick_image_and_video_links(
    urls: list[str],
    *,
    extra: dict[str, Any] | None = None,
    operation: str = "",
    provider: str = "",
) -> tuple[str, str]:
    """Return (image_https_link, video_https_link) for manager-facing Excel columns."""
    extra = extra or {}
    op = (operation or "").lower()
    prov = (provider or "").lower()
    mt = str(extra.get("media_type") or "").strip().lower()

    images: list[str] = []
    videos: list[str] = []

    img_raw = extra.get("image_url")
    vid_raw = extra.get("video_url")
    if img_raw:
        images.append(absolute_media_url(str(img_raw)))
    if vid_raw:
        videos.append(absolute_media_url(str(vid_raw)))

    for u in urls:
        if not u:
            continue
        if _url_looks_like_video(u):
            videos.append(u)
        elif _url_looks_like_image(u):
            images.append(u)
        elif mt == "video" or "video" in op or (prov == "byteplus" and "video" in op):
            videos.append(u)
        elif mt == "image" or "image" in op:
            images.append(u)
        else:
            images.append(u)

    def _first_unique(items: list[str]) -> str:
        seen: set[str] = set()
        for item in items:
            if item and item not in seen:
                seen.add(item)
                return item
        return ""

    return _first_unique(images), _first_unique(videos)


def media_urls_from_extra(extra: dict[str, Any] | None) -> list[str]:
    if not extra:
        return []
    urls: list[str] = []
    for key in ("output_urls", "image_url", "video_url", "url", "file_url", "remote_url"):
        val = extra.get(key)
        if isinstance(val, list):
            urls.extend(str(x) for x in val if x)
        elif val:
            urls.append(str(val))
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        abs_u = absolute_media_url(u)
        if abs_u and abs_u not in seen:
            seen.add(abs_u)
            out.append(abs_u)
    return out
