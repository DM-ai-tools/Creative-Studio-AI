"""Repair scraped SVG/http brand logos → /files/ PNG for compositing."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.services.brand_logo import persist_remote_logo_url, resolve_downloadable_logo_url


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as db:
        rows = (
            await db.execute(
                text("SELECT id, tenant_id, name, logo_url FROM brands WHERE logo_url IS NOT NULL")
            )
        ).fetchall()
        fixed = 0
        for row in rows:
            m = dict(row._mapping)
            raw = str(m.get("logo_url") or "").strip()
            if not raw.startswith(("http://", "https://")):
                continue
            downloadable = resolve_downloadable_logo_url(raw)
            persisted = persist_remote_logo_url(
                downloadable,
                tenant_id=str(m["tenant_id"]),
            )
            if persisted and persisted != raw:
                await db.execute(
                    text("UPDATE brands SET logo_url = :url WHERE id = :id"),
                    {"url": persisted, "id": m["id"]},
                )
                fixed += 1
                print(f"fixed {m['name']}: {persisted}")
        await db.commit()
        print(f"Done — repaired {fixed} brand logo(s)")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
