"""projects.deadlines: копия сроков контрольных точек для списка проектов (signing-route.md, 16.3)

Колонка nullable и без значения по умолчанию: у всех проектов NULL, то есть срок не задан, данных миграция не
переносит. Копию заполняет `ProjectCatalogMirror` на сохранение проекта и сверка каталога на старте, источник правды
`project.json`. Старая версия api колонку не читает и не пишет (правило expand/contract, docs/ru/deploy/operations.md).

Revision ID: dl_01_project_deadlines
Revises: sr_11_skip
Create Date: 2026-11-21 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "dl_01_project_deadlines"
down_revision: str | None = "sr_11_skip"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("deadlines", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "deadlines")
