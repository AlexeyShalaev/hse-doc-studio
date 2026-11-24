"""Обновить все раннеры установки разом (docs в PR: «предложение после обновления системы»).

Студия сама ничего не придумывает про способ обновления: у каждого устаревшего раннера берётся тот путь, который уже
есть и проверен, то есть «Обновить» поставленного из админки (Docker рядом, Deployment) или «Обновить» по сохранённому
доступу SSH. Остальные раннеры (чарт Helm, `docker run`, служба на хосте) в списке как «обновить вручную».

Запуск идёт в памяти процесса (как ход установок), по одному раннеру: так остальные раннеры продолжают брать сборки.
Раннер с идущей сборкой не трогают: его обновляют, когда он освободится, а если не освободился за `busy_wait_s`, он
пропущен с кодом `busy`. Сбой одного раннера не останавливает остальных.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Protocol
from uuid import uuid4

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.identity.session_policy import utc_now
from hse_doc_studio.core.jobs.admin import runner_status
from hse_doc_studio.core.jobs.deployment import RunnerPlatform
from hse_doc_studio.core.jobs.errors import RunnerNotFoundError
from hse_doc_studio.core.jobs.runners import Runner, RunnerOwnerKind
from hse_doc_studio.core.runner_install import (
    InstallError,
    InstallJob,
    InstallTarget,
    LocalInstance,
    SavedSshCredential,
    SshError,
)
from hse_doc_studio.core.runner_install.entities import InstallJobState, InstallStepState
from hse_doc_studio.core.runner_install.fleet import (
    MAX_BATCHES,
    FleetBatch,
    FleetBatchState,
    FleetCandidate,
    FleetItem,
    FleetItemState,
    FleetKind,
    FleetPlan,
    ManualReason,
)
from hse_doc_studio.core.runner_isolation import installed_runner, is_outdated
from hse_doc_studio.core.settings_scope import SOURCE_ADMIN
from hse_doc_studio.core.uow import IUnitOfWork, spawn_detached
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from hse_doc_studio.use_cases.runner_install.service import InstallBusyError, InstallUnavailableError
from hse_doc_studio.use_cases.runner_install.ssh_service import SshPolicyError

logger = structlog.get_logger()

KEY_OFFER_DISMISSED = "runners.fleet_offer_dismissed_version"
BUSY_WAIT_S = 900.0
BUSY_POLL_S = 10.0
JOB_TIMEOUT_S = 1800.0
JOB_POLL_S = 2.0
RECONNECT_TIMEOUT_S = 180.0
VERSION_MAX = 64
_REASON_BY_PLATFORM = {
    RunnerPlatform.kubernetes: ManualReason.helm,
    RunnerPlatform.container: ManualReason.container,
    RunnerPlatform.host: ManualReason.host,
}


class FleetBusyError(Exception):
    """Общий запуск уже идёт: второй не начинается."""


class FleetSelectionError(Exception):
    """Выбор пуст или в нём раннер, которого не нужно или нельзя обновлять отсюда; `runner_ids` перечисляет их."""

    def __init__(self, runner_ids: list[str]) -> None:
        super().__init__("invalid selection")
        self.runner_ids = runner_ids


class IInstalledUpgrades(Protocol):
    """Обновление поставленного из админки раннера на месте (`RunnerInstallService`)."""

    @property
    def version(self) -> str: ...

    async def instances(self, actor: Actor) -> list[LocalInstance]: ...

    async def start_upgrade(self, actor: Actor, target: InstallTarget, name: str) -> InstallJob: ...

    def job(self, actor: Actor, job_id: str) -> InstallJob | None: ...


class ISshUpgrades(Protocol):
    """Обновление по сохранённому доступу SSH (`SshInstallService`)."""

    async def list_credentials(self, actor: Actor) -> list[SavedSshCredential]: ...

    async def run_saved(self, actor: Actor, credential_id: str, *, action: str, studio_url: str) -> InstallJob: ...


def _require_admin(actor: Actor) -> str:
    if not actor.is_instance_admin or actor.id is None:
        raise IdentityError(IdentityErrorCode.forbidden)
    return actor.id


class RunnerFleetService:
    def __init__(  # noqa: PLR0913
        self,
        registry: RunnerRegistry,
        installs: IInstalledUpgrades,
        ssh: ISshUpgrades | None,
        settings: IInstanceSettingsRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        studio_url: str = "",
        clock: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        busy_wait_s: float = BUSY_WAIT_S,
        busy_poll_s: float = BUSY_POLL_S,
        job_timeout_s: float = JOB_TIMEOUT_S,
        job_poll_s: float = JOB_POLL_S,
        reconnect_timeout_s: float = RECONNECT_TIMEOUT_S,
    ) -> None:
        self._registry = registry
        self._installs = installs
        self._ssh = ssh
        self._settings = settings
        self._audit = audit
        self._uow = uow
        # Адрес Студии для раннеров, когда запрос его не принёс (MCP): `public_url` установки.
        self._studio_url = studio_url
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._busy_wait_s = busy_wait_s
        self._busy_poll_s = busy_poll_s
        self._job_timeout_s = job_timeout_s
        self._job_poll_s = job_poll_s
        self._reconnect_timeout_s = reconnect_timeout_s
        self._batches: dict[str, FleetBatch] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    # ---- чтение ----

    async def plan(self, actor: Actor) -> FleetPlan:
        """Устаревшие раннеры установки и способ обновить каждый; личные раннеры людей не в счёт."""
        _require_admin(actor)
        server = self._installs.version
        runners = await self._registry.list_runners(actor, owner_kind=RunnerOwnerKind.instance)
        stale = sorted(
            (r for r in runners if r.revoked_at is None and is_outdated(r.version, server)), key=lambda r: r.name
        )
        items: list[FleetCandidate] = []
        if stale:
            by_instance = await self._by_instance(actor)
            by_ssh = await self._by_ssh(actor, runners)
            load = await self._registry.running_jobs({r.id for r in stale})
            now = self._clock()
            items = [self._candidate(r, server, by_instance, by_ssh, load.get(r.id, 0), now) for r in stale]
        dismissed = (await self._settings.get_all()).get(KEY_OFFER_DISMISSED)
        return FleetPlan(
            server_version=server,
            items=tuple(items),
            dismissed_version=dismissed if isinstance(dismissed, str) and dismissed else None,
            batch=self._running(),
        )

    def batch(self, actor: Actor, batch_id: str) -> FleetBatch | None:
        _require_admin(actor)
        return self._batches.get(batch_id)

    def _running(self) -> FleetBatch | None:
        return next((b for b in self._batches.values() if b.state is FleetBatchState.running), None)

    async def _by_instance(self, actor: Actor) -> dict[str, LocalInstance]:
        try:
            found = await self._installs.instances(actor)
        except Exception:
            # Хост не ответил (docker или кластер недоступны): такие раннеры покажутся как «вручную».
            logger.warning("fleet_instances_failed", exc_info=True)
            return {}
        return {i.runner_id: i for i in found if i.runner_id is not None}

    async def _by_ssh(self, actor: Actor, runners: list[Runner]) -> dict[str, SavedSshCredential]:
        if self._ssh is None:
            return {}
        try:
            credentials = await self._ssh.list_credentials(actor)
        except Exception:
            logger.warning("fleet_credentials_failed", exc_info=True)
            return {}
        found: dict[str, SavedSshCredential] = {}
        for credential in credentials:
            runner = installed_runner(credential.runner_name, runners) if credential.runner_name else None
            if runner is not None:
                found.setdefault(runner.id, credential)
        return found

    @staticmethod
    def _candidate(  # noqa: PLR0913
        runner: Runner,
        server: str,
        by_instance: Mapping[str, LocalInstance],
        by_ssh: Mapping[str, SavedSshCredential],
        running_jobs: int,
        now: datetime,
    ) -> FleetCandidate:
        instance = by_instance.get(runner.id)
        credential = by_ssh.get(runner.id)
        reason: ManualReason | None = None
        if instance is not None:
            kind, ref = FleetKind(instance.target.value), instance.name
        elif credential is not None:
            kind, ref = FleetKind.ssh, credential.id
        else:
            kind, ref = FleetKind.manual, ""
            report = runner.deployment
            reason = _REASON_BY_PLATFORM.get(report.platform, ManualReason.unknown) if report else ManualReason.unknown
        return FleetCandidate(
            runner_id=runner.id,
            name=runner.name,
            kind=kind,
            version=runner.version,
            target_version=server,
            status=runner_status(runner, now).value,
            running_jobs=running_jobs,
            manual_reason=reason,
            ref=ref,
        )

    # ---- отказ от предложения ----

    async def dismiss(self, actor: Actor, version: str) -> None:
        """Предложение для этой версии Студии больше не показывается (для всех админов установки)."""
        actor_id = _require_admin(actor)
        version = version.strip()[:VERSION_MAX]
        if not version:
            raise ValueError("version is empty")
        async with self._uow.begin():
            await self._settings.set(KEY_OFFER_DISMISSED, version, source=SOURCE_ADMIN)
            await self._audit.record(
                "runner_fleet.offer.dismiss", actor_id=actor_id, target=version, details={"version": version}
            )

    # ---- запуск ----

    async def start(self, actor: Actor, runner_ids: list[str], *, studio_url: str | None = None) -> FleetBatch:
        """Обновить выбранные раннеры по одному; в выборе только раннеры из `plan`, ручной или чужой id это отказ."""
        actor_id = _require_admin(actor)
        if self._running() is not None:
            raise FleetBusyError
        plan = await self.plan(actor)
        known = {c.runner_id: c for c in plan.items}
        chosen = list(dict.fromkeys(runner_ids))
        bad = [i for i in chosen if i not in known or not known[i].upgradable]
        if not chosen or bad:
            raise FleetSelectionError(bad)
        # Между проверкой и записью нет await: два запроса не начнут два запуска.
        if self._running() is not None:
            raise FleetBusyError
        batch = FleetBatch(
            id=uuid4().hex,
            created_by=actor_id,
            created_at=self._clock(),
            target_version=plan.server_version,
            items=[
                FleetItem(runner_id=c.runner_id, name=c.name, kind=c.kind, from_version=c.version, ref=c.ref)
                for c in (known[i] for i in chosen)
            ],
        )
        self._remember(batch)
        try:
            await self._record(
                "runner_fleet.upgrade.start",
                actor_id,
                batch,
                {
                    "to_version": batch.target_version,
                    "runners": [
                        {"id": i.runner_id, "name": i.name, "kind": i.kind.value, "from_version": i.from_version}
                        for i in batch.items
                    ],
                },
            )
        except Exception:
            del self._batches[batch.id]
            raise
        task = spawn_detached(self._run(actor, batch, studio_url or self._studio_url))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return batch

    async def cancel(self, actor: Actor, batch_id: str) -> FleetBatch:
        """Остановить после текущего раннера: идущее обновление доделывается, остальные пропускаются (`cancelled`)."""
        actor_id = _require_admin(actor)
        batch = self._batches.get(batch_id)
        if batch is None:
            raise RunnerNotFoundError(batch_id)
        if batch.state is FleetBatchState.running and not batch.cancel_requested:
            batch.cancel_requested = True
            await self._record("runner_fleet.upgrade.cancel", actor_id, batch, {})
        return batch

    def _remember(self, batch: FleetBatch) -> None:
        self._batches[batch.id] = batch
        while len(self._batches) > MAX_BATCHES:
            oldest = min(
                (b for b in self._batches.values() if b.state is FleetBatchState.finished),
                key=lambda b: b.created_at,
                default=None,
            )
            if oldest is None:
                break
            del self._batches[oldest.id]

    async def _record(self, action: str, actor_id: str, batch: FleetBatch, details: Mapping[str, object]) -> None:
        async with self._uow.begin():
            await self._audit.record(action, actor_id=actor_id, target=batch.id, details={"batch": batch.id, **details})

    # ---- ход ----

    async def _run(self, actor: Actor, batch: FleetBatch, studio_url: str) -> None:
        try:
            await self._work(actor, batch, studio_url)
        except Exception:
            logger.exception("runner_fleet_failed", batch=batch.id)
            for item in batch.items:
                if item.state in {FleetItemState.pending, FleetItemState.waiting, FleetItemState.running}:
                    self._end(item, FleetItemState.failed, "unexpected")
        finally:
            batch.state = FleetBatchState.finished
            batch.finished_at = self._clock()
            counts = {s.value: batch.count(s) for s in FleetItemState if batch.count(s)}
            await self._record(
                "runner_fleet.upgrade.finished",
                actor.id or "",
                batch,
                {
                    "counts": counts,
                    "cancelled": batch.cancel_requested,
                    "runners": [
                        {"id": i.runner_id, "name": i.name, "state": i.state.value, "code": i.code} for i in batch.items
                    ],
                },
            )

    async def _work(self, actor: Actor, batch: FleetBatch, studio_url: str) -> None:
        """Свободные раннеры по очереди; занятые ждут: освободился, значит обновляется, не успел, пропущен."""
        remaining = list(batch.items)
        waiting_since: dict[str, float] = {}
        while remaining and not batch.cancel_requested:
            busy = await self._registry.running_jobs({i.runner_id for i in remaining})
            self._hold_busy(remaining, busy, waiting_since)
            ready = next((i for i in remaining if not busy.get(i.runner_id)), None)
            if ready is None:
                if remaining:
                    await self._sleep(self._busy_poll_s)
                continue
            remaining.remove(ready)
            if not await self._upgrade(actor, batch, ready, studio_url) and self._hold(
                ready, waiting_since, "install_busy"
            ):
                # Тот же хост занят другой установкой или обновлением: ждём, как у занятого раннера.
                remaining.append(ready)
                await self._sleep(self._busy_poll_s)
        for item in remaining:
            self._end(item, FleetItemState.skipped, "cancelled")

    def _hold_busy(self, remaining: list[FleetItem], busy: Mapping[str, int], since: dict[str, float]) -> None:
        """Занятые сборкой раннеры остаются ждать; ждавшие дольше положенного пропускаются и уходят из очереди."""
        for item in [i for i in remaining if busy.get(i.runner_id)]:
            if not self._hold(item, since, "busy"):
                remaining.remove(item)

    def _hold(self, item: FleetItem, since: dict[str, float], code: str) -> bool:
        """Раннер ждёт своей очереди; False, если он ждёт дольше положенного и пропущен с кодом `code`."""
        item.state = FleetItemState.waiting
        now = self._monotonic()
        if now - since.setdefault(item.runner_id, now) < self._busy_wait_s:
            return True
        self._end(item, FleetItemState.skipped, code)
        return False

    @staticmethod
    def _end(item: FleetItem, state: FleetItemState, code: str | None = None, detail: str = "") -> None:
        item.state = state
        item.code = code
        item.detail = detail[:400]

    async def _start(self, actor: Actor, item: FleetItem, studio_url: str) -> InstallJob:
        if item.kind is FleetKind.ssh:
            if self._ssh is None:
                raise InstallError("ssh_disabled")
            if not studio_url:
                raise InstallError("studio_url_unknown")
            return await self._ssh.run_saved(actor, item.ref, action="update", studio_url=studio_url)
        return await self._installs.start_upgrade(actor, InstallTarget(item.kind.value), item.ref)

    @staticmethod
    def _failure(exc: Exception) -> tuple[str, str]:
        """Код и подробность причины, по которой раннер не удалось даже начать обновлять."""
        if isinstance(exc, InstallUnavailableError):
            return "install_unavailable", exc.reason
        if isinstance(exc, RunnerNotFoundError):
            return "not_installed", ""
        if isinstance(exc, SshPolicyError):
            return exc.code, exc.reason
        if isinstance(exc, InstallError | SshError):
            return exc.code, exc.detail
        logger.exception("runner_fleet_item_failed", exc_info=exc)
        return "unexpected", ""

    async def _upgrade(self, actor: Actor, batch: FleetBatch, item: FleetItem, studio_url: str) -> bool:
        """Обновить один раннер и записать итог; False значит «хост занят, попробуйте позже», итога ещё нет."""
        item.state = FleetItemState.running
        try:
            job = await self._start(actor, item, studio_url)
        except InstallBusyError:
            return False
        except Exception as exc:
            code, detail = self._failure(exc)
            self._end(item, FleetItemState.failed, code, detail)
            return True
        item.job_id = job.id
        await self._finish(actor, item, job, batch.target_version)
        return True

    async def _finish(self, actor: Actor, item: FleetItem, job: InstallJob, target_version: str) -> None:
        finished = await self._await_job(actor, job)
        if finished is None:
            self._end(item, FleetItemState.failed, "job_timeout")
            return
        if finished.state is not InstallJobState.succeeded:
            self._end(item, FleetItemState.failed, finished.error_code or "unexpected", finished.error_detail)
            item.rolled_back = finished.rolled_back
            return
        reconnect = next((s for s in finished.steps if s.key == "reconnect"), None)
        if item.kind is FleetKind.ssh or reconnect is None:
            # По SSH сама установка к раннеру не возвращается: «обновлён» значит, что он сообщил новую версию.
            seen = await self._await_version(actor, item.runner_id, target_version)
            if seen is None:
                self._end(item, FleetItemState.failed, "reconnect_timeout")
                return
            item.to_version = seen
        elif reconnect.state is InstallStepState.done and reconnect.detail:
            item.to_version = reconnect.detail
        self._end(item, FleetItemState.succeeded)

    async def _await_job(self, actor: Actor, job: InstallJob) -> InstallJob | None:
        deadline = self._monotonic() + self._job_timeout_s
        while True:
            current = self._installs.job(actor, job.id)
            if current is None:
                return None
            if current.state is not InstallJobState.running:
                return current
            if self._monotonic() >= deadline:
                return None
            await self._sleep(self._job_poll_s)

    async def _await_version(self, actor: Actor, runner_id: str, version: str) -> str | None:
        deadline = self._monotonic() + self._reconnect_timeout_s
        while True:
            current = next(
                (
                    r
                    for r in await self._registry.list_runners(actor, owner_kind=RunnerOwnerKind.instance)
                    if r.id == runner_id
                ),
                None,
            )
            if current is not None and not is_outdated(current.version, version):
                return current.version
            if current is None or current.revoked_at is not None or self._monotonic() >= deadline:
                return None
            await self._sleep(self._job_poll_s)
