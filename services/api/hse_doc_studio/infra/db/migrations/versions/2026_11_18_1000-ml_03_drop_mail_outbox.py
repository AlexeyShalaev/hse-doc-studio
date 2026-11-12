"""Contract: удалена таблица mail_outbox, выведенная из употребления выпуском 0.23.0 (mail-log.md, L7, раздел 9)

Выпуск 0.23.0 (`ml_02_clear_mail_outbox`) убрал модель, репозиторий и все обращения к таблице и очистил её. Прежняя
версия api, которая ещё пишет в outbox, к этому выпуску уже не работает, поэтому таблицу можно удалить. Downgrade
создаёт пустую таблицу прежней схемы с индексом: код 0.23.0 её не читает, но на ней стоит его ревизия.

Revision ID: ml_03_drop_mail_outbox
Revises: ml_02_clear_mail_outbox
Create Date: 2026-11-18 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ml_03_drop_mail_outbox"
down_revision: str | None = "ml_02_clear_mail_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Пометка contract-миграции (expand/contract, `docs/ru/deploy/operations.md`): какие таблицы удаляются, какая ревизия
# вывела их из употребления и в каком уже вышедшем выпуске. Проверяет `test_migration_expand_contract`.
contract_drops: tuple[str, ...] = ("mail_outbox",)
contract_retired_by: str = "ml_02_clear_mail_outbox"
contract_released_in: str = "0.23.0"


def upgrade() -> None:
    op.drop_index("ix_mail_outbox_expires_at", table_name="mail_outbox")
    op.drop_table("mail_outbox")


def downgrade() -> None:
    op.create_table(
        "mail_outbox",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("to_email", sa.String(length=320), nullable=False),
        sa.Column("link", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mail_outbox")),
    )
    op.create_index("ix_mail_outbox_expires_at", "mail_outbox", ["expires_at"])
