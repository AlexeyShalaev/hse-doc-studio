"""«Диск» раннера в админке и в «Моих раннерах»: вид, обновить замер, очистить, остановить, сводка для «Хранилища».

Права по разделу 7 `docs/design/storage-cleanup.md` (`RunnerRegistry.require_disk_access`), адреса и ответы по 9.1.
Сам канал команд (очередь, переходы, просрочка и потеря) живёт в `RunnerControlService`; здесь только решения
человека и ошибки с кодами сервера: коды протокола раннера (`command_not_found` и другие) наружу не уходят.

Итог очистки (аудит `runner.disk_cleaned`, уведомление владельцу, метрика) пишет наблюдатель `RunnerDiskObserver`:
канал зовёт его ровно один раз на любое закрытие команды, на какой бы реплике оно ни случилось.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.invitations.protocols import INotifier
from hse_doc_studio.core.jobs.admin import RunnerStatus, runner_status
from hse_doc_studio.core.jobs.control import (
    RunnerCommandBusyError,
    RunnerCommandUnsupportedError,
    RunnerControlError,
    StoredDiskAuto,
    StoredDiskReport,
)
from hse_doc_studio.core.jobs.disk import (
    DISK_AUTO_MIN_RUNNER_VERSION,
    DISK_AUTO_PERCENT_RANGE,
    DISK_REPORT_STALE_S,
    RECENT_COMMAND_S,
    CommandStepStatus,
    DiskAutoLast,
    DiskAutoPolicy,
    DiskCleanupPayload,
    DiskMeasurePayload,
    DiskTarget,
    DockerDiskReason,
    RunnerCommand,
    RunnerCommandKind,
    RunnerCommandState,
)
from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.core.jobs.errors import RunnerNotFoundError
from hse_doc_studio.core.jobs.routing import RunnerScope
from hse_doc_studio.core.jobs.runners import IRunnerRepository, Runner
from hse_doc_studio.core.jobs.wire import FEATURE_DISK_AUTO
from hse_doc_studio.core.update.services import parse_version
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.jobs.runner_control import RunnerControlService, deliverable_kinds
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry

DiskScope = Literal["admin", "account"]
# Почему автоочистка раннеру недоступна (storage-cleanup.md, 14.5).
DiskAutoReason = Literal["outdated", "kubernetes", "managed_locally", "runner_disabled"]
# Сколько общих раннеров с наибольшим «можно освободить» показывает блок «Где ещё освободить место».
SUMMARY_TOP = 3


@dataclass(frozen=True)
class PersonName:
    id: str
    name: str


@dataclass(frozen=True)
class DiskCommandView:
    """Команда для ответа: кто её запустил берётся из пользователей (`null`, если человека уже нет или это
    автоочистка)."""

    command: RunnerCommand
    created_by: PersonName | None

    @property
    def auto(self) -> bool:
        return is_auto(self.command)


@dataclass(frozen=True)
class RunnerDiskAutoState:
    """Блок «Автоочистка» в «Диске» общего раннера (`RunnerDiskAuto`, 14.5)."""

    supported: bool
    reason: DiskAutoReason | None
    policy: DiskAutoPolicy
    last: DiskAutoLast | None


@dataclass(frozen=True)
class RunnerDiskState:
    """Вид «Диска» раннера (`RunnerDiskView`): замер, идущая или недавняя очистка и что сейчас можно сделать."""

    runner: Runner
    supported: bool
    online: bool
    stored: StoredDiskReport | None
    stale: bool
    command: DiskCommandView | None
    measuring: bool
    can_clean: bool
    can_include_rollback: bool
    personal_owner: PersonName | None
    # Только в админке и только у общего раннера.
    auto: RunnerDiskAutoState | None = None


@dataclass(frozen=True)
class RunnerDiskBrief:
    """Поле `disk` строки списка раннеров; у отозванного раннера его нет (`null`)."""

    supported: bool
    cleanable_bytes: int | None
    measured_at: datetime | None


@dataclass(frozen=True)
class DiskSummaryRunner:
    runner_id: str
    name: str
    cleanable_bytes: int
    measured_at: datetime


@dataclass(frozen=True)
class RunnerDiskSummary:
    """Сводка дисков неотозванных общих раннеров для «Хранилища»."""

    reporting: int
    outdated: int
    cleanable_bytes: int
    top: tuple[DiskSummaryRunner, ...]


@dataclass
class RunnerDiskMetrics:
    """Состояние метрик `/metrics`: итоги очисток этого процесса и «можно освободить» по последним замерам.

    `cleanable` обновляет `runner_commands_reaper` у лидера; до первого обновления семейство не печатается.
    """

    cleanups: Counter[str] = field(default_factory=Counter)
    cleanable: dict[str, int] | None = None


def disk_supported(runner: Runner) -> bool:
    """Раннер согласовал `control` и `disk`: ему можно ставить команды диска и он присылает замер."""
    return RunnerCommandKind.disk_cleanup in deliverable_kinds(runner)


def runner_online(runner: Runner, now: datetime, *, personal_enabled: bool) -> bool:
    """На связи по тому же критерию, что статус `offline` в списке; пауза не мешает (она про задачи)."""
    if runner.revoked_at is not None:
        return False
    status = runner_status(replace(runner, paused=False), now, personal_enabled=personal_enabled)
    return status in (RunnerStatus.online, RunnerStatus.stale)


def is_auto(command: RunnerCommand) -> bool:
    """Автоочистка, поставленная сервером по порогу места."""
    return isinstance(command.payload, DiskCleanupPayload) and command.payload.auto


def disk_auto_reason(runner: Runner, stored: StoredDiskReport | None) -> DiskAutoReason | None:
    """Почему раннер не согласовал `disk_auto`: нет Docker-части, старая версия или выключено на самом раннере."""
    if FEATURE_DISK_AUTO in runner.features:
        return None
    reason = stored.report.docker_reason if stored is not None else None
    if reason is DockerDiskReason.kubernetes:
        return "kubernetes"
    if reason is DockerDiskReason.managed_locally:
        return "managed_locally"
    if parse_version(runner.version) < parse_version(DISK_AUTO_MIN_RUNNER_VERSION):
        return "outdated"
    return "runner_disabled"


def _control_error(exc: RunnerControlError) -> IdentityError:
    if exc.code is RunnerErrorCode.command_finished:
        return IdentityError(IdentityErrorCode.command_finished)
    return IdentityError(IdentityErrorCode.not_found)


def _targets(raw: Sequence[str], include_rollback: bool) -> tuple[DiskTarget, ...]:
    """Цели запроса: 1..6 без повторов, откат только вместе со старыми версиями (иначе `DiskCleanupPayload` бросит)."""
    try:
        targets = tuple(DiskTarget(value) for value in raw)
    except ValueError:
        raise IdentityError(IdentityErrorCode.input_invalid) from None
    if not targets or len(set(targets)) != len(targets):
        raise IdentityError(IdentityErrorCode.input_invalid)
    if include_rollback and DiskTarget.old_versions not in targets:
        raise IdentityError(IdentityErrorCode.input_invalid)
    return targets


def _cleanup_targets(command: RunnerCommand) -> tuple[DiskTarget, ...]:
    return command.payload.targets if isinstance(command.payload, DiskCleanupPayload) else ()


class RunnerDiskUC:
    def __init__(  # noqa: PLR0913
        self,
        registry: RunnerRegistry,
        control: RunnerControlService,
        runners: IRunnerRepository,
        users: IUserRepository,
        audit: IAuditLog,
        *,
        metrics: RunnerDiskMetrics | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._registry = registry
        self._control = control
        self._runners = runners
        self._users = users
        self._audit = audit
        self._metrics = metrics
        self._clock = clock

    # ---- адреса 9.1 ------------------------------------------------------------------------------------------

    async def view(self, actor: Actor, runner_id: str, *, scope: DiskScope) -> RunnerDiskState:
        runner = await self._resolve(actor, runner_id, scope)
        self._registry.require_disk_access(actor, runner, rollback=False)
        now = self._clock()
        supported = disk_supported(runner)
        online = await self._online(runner, now)
        # Замер раннера, откатившегося на версию без `disk`, не показывается: экран говорит «обновите».
        stored = await self._control.disk(runner.id) if supported else None
        commands = await self._control.recent(runner.id)
        cleanup = _open(commands, RunnerCommandKind.disk_cleanup)
        command = cleanup or _recent_finished(commands, now)
        rollback = (
            stored is not None
            and DiskTarget.old_versions in stored.report.targets
            and self._may_rollback(actor, runner)
        )
        owner = None
        if scope == "admin" and runner.scope is RunnerScope.personal and runner.owner_id is not None:
            owner = await self._person(runner.owner_id)
        auto = None
        if scope == "admin" and runner.scope is RunnerScope.shared:
            auto = await self._auto_state(runner, stored)
        return RunnerDiskState(
            runner=runner,
            supported=supported,
            online=online,
            stored=stored,
            stale=stored is not None and now - stored.report.measured_at > timedelta(seconds=DISK_REPORT_STALE_S),
            command=await self._command_view(command) if command is not None else None,
            measuring=_open(commands, RunnerCommandKind.disk_measure) is not None,
            can_clean=supported and online and stored is not None and cleanup is None,
            can_include_rollback=rollback,
            personal_owner=owner,
            auto=auto,
        )

    async def set_auto(
        self, actor: Actor, runner_id: str, *, enabled: bool, min_free_percent: int
    ) -> RunnerDiskAutoState:
        """Настройка автоочистки общего раннера (14.5): только админ, у личного раннера `forbidden`."""
        runner = await self._resolve(actor, runner_id, "admin")
        if runner.revoked_at is not None:
            raise RunnerNotFoundError("runner not found")
        if runner.scope is not RunnerScope.shared:
            raise IdentityError(IdentityErrorCode.forbidden)
        low, high = DISK_AUTO_PERCENT_RANGE
        if not low <= min_free_percent <= high:
            raise IdentityError(IdentityErrorCode.input_invalid)
        before = await self._control.disk_auto(runner.id)
        policy = DiskAutoPolicy(enabled=enabled, min_free_percent=min_free_percent)
        if not await self._control.set_disk_auto(runner.id, policy):
            raise RunnerNotFoundError("runner not found")
        await self._audit.record(
            "runner.disk_auto_policy",
            actor_id=actor.id,
            target=runner.id,
            details={
                "enabled": enabled,
                "min_free_percent": min_free_percent,
                "was_enabled": before.policy.enabled if before is not None else None,
                "was_min_free_percent": before.policy.min_free_percent if before is not None else None,
            },
        )
        stored = await self._control.disk(runner.id) if disk_supported(runner) else None
        return await self._auto_state(runner, stored)

    async def refresh(self, actor: Actor, runner_id: str, *, scope: DiskScope) -> DiskCommandView:
        """«Обновить»: `disk.measure`; стоящий замер возвращается тот же, при идущей очистке `runner_disk_busy`."""
        runner = await self._resolve(actor, runner_id, scope)
        self._registry.require_disk_access(actor, runner, rollback=False)
        await self._require_ready(runner)
        command = await self._enqueue(runner, RunnerCommandKind.disk_measure, DiskMeasurePayload(), actor)
        return await self._command_view(command)

    async def cleanup(
        self, actor: Actor, runner_id: str, targets: Sequence[str], *, include_rollback: bool, scope: DiskScope
    ) -> DiskCommandView:
        runner = await self._resolve(actor, runner_id, scope)
        wanted = _targets(targets, include_rollback)
        self._registry.require_disk_access(actor, runner, rollback=include_rollback)
        await self._require_ready(runner)
        if _open(await self._control.recent(runner.id), RunnerCommandKind.disk_cleanup) is not None:
            raise IdentityError(IdentityErrorCode.runner_disk_busy)
        stored = await self._control.disk(runner.id)
        available = set(stored.report.targets) if stored is not None else set()
        if not set(wanted) <= available:
            raise IdentityError(IdentityErrorCode.disk_target_unavailable)
        payload = DiskCleanupPayload(targets=wanted, include_rollback=include_rollback)
        command = await self._enqueue(runner, RunnerCommandKind.disk_cleanup, payload, actor)
        await self._audit.record(
            "runner.disk_cleanup",
            actor_id=actor.id,
            target=runner.id,
            details={
                "targets": [target.value for target in wanted],
                "include_rollback": include_rollback,
                "owner_kind": runner.owner_kind.value,
                "owner_id": runner.owner_id,
                "command_id": str(command.id),
            },
        )
        return await self._command_view(command)

    async def cancel(self, actor: Actor, runner_id: str, command_id: str, *, scope: DiskScope) -> DiskCommandView:
        """«Остановить после текущего шага»: до доставки сразу `cancelled`, после раннер узнает в ответе на ход."""
        runner = await self._resolve(actor, runner_id, scope)
        self._registry.require_disk_access(actor, runner, rollback=False)
        try:
            cid = UUID(command_id)
        except ValueError:
            raise IdentityError(IdentityErrorCode.not_found) from None
        try:
            command = await self._control.get(runner.id, cid)
            if command.kind is not RunnerCommandKind.disk_cleanup:
                raise IdentityError(IdentityErrorCode.not_found)
            stopped = await self._control.cancel(runner.id, cid)
        except RunnerControlError as exc:
            raise _control_error(exc) from exc
        await self._audit.record(
            "runner.disk_cleanup_cancel", actor_id=actor.id, target=runner.id, details={"command_id": str(cid)}
        )
        return await self._command_view(stopped)

    async def summary(self, actor: Actor) -> RunnerDiskSummary:
        """Блок «Где ещё освободить место»: только неотозванные общие раннеры (личные это чужие машины)."""
        require_admin(actor)
        shared = [r for r in await self._runners.list() if r.revoked_at is None and r.scope is RunnerScope.shared]
        supported = [r for r in shared if disk_supported(r)]
        briefs = await self._control.disk_briefs([r.id for r in supported])
        rows = [
            DiskSummaryRunner(r.id, r.name, briefs[r.id].cleanable_bytes, briefs[r.id].measured_at)
            for r in supported
            if r.id in briefs
        ]
        top = sorted((row for row in rows if row.cleanable_bytes > 0), key=lambda row: -row.cleanable_bytes)
        return RunnerDiskSummary(
            reporting=len(rows),
            outdated=len(shared) - len(supported),
            cleanable_bytes=sum(row.cleanable_bytes for row in rows),
            top=tuple(top[:SUMMARY_TOP]),
        )

    async def briefs(self, runners: Iterable[Runner]) -> dict[str, RunnerDiskBrief | None]:
        """Поле `disk` для списков админки и «Моих раннеров»: одна проекция на страницу, без отчётов целиком."""
        listed = list(runners)
        supported = [r.id for r in listed if r.revoked_at is None and disk_supported(r)]
        found = await self._control.disk_briefs(supported) if supported else {}
        out: dict[str, RunnerDiskBrief | None] = {}
        for runner in listed:
            if runner.revoked_at is not None:
                out[runner.id] = None
                continue
            brief = found.get(runner.id)
            out[runner.id] = RunnerDiskBrief(
                supported=disk_supported(runner),
                cleanable_bytes=brief.cleanable_bytes if brief is not None else None,
                measured_at=brief.measured_at if brief is not None else None,
            )
        return out

    async def refresh_metrics(self) -> None:
        """`hse_runner_disk_cleanable_bytes{scope}`: сумма по последним замерам неотозванных раннеров."""
        if self._metrics is None:
            return
        runners = [r for r in await self._runners.list() if r.revoked_at is None and disk_supported(r)]
        briefs = await self._control.disk_briefs([r.id for r in runners])
        sums = {RunnerScope.shared.value: 0, RunnerScope.personal.value: 0}
        for runner in runners:
            brief = briefs.get(runner.id)
            if brief is not None:
                sums[runner.scope.value] += brief.cleanable_bytes
        self._metrics.cleanable = sums

    # ---- внутреннее ------------------------------------------------------------------------------------------

    async def _auto_state(self, runner: Runner, stored: StoredDiskReport | None) -> RunnerDiskAutoState:
        auto: StoredDiskAuto | None = await self._control.disk_auto(runner.id)
        reason = disk_auto_reason(runner, stored)
        return RunnerDiskAutoState(
            supported=reason is None,
            reason=reason,
            policy=auto.policy if auto is not None else DiskAutoPolicy(),
            last=auto.last if auto is not None else None,
        )

    async def _resolve(self, actor: Actor, runner_id: str, scope: DiskScope) -> Runner:
        if scope == "account":
            return await self._registry.my_runner(actor, runner_id)
        require_admin(actor)
        runner = await self._runners.get(runner_id)
        if runner is None:
            raise RunnerNotFoundError("runner not found")
        return runner

    def _may_rollback(self, actor: Actor, runner: Runner) -> bool:
        try:
            self._registry.require_disk_access(actor, runner, rollback=True)
        except IdentityError:
            return False
        return True

    async def _online(self, runner: Runner, now: datetime) -> bool:
        enabled = (await self._registry.personal_settings()).enabled
        return runner_online(runner, now, personal_enabled=enabled)

    async def _require_ready(self, runner: Runner) -> None:
        if not disk_supported(runner):
            raise IdentityError(IdentityErrorCode.runner_disk_unsupported)
        if not await self._online(runner, self._clock()):
            raise IdentityError(IdentityErrorCode.runner_offline)

    async def _enqueue(
        self,
        runner: Runner,
        kind: RunnerCommandKind,
        payload: DiskCleanupPayload | DiskMeasurePayload,
        actor: Actor,
    ) -> RunnerCommand:
        assert actor.id is not None  # noqa: S101 — права выше пропускают только вошедшего человека
        try:
            return await self._control.enqueue(runner, kind, payload, created_by=actor.id)
        except RunnerCommandUnsupportedError:
            raise IdentityError(IdentityErrorCode.runner_disk_unsupported) from None
        except RunnerCommandBusyError:
            raise IdentityError(IdentityErrorCode.runner_disk_busy) from None

    async def _person(self, user_id: str) -> PersonName | None:
        user = await self._users.get(user_id)
        return PersonName(id=user.id, name=user.name) if user is not None else None

    async def _command_view(self, command: RunnerCommand) -> DiskCommandView:
        person = await self._person(command.created_by) if command.created_by else None
        return DiskCommandView(command=command, created_by=person)


def _open(commands: Iterable[RunnerCommand], kind: RunnerCommandKind) -> RunnerCommand | None:
    return next((c for c in commands if c.kind is kind and not c.state.finished), None)


def _recent_finished(commands: Iterable[RunnerCommand], now: datetime) -> RunnerCommand | None:
    horizon = now - timedelta(seconds=RECENT_COMMAND_S)
    finished = [
        c
        for c in commands
        if c.kind is RunnerCommandKind.disk_cleanup and c.finished_at is not None and c.finished_at >= horizon
    ]
    return max(finished, key=lambda c: c.finished_at or now, default=None)


# Итог, после которого на раннере могло что-то удалиться: владелец узнаёт о нём, если чистил не он.
_NOTIFIED_STATES = frozenset(
    {RunnerCommandState.done, RunnerCommandState.cancelled, RunnerCommandState.error, RunnerCommandState.lost}
)


class RunnerDiskObserver:
    """Итог очистки: аудит `runner.disk_cleaned`, метрика и уведомление владельцу личного раннера.

    Владелец получает `runner_disk_cleaned` (только «Входящие»), если очистку запустил не он и раннер успел её
    забрать: просроченная или остановленная до доставки команда ничего не удалила.
    """

    def __init__(
        self,
        runners: IRunnerRepository,
        users: IUserRepository,
        audit: IAuditLog,
        notifier: INotifier,
        metrics: RunnerDiskMetrics | None = None,
    ) -> None:
        self._runners = runners
        self._users = users
        self._audit = audit
        self._notifier = notifier
        self._metrics = metrics

    async def command_finished(self, command: RunnerCommand) -> None:
        if command.kind is not RunnerCommandKind.disk_cleanup:
            return
        if self._metrics is not None:
            self._metrics.cleanups[command.state.value] += 1
        progress = command.progress
        freed = progress.freed_bytes if progress is not None else 0
        errors = 0
        if progress is not None:
            errors = sum(step.status is CommandStepStatus.error for step in progress.steps)
            errors += progress.error is not None
        auto = is_auto(command)
        details: dict[str, object] = {
            "command_id": str(command.id),
            "state": command.state.value,
            "freed_bytes": freed,
            "errors": errors,
            "steps": len(progress.steps) if progress is not None else 0,
        }
        if auto:
            details["auto"] = True
        await self._audit.record(
            "runner.disk_cleaned", actor_id=command.created_by or None, target=command.runner_id, details=details
        )
        if not auto:
            await self._notify_owner(command, freed)

    async def auto_started(self, command: RunnerCommand, *, free_bytes: int, total_bytes: int, percent: int) -> None:
        """Автоочистка поставлена по порогу места: событие в журнале аудита от имени системы (актор `null`)."""
        await self._audit.record(
            "runner.disk_auto_cleanup",
            actor_id=None,
            target=command.runner_id,
            details={
                "command_id": str(command.id),
                "targets": [target.value for target in _cleanup_targets(command)],
                "free_bytes": free_bytes,
                "total_bytes": total_bytes,
                "min_free_percent": percent,
            },
        )

    async def _notify_owner(self, command: RunnerCommand, freed: int) -> None:
        if command.state not in _NOTIFIED_STATES or command.delivered_at is None:
            return
        runner = await self._runners.get(command.runner_id)
        if runner is None or runner.scope is not RunnerScope.personal or runner.owner_id is None:
            return
        if runner.owner_id == command.created_by:
            return
        actor = await self._users.get(command.created_by)
        await self._notifier.notify(
            runner.owner_id,
            NotificationKind.runner_disk_cleaned,
            NotificationPayload(
                ref_id=runner.id,
                excerpt=runner.name,
                actor_name=actor.name if actor is not None else None,
                outcome=command.state.value,
                freed_bytes=freed,
            ),
            dedupe_key=f"runner_disk_cleaned:{command.id}",
            mail=False,
        )
