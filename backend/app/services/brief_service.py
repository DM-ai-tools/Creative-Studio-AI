from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brief import Brief
from app.schemas.brief import BriefCreate, BriefUpdate


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
    async def get_brief(db: AsyncSession, brief_id: UUID, tenant_id: UUID) -> Brief:
        result = await db.execute(
            select(Brief)
            .options(selectinload(Brief.variants))
            .where(Brief.id == brief_id, Brief.tenant_id == tenant_id)
        )
        brief = result.scalar_one_or_none()
        if not brief:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
        return brief

    @staticmethod
    async def list_briefs(
        db: AsyncSession,
        tenant_id: UUID,
        status_filter: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Brief]:
        q = (
            select(Brief)
            .options(selectinload(Brief.variants))
            .where(Brief.tenant_id == tenant_id)
        )
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
