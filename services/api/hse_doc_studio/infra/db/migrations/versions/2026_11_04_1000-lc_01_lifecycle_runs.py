"""lifecycle_runs: статистика последней очистки по источникам; вид уведомления system_alert

Revision ID: lc_01_lifecycle_runs
Revises: s5_01_review
Create Date: 2026-11-04 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "lc_01_lifecycle_runs"
down_revision: str | None = "s5_01_review"
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
)
_NEW_KINDS = (*_OLD_KINDS, "system_alert")


def _replace_kind_check(kinds: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_notifications_kind"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_kind"), "notifications", f"kind IN {kinds!r}")


def upgrade() -> None:
    op.create_table(
        "lifecycle_runs",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_removed", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("runs", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("total_removed", sa.BigInteger(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_lifecycle_runs")),
    )
    _replace_kind_check(_NEW_KINDS)


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind = 'system_alert'")
    _replace_kind_check(_OLD_KINDS)
    op.drop_table("lifecycle_runs")
