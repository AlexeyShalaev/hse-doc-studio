"""mail_log v2: автоповтор и ручной повтор писем (mail-log.md, раздел 14, V10), только расширение

Колонки `next_attempt_at`, `last_attempt_at`, `resent_from_id` у `mail_log` и очередь автоповтора `mail_retry` с
запросом письма шифртекстом. Прежняя версия api новых колонок и таблицы не знает и не трогает.

Revision ID: ml_04_mail_retry
Revises: sr_13_signature_places_moved
Create Date: 2026-11-25 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ml_04_mail_retry"
down_revision: str | None = "sr_13_signature_places_moved"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mail_log", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("mail_log", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("mail_log", sa.Column("resent_from_id", sa.BigInteger(), nullable=True))
    op.create_index(
        "ix_mail_log_resent_from_id",
        "mail_log",
        ["resent_from_id"],
        postgresql_where=sa.text("resent_from_id IS NOT NULL"),
    )
    op.create_index(
        "ix_mail_log_next_attempt_at",
        "mail_log",
        ["next_attempt_at"],
        postgresql_where=sa.text("next_attempt_at IS NOT NULL"),
    )
    op.create_table(
        "mail_retry",
        sa.Column("entry_id", sa.BigInteger(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_enc", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["mail_log.id"], name=op.f("fk_mail_retry_entry_id_mail_log"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("entry_id", name=op.f("pk_mail_retry")),
    )
    op.create_index("ix_mail_retry_due_at", "mail_retry", ["due_at"])


def downgrade() -> None:
    op.drop_index("ix_mail_retry_due_at", table_name="mail_retry")
    op.drop_table("mail_retry")
    op.drop_index("ix_mail_log_next_attempt_at", table_name="mail_log")
    op.drop_index("ix_mail_log_resent_from_id", table_name="mail_log")
    op.drop_column("mail_log", "resent_from_id")
    op.drop_column("mail_log", "last_attempt_at")
    op.drop_column("mail_log", "next_attempt_at")
