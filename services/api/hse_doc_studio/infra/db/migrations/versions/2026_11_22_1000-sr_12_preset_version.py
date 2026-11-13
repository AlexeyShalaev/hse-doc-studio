"""signing_routes.preset_version: версия шаблона, по пресету которой собран состав маршрута (signing-route.md, 15.7)

Колонка nullable и без значения по умолчанию: у всех маршрутов NULL, то есть состав собран не по пресету (маршруты до
раздела 15), данных миграция не переносит. Старая версия api колонку не читает и не пишет (правило expand/contract,
docs/ru/deploy/operations.md).

Revision ID: sr_12_preset_version
Revises: dl_01_project_deadlines
Create Date: 2026-11-22 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "sr_12_preset_version"
down_revision: str | None = "dl_01_project_deadlines"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("signing_routes", sa.Column("preset_version", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("signing_routes", "preset_version")
