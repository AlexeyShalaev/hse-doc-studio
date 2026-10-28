"""jobs.started_at: начало текущей попытки для проверки таймаутов

Revision ID: s2_72_jobs_started_at
Revises: s2_71_jobs_queue
Create Date: 2026-10-28 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s2_72_jobs_started_at"
down_revision: str | None = "s2_71_jobs_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "started_at")
