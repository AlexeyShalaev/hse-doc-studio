"""Движок очистки и контроль места на подставных источниках: сроки, статистика, сбои, предупреждения."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.invitations.entities import NotificationKind
from hse_doc_studio.core.lifecycle.disk import KEY_CRITICAL_PERCENT, KEY_WARN_PERCENT, SafeMode, StorageLevel
from hse_doc_studio.core.lifecycle.policies import POLICY_BY_KEY
from hse_doc_studio.core.lifecycle.ports import SourceSize
from hse_doc_studio.use_cases.lifecycle.admin import (
    GetLifecycleUC,
    RunLifecycleUC,
    TaskRun,
    UpdateRetentionUC,
    UpdateThresholdsUC,
)
from hse_doc_studio.use_cases.lifecycle.engine import LifecycleEngine
from hse_doc_studio.use_cases.lifecycle.guard import StorageGuard

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.data_lifecycle import FakeAdmins, FakeNotifier, FakeProbe, FakeRuns, FakeSource
from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.ops import NoopUow

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)
ADMIN = Actor(kind=ActorKind.user, id="boss", is_instance_admin=True)
STUDENT = Actor(kind=ActorKind.user, id="anna")


class Env:
    def __init__(self, *keys: str, fail: str | None = None) -> None:
        self.sources = {k: FakeSource(k, fail=k == fail) for k in keys}
        self.settings = InMemoryInstanceSettingsRepository()
        self.runs = FakeRuns()
        self.audit = InMemoryAuditLog()
        self.engine = LifecycleEngine(
            self.sources,
            self.settings,
            self.runs,
            self.audit,
            env_days={"audit_log": 365, "jobs": 30},
            batch_size=100,
            budget_s=10,
            clock=lambda: NOW,
        )


async def test__run_all__cutoff_from_registry_default_and_env() -> None:
    env = Env("audit_log", "notifications")

    await env.engine.run_all()

    audit_ctx = env.sources["audit_log"].seen[0]
    notif_ctx = env.sources["notifications"].seen[0]
    assert audit_ctx.cutoff == NOW - timedelta(days=365)
    assert notif_ctx.cutoff == NOW - timedelta(days=90)
    assert audit_ctx.batch_size == 100


async def test__run_all__admin_retention_overrides_default() -> None:
    env = Env("notifications")
    await env.settings.set("retention.notifications_days", 30, source="admin")

    await env.engine.run_all()

    assert env.sources["notifications"].seen[0].cutoff == NOW - timedelta(days=30)


async def test__run_all__env_zero_for_audit__no_cutoff() -> None:
    env = Env("audit_log")
    env.engine = LifecycleEngine(
        env.sources,
        env.settings,
        env.runs,
        env.audit,
        env_days={"audit_log": 0},
        batch_size=10,
        budget_s=1,
        clock=lambda: NOW,
    )

    await env.engine.run_all()

    assert env.sources["audit_log"].seen[0].cutoff is None


async def test__run_all__records_stats_and_audits_audit_purge() -> None:
    env = Env("audit_log", "notifications")

    await env.engine.run_all()
    await env.engine.run_all()

    assert env.runs.rows["notifications"].runs == 2
    assert env.runs.rows["notifications"].total_removed == 6
    actions = [e.action for e in await env.audit.list()]
    assert actions == ["audit.purged", "audit.purged"]
    assert env.engine.counters["audit_log"].partitions_dropped == 2
    assert env.engine.counters["notifications"].size == SourceSize(bytes=1024, rows=7)


async def test__run_all__one_failing_source__others_still_run_and_error_recorded() -> None:
    env = Env("audit_log", "notifications", fail="audit_log")

    outcomes = await env.engine.run_all()

    assert [o.error is not None for o in outcomes] == [True, False]
    assert env.runs.rows["audit_log"].last_error is not None
    assert env.runs.rows["notifications"].last_error is None
    assert env.engine.counters["audit_log"].errors == 1
    assert await env.audit.list() == []


async def test__run_all__skips_non_engine_policies() -> None:
    env = Env("notifications", "compile_records")

    await env.engine.run_all()

    assert env.sources["compile_records"].seen == []


async def test__update_retention__validates_bounds_and_audits() -> None:
    env = Env("notifications")
    uc = UpdateRetentionUC(env.settings, env.audit, NoopUow())

    await uc.execute(ADMIN, "notifications", 120)
    assert (await env.settings.get_all())["retention.notifications_days"] == 120
    await uc.execute(ADMIN, "notifications", None)
    assert "retention.notifications_days" not in await env.settings.get_all()
    assert [e.action for e in await env.audit.list()] == ["settings.retention_update"] * 2


@pytest.mark.parametrize(
    ("key", "days"),
    [("audit_log", 30), ("audit_log", 20000), ("notifications", 3), ("compile_records", 10), ("audit_log", 0)],
)
async def test__update_retention__out_of_bounds_or_not_editable__rejected(key: str, days: int) -> None:
    env = Env("notifications")
    uc = UpdateRetentionUC(env.settings, env.audit, NoopUow())

    with pytest.raises(IdentityError) as exc:
        await uc.execute(ADMIN, key, days)

    assert exc.value.code is IdentityErrorCode.input_invalid
    assert await env.settings.get_all() == {}


async def test__update_retention__unknown_key_or_not_admin__not_found() -> None:
    env = Env("notifications")
    uc = UpdateRetentionUC(env.settings, env.audit, NoopUow())

    for actor, key in ((ADMIN, "nope"), (STUDENT, "notifications")):
        with pytest.raises(IdentityError) as exc:
            await uc.execute(actor, key, 30)
        assert exc.value.code is IdentityErrorCode.not_found


async def test__run_now__audit_log_forbidden_others_allowed() -> None:
    env = Env("audit_log", "notifications")
    uc = RunLifecycleUC(env.engine, env.audit)

    with pytest.raises(IdentityError) as exc:
        await uc.execute(ADMIN, "audit_log")
    outcome = await uc.execute(ADMIN, "notifications")

    assert exc.value.code is IdentityErrorCode.forbidden
    assert outcome.removed == 3
    assert [e.action for e in await env.audit.list()] == ["lifecycle.run_now"]


async def test__thresholds__order_and_bounds_validated() -> None:
    env = Env("notifications")
    uc = UpdateThresholdsUC(env.settings, env.audit, NoopUow())

    await uc.execute(ADMIN, 70, 85)
    for warn, crit in ((90, 80), (80, 80), (10, 90), (80, 100)):
        with pytest.raises(IdentityError):
            await uc.execute(ADMIN, warn, crit)

    stored = await env.settings.get_all()
    assert (stored[KEY_WARN_PERCENT], stored[KEY_CRITICAL_PERCENT]) == (70, 85)


def _guard(ratio: float, settings: InMemoryInstanceSettingsRepository | None = None, *, safe_enabled: bool = True):
    probe = FakeProbe(ratio)
    notifier = FakeNotifier()
    mode = SafeMode()
    guard = StorageGuard(
        probe,
        settings or InMemoryInstanceSettingsRepository(),
        notifier,
        FakeAdmins(),
        mode,
        safe_mode_enabled=safe_enabled,
        clock=lambda: NOW,
    )
    return guard, probe, notifier, mode


async def test__guard__below_warning__quiet() -> None:
    guard, _, notifier, mode = _guard(0.5)

    assert await guard.tick() is StorageLevel.ok
    assert notifier.sent == []
    assert not mode.active


async def test__guard__warning__notifies_every_admin_without_safe_mode() -> None:
    guard, _, notifier, mode = _guard(0.82)

    assert await guard.tick() is StorageLevel.warning

    assert [s[0] for s in notifier.sent] == ["a1", "a2"]
    payload = notifier.sent[0][2]
    assert (notifier.sent[0][1], payload.outcome, payload.ref_id, payload.excerpt) == (
        NotificationKind.system_alert,
        "storage_warning",
        "data",
        "82",
    )
    assert notifier.sent[0][3] == "storage:data:storage_warning:2026-11-10"
    assert not mode.active


async def test__guard__critical__safe_mode_on_then_off_after_recovery() -> None:
    guard, probe, notifier, mode = _guard(0.95)

    await guard.tick()
    assert mode.active
    assert mode.reason == "data"
    assert notifier.sent[0][2].outcome == "storage_critical"

    probe.ratio = 0.4
    await guard.tick()
    assert not mode.active


async def test__guard__critical_with_safe_mode_disabled__only_notifies() -> None:
    guard, _, notifier, mode = _guard(0.95, safe_enabled=False)

    await guard.tick()

    assert notifier.sent
    assert not mode.active


async def test__guard__thresholds_from_admin_settings() -> None:
    settings = InMemoryInstanceSettingsRepository()
    await settings.set(KEY_WARN_PERCENT, 50, source="admin")
    await settings.set(KEY_CRITICAL_PERCENT, 60, source="admin")
    guard, _, _, mode = _guard(0.65, settings)

    assert await guard.tick() is StorageLevel.critical
    assert mode.active


async def test__overview__lists_every_policy_with_days_source_and_volumes() -> None:
    env = Env(*(k for k in POLICY_BY_KEY))
    await env.settings.set("retention.notifications_days", 120, source="admin")
    guard, _, _, mode = _guard(0.85, env.settings)
    uc = GetLifecycleUC(env.engine, env.settings, env.runs, guard, mode, lambda: {"auth_cleanup": TaskRun(4, 0, NOW)})
    await env.engine.run_one("notifications")

    view = await uc.execute(ADMIN)

    by_key = {s.policy.key: s for s in view.sources}
    assert set(by_key) == set(POLICY_BY_KEY)
    assert (by_key["notifications"].days, by_key["notifications"].days_source) == (120, "admin")
    assert (by_key["audit_log"].days, by_key["audit_log"].days_source) == (365, "default")
    assert by_key["guest_sessions"].days_source == "fixed"
    assert by_key["auth_records"].task == TaskRun(4, 0, NOW)
    assert by_key["notifications"].last_run is not None
    assert view.level is StorageLevel.warning
    assert [v.usage.name for v in view.volumes] == ["data", "database"]
