"""Системное предупреждение о месте доходит до клиента с кодом исхода, том и процент в payload."""

from __future__ import annotations

from datetime import UTC, datetime

from hse_doc_studio.api.invitation_views import notification
from hse_doc_studio.core.invitations.entities import Notification, NotificationKind, NotificationPayload


def _alert(outcome: str | None) -> Notification:
    return Notification(
        id="n1",
        user_id="boss",
        kind=NotificationKind.system_alert,
        payload=NotificationPayload(outcome=outcome, ref_id="data", excerpt="93"),
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
    )


def test__notification__storage_outcome__kept() -> None:
    model = notification(_alert("storage_critical"))

    assert model.kind == "system_alert"
    assert (model.payload.outcome, model.payload.ref_id, model.payload.excerpt) == ("storage_critical", "data", "93")


def test__notification__unknown_outcome__dropped() -> None:
    assert notification(_alert("weird")).payload.outcome is None
