"""Исполнитель compile-задач раннера: папка из манифеста, сборка и проверки кодом встроенного раннера."""

from __future__ import annotations

import asyncio
import errno
import glob
import logging
import os
from collections.abc import Callable
from functools import partial
from pathlib import Path, PurePosixPath

from hse_doc_studio.core.compile.errors import (
    BuildBackendUnavailableError,
    BuildOutOfMemoryError,
    BuildStorageExceededError,
    DockerUnavailableError,
    ImageMissingError,
)
from hse_doc_studio.core.compile.failure import DISK_FULL, PDF_MISSING
from hse_doc_studio.core.jobs.entities import compile_payload_of
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobKind
from hse_doc_studio.core.jobs.errors import JobFailure
from hse_doc_studio.core.jobs.protocols import JobRunContext
from hse_doc_studio.core.jobs.relay import RelayErrorCode
from hse_doc_studio.core.jobs.wire import JobEnvelope
from hse_doc_studio.infra.jobs.embedded_runner import EmbeddedCompileRunner
from hse_doc_studio.infra.runner.client import RunnerApiError, RunnerUnreachable
from hse_doc_studio.infra.runner.executor import JobContext, JobExecutor, JobOutcome, OutputFile
from hse_doc_studio.infra.runner.handler_executor import CODE_BLOB_UNAVAILABLE, CODE_OUTPUT_CHANGED, JobBlobFetcher
from hse_doc_studio.infra.runner.outputs import collect_file_as, collect_outputs
from hse_doc_studio.infra.runner.workspace import BlobCache, BlobIntegrityError, OutputChangedError, RunnerWorkspaces

_LOG = logging.getLogger(__name__)

_FAIL_TAIL_CHARS = 6000

CODE_IMAGE_MISSING = "image_missing"
CODE_DOCKER_UNAVAILABLE = "docker_unavailable"
CODE_BUILD_BACKEND_UNAVAILABLE = BuildBackendUnavailableError.code


def _build_outputs(root: Path, source: PurePosixPath, doc_id: str) -> tuple[OutputFile, ...]:
    """PDF сборки и, если есть, её SyncTeX.

    SyncTeX лежит в `.build/<doc_id>/` и уходит рядом с PDF (`<stem>.synctex.gz`): по нему превью на сервере
    переходит к исходнику и привязывает комментарии из PDF к тексту. Без PDF не уходит ничего.
    """
    pdf = collect_outputs(root, [glob.escape((source.parent / f"{source.stem}.pdf").as_posix())])
    name = f"{source.stem}.synctex.gz"
    synctex = (
        collect_file_as(root, (source.parent / ".build" / doc_id / name).as_posix(), (source.parent / name).as_posix())
        if pdf
        else None
    )
    return (*pdf, synctex) if synctex is not None else pdf


class RunnerLogSink:
    """Строки сборки идут в живой лог задачи; `publish_only` тоже, но в итоговый текст для проверок не входит."""

    def __init__(self, write: Callable[[str], None]) -> None:
        self._write = write
        self._lines: list[str] = []

    def emit(self, line: str) -> None:
        self._lines.append(line)
        self._write(line)

    def publish_only(self, line: str) -> None:
        self._write(line)

    def text(self) -> str:
        return "\n".join(self._lines)


class CompileJobExecutor:
    """`JobExecutor` для compile: выход один, итоговый PDF по пути рядом с исходником.

    Отмена приходит отменой задачи: исполнитель (контейнер docker или под kubernetes) гасит сборку
    на `CancelledError`, поэтому у процесса сборки ручки здесь нет.
    """

    def __init__(
        self,
        *,
        workspaces: RunnerWorkspaces,
        cache: BlobCache,
        fetcher: JobBlobFetcher,
        runner: EmbeddedCompileRunner,
        cache_max_bytes: int,
    ) -> None:
        self._workspaces = workspaces
        self._cache = cache
        self._fetcher = fetcher
        self._runner = runner
        self._cache_max_bytes = cache_max_bytes

    async def execute(self, envelope: JobEnvelope, ctx: JobContext) -> JobOutcome:  # noqa: C901, PLR0912
        spec = envelope.spec
        payload = compile_payload_of(spec)
        try:
            await self._runner.preflight(spec)
        except ImageMissingError as exc:
            raise JobFailure.of(JobErrorCategory.unavailable, CODE_IMAGE_MISSING, exc.image) from exc
        except DockerUnavailableError as exc:
            raise JobFailure.of(JobErrorCategory.unavailable, CODE_DOCKER_UNAVAILABLE, str(exc)) from exc
        except BuildBackendUnavailableError as exc:
            raise JobFailure.of(JobErrorCategory.unavailable, CODE_BUILD_BACKEND_UNAVAILABLE, str(exc)) from exc
        sink = RunnerLogSink(ctx.log)
        job_key = str(spec.id)
        try:
            with self._fetcher.bind(str(spec.id), envelope.job_token):
                async with self._workspaces.open(str(spec.project_id), envelope.manifest) as workspace:
                    run_ctx = JobRunContext(log=sink, workspace=workspace.root, on_process=lambda _process: None)
                    build = await self._runner.run_build(spec, run_ctx)
                    if not build.success:
                        # Журнал сборки живёт только в потоке задачи; без записи в журнал раннера причину не найти.
                        root_stat = workspace.root.stat()
                        _LOG.warning(
                            "compile %s failed (runner uid=%s, workspace uid=%s mode=%o), log tail:\n%s",
                            spec.id,
                            os.getuid() if hasattr(os, "getuid") else "-",
                            root_stat.st_uid,
                            root_stat.st_mode & 0o7777,
                            sink.text()[-_FAIL_TAIL_CHARS:],
                        )
                    result = await self._runner.run_post(spec, run_ctx, build)
                    source = PurePosixPath(payload.source_file)
                    final_pdf = (source.parent / f"{source.stem}.pdf").as_posix()
                    # Без baseline: PDF уходит всегда, api перекладывает его в .build и публикует.
                    outputs = (
                        await asyncio.to_thread(_build_outputs, workspace.root, source, payload.doc_id)
                        if build.success
                        else ()
                    )
                    if build.success and payload.needs_compile and not outputs:
                        # Без файла сервер принял бы «успех» без PDF: документ оставался бы со старым результатом.
                        raise JobFailure.of(JobErrorCategory.internal, PDF_MISSING, final_pdf)
                    # Выгрузка идёт после выхода из блока: копия не даёт следующей задаче проекта убрать PDF.
                    outputs = await asyncio.to_thread(self._workspaces.stage, job_key, outputs)
        except (BlobIntegrityError, RunnerApiError, RunnerUnreachable) as exc:
            raise JobFailure.of(JobErrorCategory.unavailable, CODE_BLOB_UNAVAILABLE, str(exc)) from exc
        except OutputChangedError as exc:
            raise JobFailure.of(JobErrorCategory.internal, CODE_OUTPUT_CHANGED, str(exc)) from exc
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise JobFailure.of(JobErrorCategory.unavailable, DISK_FULL, str(exc)) from exc
            raise
        except ImageMissingError as exc:
            # Исполнитель kubernetes узнаёт об отсутствии образа только при запуске пода.
            raise JobFailure.of(JobErrorCategory.unavailable, CODE_IMAGE_MISSING, exc.image) from exc
        except BuildOutOfMemoryError as exc:
            raise JobFailure.of(JobErrorCategory.unavailable, BuildOutOfMemoryError.code, str(exc)) from exc
        except BuildStorageExceededError as exc:
            raise JobFailure.of(JobErrorCategory.unavailable, BuildStorageExceededError.code, str(exc)) from exc
        except BuildBackendUnavailableError as exc:
            raise JobFailure.of(JobErrorCategory.unavailable, CODE_BUILD_BACKEND_UNAVAILABLE, str(exc)) from exc
        keep = frozenset(entry.sha256 for entry in envelope.manifest if entry.sha256)
        await asyncio.to_thread(self._cache.evict, self._cache_max_bytes, keep)
        await asyncio.to_thread(self._workspaces.evict, frozenset({str(spec.project_id)}))
        return JobOutcome(result, outputs, cleanup=partial(self._workspaces.release, job_key) if outputs else None)


class RoutingJobExecutor:
    """compile уходит в `CompileJobExecutor`, `ai.relay` в исполнитель ретрансляции, остальное в обработчики."""

    def __init__(self, compile_executor: JobExecutor, handlers: JobExecutor, relay: JobExecutor | None = None) -> None:
        self._compile = compile_executor
        self._handlers = handlers
        self._relay = relay

    async def execute(self, envelope: JobEnvelope, ctx: JobContext) -> JobOutcome:
        kind = envelope.spec.kind
        if kind is JobKind.ai_relay:
            if self._relay is None:
                raise JobFailure.of(JobErrorCategory.unavailable, RelayErrorCode.endpoint_unknown.value)
            return await self._relay.execute(envelope, ctx)
        target = self._compile if kind is JobKind.compile else self._handlers
        return await target.execute(envelope, ctx)
