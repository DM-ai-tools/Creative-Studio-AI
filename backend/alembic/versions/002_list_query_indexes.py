"""Add indexes for list/filter queries.

Revision ID: 002_list_query_indexes
Revises: 001_initial_schema
Create Date: 2026-07-28
"""

from alembic import op

revision = "002_list_query_indexes"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_briefs_tenant_created", "briefs", ["tenant_id", "created_at"], unique=False)
    op.create_index("ix_briefs_tenant_status", "briefs", ["tenant_id", "status"], unique=False)
    op.create_index("ix_variants_tenant_created", "variants", ["tenant_id", "created_at"], unique=False)
    op.create_index("ix_variants_brief_created", "variants", ["brief_id", "created_at"], unique=False)
    op.create_index(
        "ix_variants_tenant_compliance",
        "variants",
        ["tenant_id", "compliance_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_variants_tenant_compliance", table_name="variants")
    op.drop_index("ix_variants_brief_created", table_name="variants")
    op.drop_index("ix_variants_tenant_created", table_name="variants")
    op.drop_index("ix_briefs_tenant_status", table_name="briefs")
    op.drop_index("ix_briefs_tenant_created", table_name="briefs")
