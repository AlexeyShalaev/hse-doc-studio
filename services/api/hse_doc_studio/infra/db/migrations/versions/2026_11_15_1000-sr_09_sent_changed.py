"""signing_routes: причина остановки sent_changed (версия на подписи, signing-route.md 12.5)

Revision ID: sr_09_sent_changed
Revises: sr_08_notification_kinds
Create Date: 2026-11-15 10:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "sr_09_sent_changed"
down_revision: str | None = "sr_08_notification_kinds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_REASONS = ("rebuilt", "frozen_changed", "marks_changed", "participant_left", "returned")
_REASONS = (*_OLD_REASONS, "sent_changed")


def _replace_reason_check(reasons: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_signing_routes_stop_reason"), "signing_routes", type_="check")
    op.create_check_constraint(
        op.f("ck_signing_routes_stop_reason"), "signing_routes", f"stop_reason IS NULL OR stop_reason IN {reasons!r}"
    )


def upgrade() -> None:
    _replace_reason_check(_REASONS)


def downgrade() -> None:
    # Прежняя версия не знает `sent_changed`: ближайшая по смыслу причина 0.20.0 это `rebuilt`.
    op.execute("UPDATE signing_routes SET stop_reason = 'rebuilt' WHERE stop_reason = 'sent_changed'")
    _replace_reason_check(_OLD_REASONS)
