import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conversions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spend: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    revenue: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    roas: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0)
    ctr: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False, default=0)
    cpm: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    frequency: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0)
    reach: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    meta_ad_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    variant: Mapped["Variant"] = relationship("Variant", back_populates="metrics")


class PerformanceRollup(Base):
    __tablename__ = "performance_rollups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    roas_7d: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0)
    roas_personal_best: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0)
    roas_30d: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0)
    frequency_7d: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0)
    is_fatigued: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    variant: Mapped["Variant"] = relationship("Variant", back_populates="rollup")
