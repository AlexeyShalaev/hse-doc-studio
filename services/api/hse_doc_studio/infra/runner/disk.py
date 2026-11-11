"""Диск раннера: замер и очистка по целям сервера (docs/design/storage-cleanup.md, 5.1, 5.2, 6.3).

Раннер сам меряет и сам чистит (S1): сервер называет только цели, план строится здесь по свежему замеру теми же
правилами, что у локального «Диска» (`DockerDiskPlanner`, S2). Docker-часть есть только у консольного раннера,
который собирает в Docker: у Kubernetes-раннера образы на узлах чистит kubelet (S6), у локальной Студии её Docker
чистится в Настройках (S7). Кэш файлов и рабочие копии раннер чистит всегда, не мешая идущим сборкам (S9).

Канала команд здесь нет: его ведёт `RunnerControlLoop` (B4), который зовёт `measure()` и `cleanup()`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from hse_doc_studio import __version__
from hse_doc_studio.core.docker_disk.categories import (
    DEFAULT_SERVICE_VOLUMES,
    default_docker_categories,
    studio_protected_refs,
)
from hse_doc_studio.core.docker_disk.old_versions import OldVersionItem
from hse_doc_studio.core.docker_disk.planner import (
    CleanupPlanRequest,
    DockerDiskPlanner,
    DockerDiskSnapshot,
    DockerUnavailableError,
)
from hse_doc_studio.core.docker_disk.rules import (
    category_breakdown,
    stopped_managed_container_names,
    unused_app_image_refs,
)
from hse_doc_studio.core.docker_disk.steps import CleanupStep
from hse_doc_studio.core.docker_disk.usage import DANGLING_CATEGORY
from hse_doc_studio.core.jobs.codec import encode
from hse_doc_studio.core.jobs.disk import (
    MAX_DISK_REPORT_BYTES,
    MAX_LISTED_ITEMS,
    MAX_REF,
    MAX_STEP_ERROR,
    MAX_VERSION,
    MAX_VOLUME_NAME,
    MAX_VOLUMES,
    BlobCacheDisk,
    CommandProgress,
    CommandStep,
    CommandStepKind,
    CommandStepStatus,
    DataVolume,
    DiskBuildCache,
    DiskCategory,
    DiskCategoryKey,
    DiskCleanupPayload,
    DiskCount,
    DiskTarget,
    DockerDisk,
    DockerDiskReason,
    DockerVolume,
    OldItem,
    OldItemKind,
    OldVersions,
    RunnerCacheDisk,
    RunnerCommandState,
    RunnerDiskReport,
    StudioImageCategory,
    UnusedImage,
    WorkspacesDisk,
)
from hse_doc_studio.core.jobs.runners import RunnerHostKind
from hse_doc_studio.infra.docker.cleanup_jobs import CleanupJob, DockerCleanupJobManager, StepOutcome
from hse_doc_studio.infra.docker.system_manager import DockerSystemManager
from hse_doc_studio.infra.runner.config import BuildExecutorKind, RunnerConfig
from hse_doc_studio.infra.runner.workspace import BlobCache, RunnerWorkspaces

logger = logging.getLogger(__name__)

# Наблюдатель хода очистки: состояние для `/control/{id}/progress` (`running` или итог) и снимок хода.
# Снимок неизменяемый, его можно отдать в другую задачу; пока наблюдатель ждёт, следующий шаг не начнётся.
DiskCleanupObserver = Callable[[RunnerCommandState, CommandProgress], Awaitable[None]]

_RUNNER_STEPS = (CommandStepKind.runner_blobs, CommandStepKind.runner_workspaces)
# Сколько строк списков остаётся после каждой следующей обрезки, если отчёт не влез в 64 КБ.
_SHRINK = 0.75


class DiskCleanupBusyError(Exception):
    """На раннере уже идёт очистка: одновременно одна (5.3)."""


@dataclass(frozen=True)
class RunnerDocker:
    """Docker-часть раннера: планировщик с правилами «Диска» и исполнитель шагов Docker."""

    planner: DockerDiskPlanner
    system: DockerSystemManager


@dataclass(frozen=True)
class DiskCleanupOutcome:
    state: RunnerCommandState
    progress: CommandProgress


def runner_docker(config: RunnerConfig) -> RunnerDocker:
    """Правила «Диска» из конфигурации раннера (5.2): его `tex_image`, его версия, `image_base`, умолчания категорий."""
    system = DockerSystemManager(
        category_by_repo=default_docker_categories(tex_image=config.tex_image),
        app_repo_prefix=config.image_base,
        managed_volume_names=frozenset({config.tex_cache_volume, *DEFAULT_SERVICE_VOLUMES}),
    )
    planner = DockerDiskPlanner(
        system,
        protected_refs=frozenset({config.tex_image}) | studio_protected_refs(config.image_base, __version__),
        current_version=__version__,
        image_base=config.image_base,
    )
    return RunnerDocker(planner=planner, system=system)


def build_runner_disk_service(
    config: RunnerConfig, cache: BlobCache, workspaces: RunnerWorkspaces
) -> RunnerDiskService:
    """Сервис из конфигурации: Docker-часть только у консольного раннера с исполнителем docker."""
    docker: RunnerDocker | DockerDiskReason
    if config.executor is BuildExecutorKind.kubernetes:
        docker = DockerDiskReason.kubernetes
    elif config.host_kind is RunnerHostKind.desktop:
        docker = DockerDiskReason.managed_locally
    else:
        docker = runner_docker(config)
    return RunnerDiskService(
        cache=cache,
        workspaces=workspaces,
        data_dir=config.data_dir,
        blobs_limit_bytes=config.cache_max_bytes,
        workspaces_limit_bytes=config.workspaces_max_bytes,
        docker=docker,
    )


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RunnerDiskService:
    """Замер (`measure`) и очистка (`cleanup`) диска раннера; одна очистка за раз."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        cache: BlobCache,
        workspaces: RunnerWorkspaces,
        data_dir: Path,
        blobs_limit_bytes: int,
        workspaces_limit_bytes: int,
        docker: RunnerDocker | DockerDiskReason,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._cache = cache
        self._workspaces = workspaces
        self._data_dir = data_dir
        self._blobs_limit = blobs_limit_bytes
        self._workspaces_limit = workspaces_limit_bytes
        self._docker = docker if isinstance(docker, RunnerDocker) else None
        self._docker_reason = docker if isinstance(docker, DockerDiskReason) else None
        self._clock = clock
        # Свой исполнитель: шаги кэша раннера подключаются к шагам Docker (у Kubernetes и Студии Docker-шагов нет,
        # планировщик их не строит, поэтому исполнитель Docker без Docker не вызывается).
        system = self._docker.system if self._docker is not None else _no_docker_system()
        self._jobs = DockerCleanupJobManager(
            system,
            extra_steps={
                CommandStepKind.runner_blobs.value: self._clear_blobs,
                CommandStepKind.runner_workspaces.value: self._clear_workspaces,
            },
        )
        self._run: DiskCleanupRun | None = None

    @property
    def docker_reason(self) -> DockerDiskReason | None:
        return self._docker_reason

    def current(self) -> DiskCleanupRun | None:
        """Идущая или последняя очистка."""
        return self._run

    async def measure(self) -> RunnerDiskReport:
        """Свежий замер: Docker (до 90 с), кэш и рабочие копии, том `data_dir`. Отчёт влезает в 64 КБ."""
        snapshot = await self._measure_docker()
        blobs, spaces, volume = await asyncio.gather(
            self._cache.usage(), self._workspaces.usage(), asyncio.to_thread(_data_volume, self._data_dir)
        )
        cache = RunnerCacheDisk(
            blobs=BlobCacheDisk(bytes=blobs.bytes, count=blobs.count, limit_bytes=self._blobs_limit),
            workspaces=WorkspacesDisk(
                bytes=spaces.bytes, count=spaces.count, limit_bytes=self._workspaces_limit, busy=spaces.busy
            ),
        )
        measured_at = self._clock()

        def report(limit: int) -> RunnerDiskReport:
            docker = None if self._docker_reason is not None else _docker_disk(snapshot, limit)
            usable = docker is not None and docker.available
            targets = tuple(DiskTarget) if usable else (DiskTarget.runner_cache,)
            return RunnerDiskReport(
                measured_at=measured_at,
                targets=targets,
                docker=docker,
                docker_reason=self._docker_reason,
                cache=cache,
                volume=volume,
            )

        return fit_report(report)

    async def _measure_docker(self) -> DockerDiskSnapshot | None:
        if self._docker is None:
            return None
        try:
            return await self._docker.planner.measure()
        except Exception:  # noqa: BLE001 — Docker, ответивший мусором, не должен ломать отчёт о кэше
            logger.warning("runner disk: docker probe failed", exc_info=True)
            return None

    def cleanup(self, payload: DiskCleanupPayload, observer: DiskCleanupObserver | None = None) -> DiskCleanupRun:
        """Запускает очистку в фоне и сразу возвращает её; `DiskCleanupBusyError`, если одна уже идёт.

        План строится по свежему замеру в начале очистки (S1). Цель, которую раннер выполнить не может (Docker-цель
        у Kubernetes, у локальной Студии или при недоступном Docker), не планируется: причина уходит в
        `CommandProgress.error`, остальные цели выполняются, итог `error`.
        """
        if self._run is not None and not self._run.finished:
            raise DiskCleanupBusyError
        run = DiskCleanupRun(observer)
        self._run = run
        run.task = asyncio.create_task(self._execute(run, payload))
        return run

    async def _execute(self, run: DiskCleanupRun, payload: DiskCleanupPayload) -> None:
        try:
            await self._execute_plan(run, payload)
        finally:
            if not run.finished:
                # Задачу сняли (остановка процесса): ждущий итога не должен висеть.
                if run.state is RunnerCommandState.running:
                    run.settle(RunnerCommandState.cancelled, run.job.steps if run.job is not None else [])
                run.close()

    async def _execute_plan(self, run: DiskCleanupRun, payload: DiskCleanupPayload) -> None:
        try:
            steps, error = await self._plan(payload)
            run.plan_error = error
            if run.cancel_requested:
                for step in steps:
                    step.status = "skipped"
                run.settle(RunnerCommandState.cancelled, steps)
                await run.notify()
                run.close()
                return
            job = await self._jobs.start(steps, observer=run.observe)
            run.attach(job, self._jobs.cancel)
            assert job.task is not None  # noqa: S101
            await job.task
        except Exception as exc:  # noqa: BLE001 — фоновая очистка не роняет раннер, причина уходит в итог
            logger.warning("runner disk cleanup failed", exc_info=True)
            run.plan_error = run.plan_error or type(exc).__name__
            run.settle(RunnerCommandState.error, run.job.steps if run.job is not None else [])
            await run.notify()
            run.close()

    async def _plan(self, payload: DiskCleanupPayload) -> tuple[list[CleanupStep], str | None]:
        steps: list[CleanupStep] = []
        error: str | None = None
        docker_targets = [target for target in payload.targets if target.needs_docker]
        if docker_targets:
            if self._docker is None:
                names = ", ".join(target.value for target in docker_targets)
                error = f"docker targets are not available on this runner: {names}"
            else:
                request = CleanupPlanRequest(
                    targets=[target.value for target in docker_targets], include_rollback=payload.include_rollback
                )
                try:
                    steps = await self._docker.planner.plan(request)
                except (DockerUnavailableError, ValueError) as exc:
                    error = str(exc) or type(exc).__name__
        if DiskTarget.runner_cache in payload.targets:
            steps.extend(CleanupStep(kind=kind.value) for kind in _RUNNER_STEPS)
        return steps, error

    async def _clear_blobs(self, _step: CleanupStep) -> StepOutcome:
        return StepOutcome(freed_bytes=await self._cache.clear())

    async def _clear_workspaces(self, _step: CleanupStep) -> StepOutcome:
        return StepOutcome(freed_bytes=await self._workspaces.clear())


class DiskCleanupRun:
    """Идущая очистка: ход в форме `CommandProgress`, отмена после текущего шага, ожидание итога."""

    def __init__(self, observer: DiskCleanupObserver | None) -> None:
        self._observer = observer
        self._state = RunnerCommandState.running
        self._progress = CommandProgress(steps=(), freed_bytes=0, error=None)
        self.plan_error: str | None = None
        self.cancel_requested = False
        self.job: CleanupJob | None = None
        self.task: asyncio.Task[None] | None = None
        self._cancel_job: Callable[[], object] | None = None
        self._done = asyncio.Event()

    @property
    def state(self) -> RunnerCommandState:
        """`running` или итог: `done`, `cancelled`, `error`."""
        return self._state

    @property
    def progress(self) -> CommandProgress:
        return self._progress

    @property
    def finished(self) -> bool:
        return self._done.is_set()

    def cancel(self) -> None:
        """Остановить после текущего шага; оставшиеся шаги станут `skipped`, итог `cancelled`."""
        if self.finished:
            return
        self.cancel_requested = True
        if self._cancel_job is not None:
            self._cancel_job()

    def attach(self, job: CleanupJob, cancel_job: Callable[[], object]) -> None:
        """Очистка пошла в исполнителе; остановка, пришедшая во время замера, передаётся ему сразу."""
        self.job = job
        self._cancel_job = cancel_job
        if self.cancel_requested:
            cancel_job()

    async def wait(self) -> DiskCleanupOutcome:
        """Итог; возвращается после того, как наблюдатель получил итог (ровно один раз)."""
        await self._done.wait()
        return DiskCleanupOutcome(self._state, self._progress)

    async def observe(self, job: CleanupJob) -> None:
        """Наблюдатель `DockerCleanupJobManager`: снимок берётся до первого `await`, задача менеджера изменяемая."""
        self._progress = _progress(job.steps, self.plan_error)
        final = job.status not in ("running", "cancelling")
        if final:
            self.settle(_final_state(job.status, self._progress), job.steps)
        await self.notify()
        if final:
            self.close()

    def settle(self, state: RunnerCommandState, steps: list[CleanupStep]) -> None:
        """Итоговые состояние и ход; ждущие `wait` узнают о них после `close`."""
        self._progress = _progress(steps, self.plan_error)
        if state is RunnerCommandState.done and self._progress.error is not None:
            state = RunnerCommandState.error
        self._state = state

    def close(self) -> None:
        self._done.set()

    async def notify(self) -> None:
        if self._observer is None:
            return
        state, progress = self._state, self._progress
        try:
            await self._observer(state, progress)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — сбой доставки хода не останавливает очистку
            logger.warning("runner disk cleanup observer failed", exc_info=True)


def _final_state(status: str, progress: CommandProgress) -> RunnerCommandState:
    if status == "cancelled":
        return RunnerCommandState.cancelled
    if status == "error" or progress.error is not None:
        return RunnerCommandState.error
    return RunnerCommandState.done


def _progress(steps: list[CleanupStep], error: str | None) -> CommandProgress:
    wire = tuple(_step(step) for step in steps)
    return CommandProgress(
        steps=wire, freed_bytes=sum(step.freed_bytes for step in wire), error=_one_line(error) if error else None
    )


def _step(step: CleanupStep) -> CommandStep:
    kind = CommandStepKind(step.kind)
    with_ref = kind in (CommandStepKind.image, CommandStepKind.container)
    return CommandStep(
        kind=kind,
        ref=(step.ref or "?")[:MAX_REF] if with_ref else None,
        status=CommandStepStatus(step.status),
        freed_bytes=max(step.freed_bytes, 0),
        error=_one_line(step.error) if step.error else None,
    )


def _one_line(text: str) -> str:
    """Ошибка шага по контракту: одна непустая строка до 300 символов."""
    line = " ".join(text.split())
    return line[:MAX_STEP_ERROR] or "error"


def _data_volume(path: Path) -> DataVolume | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return DataVolume(total_bytes=usage.total, free_bytes=min(usage.free, usage.total))


# ----------------------------------------------------------------------------- отчёт


def fit_report(build: Callable[[int], RunnerDiskReport]) -> RunnerDiskReport:
    """Отчёт со списками до 100 строк; если закодированный больше 64 КБ, списки укорачиваются дальше (5.1)."""
    limit = MAX_LISTED_ITEMS
    while True:
        report = build(limit)
        if limit == 0 or _encoded_size(report) <= MAX_DISK_REPORT_BYTES:
            return report
        limit = int(limit * _SHRINK)


def _encoded_size(report: RunnerDiskReport) -> int:
    return len(json.dumps(encode(report)).encode())


def _empty_old(current_version: str) -> OldVersions:
    return OldVersions(current_version=current_version, rollback=None, items=(), reclaimable_bytes=0, rollback_bytes=0)


def _unavailable_docker() -> DockerDisk:
    return DockerDisk(
        available=False,
        categories=(),
        total_bytes=0,
        cleanable_bytes=0,
        build_cache=DiskBuildCache(bytes=0, reclaimable_bytes=0, count=0),
        dangling=DiskCount(bytes=0, count=0),
        stopped_containers=DiskCount(bytes=0, count=0),
        unused_images=(),
        unused_truncated=False,
        old_versions=_empty_old(__version__[:MAX_VERSION]),
        volumes=(),
    )


def _docker_disk(snapshot: DockerDiskSnapshot | None, limit: int) -> DockerDisk:
    """Docker-часть отчёта из замера `DockerDiskPlanner`; списки до `limit` строк, итоги по всем."""
    if snapshot is None or not snapshot.usage.available:
        return _unavailable_docker()
    usage = snapshot.usage
    by_ref = {image.reference: image for image in usage.images}
    unused = sorted(
        (
            UnusedImage(ref=ref, category=StudioImageCategory(by_ref[ref].category), size_bytes=by_ref[ref].size_bytes)
            for ref in unused_app_image_refs(usage)
            if _fits(ref, MAX_REF)
        ),
        key=lambda image: (-image.size_bytes, image.ref),
    )
    dangling = [image for image in usage.images if image.category == DANGLING_CATEGORY]
    stopped = set(stopped_managed_container_names(usage))
    stopped_bytes = sum(c.size_bytes for c in usage.containers if c.name in stopped)
    volumes = sorted(
        (DockerVolume(name=v.name, size_bytes=v.size_bytes) for v in usage.volumes if _fits(v.name, MAX_VOLUME_NAME)),
        key=lambda volume: (-volume.size_bytes, volume.name),
    )
    return DockerDisk(
        available=True,
        categories=tuple(DiskCategory(key=DiskCategoryKey(key), bytes=size) for key, size in category_breakdown(usage)),
        total_bytes=usage.total_bytes,
        cleanable_bytes=snapshot.cleanable_bytes,
        build_cache=DiskBuildCache(
            bytes=usage.build_cache_bytes,
            reclaimable_bytes=usage.build_cache_reclaimable_bytes,
            count=usage.build_cache_count,
        ),
        dangling=DiskCount(bytes=sum(image.size_bytes for image in dangling), count=len(dangling)),
        stopped_containers=DiskCount(bytes=stopped_bytes, count=len(stopped)),
        unused_images=tuple(unused[:limit]),
        unused_truncated=len(unused) > limit,
        old_versions=_old_versions(snapshot, limit),
        volumes=tuple(volumes[:MAX_VOLUMES]),
    )


def _old_versions(snapshot: DockerDiskSnapshot, limit: int) -> OldVersions:
    old = snapshot.old_versions
    items = [_old_item(item) for item in old.items if _fits(item.ref, MAX_REF)]
    rollback = old.rollback if old.rollback is not None and _fits(old.rollback.ref, MAX_REF) else None
    return OldVersions(
        current_version=old.current_version[:MAX_VERSION],
        rollback=_old_item(rollback) if rollback is not None else None,
        items=tuple(items[:limit]),
        reclaimable_bytes=old.reclaimable_bytes,
        rollback_bytes=old.rollback_bytes,
    )


def _old_item(item: OldVersionItem) -> OldItem:
    return OldItem(
        kind=OldItemKind(item.kind), ref=item.ref, version=item.version[:MAX_VERSION], size_bytes=item.size_bytes
    )


def _fits(text: str, limit: int) -> bool:
    """Строка влезает в контракт; иная (пустое имя, сверхдлинная ссылка) в списки не попадает, итоги её учитывают."""
    return 1 <= len(text) <= limit


def _no_docker_system() -> DockerSystemManager:
    # Без Docker-части шаги Docker не планируются; исполнителю нужен менеджер только по типу.
    return DockerSystemManager(category_by_repo={}, app_repo_prefix="", managed_volume_names=frozenset())


__all__ = [
    "DiskCleanupBusyError",
    "DiskCleanupObserver",
    "DiskCleanupOutcome",
    "DiskCleanupRun",
    "RunnerDiskService",
    "RunnerDocker",
    "build_runner_disk_service",
    "fit_report",
    "runner_docker",
]
