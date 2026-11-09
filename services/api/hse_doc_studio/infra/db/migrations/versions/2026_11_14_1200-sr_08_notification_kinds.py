"""notifications: виды уведомлений маршрута подписания (signing_*)

Revision ID: sr_08_notification_kinds
Revises: sr_01_signing_routes
Create Date: 2026-11-14 12:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "sr_08_notification_kinds"
down_revision: str | None = "sr_01_signing_routes"
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
)
_SIGNING_KINDS = (
    "signing_request",
    "signing_reminder",
    "signing_returned",
    "signing_paused",
    "signing_completed",
    "signing_cancelled",
)


def _replace_kind_check(kinds: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_notifications_kind"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_kind"), "notifications", f"kind IN {kinds!r}")


def upgrade() -> None:
    _replace_kind_check((*_OLD_KINDS, *_SIGNING_KINDS))


def downgrade() -> None:
    op.execute(f"DELETE FROM notifications WHERE kind IN {_SIGNING_KINDS!r}")  # noqa: S608 — константы модуля
    _replace_kind_check(_OLD_KINDS)
