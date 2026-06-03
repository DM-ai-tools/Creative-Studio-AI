"""Initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("plan", sa.String(50), nullable=False, server_default="starter"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("settings", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "brands",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("industry", sa.String(100), nullable=False, server_default="general"),
        sa.Column("language", sa.String(50), nullable=False, server_default="English"),
        sa.Column("voice_rules", JSONB, nullable=False, server_default="{}"),
        sa.Column("forbidden_words", ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("primary_color", sa.String(20), nullable=True),
        sa.Column("secondary_color", sa.String(20), nullable=True),
        sa.Column("profile_vector_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "brand_kits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, server_default="Default Kit"),
        sa.Column("colors", JSONB, nullable=False, server_default="{}"),
        sa.Column("fonts", JSONB, nullable=False, server_default="{}"),
        sa.Column("logo_variations", JSONB, nullable=False, server_default="{}"),
        sa.Column("guidelines_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "briefs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("objective", sa.Text, nullable=False, server_default=""),
        sa.Column("target_audience", sa.Text, nullable=False, server_default=""),
        sa.Column("formats", ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("ad_copy_tone", sa.String(100), nullable=False, server_default="Professional"),
        sa.Column("cta", sa.String(100), nullable=False, server_default="Shop Now"),
        sa.Column("product_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("key_benefits", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(50), nullable=False, server_default="DRAFT"),
        sa.Column("variant_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed_variants", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "variants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("brief_id", UUID(as_uuid=True), sa.ForeignKey("briefs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("format", sa.String(50), nullable=False),
        sa.Column("hook", sa.Text, nullable=False, server_default=""),
        sa.Column("headline", sa.String(255), nullable=False, server_default=""),
        sa.Column("body_copy", sa.Text, nullable=False, server_default=""),
        sa.Column("cta", sa.String(100), nullable=False, server_default=""),
        sa.Column("hashtags", ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("ai_model", sa.String(50), nullable=False, server_default="claude"),
        sa.Column("generation_params", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("compliance_status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("compliance_notes", JSONB, nullable=False, server_default="{}"),
        sa.Column("performance_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_id", UUID(as_uuid=True), sa.ForeignKey("variants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id", ondelete="SET NULL"), nullable=True),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("file_url", sa.String(1000), nullable=False),
        sa.Column("file_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("asset_type", sa.String(50), nullable=False, server_default="image"),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("duration_seconds", sa.Numeric(8, 2), nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "performance_metrics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("variant_id", UUID(as_uuid=True), sa.ForeignKey("variants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("impressions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("conversions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("spend", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("revenue", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("roas", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("ctr", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("cpm", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("frequency", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("reach", sa.Integer, nullable=False, server_default="0"),
        sa.Column("meta_ad_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("variant_id", "date", name="uq_metric_variant_date"),
    )

    op.create_table(
        "performance_rollups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("variant_id", UUID(as_uuid=True), sa.ForeignKey("variants.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("roas_7d", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("roas_personal_best", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("roas_30d", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("frequency_7d", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("is_fatigued", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("passed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("checked", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(50), nullable=False, server_default="ACTIVE"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade():
    op.drop_table("performance_rollups")
    op.drop_table("performance_metrics")
    op.drop_table("assets")
    op.drop_table("variants")
    op.drop_table("briefs")
    op.drop_table("brand_kits")
    op.drop_table("brands")
    op.drop_table("users")
    op.drop_table("tenants")
