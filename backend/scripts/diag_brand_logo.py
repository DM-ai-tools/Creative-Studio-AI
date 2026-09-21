"""One-off: inspect brand logos and compositing readiness."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.services.brand_logo import resolve_overlay_logo_paths, resolve_video_logo_urls


async def main() -> None:
    print("UPLOAD_DIR:", Path(settings.UPLOAD_DIR).resolve())
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as db:
        r = await db.execute(
            text(
                "SELECT b.id, b.tenant_id, b.name, b.logo_url, b.primary_color, b.secondary_color, "
                "k.logo_variations "
                "FROM brands b "
                "LEFT JOIN brand_kits k ON k.brand_id = b.id "
                "ORDER BY b.updated_at DESC NULLS LAST "
                "LIMIT 8"
            )
        )
        rows = r.fetchall()
        for row in rows:
            m = dict(row._mapping)
            name = m["name"]
            snap = {
                "brand_name": name,
                "logo_url": m.get("logo_url"),
                "logo_variations": m.get("logo_variations") or {},
            }
            on_light = (snap["logo_variations"] or {}).get("on_light")
            primary_path, on_light_path = resolve_overlay_logo_paths(
                str(m.get("logo_url") or ""),
                str(on_light or "") or None,
            )
            resolved, resolved_light = resolve_video_logo_urls(
                brand=snap,
                tenant_id=str(m["tenant_id"]),
            )
            print("---", name, "---")
            print("  logo_url:", m.get("logo_url"))
            print("  on_light:", on_light)
            print("  colors:", m.get("primary_color"), m.get("secondary_color"))
            print("  disk primary:", primary_path)
            print("  disk on_light:", on_light_path)
            print("  resolved:", resolved, resolved_light)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
