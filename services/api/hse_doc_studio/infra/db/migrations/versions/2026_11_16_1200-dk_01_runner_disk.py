"""runner_disk: замер диска раннера, канал команд `runner_commands`, вид уведомления runner_disk_cleaned
(storage-cleanup.md, 5.5)

Revision ID: dk_01_runner_disk
Revises: dk_02_lifecycle_sweeps
Create Date: 2026-11-16 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "dk_01_runner_disk"
# Цепочка одна (`test__migrations__chain__has_single_head`): B7 слит раньше, поэтому `dk_01` идёт после `dk_02`.
down_revision: str | None = "dk_02_lifecycle_sweeps"
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
    "backup_failed",
    "system_alert",
    "signing_request",
    "signing_reminder",
    "signing_returned",
    "signing_paused",
    "signing_completed",
    "signing_cancelled",
    "signing_new_version",
)
_NEW_KINDS = ("runner_disk_cleaned",)
_OPEN = "('queued', 'delivered', 'running', 'cancelling')"


def _replace_kind_check(kinds: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_notifications_kind"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_kind"), "notifications", f"kind IN {kinds!r}")


def upgrade() -> None:
    # Старая версия api колонки не читает и не пишет: замер пуст до первого `/disk` нового раннера.
    op.add_column("runners", sa.Column("disk", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("runners", sa.Column("disk_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "runner_commands",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("runner_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("progress", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('disk.measure', 'disk.cleanup')", name=op.f("ck_runner_commands_kind")),
        sa.CheckConstraint(
            "state IN ('queued', 'delivered', 'running', 'cancelling', "
            "'done', 'cancelled', 'error', 'expired', 'lost')",
            name=op.f("ck_runner_commands_state"),
        ),
        sa.ForeignKeyConstraint(
            ["runner_id"], ["runners.id"], name=op.f("fk_runner_commands_runner_id_runners"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runner_commands")),
    )
    op.create_index("ix_runner_commands_runner_created", "runner_commands", ["runner_id", sa.text("created_at DESC")])
    op.create_index(
        "uq_runner_commands_cleanup_open",
        "runner_commands",
        ["runner_id"],
        unique=True,
        postgresql_where=sa.text(f"kind = 'disk.cleanup' AND state IN {_OPEN}"),
    )
    _replace_kind_check((*_OLD_KINDS, *_NEW_KINDS))


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind = 'runner_disk_cleaned'")
    _replace_kind_check(_OLD_KINDS)
    op.drop_index("uq_runner_commands_cleanup_open", table_name="runner_commands")
    op.drop_index("ix_runner_commands_runner_created", table_name="runner_commands")
    op.drop_table("runner_commands")
    op.drop_column("runners", "disk_at")
    op.drop_column("runners", "disk")
