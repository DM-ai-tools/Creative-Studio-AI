"""Add users.product_scope for per-account feature limits.

Revision ID: 005_user_product_scope
Revises: 004_cs_asset_types
"""

from alembic import op
import sqlalchemy as sa

revision = "005_user_product_scope"
down_revision = "004_cs_asset_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "product_scope" not in columns:
        op.add_column(
            "users",
            sa.Column("product_scope", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "product_scope" in columns:
        op.drop_column("users", "product_scope")
