"""Автообновление: проверка релизов, решение планировщика, запуски, приём сообщений апдейтера.

Исполняет обновление не этот процесс, а отдельный сервис-апдейтер (docs/design/auto-update.md): здесь только решения и
учёт. Апдейтер приходит за работой сам (`poll`) и сообщает ход событиями; api с докером не работает.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import uuid4

import structlog

from hse_doc_studio.core.backup.entities import BackupRun
from hse_doc_studio.core.backup.entities import RunStatus as BackupRunStatus
from hse_doc_studio.core.backup.entities import RunTrigger as BackupTrigger
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.backup.protocols import IAdminDirectory, IBackupDestinationRepository, IBackupRunRepository
from hse_doc_studio.core.diagnostics.acceptance import BACKUPS_CHECK, Acceptance, live_acceptance
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.invitations.protocols import INotifier
from hse_doc_studio.core.listing import Found, Window
from hse_doc_studio.core.server_update.decision import Action, DecisionInput, decide
from hse_doc_studio.core.server_update.entities import (
    TERMINAL_STATUSES,
    RunEvent,
    RunKind,
    RunStatus,
    RunTrigger,
    UpdatePolicy,
    UpdateRun,
    UpdateSettings,
    Verify,
)
from hse_doc_studio.core.server_update.errors import UpdateError, UpdateErrorCode
from hse_doc_studio.core.server_update.options import UpdateOptions
from hse_doc_studio.core.server_update.protocols import IReleaseSource, IUpdateRunRepository, append_events
from hse_doc_studio.core.server_update.settings import (
    KEY_ATTEMPT_AT,
    KEY_CHECK_ERROR,
    KEY_CHECKED_AT,
    KEY_NOTIFIED,
    KEY_RELEASES,
    KEY_UPDATER_SEEN,
    KEY_UPDATER_VERSION,
    releases_from,
    releases_to,
    settings_from,
    settings_to,
    time_from,
    validate_settings,
)
from hse_doc_studio.core.server_update.status import UpdateStatus
from hse_doc_studio.core.server_update.versions import newest_release, pick_target
from hse_doc_studio.core.server_update.window import in_window, next_window_start
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.core.update.services import is_newer
from hse_doc_studio.use_cases.identity.auth_settings import SOURCE_ADMIN

logger = structlog.get_logger()

SOURCE_SYSTEM = "system"
_SEEN_WRITE_EVERY_S = 20.0
_ERROR_LIMIT = 500
_RISK_NOTE = "no full backup and no schema rollback: the risk is accepted"
_WAIVER_NOTE = "no full backup and no schema rollback: backups are off on purpose (accepted in self-diagnostics)"

# Исход запуска -> код `system_alert` во «Входящих».
_ALERT = {
    RunStatus.succeeded: "update_succeeded",
    RunStatus.rolled_back: "update_rolled_back",
    RunStatus.failed: "update_failed",
    RunStatus.cancelled: "update_cancelled",
}


class IBackupStarter(Protocol):
    async def start(self, *, trigger: BackupTrigger, destination_id: str | None, actor_id: str | None) -> BackupRun: ...


@dataclass(frozen=True)
class RunSpec:
    """Что апдейтер получает на исполнение."""

    run_id: str
    kind: RunKind
    from_version: str
    to_version: str
    verify: Verify
    digests_url: str
    restore_db: bool


@dataclass(frozen=True)
class PollReport:
    updater_version: str = ""
    busy: bool = False


@dataclass(frozen=True)
class EventReport:
    seq: int
    at: datetime
    phase: str
    level: str
    message: str
    status: RunStatus | None = None
    from_revision: str | None = None
    to_revision: str | None = None
    db_restored: bool | None = None
    error_code: str | None = None


@dataclass
class UpdateSnapshot:
    """Последнее известное состояние для метрик `hse_update_*`: читается без базы."""

    policy: UpdatePolicy = UpdatePolicy.notify
    available: bool = False
    updater_online: bool = False
    executor_enabled: bool = False
    checked_at: datetime | None = None
    active: bool = False
    counts: Mapping[RunStatus, int] = field(default_factory=dict)
    last_finished_at: datetime | None = None
    last_duration_s: float | None = None
    last_success: bool | None = None


class UpdateService:
    def __init__(  # noqa: PLR0913
        self,
        runs: IUpdateRunRepository,
        repo: IInstanceSettingsRepository,
        source: IReleaseSource,
        backup_service: IBackupStarter,
        backup_runs: IBackupRunRepository,
        destinations: IBackupDestinationRepository,
        audit: IAuditLog,
        notifier: INotifier,
        admins: IAdminDirectory,
        uow: IUnitOfWork,
        options: UpdateOptions,
        clock: Clock = utc_now,
    ) -> None:
        self._runs = runs
        self._repo = repo
        self._source = source
        self._backup = backup_service
        self._backup_runs = backup_runs
        self._destinations = destinations
        self._audit = audit
        self._notifier = notifier
        self._admins = admins
        self._uow = uow
        self._options = options
        self._clock = clock
        self._last_seen_write: datetime | None = None
        self.snapshot = UpdateSnapshot()

    @property
    def _cur(self) -> str:
        return self._options.current_version

    # ---- состояние ----

    def _updater_online(self, values: Mapping[str, object], now: datetime) -> bool:
        seen = time_from(values, KEY_UPDATER_SEEN)
        return seen is not None and (now - seen).total_seconds() <= self._options.updater_stale_s

    async def status(self) -> UpdateStatus:
        now = self._clock()
        values = await self._repo.get_all()
        settings = settings_from(values)
        releases = releases_from(values)
        last_ok = await self._runs.last_succeeded_update()
        can_rollback = (
            last_ok is not None
            and self._options.executor_enabled
            and last_ok.to_version == self._cur
            and last_ok.from_version != self._cur
        )
        schema_changed = bool(last_ok and last_ok.to_revision and last_ok.from_revision != last_ok.to_revision)
        has_destination = await self._destinations.get_default() is not None
        snapshotless = self._options.snapshotless
        unsafe_rollback = bool(last_ok and snapshotless and (schema_changed or not last_ok.to_revision))
        risky = self._options.executor_enabled and snapshotless and not (settings.backup_first and has_destination)
        waiver = live_acceptance(values, BACKUPS_CHECK, now) if risky else None
        return UpdateStatus(
            settings=settings,
            current_version=self._cur,
            executor_enabled=self._options.executor_enabled,
            updater_online=self._updater_online(values, now),
            updater_seen_at=time_from(values, KEY_UPDATER_SEEN),
            updater_version=str(values.get(KEY_UPDATER_VERSION) or "") or None,
            releases=releases,
            available=newest_release(self._cur, releases),
            auto_target=pick_target(self._cur, releases, settings.max_bump),
            checked_at=time_from(values, KEY_CHECKED_AT),
            check_error=str(values.get(KEY_CHECK_ERROR) or "") or None,
            in_window=in_window(now, settings.window_days, settings.window_start_min, settings.window_minutes),
            next_window_at=next_window_start(
                now, settings.window_days, settings.window_start_min, settings.window_minutes
            ),
            backup_destination_configured=has_destination,
            active_run=await self._runs.active(),
            last_run=await self._runs.last_finished(),
            rollback_version=last_ok.from_version if can_rollback and last_ok and not unsafe_rollback else None,
            rollback_needs_restore=bool(can_rollback and schema_changed and not snapshotless),
            executor=self._options.executor if self._options.executor_enabled else "none",
            rollback_blocked=can_rollback and unsafe_rollback,
            risk_confirmation_required=risky and waiver is None,
            backups_accepted=waiver,
        )

    # ---- настройки ----

    async def update_settings(self, actor_id: str, new: UpdateSettings) -> UpdateSettings:
        validate_settings(new)
        before = settings_from(await self._repo.get_all())
        async with self._uow.begin():
            for key, value in settings_to(new).items():
                await self._repo.set(key, value, source=SOURCE_ADMIN)
            if before.policy is UpdatePolicy.off and new.policy is not UpdatePolicy.off:
                await self._repo.delete(KEY_ATTEMPT_AT)  # включили: проверка на ближайшем тике
            if settings_to(before) != settings_to(new):
                await self._audit.record(
                    "update.settings_update",
                    actor_id=actor_id,
                    details={"before": settings_to(before), "after": settings_to(new)},
                )
        return new

    # ---- проверка релизов ----

    async def check_now(self, actor_id: str) -> UpdateStatus:
        await self._check(self._clock())
        await self._audit.record("update.check", actor_id=actor_id)
        return await self.status()

    async def _check(self, now: datetime) -> None:
        answer = await self._source.fetch()
        async with self._uow.begin():
            await self._repo.set(KEY_ATTEMPT_AT, now.isoformat(), source=SOURCE_SYSTEM)
            if answer.checked:
                await self._repo.set(KEY_RELEASES, releases_to(answer.releases), source=SOURCE_SYSTEM)
                await self._repo.set(KEY_CHECKED_AT, now.isoformat(), source=SOURCE_SYSTEM)
                await self._repo.delete(KEY_CHECK_ERROR)
            else:
                await self._repo.set(KEY_CHECK_ERROR, answer.reason[:_ERROR_LIMIT], source=SOURCE_SYSTEM)

    def _check_due(self, values: Mapping[str, object], now: datetime) -> bool:
        attempt = time_from(values, KEY_ATTEMPT_AT)
        if attempt is None:
            return True
        failed = bool(values.get(KEY_CHECK_ERROR))
        wait = self._options.retry_interval_s if failed else self._options.check_interval_s
        return (now - attempt).total_seconds() >= wait

    # ---- плановый тик ----

    async def tick(self) -> None:
        """Один проход планировщика под лидерским локом: уборка, бэкап, проверка релизов, решение."""
        now = self._clock()
        values = await self._repo.get_all()
        settings = settings_from(values)
        await self._janitor(now, values)
        await self._advance_backup(now)
        if settings.policy is not UpdatePolicy.off:
            if self._check_due(values, now):
                await self._check(now)
                values = await self._repo.get_all()
            await self._act(now, values, settings)
        await self._refresh_snapshot(now, values, settings)

    async def _act(self, now: datetime, values: Mapping[str, object], settings: UpdateSettings) -> None:
        decision = decide(
            DecisionInput(
                settings=settings,
                current=self._cur,
                releases=releases_from(values),
                now=now,
                executor_ready=self._options.executor_enabled,
                updater_online=self._updater_online(values, now),
                run_active=await self._runs.active() is not None,
                failed_versions=await self._runs.failed_targets(),
                notified_version=str(values.get(KEY_NOTIFIED) or "") or None,
                backup_unavailable=await self._risk_unconfirmed(settings),
            )
        )
        target = decision.target
        if target is None:
            return
        if decision.action is Action.notify:
            await self._repo.set(KEY_NOTIFIED, target.version, source=SOURCE_SYSTEM)
            if settings.notify_admins:
                await self._alert("update_available", target.version, decision.reason.value, f"upd-av:{target.version}")
        elif decision.action is Action.start:
            await self._create_run(
                RunKind.update, RunTrigger.auto, target.version, target.digests_url, settings, actor_id=None
            )

    # ---- запуски ----

    async def _risk_unconfirmed(self, settings: UpdateSettings) -> bool:
        """kubernetes: снимка базы нет, поэтому без полного бэкапа обновление идёт только с подтверждением риска."""
        if not self._options.snapshotless:
            return False
        return not (settings.backup_first and await self._destinations.get_default() is not None)

    async def request_update(self, actor_id: str, version: str | None, *, accept_risk: bool = False) -> UpdateRun:
        values = await self._repo.get_all()
        settings = settings_from(values)
        self._require_executor(values)
        releases = releases_from(values)
        if version:
            target = next((r for r in releases if r.version == version), None)
            if target is None:
                raise UpdateError(
                    UpdateErrorCode.unknown_version, "version is not in the release list", field="version"
                )
        else:
            target = newest_release(self._cur, releases)
        if target is None or not is_newer(target.version, self._cur):
            raise UpdateError(UpdateErrorCode.nothing_to_update, "already on the latest version")
        risky = await self._risk_unconfirmed(settings)
        # «Бэкапы не делаю сознательно» принято на странице самодиагностики: подтверждение каждый раз не нужно.
        waiver = live_acceptance(values, BACKUPS_CHECK, self._clock()) if risky else None
        if risky and not accept_risk and waiver is None:
            raise UpdateError(
                UpdateErrorCode.risk_not_confirmed,
                "there is no full backup before this update and the database cannot be rolled back: configure a "
                "backup destination or confirm the risk",
                field="accept_risk",
            )
        return await self._create_run(
            RunKind.update,
            RunTrigger.manual,
            target.version,
            target.digests_url,
            settings,
            actor_id=actor_id,
            risk_accepted=risky,
            risk_waiver=waiver,
        )

    async def request_rollback(self, actor_id: str, *, restore_db: bool) -> UpdateRun:
        values = await self._repo.get_all()
        settings = settings_from(values)
        self._require_executor(values)
        last = await self._runs.last_succeeded_update()
        if last is None or last.to_version != self._cur or last.from_version == self._cur:
            raise UpdateError(UpdateErrorCode.no_previous_version, "there is no update to roll back")
        needs_restore = bool(last.to_revision and last.from_revision != last.to_revision)
        if self._options.snapshotless:
            if needs_restore or not last.to_revision:
                raise UpdateError(
                    UpdateErrorCode.rollback_unsafe,
                    "the update changed the database schema (or its revision is unknown) and there is no snapshot: "
                    "the previous version cannot start on it; restore a backup by hand",
                )
            restore_db = False
        elif needs_restore and not restore_db:
            raise UpdateError(
                UpdateErrorCode.invalid_input,
                "the update changed the database schema: rolling back restores the pre-update snapshot "
                "and loses everything written since; confirm it",
                field="restore_db",
            )
        return await self._create_run(
            RunKind.rollback,
            RunTrigger.manual,
            last.from_version,
            "",
            settings,
            actor_id=actor_id,
            restore_db=needs_restore,
            verify=Verify.none,  # образ уже стоял на этом хосте и был проверен при установке
        )

    async def cancel(self, actor_id: str, run_id: str) -> UpdateRun:
        run = await self.get_run(run_id)
        if run.status not in {RunStatus.waiting_backup, RunStatus.queued}:
            raise UpdateError(UpdateErrorCode.not_cancellable, "the updater has already started this run")
        done = await self._finish(run, RunStatus.cancelled, "cancelled", "cancelled by an administrator")
        await self._audit.record("update.run_cancel", actor_id=actor_id, target=run.id)
        return done

    def _require_executor(self, values: Mapping[str, object]) -> None:
        if not self._options.executor_enabled:
            raise UpdateError(
                UpdateErrorCode.executor_unavailable,
                "this installation updates by hand (helm upgrade --atomic); the in-app executor is off",
            )
        if not self._updater_online(values, self._clock()):
            raise UpdateError(UpdateErrorCode.updater_offline, "the updater service does not answer")

    async def _create_run(  # noqa: PLR0913
        self,
        kind: RunKind,
        trigger: RunTrigger,
        to_version: str,
        digests_url: str,
        settings: UpdateSettings,
        *,
        actor_id: str | None,
        restore_db: bool = False,
        verify: Verify | None = None,
        risk_accepted: bool = False,
        risk_waiver: Acceptance | None = None,
    ) -> UpdateRun:
        now = self._clock()
        want_backup = settings.backup_first and await self._destinations.get_default() is not None
        run = UpdateRun(
            id=str(uuid4()),
            kind=kind,
            trigger=trigger,
            status=RunStatus.waiting_backup if want_backup else RunStatus.queued,
            from_version=self._cur,
            to_version=to_version,
            created_at=now,
            requested_by=actor_id,
            restore_db=restore_db,
            digests_url=digests_url,
            verify=verify or settings.verify,
            events=(RunEvent(0, now, "request", "info", f"requested {kind.value} to {to_version} ({trigger.value})"),),
        )
        if risk_accepted:
            run = append_events(
                run,
                [RunEvent(0, now, "backup", "warn", _RISK_NOTE if risk_waiver is None else _WAIVER_NOTE)],
            )
        if not await self._runs.add(run):
            raise UpdateError(UpdateErrorCode.already_running, "another update is already in progress")
        await self._audit.record(
            "update.run_request" if kind is RunKind.update else "update.rollback_request",
            actor_id=actor_id,
            target=run.id,
            details={
                "trigger": trigger.value,
                "from": run.from_version,
                "to": to_version,
                "backup_first": want_backup,
                "restore_db": restore_db,
                "risk_accepted": risk_accepted,
                "risk_waiver": risk_waiver.reason if risk_waiver else None,
            },
        )
        if want_backup:
            run = await self._start_backup(run, actor_id)
        return run

    # ---- полный бэкап перед запуском ----

    async def _start_backup(self, run: UpdateRun, actor_id: str | None) -> UpdateRun:
        try:
            started = await self._backup.start(trigger=BackupTrigger.manual, destination_id=None, actor_id=actor_id)
        except BackupError as exc:
            if exc.code is BackupErrorCode.already_running:
                return run  # другой бэкап идёт: следующий тик попробует снова
            if exc.code is BackupErrorCode.no_destination:
                return await self._advance(run, RunStatus.queued, "backup", "warn", "no backup destination: skipped")
            raise
        return await self._advance(
            run.with_(backup_run_id=started.id), RunStatus.waiting_backup, "backup", "info", "full backup started"
        )

    async def _advance_backup(self, now: datetime) -> None:
        run = await self._runs.active()
        if run is None or run.status is not RunStatus.waiting_backup:
            return
        if run.backup_run_id is None:
            if (now - run.created_at).total_seconds() > self._options.backup_wait_s:
                await self._finish(run, RunStatus.cancelled, "backup_failed", "timed out waiting for a backup slot")
                return
            await self._start_backup(run, run.requested_by)
            return
        backup = await self._backup_runs.get(run.backup_run_id)
        if backup is None or backup.status is BackupRunStatus.running:
            return
        if backup.status is BackupRunStatus.ok:
            await self._advance(run, RunStatus.queued, "backup", "info", "full backup finished")
        else:
            reason = f"pre-update backup failed: {backup.error or backup.status.value}"
            await self._finish(run, RunStatus.cancelled, "backup_failed", reason)

    async def _advance(self, run: UpdateRun, status: RunStatus, phase: str, level: str, message: str) -> UpdateRun:
        moved = append_events(
            run.with_(status=status, phase=phase), [RunEvent(0, self._clock(), phase, level, message)]
        )
        await self._runs.save(moved)
        return moved

    # ---- уборка ----

    async def _janitor(self, now: datetime, values: Mapping[str, object]) -> None:
        run = await self._runs.active()
        if run is None:
            return
        if run.status is RunStatus.queued and not self._updater_online(values, now):
            if (now - run.created_at).total_seconds() > self._options.queued_timeout_s:
                await self._finish(run, RunStatus.cancelled, "updater_offline", "the updater did not pick the run up")
        elif run.status is RunStatus.running:
            seen = time_from(values, KEY_UPDATER_SEEN)
            last = max(t for t in (seen, run.started_at, run.created_at) if t is not None)
            if (now - last).total_seconds() > self._options.run_lost_s:
                await self._finish(
                    run, RunStatus.failed, "updater_lost", "the updater went silent in the middle of the run"
                )

    # ---- протокол апдейтера ----

    async def poll(self, report: PollReport) -> RunSpec | None:
        now = self._clock()
        if self._last_seen_write is None or (now - self._last_seen_write).total_seconds() >= _SEEN_WRITE_EVERY_S:
            self._last_seen_write = now
            await self._repo.set(KEY_UPDATER_SEEN, now.isoformat(), source=SOURCE_SYSTEM)
            if report.updater_version:
                await self._repo.set(KEY_UPDATER_VERSION, report.updater_version, source=SOURCE_SYSTEM)
        if report.busy or not self._options.executor_enabled:
            return None
        async with self._uow.begin():
            run = await self._runs.claim_next(now_iso=now.isoformat())
            if run is None:
                return None
            run = append_events(run, [RunEvent(0, now, "preflight", "info", "picked up by the updater")])
            await self._runs.save(run)
        return RunSpec(run.id, run.kind, run.from_version, run.to_version, run.verify, run.digests_url, run.restore_db)

    async def report(self, run_id: str, event: EventReport) -> UpdateRun:
        """Событие апдейтера. Повтор `seq` и события после конца запуска игнорируются (доставка «хотя бы раз»)."""
        async with self._uow.begin():
            run = await self._runs.lock(run_id)
            if run is None:
                raise UpdateError(UpdateErrorCode.not_found, "run not found")
            if run.status in TERMINAL_STATUSES or event.seq <= run.last_seq:
                return run
            changes: dict[str, object] = {"phase": event.phase or run.phase}
            if event.from_revision:
                changes["from_revision"] = event.from_revision
            if event.to_revision:
                changes["to_revision"] = event.to_revision
            if event.db_restored is not None:
                changes["db_restored"] = event.db_restored
            updated = append_events(
                run.with_(**changes), [RunEvent(event.seq, event.at, event.phase, event.level, event.message[:1000])]
            )
            await self._runs.save(updated)
        if event.status is not None and event.status in TERMINAL_STATUSES:
            return await self._finish(updated, event.status, event.error_code or "", event.message)
        return updated

    async def _finish(self, run: UpdateRun, status: RunStatus, code: str, message: str) -> UpdateRun:
        now = self._clock()
        failed = status is not RunStatus.succeeded
        done = run.with_(
            status=status,
            finished_at=now,
            phase="finish",
            error_code=(code or None) if failed else None,
            error=message[:_ERROR_LIMIT] if failed else None,
        )
        await self._runs.save(done)
        await self._audit.record(
            "update.run_finish",
            actor_id=None,
            target=run.id,
            details={
                "result": status.value,
                "kind": run.kind.value,
                "from": run.from_version,
                "to": run.to_version,
                "from_revision": done.from_revision,
                "to_revision": done.to_revision,
                "db_restored": done.db_restored,
                "error_code": code or None,
                "duration_s": done.duration_s,
            },
        )
        if status is RunStatus.succeeded:
            await self._repo.delete(KEY_NOTIFIED)
        if settings_from(await self._repo.get_all()).notify_admins:
            await self._alert(_ALERT[status], run.to_version, message if failed else "", f"upd:{run.id}")
        self.snapshot.active = False
        logger.info("update run finished", run_id=run.id, status=status.value, to=run.to_version)
        return done

    # ---- уведомления и метрики ----

    async def _alert(self, outcome: str, version: str, excerpt: str, dedupe: str) -> None:
        payload = NotificationPayload(outcome=outcome, path=version, excerpt=excerpt[:200])
        try:
            for admin_id in await self._admins.active_admin_ids():
                await self._notifier.notify(admin_id, NotificationKind.system_alert, payload, dedupe_key=dedupe)
        except Exception:
            logger.warning("update notification failed", outcome=outcome, exc_info=True)

    async def _refresh_snapshot(self, now: datetime, values: Mapping[str, object], settings: UpdateSettings) -> None:
        last = await self._runs.last_finished()
        snap = self.snapshot
        snap.policy = settings.policy
        snap.available = newest_release(self._cur, releases_from(values)) is not None
        snap.updater_online = self._updater_online(values, now)
        snap.executor_enabled = self._options.executor_enabled
        snap.checked_at = time_from(values, KEY_CHECKED_AT)
        snap.active = await self._runs.active() is not None
        snap.counts = await self._runs.counts()
        snap.last_finished_at = last.finished_at if last else None
        snap.last_duration_s = last.duration_s if last else None
        snap.last_success = (last.status is RunStatus.succeeded) if last else None

    # ---- чтение ----

    async def list_runs(self, window: Window) -> Found[UpdateRun]:
        return await self._runs.page(window)

    async def get_run(self, run_id: str) -> UpdateRun:
        run = await self._runs.get(run_id)
        if run is None:
            raise UpdateError(UpdateErrorCode.not_found, "run not found")
        return run
