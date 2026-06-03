import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Variant(Base):
    __tablename__ = "variants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("briefs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    format: Mapped[str] = mapped_column(String(50), nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False, default="")
    headline: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    body_copy: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cta: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    hashtags: Mapped[list] = mapped_column(ARRAY(String), nullable=False, default=list)
    ai_model: Mapped[str] = mapped_column(String(50), nullable=False, default="claude")
    generation_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING", index=True)
    compliance_status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING", index=True)
    compliance_notes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    performance_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    brief: Mapped["Brief"] = relationship("Brief", back_populates="variants")
    assets: Mapped[list["Asset"]] = relationship("Asset", back_populates="variant")
    metrics: Mapped[list["PerformanceMetric"]] = relationship("PerformanceMetric", back_populates="variant")
    rollup: Mapped["PerformanceRollup | None"] = relationship("PerformanceRollup", back_populates="variant", uselist=False)
