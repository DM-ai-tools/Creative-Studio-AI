"""Resolve brand / ClickTrends logo URLs for image and video overlays."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.services.logo_overlay import file_url_to_local_path

logger = logging.getLogger(__name__)

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _BACKEND_ROOT.parent


def _default_logo_file_candidates() -> list[Path]:
    names = (
        "clicktrends_logo.png",
        "clicktrends-logo.png",
        "Clicktrends_logo.png",
        "traffic-radius-logo.png",
    )
    dirs = (
        _ASSETS_DIR,
        _REPO_ROOT / "frontend" / "public",
        _BACKEND_ROOT / "assets",
    )
    out: list[Path] = []
    for d in dirs:
        for name in names:
            out.append((d / name).resolve())
    env_name = (settings.CLICKTRENDS_LOGO_FILE or "").strip()
    if env_name:
        p = Path(env_name)
        if not p.is_absolute():
            out.insert(0, (_BACKEND_ROOT / env_name).resolve())
            out.insert(0, (_ASSETS_DIR / Path(env_name).name).resolve())
        else:
            out.insert(0, p.resolve())
    return out


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def logos_from_brand_snapshot(snap: dict | None) -> tuple[str | None, str | None]:
    """Primary logo (dark backgrounds) + on-light variant from Brand + Brand Kit."""
    if not snap:
        return None, None
    on_light = snap.get("logo_on_light_url")
    if not on_light and isinstance(snap.get("logo_variations"), dict):
        on_light = snap["logo_variations"].get("on_light")
    return _first_non_empty(snap.get("logo_url")), _first_non_empty(on_light)


def resolve_video_logo_urls(
    *,
    brief: dict | None = None,
    brand: dict | None = None,
    logo_url: str | None = None,
    logo_on_light_url: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Logo for video burn-in from Brand Kit only:
    - brand.logo_url — main asset (typically light/white mark for dark video areas)
    - brand_kit.logo_variations.on_light — dark mark for white/light video areas
    Env / repo file fallbacks apply only when no brand logo is uploaded.
    """
    brand = brand or {}
    brief = brief or {}
    kb = brief.get("key_benefits")
    if not isinstance(kb, dict):
        kb = {}

    # on_light from brand snapshot (logo_variations dict stored in snap)
    snap_on_light = None
    if isinstance(brand.get("logo_variations"), dict):
        snap_on_light = brand["logo_variations"].get("on_light")

    # on_light from key_benefits (brand kit passed through brief)
    kit_variations = kb.get("logo_variations")
    kb_on_light = None
    if isinstance(kit_variations, dict):
        kb_on_light = kit_variations.get("on_light")

    resolved_logo = _first_non_empty(
        logo_url,
        brand.get("logo_url"),
        brief.get("logo_url"),
        kb.get("logo_url"),
    )
    resolved_on_light = _first_non_empty(
        logo_on_light_url,
        brand.get("logo_on_light_url"),
        snap_on_light,
        brief.get("logo_on_light_url"),
        kb_on_light,
    )

    if resolved_logo:
        logger.info(
            "Video logo from brand kit: primary=yes on_light=%s",
            "yes" if resolved_on_light else "no",
        )
        return resolved_logo, resolved_on_light

    default_url = (settings.DEFAULT_VIDEO_LOGO_URL or "").strip()
    if not default_url:
        for path in _default_logo_file_candidates():
            if path.is_file():
                default_url = str(path)
                logger.warning(
                    "No brand kit logo — using fallback file %s (upload logo on Brand Kit)",
                    path.name,
                )
                break

    return default_url or None, resolved_on_light


def logo_local_path(logo_url: str | None) -> Path | None:
    """Map /files/ URL, absolute path, or http(s) URL to a readable local file."""
    if not logo_url or not str(logo_url).strip():
        return None
    raw = str(logo_url).strip()

    local = file_url_to_local_path(raw)
    if local and local.is_file():
        return local

    if raw.startswith("/files/"):
        logger.error(
            "Brand kit logo file missing on disk: %s (re-upload on Brand Kit)",
            raw[:120],
        )
        return None

    path = Path(raw)
    if path.is_file():
        return path.resolve()

    upload_root = Path(settings.UPLOAD_DIR).resolve()
    under_uploads = upload_root / raw.lstrip("/\\")
    if under_uploads.is_file():
        return under_uploads

    if raw.startswith(("http://", "https://")):
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                resp = client.get(raw)
                resp.raise_for_status()
                suffix = ".png"
                ctype = (resp.headers.get("content-type") or "").lower()
                if "jpeg" in ctype or "jpg" in ctype:
                    suffix = ".jpg"
                elif "webp" in ctype:
                    suffix = ".webp"
                elif "svg" in ctype:
                    suffix = ".svg"
                tmp = Path(tempfile.mkstemp(suffix=suffix)[1])
                tmp.write_bytes(resp.content)
                return tmp
        except Exception:
            logger.exception("Failed to download logo from %s", raw[:80])
            return None

    return None
