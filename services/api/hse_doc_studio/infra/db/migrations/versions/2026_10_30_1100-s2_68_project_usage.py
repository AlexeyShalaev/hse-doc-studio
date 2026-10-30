"""project_usage: учёт места проекта и предел размера

Revision ID: s2_68_project_usage
Revises: s2_66_submissions
Create Date: 2026-10-30 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s2_68_project_usage"
down_revision: str | None = "s2_66_submissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_usage",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("bytes_tree", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("bytes_git", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("bytes_s3", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_index("ix_project_usage_measured_at", "project_usage", ["measured_at"])


def downgrade() -> None:
    op.drop_index("ix_project_usage_measured_at", table_name="project_usage")
    op.drop_table("project_usage")
