"""Resolve brand / ClickTrends logo URLs for image and video overlays."""

from __future__ import annotations

import io
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

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


def _has_active_client_brand(brand: dict | None, brief: dict | None) -> bool:
    """True when generating for a saved client brand (not a generic/demo run)."""
    brand = brand or {}
    brief = brief or {}
    kb = brief.get("key_benefits") if isinstance(brief.get("key_benefits"), dict) else {}
    return bool(
        _first_non_empty(
            brand.get("brand_name"),
            brief.get("brand_name"),
            brief.get("brand_id"),
            kb.get("brand_id"),
        )
    )


def _collect_logo_url_candidates(
    *,
    brand: dict | None = None,
    brief: dict | None = None,
    logo_url: str | None = None,
    logo_on_light_url: str | None = None,
) -> tuple[str | None, str | None]:
    """Gather primary + on-light logo URLs from brand, brief, and kit variations."""
    brand = brand or {}
    brief = brief or {}
    kb = brief.get("key_benefits") if isinstance(brief.get("key_benefits"), dict) else {}

    variations = brand.get("logo_variations") if isinstance(brand.get("logo_variations"), dict) else {}
    kit_variations = kb.get("logo_variations") if isinstance(kb.get("logo_variations"), dict) else {}

    primary = _first_non_empty(
        logo_url,
        brand.get("logo_url"),
        brief.get("logo_url"),
        kb.get("logo_url"),
        variations.get("primary"),
        variations.get("default"),
    )
    on_light = _first_non_empty(
        logo_on_light_url,
        brand.get("logo_on_light_url"),
        variations.get("on_light"),
        kit_variations.get("on_light"),
        brief.get("logo_on_light_url"),
        kb.get("logo_on_light_url"),
    )
    # Scraped full-colour marks often live in logo_url; on-light slot may hold the dark variant.
    if not primary:
        primary = on_light
    if not on_light:
        on_light = primary
    return primary, on_light


def ensure_composable_logo_urls(
    logo_url: str | None,
    logo_on_light_url: str | None = None,
    *,
    tenant_id: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Ensure logo URLs resolve to raster files for overlay.
    Re-persists remote http(s) logos at generation time when needed.
    """
    def _ensure_one(url: str | None) -> str | None:
        if not url:
            return None
        # Stable local copy is best for compositing — persist remote URLs first.
        if url.startswith(("http://", "https://")) and tenant_id:
            persisted = persist_remote_logo_url(url, tenant_id=tenant_id)
            if persisted:
                p, _ = resolve_overlay_logo_paths(persisted, None)
                if p:
                    return persisted
        primary_path, _ = resolve_overlay_logo_paths(url, None, tenant_id=tenant_id)
        if primary_path:
            if url.startswith("/files/"):
                return url
            if tenant_id and url.startswith(("http://", "https://")):
                persisted = persist_remote_logo_url(url, tenant_id=tenant_id)
                if persisted:
                    return persisted
            return url
        if url.startswith("/files/"):
            logger.error(
                "Brand kit logo file missing or unreadable on disk: %s (re-upload PNG/JPG on Brand Kit)",
                url[:120],
            )
        return None

    primary = _ensure_one(logo_url)
    on_light = _ensure_one(logo_on_light_url)
    if not primary:
        primary = _ensure_one(logo_on_light_url)
    if not on_light:
        on_light = _ensure_one(logo_url)
    if primary and not on_light:
        on_light = primary
    elif on_light and not primary:
        primary = on_light
    return primary, on_light


def resolve_video_logo_urls(
    *,
    brief: dict | None = None,
    brand: dict | None = None,
    logo_url: str | None = None,
    logo_on_light_url: str | None = None,
    tenant_id: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Logo for video burn-in from Brand Kit only:
    - brand.logo_url — main asset (typically light/white mark for dark video areas)
    - brand_kit.logo_variations.on_light — dark mark for white/light video areas
    Env / repo file fallbacks apply only when no brand logo is uploaded.
    """
    brand = brand or {}
    brief = brief or {}

    resolved_logo, resolved_on_light = _collect_logo_url_candidates(
        brand=brand,
        brief=brief,
        logo_url=logo_url,
        logo_on_light_url=logo_on_light_url,
    )

    if resolved_logo or resolved_on_light:
        comp_primary, comp_on_light = ensure_composable_logo_urls(
            resolved_logo,
            resolved_on_light,
            tenant_id=tenant_id,
        )
        if comp_primary or comp_on_light:
            logger.info(
                "Brand kit logo ready for overlay: primary=%s on_light=%s",
                "yes" if comp_primary else "no",
                "yes" if comp_on_light else "no",
            )
            return comp_primary, comp_on_light
        if _has_active_client_brand(brand, brief):
            logger.warning(
                "Brand kit logo URL exists but is not compositable for %s — "
                "re-upload PNG/JPG on Brand Kit (SVG/remote URLs may fail)",
                _first_non_empty(brand.get("brand_name"), brief.get("brand_name")) or "unknown",
            )
            return None, None

    if _has_active_client_brand(brand, brief):
        logger.warning(
            "No compositable logo for client brand %s — skipping logo overlay "
            "(upload PNG/JPG on Brand Kit; never use platform default logo)",
            _first_non_empty(brand.get("brand_name"), brief.get("brand_name")) or "unknown",
        )
        return None, resolved_on_light

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


_RASTER_LOGO_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})


def _is_raster_logo_path(path: Path | None) -> bool:
    return bool(path and path.is_file() and path.suffix.lower() in _RASTER_LOGO_SUFFIXES)


def resolve_overlay_logo_paths(
    logo_url: str | None,
    logo_on_light_url: str | None = None,
    *,
    allow_platform_fallback: bool = False,
    tenant_id: str | None = None,
) -> tuple[Path | None, Path | None]:
    """
    Resolve readable raster logo files for still-image compositing.
    SVG logos are auto-converted to PNG. Never inject Traffic Radius / ClickTrends
    platform logos unless allow_platform_fallback is True.
    """
    if not logo_url and not logo_on_light_url:
        return None, None

    def _resolve_one(url: str | None) -> Path | None:
        if not url:
            return None
        path = logo_local_path(url)
        if not path:
            return None
        return _path_to_raster_logo(path, tenant_id=tenant_id, source_url=url)

    primary = _resolve_one(logo_url)
    on_light = _resolve_one(logo_on_light_url) if logo_on_light_url else None

    if not primary and on_light:
        primary = on_light
        on_light = None

    if not primary:
        if allow_platform_fallback:
            for candidate in _default_logo_file_candidates():
                if _is_raster_logo_path(candidate):
                    logger.warning(
                        "Brand logo unreadable for overlay — using platform fallback %s",
                        candidate.name,
                    )
                    return candidate, on_light
        elif logo_url or logo_on_light_url:
            logger.warning(
                "Client brand logo not readable for overlay — skipping (SVG/remote may need re-save): %s",
                str(logo_url or logo_on_light_url)[:120],
            )
        return None, on_light

    return primary, on_light


def _is_svg_bytes(content: bytes) -> bool:
    head = content[:256].lstrip().lower()
    return head.startswith(b"<svg") or b"<svg" in head[:80]


def _raster_alternate_urls(url: str) -> list[str]:
    """WordPress/CDN sites often host logo.svg and logo.png at the same path."""
    if not url.startswith(("http://", "https://")):
        return []
    parsed = urlparse(url)
    path = parsed.path or ""
    lower = path.lower()
    alts: list[str] = []
    if lower.endswith(".svg"):
        stem = path[:-4]
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            alts.append(urlunparse(parsed._replace(path=stem + ext)))
    return alts


def _head_request_ok_raster(url: str) -> bool:
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.head(url)
            if resp.status_code in {403, 405} or resp.status_code >= 400:
                resp = client.get(url)
            if resp.status_code >= 400:
                return False
            ctype = (resp.headers.get("content-type") or "").lower()
            if "svg" in ctype:
                return False
            body = resp.content[:16]
            return bool(
                body.startswith(b"\x89PNG")
                or body[:3] == b"\xff\xd8\xff"
                or body[:6] in (b"GIF87a", b"GIF89a")
                or (len(body) >= 12 and body[:4] == b"RIFF")
            )
    except Exception:
        return False


def resolve_downloadable_logo_url(url: str) -> str:
    """Prefer a raster sibling (.png/.jpg) when the stored logo is SVG."""
    raw = (url or "").strip()
    if not raw.startswith(("http://", "https://")):
        return raw
    lower = raw.lower()
    if not (lower.endswith(".svg") or "/svg" in lower):
        return raw
    for alt in _raster_alternate_urls(raw):
        if _head_request_ok_raster(alt):
            logger.info("Using raster logo URL instead of SVG: %s", alt[:120])
            return alt
    return raw


def _svg_to_png_headless_browser(svg_bytes: bytes) -> bytes | None:
    """Render SVG → PNG via Edge/Chrome headless (works on Windows without cairo)."""
    browsers = (
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
    )
    try:
        with tempfile.TemporaryDirectory() as td:
            svg_path = Path(td) / "logo.svg"
            png_path = Path(td) / "logo.png"
            svg_path.write_bytes(svg_bytes)
            uri = svg_path.resolve().as_uri()
            for exe in browsers:
                if not exe.is_file():
                    continue
                try:
                    proc = subprocess.run(
                        [
                            str(exe),
                            "--headless=new",
                            "--disable-gpu",
                            f"--screenshot={png_path}",
                            "--window-size=1200,600",
                            uri,
                        ],
                        timeout=45,
                        capture_output=True,
                    )
                    if proc.returncode == 0 and png_path.is_file() and png_path.stat().st_size > 64:
                        return png_path.read_bytes()
                except Exception:
                    continue
    except Exception:
        logger.debug("Headless browser SVG rasterize failed", exc_info=True)
    return None


def _logo_bytes_to_raster_png(content: bytes) -> bytes | None:
    """Convert SVG logo bytes to PNG for compositing."""
    if not _is_svg_bytes(content):
        return None
    try:
        import cairosvg  # type: ignore[import-untyped]

        return cairosvg.svg2png(bytestring=content, output_width=1200)
    except Exception:
        pass
    png = _svg_to_png_headless_browser(content)
    if png:
        return png
    try:
        from reportlab.graphics import renderPM  # type: ignore[import-untyped]
        from svglib.svglib import svg2rlg  # type: ignore[import-untyped]

        drawing = svg2rlg(io.BytesIO(content))
        if drawing is None:
            return None
        return renderPM.drawToString(drawing, fmt="PNG")
    except Exception:
        logger.debug("svglib rasterize failed", exc_info=True)
    return None


def _path_to_raster_logo(
    path: Path,
    *,
    tenant_id: str | None = None,
    source_url: str = "",
) -> Path | None:
    """Return a raster logo path, converting SVG to PNG when needed."""
    if not path.is_file():
        return None
    if _is_raster_logo_path(path):
        return path

    content = path.read_bytes()
    raster = _logo_bytes_to_raster_png(content)
    if not raster:
        logger.warning(
            "Logo is not compositable raster (%s) — convert to PNG/JPG on Brand Kit",
            path.suffix.lower() or "unknown",
        )
        return None

    try:
        from app.services.file_service import file_service
        from app.services.media_content import image_suffix_and_type

        ext, content_type = image_suffix_and_type(raster)
        if tenant_id:
            saved = file_service.save_bytes(
                content=raster,
                tenant_id=tenant_id,
                subfolder="brand",
                suffix=ext,
                content_type=content_type,
            )
            local = file_url_to_local_path(str(saved.get("file_url") or ""))
            if local and local.is_file():
                logger.info(
                    "Rasterized logo for overlay: %s → %s",
                    (source_url or path.name)[:80],
                    saved.get("file_url"),
                )
                return local
        tmp = Path(tempfile.mkstemp(suffix=ext)[1])
        tmp.write_bytes(raster)
        return tmp
    except Exception:
        logger.exception("Failed to cache rasterized logo from %s", source_url[:80] or path.name)
        return None


def _suffix_from_url(url: str) -> str:
    try:
        return Path(urlparse(url).path).suffix.lower()
    except Exception:
        return ""


def persist_remote_logo_url(
    logo_url: str | None,
    *,
    tenant_id: str,
) -> str | None:
    """
    Store a brand logo under /files/ for compositing.
    Remote http(s) URLs from website scrape are downloaded once per save.
    """
    raw = (logo_url or "").strip()
    if not raw:
        return None
    raw = resolve_downloadable_logo_url(raw)
    if raw.startswith("/files/") or raw.startswith("files/"):
        normalized = raw if raw.startswith("/files/") else f"/{raw.lstrip('/')}"
        path, _ = resolve_overlay_logo_paths(normalized, None, tenant_id=tenant_id)
        if path:
            return normalized
        local = file_url_to_local_path(normalized)
        if local and local.is_file() and _is_svg_bytes(local.read_bytes()):
            raster_path = _path_to_raster_logo(local, tenant_id=tenant_id, source_url=normalized)
            if raster_path and tenant_id:
                from app.services.file_service import file_service

                ext = raster_path.suffix or ".png"
                saved = file_service.save_bytes(
                    content=raster_path.read_bytes(),
                    tenant_id=tenant_id,
                    subfolder="brand",
                    suffix=ext,
                    content_type="image/png",
                )
                return str(saved.get("file_url") or "") or None
        return None

    path = logo_local_path(raw)
    if not path or not path.is_file():
        logger.warning("Could not resolve logo for persistence: %s", raw[:120])
        return None

    content = path.read_bytes()
    url_suffix = _suffix_from_url(raw)
    if _is_svg_bytes(content) or url_suffix == ".svg":
        raster = _logo_bytes_to_raster_png(content)
        if raster:
            content = raster
        else:
            logger.warning(
                "SVG logo cannot be composited onto images — re-upload PNG/JPG on Brand Kit (%s)",
                raw[:80],
            )
            return None

    try:
        from app.services.media_content import image_suffix_and_type
        from app.services.file_service import file_service

        ext, content_type = image_suffix_and_type(content, fallback_suffix=url_suffix or path.suffix)
        saved = file_service.save_bytes(
            content=content,
            tenant_id=tenant_id,
            subfolder="brand",
            suffix=ext,
            content_type=content_type,
        )
        logger.info("Persisted brand logo to %s (from %s)", saved.get("file_url"), raw[:80])
        return str(saved.get("file_url") or "") or None
    except Exception:
        logger.exception("Failed to persist brand logo from %s", raw[:80])
        return None


def _svg_bytes_to_png(content: bytes) -> bytes | None:
    """Backward-compatible alias."""
    return _logo_bytes_to_raster_png(content)


def logo_local_path(logo_url: str | None) -> Path | None:
    """Map /files/ URL, absolute path, or http(s) URL to a readable local file."""
    if not logo_url or not str(logo_url).strip():
        return None
    raw = str(logo_url).strip()
    raw = resolve_downloadable_logo_url(raw)

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
                elif "gif" in ctype:
                    suffix = ".gif"
                url_path_suffix = _suffix_from_url(raw)
                if url_path_suffix in {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                    suffix = url_path_suffix
                tmp = Path(tempfile.mkstemp(suffix=suffix)[1])
                tmp.write_bytes(resp.content)
                return tmp
        except Exception:
            logger.exception("Failed to download logo from %s", raw[:80])
            return None

    return None
