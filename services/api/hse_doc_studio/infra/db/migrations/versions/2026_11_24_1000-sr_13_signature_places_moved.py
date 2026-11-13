"""compile_records.signature_places_moved: сколько мест подписей сдвинул пересчёт по якорям сборки (signing-route.md,
15.17.9)

Колонка nullable и без значения по умолчанию: у прежних сборок NULL (пересчёта не было), данных миграция не переносит.
Старая версия api колонку не читает и не пишет (правило expand/contract, docs/ru/deploy/operations.md).

Revision ID: sr_13_signature_places_moved
Revises: dl_02_checkpoint_reminders
Create Date: 2026-11-24 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "sr_13_signature_places_moved"
down_revision: str | None = "dl_02_checkpoint_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("compile_records", sa.Column("signature_places_moved", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("compile_records", "signature_places_moved")
