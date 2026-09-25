"""Allow uploaded reference images in databases created by the legacy SQL schema.

Revision ID: 004_cs_asset_types
Revises: 003_user_last_login
"""

from alembic import op

revision = "004_cs_asset_types"
down_revision = "003_user_last_login"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_asset_type_check")
    op.create_check_constraint(
        "assets_asset_type_check", "assets",
        "asset_type IN ('image', 'video', 'copy', 'thumbnail', 'logo', 'guideline', "
        "'reference_image', 'creative_studio_reference')",
    )


def downgrade() -> None:
    # Refuse to invalidate existing reference rows; never delete uploaded assets.
    op.execute("ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_asset_type_check")
    op.create_check_constraint(
        "assets_asset_type_check", "assets",
        "asset_type IN ('image', 'video', 'copy', 'thumbnail', 'logo', 'guideline')",
    )
