"""signing_routes.point_deadline и вид уведомления checkpoint_due (signing-route.md, 16.5 и 16.7)

Колонка nullable и без значения по умолчанию: у всех маршрутов NULL, то есть срок черновика не считался из срока точки
(маршруты до раздела 16), данных миграция не переносит. Вид `checkpoint_due` только расширяет проверку
`notifications.kind`. Старая версия api колонку не читает и не пишет, новых видов уведомлений не создаёт (правило
expand/contract, docs/ru/deploy/operations.md).

Revision ID: dl_02_checkpoint_reminders
Revises: sr_12_preset_version
Create Date: 2026-11-23 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "dl_02_checkpoint_reminders"
down_revision: str | None = "sr_12_preset_version"
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
    "signing_skipped",
    "runner_disk_cleaned",
)
_NEW_KINDS = ("checkpoint_due",)


def _replace_kind_check(kinds: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_notifications_kind"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_kind"), "notifications", f"kind IN {kinds!r}")


def upgrade() -> None:
    op.add_column("signing_routes", sa.Column("point_deadline", sa.DateTime(timezone=True), nullable=True))
    _replace_kind_check((*_OLD_KINDS, *_NEW_KINDS))


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind = 'checkpoint_due'")
    _replace_kind_check(_OLD_KINDS)
    op.drop_column("signing_routes", "point_deadline")
