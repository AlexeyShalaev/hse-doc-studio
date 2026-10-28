from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.observability.install import install_auth_cleanup
from hse_doc_studio.use_cases.identity.housekeeping import AuthCleanupService

from tests.contract.test_auth_contract import NOW, make_mail, make_session
from tests.fakes.auth import (
    InMemoryAuthTokenRepository,
    InMemoryLoginAttemptRepository,
    InMemoryMailOutboxRepository,
    InMemorySessionRepository,
)

HOUR = timedelta(hours=1)


def _delay(failures: int) -> timedelta:
    return timedelta(seconds=failures)


def _service() -> tuple[AuthCleanupService, dict[str, object]]:
    repos: dict[str, object] = {
        "sessions": InMemorySessionRepository(),
        "tokens": InMemoryAuthTokenRepository(),
        "outbox": InMemoryMailOutboxRepository(),
        "attempts": InMemoryLoginAttemptRepository(),
    }
    service = AuthCleanupService(
        repos["sessions"],  # type: ignore[arg-type]
        repos["tokens"],  # type: ignore[arg-type]
        repos["outbox"],  # type: ignore[arg-type]
        repos["attempts"],  # type: ignore[arg-type]
        attempt_ttl=HOUR,
        clock=lambda: NOW,
    )
    return service, repos


async def test__run__removes_expired_and_keeps_live() -> None:
    service, repos = _service()
    sessions: InMemorySessionRepository = repos["sessions"]  # type: ignore[assignment]
    outbox: InMemoryMailOutboxRepository = repos["outbox"]  # type: ignore[assignment]
    attempts: InMemoryLoginAttemptRepository = repos["attempts"]  # type: ignore[assignment]
    await sessions.add(make_session("old", created=NOW - 2 * HOUR, ttl=HOUR))
    await sessions.add(make_session("live", created=NOW, ttl=HOUR))
    await outbox.add(make_mail("gone", NOW - 2 * HOUR))
    await outbox.add(make_mail("kept", NOW))
    await attempts.record_failure("stale", NOW - 2 * HOUR, _delay)
    await attempts.record_failure("fresh", NOW, _delay)

    report = await service.run()

    assert (report.sessions, report.mail_outbox, report.login_attempts) == (1, 1, 1)
    assert await sessions.get("old") is None
    assert await sessions.get("live") is not None
    assert await attempts.get("stale") is None
    assert await attempts.get("fresh") is not None


async def test__run__one_step_fails__others_still_run_and_error_is_raised() -> None:
    service, repos = _service()
    outbox: InMemoryMailOutboxRepository = repos["outbox"]  # type: ignore[assignment]
    await outbox.add(make_mail("gone", NOW - 2 * HOUR))

    async def boom(now: datetime) -> int:
        raise ConnectionError("db down")

    repos["sessions"].delete_expired = boom  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError):
        await service.run()
    assert await outbox.list_active(NOW - 2 * HOUR) == []


def test__install_auth_cleanup__registers_periodic_task() -> None:
    class _Runner:
        def __init__(self) -> None:
            self.tasks: list[object] = []

        def register(self, task: object) -> None:
            self.tasks.append(task)

    app = FastAPI()
    app.state.background = _Runner()
    cfg = Settings()

    install_auth_cleanup(app, None, cfg)  # type: ignore[arg-type]

    (task,) = app.state.background.tasks
    assert task.name == "auth_cleanup"  # type: ignore[attr-defined]
    assert task.interval_s == cfg.server.auth_cleanup_interval_s  # type: ignore[attr-defined]
