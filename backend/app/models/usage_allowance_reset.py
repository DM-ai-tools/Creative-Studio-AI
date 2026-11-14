import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UsageAllowanceReset(Base):
    """Immutable audit record for starting a fresh per-user spend allowance period."""

    __tablename__ = "usage_allowance_resets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reset_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    limit_usd: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=30)
    previous_period_spend_usd: Mapped[float] = mapped_column(Numeric(14, 6), nullable=False, default=0)
    note: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

