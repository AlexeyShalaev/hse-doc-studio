"""jobs.batch_id: задачи одной команды «Собрать все» группируются в очереди админки

Revision ID: jb_01_jobs_batch_id
Revises: rd_01_runner_deployment
Create Date: 2026-11-13 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "jb_01_jobs_batch_id"
down_revision: str | None = "rd_01_runner_deployment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Пустая у старых и одиночных задач: прежняя версия api колонку не читает и не пишет.
    op.add_column("jobs", sa.Column("batch_id", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_jobs_batch_id",
        "jobs",
        ["batch_id"],
        unique=False,
        postgresql_where=sa.text("batch_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_batch_id", table_name="jobs", postgresql_where=sa.text("batch_id IS NOT NULL"))
    op.drop_column("jobs", "batch_id")
