"""notifications: вид уведомления signing_new_version (новая версия на подписи, signing-route.md 12.6)

Revision ID: sr_10_new_version_kind
Revises: sr_09_sent_changed
Create Date: 2026-11-15 11:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "sr_10_new_version_kind"
down_revision: str | None = "sr_09_sent_changed"
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
)
_NEW_KINDS = ("signing_new_version",)


def _replace_kind_check(kinds: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_notifications_kind"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_kind"), "notifications", f"kind IN {kinds!r}")


def upgrade() -> None:
    _replace_kind_check((*_OLD_KINDS, *_NEW_KINDS))


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind = 'signing_new_version'")
    _replace_kind_check(_OLD_KINDS)
