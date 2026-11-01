"""jobs.applied_at: метка применённого итога задачи

Revision ID: s2_78_jobs_applied_at
Revises: s2_73_runners
Create Date: 2026-10-30 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s2_78_jobs_applied_at"
down_revision: str | None = "s2_73_runners"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True))
    # Задачи, закончившиеся до появления метки, считаются применёнными: довершать при старте нечего.
    op.execute(
        "UPDATE jobs SET applied_at = COALESCE(finished_at, now()) "
        "WHERE state IN ('succeeded', 'failed', 'cancelled', 'timed_out')"
    )
    op.create_index(
        "ix_jobs_unapplied",
        "jobs",
        ["seq"],
        postgresql_where=sa.text("applied_at IS NULL AND state IN ('succeeded', 'failed', 'cancelled', 'timed_out')"),
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_unapplied", table_name="jobs")
    op.drop_column("jobs", "applied_at")
