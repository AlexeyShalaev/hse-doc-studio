"""Автообновление сервера: журнал запусков обновления и отката

Revision ID: up_01_server_updates
Revises: bk_01_backups
Create Date: 2026-11-05 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "up_01_server_updates"
down_revision: str | None = "bk_01_backups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "update_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=True),
        sa.Column("from_version", sa.String(length=64), nullable=False),
        sa.Column("to_version", sa.String(length=64), nullable=False),
        sa.Column("from_revision", sa.String(length=64), nullable=True),
        sa.Column("to_revision", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_by", sa.String(length=64), nullable=True),
        sa.Column("backup_run_id", sa.Uuid(), nullable=True),
        sa.Column("restore_db", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("db_restored", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("digests_url", sa.Text(), server_default="", nullable=False),
        sa.Column("verify", sa.String(length=16), server_default="digest", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("last_seq", sa.Integer(), server_default="0", nullable=False),
        sa.Column("events", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.CheckConstraint("kind IN ('update', 'rollback')", name=op.f("ck_update_runs_kind")),
        sa.CheckConstraint("trigger IN ('auto', 'manual')", name=op.f("ck_update_runs_trigger")),
        sa.CheckConstraint(
            "status IN ('waiting_backup', 'queued', 'running', 'succeeded', 'rolled_back', 'failed', 'cancelled')",
            name=op.f("ck_update_runs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], name=op.f("fk_update_runs_requested_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["backup_run_id"],
            ["backup_runs.id"],
            name=op.f("fk_update_runs_backup_run_id_backup_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_update_runs")),
    )
    op.create_index("ix_update_runs_created", "update_runs", [sa.text("created_at DESC")])
    op.create_index(
        "uq_update_runs_single_active",
        "update_runs",
        [sa.text("(true)")],
        unique=True,
        postgresql_where=sa.text("status IN ('waiting_backup', 'queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_table("update_runs")
