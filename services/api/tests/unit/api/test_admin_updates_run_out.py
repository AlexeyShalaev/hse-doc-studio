"""Форма запуска в `/api/admin/updates`: тексты исполнителя очищены, имя инициатора на месте."""

from __future__ import annotations

from datetime import UTC, datetime

from hse_doc_studio.api.routers.admin_updates import _run
from hse_doc_studio.core.server_update.entities import RunEvent, RunKind, RunStatus, RunTrigger, UpdateRun

NOW = datetime(2026, 11, 17, 3, tzinfo=UTC)


def _failed() -> UpdateRun:
    return UpdateRun(
        id="r1",
        kind=RunKind.update,
        trigger=RunTrigger.manual,
        status=RunStatus.failed,
        from_version="0.3.1",
        to_version="0.3.2",
        created_at=NOW,
        requested_by="u1",
        requested_by_name="Анна",
        error_code="kube_forbidden",
        error="cannot write to /var/run/secrets with token=abc123 at 10.1.2.3:443",
        events=(
            RunEvent(1, NOW, "preflight", "info", "reading Deployment via api.ns.svc.cluster.local"),
            RunEvent(2, NOW, "finish", "error", "Authorization: Bearer SECRETVALUE rejected"),
        ),
    )


def test__run_out__redacts_error_and_events_but_keeps_the_code() -> None:
    out = _run(_failed())
    blob = out.error or ""
    for event in out.events:
        blob += " " + event.message
    for secret in ("abc123", "10.1.2.3", "/var/run/secrets", "SECRETVALUE", "svc.cluster.local"):
        assert secret not in blob
    assert out.error_code == "kube_forbidden"
    assert out.requested_by_name == "Анна"
    assert [e.phase for e in out.events] == ["preflight", "finish"]
