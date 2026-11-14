"""Tenant-level email layout reference (Creative Studio / upload base)."""

from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.tenant import Tenant

_SETTINGS_KEY = "email_layout_base"
_MAX_HTML = 200_000


def _norm_hex(value: str | None) -> str | None:
    text = (value or "").strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{6}", text):
        return f"#{text.upper()}"
    return None


def extract_palette_from_html(html: str) -> dict[str, str | None]:
    """Best-effort colours from an uploaded email HTML mock."""
    theme = re.search(
        r'<meta[^>]+name=["\']theme-color["\'][^>]+content=["\']([^"\']+)',
        html,
        flags=re.I,
    )
    theme_color = _norm_hex(theme.group(1)) if theme else None
    hexes = [_norm_hex(m) for m in re.findall(r"#[0-9a-fA-F]{6}\b", html[:120_000])]
    hexes = [h for h in hexes if h]
    counts: dict[str, int] = {}
    for color in hexes:
        counts[color] = counts.get(color, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    primary = theme_color or (ranked[0][0] if ranked else None)
    secondary = None
    for color, _ in ranked:
        if color != primary:
            secondary = color
            break
    return {
        "primary_color": primary,
        "secondary_color": secondary,
        "background_color": ranked[1][0] if len(ranked) > 1 else None,
    }


def public_layout_base(settings: dict | None) -> dict[str, Any]:
    block = dict((settings or {}).get(_SETTINGS_KEY) or {})
    html = str(block.get("layout_html") or "")
    if len(html) > _MAX_HTML:
        html = html[:_MAX_HTML]
    return {
        "label": str(block.get("label") or "Email layout base"),
        "layout_image_url": block.get("layout_image_url"),
        "layout_asset_id": block.get("layout_asset_id"),
        "layout_html": html,
        "updated_at": block.get("updated_at"),
    }


async def load_layout_base(db: AsyncSession, tenant_id: UUID) -> dict[str, Any]:
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if not tenant:
        return public_layout_base({})
    return public_layout_base(tenant.settings or {})


async def save_layout_base(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    label: str,
    layout_image_url: str | None,
    layout_asset_id: UUID | None,
    layout_html: str | None,
) -> dict[str, Any]:
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if not tenant:
        raise ValueError("Tenant not found")
    settings = copy.deepcopy(tenant.settings or {})
    html = (layout_html or "").strip()
    if len(html) > _MAX_HTML:
        html = html[:_MAX_HTML]
    settings[_SETTINGS_KEY] = {
        "label": (label or "Email layout base").strip()[:120],
        "layout_image_url": (layout_image_url or "").strip() or None,
        "layout_asset_id": str(layout_asset_id) if layout_asset_id else None,
        "layout_html": html or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    tenant.settings = settings
    await db.flush()
    return public_layout_base(settings)


async def resolve_layout_asset_url(
    db: AsyncSession,
    tenant_id: UUID,
    asset_id: UUID | None,
    fallback_url: str | None,
) -> str | None:
    if asset_id:
        row = (
            await db.execute(
                select(Asset).where(Asset.id == asset_id, Asset.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if row and row.file_url:
            return str(row.file_url)
    url = (fallback_url or "").strip()
    return url or None
