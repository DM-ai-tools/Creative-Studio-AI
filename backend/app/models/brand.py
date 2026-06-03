import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str] = mapped_column(String(100), nullable=False, default="general")
    language: Mapped[str] = mapped_column(String(50), nullable=False, default="English")
    voice_rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    forbidden_words: Mapped[list] = mapped_column(ARRAY(String), nullable=False, default=list)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(20), nullable=True, default="#0F1B3D")
    secondary_color: Mapped[str | None] = mapped_column(String(20), nullable=True, default="#00C2A8")
    profile_vector_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="brands")
    brand_kits: Mapped[list["BrandKit"]] = relationship("BrandKit", back_populates="brand", cascade="all, delete-orphan")
    briefs: Mapped[list["Brief"]] = relationship("Brief", back_populates="brand")


class BrandKit(Base):
    __tablename__ = "brand_kits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Default Kit")
    colors: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    fonts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    logo_variations: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    guidelines_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    brand: Mapped["Brand"] = relationship("Brand", back_populates="brand_kits")
