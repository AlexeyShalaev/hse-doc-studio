"""submissions: записи сдачи пакетов на сервере

Revision ID: s2_66_submissions
Revises: s2_73_runners
Create Date: 2026-10-30 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "s2_66_submissions"
down_revision: str | None = "s2_73_runners"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.String(length=256), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("actor_name", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archive_format", sa.String(length=16), server_default="zip", nullable=False),
        sa.Column("artifact_key", sa.Text(), nullable=True),
        sa.Column("output_path", sa.Text(), nullable=False),
        sa.Column("data", JSONB(), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_submissions_project_created", "submissions", ["project_id", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_submissions_project_created", table_name="submissions")
    op.drop_table("submissions")
