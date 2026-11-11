"""mail_log: журнал писем, строка на каждую попытку отправки без тела и ссылок (mail-log.md, 5.1)

Revision ID: ml_01_mail_log
Revises: dk_01_runner_disk
Create Date: 2026-11-17 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ml_01_mail_log"
down_revision: str | None = "dk_01_runner_disk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Значения зафиксированы на момент миграции: новые итоги или виды вызова добавит своя миграция.
_STATUSES = ("sent", "failed", "not_sent", "suppressed")
_CAUSES = ("user", "anonymous", "system")


def upgrade() -> None:
    op.create_table(
        "mail_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("template", sa.String(length=64), nullable=False),
        sa.Column("lang", sa.String(length=8), nullable=False),
        sa.Column("to_email", sa.String(length=320), nullable=False),
        sa.Column("to_user_id", sa.String(length=64), nullable=True),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("smtp_code", sa.SmallInteger(), nullable=True),
        sa.Column("error_text", sa.String(length=300), nullable=True),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("cause", sa.String(length=16), nullable=False),
        sa.Column("actor_user_id", sa.String(length=64), nullable=True),
        sa.Column("task", sa.String(length=64), nullable=True),
        sa.Column("origin", sa.String(length=48), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("ref_kind", sa.String(length=32), nullable=True),
        sa.Column("ref_id", sa.String(length=64), nullable=True),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("template_digest", sa.String(length=16), nullable=False),
        sa.CheckConstraint(f"status IN {_STATUSES!r}", name=op.f("ck_mail_log_status")),
        sa.CheckConstraint(f"cause IN {_CAUSES!r}", name=op.f("ck_mail_log_cause")),
        sa.CheckConstraint("status <> 'sent' OR message_id IS NOT NULL", name=op.f("ck_mail_log_sent_message_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mail_log")),
    )
    op.create_index("ix_mail_log_at", "mail_log", ["at"])
    op.create_index("ix_mail_log_to_email_id", "mail_log", [sa.text("lower(to_email)"), sa.text("id DESC")])
    op.create_index(
        "ix_mail_log_to_user_id_id",
        "mail_log",
        ["to_user_id", sa.text("id DESC")],
        postgresql_where=sa.text("to_user_id IS NOT NULL"),
    )
    op.create_index(
        "ix_mail_log_project_id_id",
        "mail_log",
        ["project_id", sa.text("id DESC")],
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )
    op.create_index("ix_mail_log_failed_at", "mail_log", ["at"], postgresql_where=sa.text("status = 'failed'"))


def downgrade() -> None:
    op.drop_index("ix_mail_log_failed_at", table_name="mail_log")
    op.drop_index("ix_mail_log_project_id_id", table_name="mail_log")
    op.drop_index("ix_mail_log_to_user_id_id", table_name="mail_log")
    op.drop_index("ix_mail_log_to_email_id", table_name="mail_log")
    op.drop_index("ix_mail_log_at", table_name="mail_log")
    op.drop_table("mail_log")
