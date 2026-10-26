from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.jobs.base import JobPayload, JobResultData
from hse_doc_studio.core.jobs.entities import BuildOutcome, JobResult, JobSpec
from hse_doc_studio.core.jobs.files import ManifestFile
from hse_doc_studio.core.jobs.outputs import IJobOutputs


class ProcessHandle(Protocol):
    """Подпроцесс сборки: диспетчер гасит его в порядке terminate, ожидание, kill."""

    @property
    def returncode(self) -> int | None: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...
    async def wait(self) -> int: ...


class JobLogSink(Protocol):
    def emit(self, line: str) -> None:
        """Дописывает строку в лог записи и публикует её в шину."""
        ...

    def publish_only(self, line: str) -> None:
        """Публикует строку в шину, не добавляя её в лог записи."""
        ...

    def text(self) -> str:
        """Весь накопленный лог записи."""
        ...


@dataclass(frozen=True)
class JobRunContext:
    """Что получает раннер сборки."""

    log: JobLogSink
    workspace: Path
    on_process: Callable[[ProcessHandle], None]


@dataclass(frozen=True)
class JobContext:
    """Что получает обработчик не-compile вида."""

    job_id: UUID
    project_id: UUID
    actor: Actor
    locale: Lang
    # Папка, относительно которой разворачиваются ManifestFile: в нулевом этапе это
    # `spec.local_root`, на втором этапе рабочая папка раннера.
    workspace: Path
    outputs: IJobOutputs

    def path_of(self, file: ManifestFile) -> Path:
        root = self.workspace.resolve()
        target = (self.workspace / file.path).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"path escapes the workspace: {file.path!r}")
        return self.workspace / file.path


class IJobHandler[P: JobPayload](Protocol):
    """Обработчик одного не-compile вида; об ожидаемом сбое сообщает JobFailure."""

    async def handle(self, payload: P, ctx: JobContext) -> JobResultData: ...


class ICompileJobRunner(Protocol):
    async def preflight(self, spec: JobSpec) -> None:
        """Бросает CompileSetupError до создания записи сборки."""
        ...

    async def run_build(self, spec: JobSpec, ctx: JobRunContext) -> BuildOutcome:
        """Очередь, контейнер или копирование и превью; под охраной диспетчера."""
        ...

    async def run_post(self, spec: JobSpec, ctx: JobRunContext, outcome: BuildOutcome) -> JobResult:
        """Проверки; вызывается диспетчером вне охраны, как в исходном коде."""
        ...


class IJobHooks(Protocol):
    # Намеренно без реализаций по умолчанию: ложный on_started прерывает сборку,
    # и заглушка, молча возвращающая False, оставила бы задачу висеть.
    async def on_started(self, spec: JobSpec) -> bool:
        """False, если записи сборки нет: задача прекращается, шина не закрывается."""
        ...

    async def on_finished(self, spec: JobSpec, result: JobResult, log: str) -> None: ...


class IJobObserver(Protocol):
    """Получатель итога фоновой задачи."""

    async def on_finished(self, spec: JobSpec, result: JobResult) -> None: ...


class IJobDispatcher(Protocol):
    async def preflight(self, spec: JobSpec) -> None:
        """Проверки окружения до постановки; для видов кроме compile ничего не делает."""
        ...

    def submit(self, spec: JobSpec, hooks: IJobHooks) -> None:
        """Ставит compile в работу и сразу возвращается; вызывать нужно внутри запроса."""
        ...

    async def cancel(self, job_id: UUID) -> bool: ...

    async def run(self, spec: JobSpec, *, timeout_s: float | None = None) -> JobResult:
        """Выполняет задачу и ждёт результат; отмена вызывающего отменяет задачу."""
        ...

    def submit_detached(self, spec: JobSpec, observer: IJobObserver | None = None) -> None:
        """Запускает задачу в фоне, не блокируя; нужен работающий цикл событий."""
        ...

    async def drain_detached(self, timeout_s: float) -> None:
        """Дожидается фоновых задач при остановке приложения."""
        ...

    def is_active(self, job_id: UUID) -> bool: ...
    def has_any_active(self) -> bool: ...
    def has_active_for_folder(self, folder: Path) -> bool: ...
