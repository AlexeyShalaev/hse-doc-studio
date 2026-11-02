"""Бэкапы сервера: назначения, запуски, вид уведомления backup_failed

Revision ID: bk_01_backups
Revises: lc_02_partition_logs
Create Date: 2026-11-04 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "bk_01_backups"
down_revision: str | None = "lc_02_partition_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_KINDS = (
    "project_invitation",
    "invitation_accepted",
    "invitation_declined",
    "access_request",
    "access_request_decided",
    "transfer_request",
    "transfer_decided",
    "member_removed",
    "review_thread",
    "review_reply",
    "review_mention",
    "review_resolved",
    "system_alert",
)
_NEW_KINDS = (*_OLD_KINDS, "backup_failed")


def _replace_kind_check(kinds: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_notifications_kind"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_kind"), "notifications", f"kind IN {kinds!r}")


def upgrade() -> None:
    op.create_table(
        "backup_destinations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=True),
        sa.Column("region", sa.String(length=64), server_default="us-east-1", nullable=False),
        sa.Column("bucket", sa.String(length=256), nullable=True),
        sa.Column("prefix", sa.String(length=512), server_default="", nullable=False),
        sa.Column("path_style", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("local_path", sa.Text(), nullable=True),
        sa.Column("access_key_enc", sa.Text(), nullable=True),
        sa.Column("secret_key_enc", sa.Text(), nullable=True),
        sa.Column("access_key_hint", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_ok", sa.Boolean(), nullable=True),
        sa.Column("last_check_error", sa.Text(), nullable=True),
        sa.CheckConstraint("kind IN ('s3', 'local')", name=op.f("ck_backup_destinations_kind")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backup_destinations")),
    )
    op.create_index("uq_backup_destinations_name", "backup_destinations", [sa.text("lower(name)")], unique=True)
    op.create_index(
        "uq_backup_destinations_default",
        "backup_destinations",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_table(
        "backup_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("destination_id", sa.Uuid(), nullable=True),
        sa.Column("destination_name", sa.String(length=128), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("started_by", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("backup_id", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint("status IN ('running', 'ok', 'failed', 'interrupted')", name=op.f("ck_backup_runs_status")),
        sa.CheckConstraint("trigger IN ('manual', 'schedule')", name=op.f("ck_backup_runs_trigger")),
        sa.ForeignKeyConstraint(
            ["destination_id"],
            ["backup_destinations.id"],
            name=op.f("fk_backup_runs_destination_id_backup_destinations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["started_by"], ["users.id"], name=op.f("fk_backup_runs_started_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backup_runs")),
    )
    op.create_index("ix_backup_runs_started", "backup_runs", [sa.text("started_at DESC")])
    op.create_index("ix_backup_runs_destination", "backup_runs", ["destination_id", sa.text("started_at DESC")])
    op.create_index(
        "uq_backup_runs_single_running",
        "backup_runs",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    _replace_kind_check(_NEW_KINDS)


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind = 'backup_failed'")
    _replace_kind_check(_OLD_KINDS)
    op.drop_table("backup_runs")
    op.drop_table("backup_destinations")
