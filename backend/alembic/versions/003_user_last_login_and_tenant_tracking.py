"""Add users.last_login_at for admin activity tracking.

Revision ID: 003_user_last_login
Revises: 002_list_query_indexes
Create Date: 2026-08-11
"""

from alembic import op
import sqlalchemy as sa

revision = "003_user_last_login"
down_revision = "002_list_query_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_login_at")
