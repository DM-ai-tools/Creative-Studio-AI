from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brief import Brief
from app.schemas.brief import BriefCreate, BriefUpdate

# Generation now runs as a background job (HeyGen can take 15–60+ min).
# Only treat RUNNING as abandoned when it is truly stale — not mid-render.
_STALE_RUNNING_ZERO_VARIANTS_MINUTES = 90
_STALE_RUNNING_PARTIAL_MINUTES = 120


class BriefService:
    @staticmethod
    async def create_brief(
        db: AsyncSession, tenant_id: UUID, user_id: UUID, data: BriefCreate
    ) -> Brief:
        brief = Brief(
            tenant_id=tenant_id,
            created_by=user_id,
            **data.model_dump(),
        )
        db.add(brief)
        await db.flush()
        # Reload with variants eager-loaded; BriefResponse reads `variants` and lazy
        # load would raise MissingGreenlet during response serialization.
        return await BriefService.get_brief(db, brief.id, tenant_id)

    @staticmethod
    def _reconcile_running_with_variants(brief: Brief) -> bool:
        """Sync progress while RUNNING — only flip READY when the full target is done.

        Important: do NOT mark PARTIAL after the first variant. That stops the UI poller
        while later image variants are still generating.
        """
        if brief.status != "RUNNING":
            return False
        variants = getattr(brief, "variants", None) or []
        if not variants:
            return False
        ready = sum(1 for v in variants if getattr(v, "status", "") == "READY")
        total = len(variants)
        target = max(1, int(brief.variant_count or 0))
        changed = False

        # Progress counter for the brief page ("1/3 variants ready").
        done = max(int(brief.completed_variants or 0), ready, total)
        if done != brief.completed_variants:
            brief.completed_variants = done
            changed = True

        # Only finish when every requested variant exists and is ready.
        if total >= target and ready >= target:
            brief.status = "READY"
            brief.completed_variants = max(brief.completed_variants, ready)
            return True

        # Still generating the rest — keep RUNNING so the UI keeps polling.
        return changed

    @staticmethod
    def _reconcile_stale_running(brief: Brief, *, force_orphan: bool = False) -> bool:
        """Mark abandoned RUNNING jobs as DRAFT/READY/PARTIAL so the UI stops showing fake progress."""
        if brief.status != "RUNNING":
            return False

        updated = brief.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - updated

        if brief.completed_variants <= 0:
            if force_orphan or age >= timedelta(minutes=_STALE_RUNNING_ZERO_VARIANTS_MINUTES):
                brief.status = "DRAFT"
                return True
            return False

        if brief.completed_variants >= brief.variant_count:
            brief.status = "READY"
            return True

        if force_orphan or age >= timedelta(minutes=_STALE_RUNNING_PARTIAL_MINUTES):
            brief.status = "PARTIAL"
            return True
        return False

    @staticmethod
    async def reconcile_orphaned_running_briefs(db: AsyncSession) -> int:
        """On server startup: sync generation cannot survive a process restart."""
        result = await db.execute(
            select(Brief).options(selectinload(Brief.variants)).where(Brief.status == "RUNNING")
        )
        briefs = list(result.scalars().all())
        changed = 0
        for brief in briefs:
            if BriefService._reconcile_running_with_variants(brief):
                changed += 1
            elif BriefService._reconcile_stale_running(brief, force_orphan=True):
                changed += 1
        if changed:
            await db.commit()
        return changed

    @staticmethod
    async def _reconcile_briefs_in_list(briefs: list[Brief], db: AsyncSession) -> None:
        changed = False
        for b in briefs:
            if BriefService._reconcile_running_with_variants(b):
                changed = True
            elif BriefService._reconcile_stale_running(b):
                changed = True
        if changed:
            await db.commit()

    @staticmethod
    async def get_brief(db: AsyncSession, brief_id: UUID, tenant_id: UUID) -> Brief:
        result = await db.execute(
            select(Brief)
            .options(selectinload(Brief.variants))
            .where(Brief.id == brief_id, Brief.tenant_id == tenant_id)
        )
        brief = result.scalar_one_or_none()
        if not brief:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
        if BriefService._reconcile_running_with_variants(brief) or BriefService._reconcile_stale_running(
            brief
        ):
            await db.flush()
            # Refresh so server-side onupdate columns (updated_at) are loaded before
            # response serialization — avoids MissingGreenlet on expired attributes.
            await db.refresh(brief, attribute_names=["updated_at", "status", "completed_variants"])
        return brief

    @staticmethod
    async def list_briefs(
        db: AsyncSession,
        tenant_id: UUID,
        status_filter: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Brief]:
        # List view: no variant eager-load or reconciliation — keeps History/Briefs fast.
        q = select(Brief).where(Brief.tenant_id == tenant_id)
        if status_filter:
            q = q.where(Brief.status == status_filter)
        q = q.order_by(Brief.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def update_brief(
        db: AsyncSession, brief_id: UUID, tenant_id: UUID, data: BriefUpdate
    ) -> Brief:
        brief = await BriefService.get_brief(db, brief_id, tenant_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(brief, field, value)
        await db.flush()
        return await BriefService.get_brief(db, brief_id, tenant_id)

    @staticmethod
    async def delete_brief(db: AsyncSession, brief_id: UUID, tenant_id: UUID) -> None:
        brief = await BriefService.get_brief(db, brief_id, tenant_id)
        await db.delete(brief)

    @staticmethod
    async def submit_brief(db: AsyncSession, brief_id: UUID, tenant_id: UUID) -> Brief:
        brief = await BriefService.get_brief(db, brief_id, tenant_id)
        if brief.status not in ("DRAFT", "FAILED"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Brief cannot be submitted from status '{brief.status}'",
            )
        brief.status = "PENDING"
        await db.flush()
        return await BriefService.get_brief(db, brief_id, tenant_id)
