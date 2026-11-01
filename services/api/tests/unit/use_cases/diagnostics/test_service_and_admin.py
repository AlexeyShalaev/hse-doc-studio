"""Сервис самодиагностики: прогон, изоляция сбоев, антидребезг уведомлений, ручной прогон и пороги."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.diagnostics.entities import CHECK_BY_ID, CheckId, CheckSpec, DiagStatus, Verdict
from hse_doc_studio.core.diagnostics.thresholds import BOUNDS, DEFAULTS, KEY_LAST_TICK, KEY_NOTIFY, KEY_PREFIX
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.invitations.entities import NotificationKind
from hse_doc_studio.use_cases.diagnostics.admin import (
    GetDiagnosticsUC,
    RunDiagnosticsUC,
    UpdateDiagnosticsThresholdsUC,
)
from hse_doc_studio.use_cases.diagnostics.service import DiagnosticsService

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.data_lifecycle import FakeAdmins, FakeNotifier
from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.ops import NoopUow

ADMIN = Actor(kind=ActorKind.user, id="boss", is_instance_admin=True)
STUDENT = Actor(kind=ActorKind.user, id="anna")


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 5, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def step(self, minutes: int = 5) -> None:
        self.now += timedelta(minutes=minutes)


class ScriptedCheck:
    def __init__(self, check_id: CheckId, *script: Verdict | BaseException) -> None:
        self._spec = CHECK_BY_ID[check_id.value]
        self.script = list(script)
        self.calls = 0

    @property
    def spec(self) -> CheckSpec:
        return self._spec

    async def run(self, t: object, now: datetime) -> Verdict:
        self.calls += 1
        item = self.script[min(self.calls, len(self.script)) - 1]
        if isinstance(item, BaseException):
            raise item
        return item


class HangingCheck(ScriptedCheck):
    async def run(self, t: object, now: datetime) -> Verdict:
        await asyncio.sleep(10)
        return Verdict(DiagStatus.ok, "ok")


class MemStore:
    def __init__(self) -> None:
        self.rows: dict[str, object] = {}

    async def load(self) -> dict[str, object]:
        return dict(self.rows)

    async def save(self, state: object) -> None:
        self.rows[state.result.check_id] = state  # type: ignore[attr-defined]


def _ok() -> Verdict:
    return Verdict(DiagStatus.ok, "ok")


def _fail() -> Verdict:
    return Verdict(DiagStatus.fail, "db_unreachable", {"error": "OSError"})


class Env:
    def __init__(self, *checks: ScriptedCheck, timeout_s: float = 5) -> None:
        self.clock = Clock()
        self.store = MemStore()
        self.settings = InMemoryInstanceSettingsRepository()
        self.notifier = FakeNotifier()
        self.audit = InMemoryAuditLog()
        self.service = DiagnosticsService(
            checks,  # type: ignore[arg-type]
            self.store,  # type: ignore[arg-type]
            self.settings,
            self.notifier,  # type: ignore[arg-type]
            FakeAdmins(),
            timeout_s=timeout_s,
            clock=self.clock,
        )
        self.get = GetDiagnosticsUC(self.service, self.settings, interval_s=300, enabled=True)


async def test__tick__saves_results_and_heartbeat() -> None:
    env = Env(ScriptedCheck(CheckId.database, _ok()))

    await env.service.tick()

    saved = env.store.rows["database"]
    assert saved.result.status is DiagStatus.ok  # type: ignore[attr-defined]
    assert (await env.settings.get_all())[KEY_LAST_TICK] == env.clock.now.isoformat()


async def test__tick__failing_check__notifies_each_admin_after_confirmation() -> None:
    env = Env(ScriptedCheck(CheckId.database, _fail()))

    await env.service.tick()
    assert env.notifier.sent == []
    env.clock.step()
    await env.service.tick()

    assert [(u, k) for u, k, _, _ in env.notifier.sent] == [
        ("a1", NotificationKind.system_alert),
        ("a2", NotificationKind.system_alert),
    ]
    payload = env.notifier.sent[0][2]
    assert (payload.outcome, payload.ref_id, payload.excerpt) == ("diag_fail", "database", "db_unreachable")
    assert env.notifier.sent[0][3].startswith("diag:database:diag_fail:")  # type: ignore[union-attr]

    env.clock.step()
    await env.service.tick()
    assert len(env.notifier.sent) == 2  # без повторов, пока проблема та же


async def test__tick__recovery_notifies() -> None:
    env = Env(ScriptedCheck(CheckId.database, _fail(), _fail(), _ok(), _ok()))
    for _ in range(4):
        await env.service.tick()
        env.clock.step()

    outcomes = [p.outcome for _, _, p, _ in env.notifier.sent]
    assert outcomes == ["diag_fail", "diag_fail", "diag_recovered", "diag_recovered"]


async def test__tick__notify_off__stores_but_silent() -> None:
    env = Env(ScriptedCheck(CheckId.database, _fail()))
    await env.settings.set(KEY_NOTIFY, False, source="admin")

    await env.service.tick()
    env.clock.step()
    await env.service.tick()

    assert env.notifier.sent == []
    assert env.store.rows["database"].result.status is DiagStatus.fail  # type: ignore[attr-defined]


async def test__run__exception_becomes_fail_without_secrets_and_others_continue() -> None:
    boom = ScriptedCheck(CheckId.database, RuntimeError("password=hunter2"))
    fine = ScriptedCheck(CheckId.migrations, _ok())
    env = Env(boom, fine)

    states = await env.service.run(notify=False)

    broken = states["database"].result
    assert (broken.status, broken.reason, dict(broken.values)) == (
        DiagStatus.fail,
        "check_error",
        {"error": "RuntimeError"},
    )
    assert "hunter2" not in repr(states)
    assert states["migrations"].result.status is DiagStatus.ok


async def test__run__timeout_becomes_fail() -> None:
    env = Env(HangingCheck(CheckId.database), timeout_s=0.05)

    states = await env.service.run(notify=False)

    assert states["database"].result.reason == "check_timeout"


async def test__manual_run__does_not_advance_notifications() -> None:
    env = Env(ScriptedCheck(CheckId.database, _fail()))

    for _ in range(3):
        await env.service.run(notify=False)

    assert env.notifier.sent == []
    assert env.store.rows["database"].notified_status is None  # type: ignore[attr-defined]


async def test__run_only__runs_one_check() -> None:
    a = ScriptedCheck(CheckId.database, _ok())
    b = ScriptedCheck(CheckId.migrations, _ok())
    env = Env(a, b)

    await env.service.run(notify=False, only="migrations")

    assert (a.calls, b.calls) == (0, 1)


async def test__overview__not_yet_checked__status_none_and_overall_ok() -> None:
    env = Env(ScriptedCheck(CheckId.database, _fail()))

    fresh = await env.get.execute(ADMIN)
    assert fresh.overall is DiagStatus.ok
    assert all(c.state is None for c in fresh.checks)

    await env.service.run(notify=False)
    after = await env.get.execute(ADMIN)
    assert after.overall is DiagStatus.fail


async def test__overview__requires_admin() -> None:
    env = Env()
    with pytest.raises(IdentityError) as err:
        await env.get.execute(STUDENT)
    assert err.value.code is not None


async def test__run_uc__unknown_check__not_found_and_audited_run() -> None:
    env = Env(ScriptedCheck(CheckId.database, _ok()))
    uc = RunDiagnosticsUC(env.service, env.get, env.audit)

    with pytest.raises(IdentityError) as err:
        await uc.execute(ADMIN, "nope")
    assert err.value.code is IdentityErrorCode.not_found

    view = await uc.execute(ADMIN, "database")
    assert view.checks[0].state is not None
    assert any(e.action == "diagnostics.run" for e in env.audit._entries)  # noqa: SLF001


def _full() -> dict[str, int]:
    return {name: int(getattr(DEFAULTS, name)) for name in BOUNDS}


async def test__update_thresholds__saves_only_non_defaults() -> None:
    env = Env()
    uc = UpdateDiagnosticsThresholdsUC(env.settings, env.audit, NoopUow(), env.get)  # type: ignore[arg-type]

    view = await uc.execute(ADMIN, {**_full(), "tls_warn_days": 45}, False)

    stored = await env.settings.get_all()
    assert stored[KEY_PREFIX + "tls_warn_days"] == 45
    assert KEY_PREFIX + "tls_fail_days" not in stored
    assert stored[KEY_NOTIFY] is False
    assert view.thresholds.tls_warn_days == 45


@pytest.mark.parametrize(
    "patch",
    [{"tls_warn_days": 100000}, {"db_latency_warn_ms": 5000}, {"tls_warn_days": 3}],
)
async def test__update_thresholds__invalid__rejected(patch: dict[str, int]) -> None:
    env = Env()
    uc = UpdateDiagnosticsThresholdsUC(env.settings, env.audit, NoopUow(), env.get)  # type: ignore[arg-type]

    with pytest.raises(IdentityError) as err:
        await uc.execute(ADMIN, {**_full(), **patch}, True)
    assert err.value.code is IdentityErrorCode.input_invalid


async def test__update_thresholds__partial_set__rejected() -> None:
    env = Env()
    uc = UpdateDiagnosticsThresholdsUC(env.settings, env.audit, NoopUow(), env.get)  # type: ignore[arg-type]
    with pytest.raises(IdentityError):
        await uc.execute(ADMIN, {"tls_warn_days": 30}, True)
