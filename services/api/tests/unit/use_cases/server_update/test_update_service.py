from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.backup.entities import RunStatus as BackupStatus
from hse_doc_studio.core.backup.errors import BackupErrorCode
from hse_doc_studio.core.diagnostics.acceptance import KEY_ACCEPTED, Acceptance, acceptances_to
from hse_doc_studio.core.server_update.entities import (
    ReleaseInfo,
    RunKind,
    RunStatus,
    UpdatePolicy,
    UpdateSettings,
)
from hse_doc_studio.core.server_update.errors import UpdateError, UpdateErrorCode
from hse_doc_studio.core.server_update.options import UpdateOptions
from hse_doc_studio.core.server_update.protocols import FeedAnswer
from hse_doc_studio.core.server_update.settings import settings_to
from hse_doc_studio.use_cases.server_update.service import EventReport, PollReport, UpdateService

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.backup import Admins, InMemoryDestinations, InMemoryRuns, RecordingNotifier
from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.ops import NoopUow
from tests.fakes.server_update import FakeBackupStarter, InMemoryUpdateRuns, StaticSource

NOW = datetime(2026, 11, 2, 3, 0, tzinfo=UTC)  # понедельник, внутри окна по умолчанию


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)


@dataclass
class Env:
    clock: Clock
    service: UpdateService
    runs: InMemoryUpdateRuns
    settings: InMemoryInstanceSettingsRepository
    source: StaticSource
    backup: FakeBackupStarter
    backup_runs: InMemoryRuns
    destinations: InMemoryDestinations
    audit: InMemoryAuditLog
    notifier: RecordingNotifier


def make(
    *, current: str = "0.3.1", executor: bool = True, releases: tuple[ReleaseInfo, ...] = (), kind: str = "compose"
) -> Env:
    clock = Clock()
    runs, settings, backup_runs = InMemoryUpdateRuns(), InMemoryInstanceSettingsRepository(), InMemoryRuns()
    destinations, audit, notifier = InMemoryDestinations(), InMemoryAuditLog(), RecordingNotifier()
    source = StaticSource(FeedAnswer(releases=releases, checked=True))
    backup = FakeBackupStarter(backup_runs)
    service = UpdateService(
        runs,
        settings,
        source,
        backup,
        backup_runs,
        destinations,
        audit,
        notifier,  # type: ignore[arg-type]
        Admins("boss"),
        NoopUow(),  # type: ignore[arg-type]
        UpdateOptions(current_version=current, executor_enabled=executor, executor=kind),
        clock,
    )
    return Env(clock, service, runs, settings, source, backup, backup_runs, destinations, audit, notifier)


async def configure(env: Env, **changes: object) -> UpdateSettings:
    base = UpdateSettings(policy=UpdatePolicy.auto, window_start_min=0, window_minutes=24 * 60, backup_first=False)
    new = UpdateSettings(**{**base.__dict__, **changes})
    for key, value in settings_to(new).items():
        await env.settings.set(key, value, source="admin")
    return new


async def updater_alive(env: Env) -> None:
    await env.service.poll(PollReport(updater_version="0.3.1", busy=True))


REL = (ReleaseInfo("0.3.2", digests_url="https://example.org/d.json"), ReleaseInfo("0.3.1"))


async def test__tick__auto_policy_queues_a_run_and_audits_it() -> None:
    env = make(releases=REL)
    await configure(env)
    await updater_alive(env)

    await env.service.tick()

    run = await env.runs.active()
    assert run is not None
    assert (run.status, run.to_version, run.trigger.value) == (RunStatus.queued, "0.3.2", "auto")
    assert [e.action for e in await env.audit.list()] == ["update.run_request"]


async def test__tick__notify_policy_alerts_admins_once_per_version() -> None:
    env = make(releases=REL)
    await configure(env, policy=UpdatePolicy.notify)

    await env.service.tick()
    env.clock.advance(hours=7)
    await env.service.tick()

    assert await env.runs.active() is None
    kinds = [(uid, kind, p.outcome, p.path) for uid, kind, p, _ in env.notifier.sent]  # type: ignore[attr-defined]
    assert kinds == [("boss", "system_alert", "update_available", "0.3.2")]


async def test__tick__policy_off_never_asks_the_feed() -> None:
    env = make(releases=REL)
    await configure(env, policy=UpdatePolicy.off)
    await env.service.tick()
    assert env.source.calls == 0


async def test__tick__feed_failure_is_recorded_and_retried_later() -> None:
    env = make()
    env.source.answer = FeedAnswer(reason="offline")
    await configure(env, policy=UpdatePolicy.notify)

    await env.service.tick()
    status = await env.service.status()
    assert status.check_error == "offline"
    calls = env.source.calls
    await env.service.tick()  # раньше времени повтора
    assert env.source.calls == calls
    env.clock.advance(minutes=31)
    await env.service.tick()
    assert env.source.calls == calls + 1


async def test__manual_update__needs_executor_and_a_live_updater() -> None:
    helm = make(executor=False, releases=REL)
    await configure(helm)
    await helm.service.check_now("boss")
    with pytest.raises(UpdateError) as exc:
        await helm.service.request_update("boss", None)
    assert exc.value.code is UpdateErrorCode.executor_unavailable

    env = make(releases=REL)
    await env.service.check_now("boss")
    with pytest.raises(UpdateError) as exc2:
        await env.service.request_update("boss", None)
    assert exc2.value.code is UpdateErrorCode.updater_offline


async def test__manual_update__validates_target_and_single_active_run() -> None:
    env = make(releases=REL)
    await configure(env)
    await env.service.check_now("boss")
    await updater_alive(env)

    with pytest.raises(UpdateError) as unknown:
        await env.service.request_update("boss", "9.9.9")
    run = await env.service.request_update("boss", None)
    with pytest.raises(UpdateError) as busy:
        await env.service.request_update("boss", None)

    assert unknown.value.code is UpdateErrorCode.unknown_version
    assert busy.value.code is UpdateErrorCode.already_running
    assert (run.to_version, run.requested_by) == ("0.3.2", "boss")


async def _destination(env: Env) -> None:
    from hse_doc_studio.core.backup.entities import (
        BackupDestination,
        DestinationKind,
        DestinationSpec,
        StoredDestination,
    )

    spec = DestinationSpec(name="d", kind=DestinationKind.local, local_path="x")
    dest = BackupDestination(
        id="d1", spec=spec, is_default=True, access_key_hint=None, secret_key_set=False, created_at=NOW, updated_at=NOW
    )
    await env.destinations.add(StoredDestination(dest, None, None))


async def test__backup_first__run_waits_for_the_backup_then_is_queued() -> None:
    env = make(releases=REL)
    await configure(env, backup_first=True)
    await _destination(env)
    await env.service.check_now("boss")
    await updater_alive(env)

    run = await env.service.request_update("boss", None)
    assert run.status is RunStatus.waiting_backup
    assert run.backup_run_id
    assert await env.service.poll(PollReport()) is None  # апдейтер работу ещё не получает

    await env.service.tick()
    assert (await env.runs.get(run.id)).status is RunStatus.waiting_backup  # type: ignore[union-attr]
    await env.backup.finish(run.backup_run_id, BackupStatus.ok)
    await env.service.tick()
    assert (await env.runs.get(run.id)).status is RunStatus.queued  # type: ignore[union-attr]
    spec = await env.service.poll(PollReport())
    assert spec is not None
    assert spec.to_version == "0.3.2"


async def test__backup_first__failed_backup_cancels_the_run_and_alerts() -> None:
    env = make(releases=REL)
    await configure(env, backup_first=True)
    await _destination(env)
    await env.service.check_now("boss")
    await updater_alive(env)
    run = await env.service.request_update("boss", None)

    await env.backup.finish(run.backup_run_id or "", BackupStatus.failed, "disk full")
    await env.service.tick()

    done = await env.runs.get(run.id)
    assert done is not None
    assert done.status is RunStatus.cancelled
    assert done.error_code == "backup_failed"
    assert "disk full" in (done.error or "")
    assert any(p.outcome == "update_cancelled" for _u, _k, p, _d in env.notifier.sent)  # type: ignore[attr-defined]


async def test__backup_first__no_destination_skips_the_full_backup() -> None:
    env = make(releases=REL)
    await configure(env, backup_first=True)
    await env.service.check_now("boss")
    await updater_alive(env)
    run = await env.service.request_update("boss", None)
    assert run.status is RunStatus.queued


async def test__backup_first__another_backup_running_keeps_waiting() -> None:
    env = make(releases=REL)
    env.backup.error = BackupErrorCode.already_running
    await configure(env, backup_first=True)
    await _destination(env)
    await env.service.check_now("boss")
    await updater_alive(env)
    run = await env.service.request_update("boss", None)
    assert run.status is RunStatus.waiting_backup
    assert run.backup_run_id is None


async def _claimed(env: Env) -> str:
    await configure(env)
    await env.service.check_now("boss")
    await updater_alive(env)
    await env.service.request_update("boss", None)
    spec = await env.service.poll(PollReport())
    assert spec is not None
    return spec.run_id


def ev(seq: int, **kw: object) -> EventReport:
    base: dict[str, object] = {"seq": seq, "at": NOW, "phase": "pull", "level": "info", "message": "m"}
    base.update(kw)
    return EventReport(**base)  # type: ignore[arg-type]


async def test__report__events_are_idempotent_and_terminal_runs_are_frozen() -> None:
    env = make(releases=REL)
    run_id = await _claimed(env)

    await env.service.report(run_id, ev(1, phase="snapshot", from_revision="r1"))
    await env.service.report(run_id, ev(1, phase="snapshot", message="dup"))
    await env.service.report(run_id, ev(2, phase="migrate", to_revision="r2"))
    done = await env.service.report(
        run_id, ev(3, phase="finish", status=RunStatus.succeeded, from_revision="r1", to_revision="r2")
    )
    again = await env.service.report(run_id, ev(4, status=RunStatus.failed))

    assert done.status is RunStatus.succeeded
    assert again.status is RunStatus.succeeded
    assert [e.seq for e in done.events if e.seq] == [1, 2, 3]
    assert (done.from_revision, done.to_revision) == ("r1", "r2")
    assert [e.action for e in await env.audit.list()][0] == "update.run_finish"
    assert any(p.outcome == "update_succeeded" for _u, _k, p, _d in env.notifier.sent)  # type: ignore[attr-defined]


async def test__report__rollback_outcome_is_audited_and_alerted_with_the_reason() -> None:
    env = make(releases=REL)
    run_id = await _claimed(env)
    done = await env.service.report(
        run_id,
        ev(
            1,
            phase="finish",
            status=RunStatus.rolled_back,
            message="health timeout",
            error_code="health_timeout",
            db_restored=True,
        ),
    )
    assert done.status is RunStatus.rolled_back
    assert done.error_code == "health_timeout"
    assert done.db_restored
    sent = [p for _u, _k, p, _d in env.notifier.sent]  # type: ignore[attr-defined]
    assert sent[-1].outcome == "update_rolled_back"
    assert "health timeout" in (sent[-1].excerpt or "")
    # откатившаяся версия автоматически больше не ставится
    await env.service.tick()
    assert await env.runs.active() is None


async def test__janitor__queued_run_without_updater_is_cancelled() -> None:
    env = make(releases=REL)
    await configure(env)
    await env.service.check_now("boss")
    await updater_alive(env)
    run = await env.service.request_update("boss", None)
    env.clock.advance(minutes=20)
    await env.service.tick()
    done = await env.runs.get(run.id)
    assert done is not None
    assert done.status is RunStatus.cancelled
    assert done.error_code == "updater_offline"


async def test__janitor__running_run_with_silent_updater_fails() -> None:
    env = make(releases=REL)
    run_id = await _claimed(env)
    env.clock.advance(minutes=20)
    await env.service.tick()
    done = await env.runs.get(run_id)
    assert done is not None
    assert done.status is RunStatus.failed
    assert done.error_code == "updater_lost"


async def test__rollback__guards_and_schema_confirmation() -> None:
    env = make(releases=REL)
    await updater_alive(env)
    with pytest.raises(UpdateError) as none:
        await env.service.request_rollback("boss", restore_db=False)
    assert none.value.code is UpdateErrorCode.no_previous_version

    run_id = await _claimed(env)
    await env.service.report(
        run_id, ev(1, phase="finish", status=RunStatus.succeeded, from_revision="r1", to_revision="r2")
    )
    # приложение теперь на 0.3.2
    env.service._options = UpdateOptions(current_version="0.3.2", executor_enabled=True)  # noqa: SLF001
    await updater_alive(env)

    status = await env.service.status()
    assert (status.rollback_version, status.rollback_needs_restore) == ("0.3.1", True)
    with pytest.raises(UpdateError) as unconfirmed:
        await env.service.request_rollback("boss", restore_db=False)
    assert unconfirmed.value.code is UpdateErrorCode.invalid_input
    assert unconfirmed.value.field == "restore_db"

    run = await env.service.request_rollback("boss", restore_db=True)
    assert (run.kind, run.to_version, run.restore_db) == (RunKind.rollback, "0.3.1", True)


async def test__cancel__only_before_the_updater_starts() -> None:
    env = make(releases=REL)
    await configure(env)
    await env.service.check_now("boss")
    await updater_alive(env)
    run = await env.service.request_update("boss", None)
    cancelled = await env.service.cancel("boss", run.id)
    assert cancelled.status is RunStatus.cancelled

    run2 = await env.service.request_update("boss", None)
    await env.service.poll(PollReport())
    with pytest.raises(UpdateError) as late:
        await env.service.cancel("boss", run2.id)
    assert late.value.code is UpdateErrorCode.not_cancellable


async def test__poll__marks_the_updater_online_and_busy_updaters_get_no_work() -> None:
    env = make(releases=REL)
    await configure(env)
    await env.service.check_now("boss")
    assert (await env.service.status()).updater_online is False
    await env.service.poll(PollReport(updater_version="0.3.1"))
    status = await env.service.status()
    assert status.updater_online
    assert status.updater_version == "0.3.1"
    await env.service.request_update("boss", None)
    assert await env.service.poll(PollReport(busy=True)) is None
    env.clock.advance(minutes=3)
    assert (await env.service.status()).updater_online is False


async def test__snapshot_feeds_metrics() -> None:
    env = make(releases=REL)
    await configure(env)
    await updater_alive(env)
    await env.service.tick()
    snap = env.service.snapshot
    assert snap.available
    assert snap.updater_online
    assert snap.active
    assert snap.executor_enabled


# ---- kubernetes: снимка базы нет ----


async def test__kubernetes__manual_update_without_backup_needs_the_risk_confirmed() -> None:
    env = make(releases=REL, kind="kubernetes")
    await configure(env, backup_first=True)
    await env.service.check_now("boss")
    await updater_alive(env)
    assert (await env.service.status()).risk_confirmation_required is True

    with pytest.raises(UpdateError) as caught:
        await env.service.request_update("boss", None)
    assert (caught.value.code, caught.value.field) == (UpdateErrorCode.risk_not_confirmed, "accept_risk")
    assert await env.runs.active() is None

    run = await env.service.request_update("boss", None, accept_risk=True)

    assert run.status is RunStatus.queued
    assert any(e.level == "warn" and "risk is accepted" in e.message for e in run.events)
    (audit,) = [e for e in await env.audit.list() if e.action == "update.run_request"]
    assert audit.details["risk_accepted"] is True


async def _accept_no_backups(env: Env, *, until: datetime | None = None, reason: str = "Бэкапы делает хостер") -> None:
    stored = {"backups": Acceptance("backups", reason, "boss", "Админ", env.clock.now, until)}
    await env.settings.set(KEY_ACCEPTED, acceptances_to(stored), source="admin")


async def test__kubernetes__backups_accepted_on_purpose__manual_update_does_not_ask_and_says_why() -> None:
    env = make(releases=REL, kind="kubernetes")
    await configure(env, backup_first=True)
    await _accept_no_backups(env)
    await env.service.check_now("boss")
    await updater_alive(env)

    status = await env.service.status()
    assert status.risk_confirmation_required is False
    assert status.backups_accepted is not None
    assert status.backups_accepted.reason == "Бэкапы делает хостер"

    run = await env.service.request_update("boss", None)  # accept_risk не нужен

    assert run.status is RunStatus.queued
    assert any(e.level == "warn" and "on purpose" in e.message for e in run.events)
    (audit,) = [e for e in await env.audit.list() if e.action == "update.run_request"]
    assert (audit.details["risk_accepted"], audit.details["risk_waiver"]) == (True, "Бэкапы делает хостер")


async def test__kubernetes__acceptance_expired_or_destination_added__confirmation_is_asked_again() -> None:
    env = make(releases=REL, kind="kubernetes")
    await configure(env, backup_first=True)
    await _accept_no_backups(env, until=env.clock.now + timedelta(hours=1))
    await env.service.check_now("boss")
    await updater_alive(env)
    env.clock.advance(hours=2)
    await updater_alive(env)

    status = await env.service.status()
    assert (status.risk_confirmation_required, status.backups_accepted) == (True, None)
    with pytest.raises(UpdateError) as caught:
        await env.service.request_update("boss", None)
    assert caught.value.code is UpdateErrorCode.risk_not_confirmed

    await _accept_no_backups(env)
    await _destination(env)  # бэкапы появились: подтверждение не нужно вовсе, запись молчит
    status = await env.service.status()
    assert (status.risk_confirmation_required, status.backups_accepted) == (False, None)


async def test__kubernetes__auto_install_ignores_the_acceptance_and_still_only_tells_the_admins() -> None:
    env = make(releases=REL, kind="kubernetes")
    await configure(env, backup_first=True)
    await _accept_no_backups(env)
    await updater_alive(env)

    await env.service.tick()

    assert await env.runs.active() is None
    outcomes = [(p.outcome, p.excerpt) for _, _, p, _ in env.notifier.sent]  # type: ignore[attr-defined]
    assert outcomes == [("update_available", "backup_required")]


async def test__kubernetes__with_a_backup_destination_no_confirmation_is_needed_and_the_backup_runs() -> None:
    env = make(releases=REL, kind="kubernetes")
    await configure(env, backup_first=True)
    await _destination(env)
    await env.service.check_now("boss")
    await updater_alive(env)
    assert (await env.service.status()).risk_confirmation_required is False

    run = await env.service.request_update("boss", None)

    assert run.status is RunStatus.waiting_backup
    assert run.backup_run_id is not None


async def test__kubernetes__backup_switched_off_still_needs_the_confirmation_even_with_a_destination() -> None:
    env = make(releases=REL, kind="kubernetes")
    await configure(env, backup_first=False)
    await _destination(env)
    await env.service.check_now("boss")
    await updater_alive(env)

    with pytest.raises(UpdateError) as caught:
        await env.service.request_update("boss", None)
    assert caught.value.code is UpdateErrorCode.risk_not_confirmed


async def test__compose__never_asks_for_the_risk_confirmation() -> None:
    env = make(releases=REL)
    await configure(env, backup_first=True)
    await env.service.check_now("boss")
    await updater_alive(env)

    run = await env.service.request_update("boss", None)

    assert run.status is RunStatus.queued
    assert (await env.service.status()).risk_confirmation_required is False


async def test__kubernetes__auto_policy_does_not_install_without_a_backup_and_tells_the_admins_once() -> None:
    env = make(releases=REL, kind="kubernetes")
    await configure(env, backup_first=True)
    await updater_alive(env)

    await env.service.tick()
    await env.service.tick()

    assert await env.runs.active() is None
    assert [p.outcome for _u, _k, p, _d in env.notifier.sent] == ["update_available"]  # type: ignore[attr-defined]


async def test__kubernetes__auto_policy_installs_when_the_backup_will_run() -> None:
    env = make(releases=REL, kind="kubernetes")
    await configure(env, backup_first=True)
    await _destination(env)
    await updater_alive(env)

    await env.service.tick()

    run = await env.runs.active()
    assert run is not None
    assert run.status is RunStatus.waiting_backup


async def _succeeded_on_kubernetes(env: Env, *, from_rev: str, to_rev: str) -> None:
    await configure(env, backup_first=False)
    await env.service.check_now("boss")
    await updater_alive(env)
    await env.service.request_update("boss", None, accept_risk=True)
    spec = await env.service.poll(PollReport())
    assert spec is not None
    await env.service.report(
        spec.run_id, ev(1, phase="finish", status=RunStatus.succeeded, from_revision=from_rev, to_revision=to_rev)
    )
    env.service._options = UpdateOptions(  # noqa: SLF001
        current_version="0.3.2", executor_enabled=True, executor="kubernetes"
    )
    await updater_alive(env)


async def test__kubernetes__rollback_is_offered_only_while_the_schema_is_unchanged() -> None:
    env = make(releases=REL, kind="kubernetes")
    await _succeeded_on_kubernetes(env, from_rev="r1", to_rev="r1")

    status = await env.service.status()
    assert (status.rollback_version, status.rollback_blocked, status.rollback_needs_restore) == ("0.3.1", False, False)
    run = await env.service.request_rollback("boss", restore_db=True)
    assert (run.kind, run.restore_db) == (RunKind.rollback, False), "восстанавливать базу в kubernetes нечем"


async def test__kubernetes__rollback_after_a_schema_change_is_blocked() -> None:
    env = make(releases=REL, kind="kubernetes")
    await _succeeded_on_kubernetes(env, from_rev="r1", to_rev="r2")

    status = await env.service.status()
    assert (status.rollback_version, status.rollback_blocked, status.rollback_needs_restore) == (None, True, False)
    with pytest.raises(UpdateError) as caught:
        await env.service.request_rollback("boss", restore_db=True)
    assert caught.value.code is UpdateErrorCode.rollback_unsafe


async def test__status__executor_kind_follows_the_options() -> None:
    assert (await make(kind="kubernetes").service.status()).executor == "kubernetes"
    assert (await make(executor=False, kind="kubernetes").service.status()).executor == "none"
    assert (await make().service.status()).executor == "compose"
