"""runner_disk_auto: настройка и итог автоочистки диска раннера (storage-cleanup.md, раздел 14)

Колонки с умолчаниями (включено, 10 %) и пустыми временем и итогом: данных миграция не переносит. Старая версия api
колонки не читает и не пишет (правило expand/contract, docs/ru/deploy/operations.md).

Revision ID: dk_03_runner_disk_auto
Revises: sr_13_signature_places_moved
Create Date: 2026-11-25 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "dk_03_runner_disk_auto"
down_revision: str | None = "sr_13_signature_places_moved"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runners", sa.Column("disk_auto_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False)
    )
    op.add_column(
        "runners", sa.Column("disk_auto_min_free_percent", sa.SmallInteger(), server_default="10", nullable=False)
    )
    op.add_column("runners", sa.Column("disk_auto_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("runners", sa.Column("disk_auto_last", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_check_constraint(
        op.f("ck_runners_disk_auto_min_free_percent"), "runners", "disk_auto_min_free_percent BETWEEN 1 AND 50"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_runners_disk_auto_min_free_percent"), "runners", type_="check")
    op.drop_column("runners", "disk_auto_last")
    op.drop_column("runners", "disk_auto_at")
    op.drop_column("runners", "disk_auto_min_free_percent")
    op.drop_column("runners", "disk_auto_enabled")
