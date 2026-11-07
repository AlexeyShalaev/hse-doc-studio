"""runner_deployment: как раннер развёрнут (его отчёт `/deployment`) для экрана админки

Revision ID: rd_01_runner_deployment
Revises: dg_01_update_run_downgrade
Create Date: 2026-11-12 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "rd_01_runner_deployment"
down_revision: str | None = "dg_01_update_run_downgrade"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Обе колонки пустые у старых раннеров: прежняя версия api их не читает и не пишет.
    op.add_column("runners", sa.Column("deployment", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("runners", sa.Column("deployment_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("runners", "deployment_at")
    op.drop_column("runners", "deployment")
