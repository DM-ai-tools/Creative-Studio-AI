from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.variant import Variant
from app.models.performance import PerformanceRollup
from app.schemas.variant import VariantUpdate


class VariantService:
    @staticmethod
    async def list_variants(
        db: AsyncSession,
        tenant_id: UUID,
        brief_id: UUID | None = None,
        variant_status: str | None = None,
        compliance_status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Variant]:
        q = select(Variant).where(Variant.tenant_id == tenant_id)
        if brief_id:
            q = q.where(Variant.brief_id == brief_id)
        if variant_status:
            q = q.where(Variant.status == variant_status)
        if compliance_status:
            q = q.where(Variant.compliance_status == compliance_status)
        q = q.order_by(Variant.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def get_variant(db: AsyncSession, variant_id: UUID, tenant_id: UUID) -> Variant:
        result = await db.execute(
            select(Variant).where(Variant.id == variant_id, Variant.tenant_id == tenant_id)
        )
        variant = result.scalar_one_or_none()
        if not variant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
        return variant

    @staticmethod
    async def update_variant(
        db: AsyncSession, variant_id: UUID, tenant_id: UUID, data: VariantUpdate
    ) -> Variant:
        variant = await VariantService.get_variant(db, variant_id, tenant_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(variant, field, value)
        await db.flush()
        await db.refresh(variant)
        return variant

    @staticmethod
    async def approve_variant(db: AsyncSession, variant_id: UUID, tenant_id: UUID) -> Variant:
        variant = await VariantService.get_variant(db, variant_id, tenant_id)
        variant.status = "APPROVED"
        await db.flush()
        await db.refresh(variant)
        return variant

    @staticmethod
    async def reject_variant(db: AsyncSession, variant_id: UUID, tenant_id: UUID) -> Variant:
        variant = await VariantService.get_variant(db, variant_id, tenant_id)
        variant.status = "REJECTED"
        await db.flush()
        await db.refresh(variant)
        return variant

    @staticmethod
    def _unlink_pipeline_file(file_url: str | None) -> None:
        if not file_url or not file_url.startswith("/files/"):
            return
        upload_root = Path(settings.UPLOAD_DIR).resolve()
        rel = file_url.removeprefix("/files/")
        path = (upload_root / rel).resolve()
        try:
            path.relative_to(upload_root)
        except ValueError:
            return
        if path.is_file():
            path.unlink()

    @staticmethod
    async def delete_variant(db: AsyncSession, variant_id: UUID, tenant_id: UUID) -> None:
        variant = await VariantService.get_variant(db, variant_id, tenant_id)
        pipeline = (variant.generation_params or {}).get("pipeline") or {}
        for step in ("image", "video"):
            media = pipeline.get(step) or {}
            VariantService._unlink_pipeline_file(media.get("url"))
        await db.delete(variant)
        await db.flush()

    @staticmethod
    async def create_from_creative_studio(
        db: AsyncSession,
        *,
        tenant_id: UUID,
        user_id: UUID | None,
        brief_id: UUID | None,
        brand_id: UUID | None,
        media_url: str,
        media_mode: str = "video",
        aspect: str = "9/16",
        model: str = "creative-studio",
        prompt: str = "",
        duration_seconds: int | None = None,
        seed_image_url: str | None = None,
        brief_title: str | None = None,
        product_name: str = "",
    ) -> Variant:
        """Persist a Creative Studio still/video as a READY variant for the Variants library."""
        from app.models.brief import Brief
        from app.schemas.brief import BriefCreate

        media_url = (media_url or "").strip()
        if not media_url:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="media_url is required")

        mode = (media_mode or "video").strip().lower()
        a = (aspect or "9/16").replace(":", "/")
        if mode == "image":
            fmt = "static" if a in {"1/1", "4/3"} else "static"
        elif a in {"16/9"}:
            fmt = "video"
        else:
            fmt = "reel"

        brief: Brief | None = None
        if brief_id:
            result = await db.execute(
                select(Brief).where(Brief.id == brief_id, Brief.tenant_id == tenant_id)
            )
            brief = result.scalar_one_or_none()
            if not brief:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
        else:
            if not brand_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Select a brand (or open Creative Studio from an existing brief) to save to Variants.",
                )
            title = (brief_title or "").strip() or "Creative Studio"
            if product_name:
                title = f"{title} — {product_name}".strip(" —")
            from app.services.brief_service import BriefService

            brief = await BriefService.create_brief(
                db,
                tenant_id,
                user_id,
                BriefCreate(
                    brand_id=brand_id,
                    title=title[:255],
                    objective="Creative Studio scene",
                    target_audience="",
                    formats=[fmt],
                    ad_copy_tone="Professional",
                    cta="Shop Now",
                    product_name=(product_name or "")[:255],
                    key_benefits={
                        "media_type": "creative_studio",
                        "creative_studio": True,
                    },
                ),
            )
            brief.status = "READY"
            brief.variant_count = 1

        pipeline: dict = {}
        if mode == "image":
            pipeline["image"] = {
                "status": "done",
                "url": media_url,
                "provider": "higgsfield",
                "model": model,
            }
            pipeline["video"] = {"status": "skipped"}
        else:
            pipeline["video"] = {
                "status": "done",
                "url": media_url,
                "provider": "higgsfield",
                "model": model,
                "duration_seconds": duration_seconds,
            }
            if seed_image_url:
                pipeline["image"] = {
                    "status": "done",
                    "url": seed_image_url,
                    "provider": "higgsfield",
                    "role": "seed_frame",
                }
            else:
                pipeline["image"] = {"status": "skipped"}

        hook = (prompt or "").strip()
        if len(hook) > 280:
            hook = hook[:277].rsplit(" ", 1)[0] + "…"

        variant = Variant(
            brief_id=brief.id,
            brand_id=brief.brand_id,
            tenant_id=tenant_id,
            format=fmt,
            hook=hook or "Creative Studio",
            headline="Creative Studio",
            body_copy=(prompt or "")[:4000],
            cta=brief.cta or "Shop Now",
            hashtags=[],
            ai_model=(model or "creative-studio")[:50],
            generation_params={
                "format": fmt,
                "source": "creative_studio",
                "aspect": aspect,
                "models": {
                    "image": model if mode == "image" else None,
                    "video": model if mode != "image" else None,
                },
                "pipeline": pipeline,
            },
            status="READY",
            compliance_status="PENDING",
            compliance_notes={},
        )
        db.add(variant)
        brief.completed_variants = int(brief.completed_variants or 0) + 1
        brief.variant_count = max(int(brief.variant_count or 0), brief.completed_variants)
        if brief.status in {"DRAFT", "PENDING"}:
            brief.status = "READY"
        await db.flush()
        await db.refresh(variant)
        return variant
        result = await db.execute(
            select(PerformanceRollup, Variant)
            .join(Variant, PerformanceRollup.variant_id == Variant.id)
            .where(PerformanceRollup.tenant_id == tenant_id, PerformanceRollup.is_fatigued == True)
            .order_by(PerformanceRollup.roas_7d.asc())
        )
        alerts = []
        for rollup, variant in result.all():
            drop_pct = 0.0
            if rollup.roas_personal_best > 0:
                drop_pct = round(
                    (1 - float(rollup.roas_7d) / float(rollup.roas_personal_best)) * 100, 1
                )
            alerts.append({
                "variant_id": str(variant.id),
                "hook": variant.hook,
                "format": variant.format,
                "roas_personal_best": float(rollup.roas_personal_best),
                "roas_7d": float(rollup.roas_7d),
                "drop_pct": drop_pct,
                "frequency_7d": float(rollup.frequency_7d),
                "status": rollup.status,
            })
        return alerts
