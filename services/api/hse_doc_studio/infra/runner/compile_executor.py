"""Исполнитель compile-задач раннера: папка из манифеста, сборка и проверки кодом встроенного раннера."""

from __future__ import annotations

import asyncio
import glob
from collections.abc import Callable
from pathlib import PurePosixPath

from hse_doc_studio.core.compile.errors import DockerUnavailableError, ImageMissingError
from hse_doc_studio.core.jobs.entities import compile_payload_of
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobKind
from hse_doc_studio.core.jobs.errors import JobFailure
from hse_doc_studio.core.jobs.protocols import JobRunContext
from hse_doc_studio.core.jobs.wire import JobEnvelope
from hse_doc_studio.infra.jobs.embedded_runner import EmbeddedCompileRunner
from hse_doc_studio.infra.runner.client import RunnerApiError, RunnerUnreachable
from hse_doc_studio.infra.runner.executor import JobContext, JobExecutor, JobOutcome
from hse_doc_studio.infra.runner.handler_executor import CODE_BLOB_UNAVAILABLE, JobBlobFetcher
from hse_doc_studio.infra.runner.outputs import collect_outputs
from hse_doc_studio.infra.runner.workspace import BlobCache, BlobIntegrityError, RunnerWorkspaces

CODE_IMAGE_MISSING = "image_missing"
CODE_DOCKER_UNAVAILABLE = "docker_unavailable"


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

    Отмена приходит отменой задачи: `DockerCompileExecutor` гасит свой контейнер на `CancelledError`,
    поэтому у процесса сборки ручки здесь нет.
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

    async def execute(self, envelope: JobEnvelope, ctx: JobContext) -> JobOutcome:
        spec = envelope.spec
        payload = compile_payload_of(spec)
        try:
            await self._runner.preflight(spec)
        except ImageMissingError as exc:
            raise JobFailure.of(JobErrorCategory.unavailable, CODE_IMAGE_MISSING, exc.image) from exc
        except DockerUnavailableError as exc:
            raise JobFailure.of(JobErrorCategory.unavailable, CODE_DOCKER_UNAVAILABLE, str(exc)) from exc
        sink = RunnerLogSink(ctx.log)
        try:
            with self._fetcher.bind(str(spec.id), envelope.job_token):
                async with self._workspaces.open(str(spec.project_id), envelope.manifest) as workspace:
                    run_ctx = JobRunContext(log=sink, workspace=workspace.root, on_process=lambda _process: None)
                    build = await self._runner.run_build(spec, run_ctx)
                    result = await self._runner.run_post(spec, run_ctx, build)
                    source = PurePosixPath(payload.source_file)
                    final_pdf = (source.parent / f"{source.stem}.pdf").as_posix()
                    # Без baseline: PDF уходит всегда, api перекладывает его в .build и публикует.
                    outputs = (
                        await asyncio.to_thread(collect_outputs, workspace.root, [glob.escape(final_pdf)])
                        if build.success
                        else ()
                    )
        except (BlobIntegrityError, RunnerApiError, RunnerUnreachable) as exc:
            raise JobFailure.of(JobErrorCategory.unavailable, CODE_BLOB_UNAVAILABLE, str(exc)) from exc
        keep = frozenset(entry.sha256 for entry in envelope.manifest if entry.sha256)
        await asyncio.to_thread(self._cache.evict, self._cache_max_bytes, keep)
        return JobOutcome(result, outputs)


class RoutingJobExecutor:
    """compile уходит в `CompileJobExecutor`, остальное в исполнитель обработчиков."""

    def __init__(self, compile_executor: JobExecutor, handlers: JobExecutor) -> None:
        self._compile = compile_executor
        self._handlers = handlers

    async def execute(self, envelope: JobEnvelope, ctx: JobContext) -> JobOutcome:
        target = self._compile if envelope.spec.kind is JobKind.compile else self._handlers
        return await target.execute(envelope, ctx)
