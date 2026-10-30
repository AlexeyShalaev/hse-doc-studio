"""Исполнитель раннера для не-compile видов: рабочая папка из манифеста, обработчик вида, выходы из белого списка."""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import glob
from collections.abc import Iterator
from pathlib import Path

from hse_doc_studio.core.jobs.base import JobResultData
from hse_doc_studio.core.jobs.entities import JobResult
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobStatus
from hse_doc_studio.core.jobs.errors import JobFailure
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.office import OfficeConvertResult
from hse_doc_studio.core.jobs.outputs import IJobOutputs
from hse_doc_studio.core.jobs.pack import PackResult
from hse_doc_studio.core.jobs.protocols import JobContext as HandlerContext
from hse_doc_studio.core.jobs.wire import JobEnvelope
from hse_doc_studio.infra.jobs.handler_registry import JobHandlerRegistry
from hse_doc_studio.infra.runner.client import RunnerApiError, RunnerClient, RunnerUnreachable
from hse_doc_studio.infra.runner.executor import JobContext, JobOutcome, OutputFile
from hse_doc_studio.infra.runner.outputs import collect_outputs
from hse_doc_studio.infra.runner.workspace import BlobCache, BlobIntegrityError, RunnerWorkspaces

CODE_UNSUPPORTED_KIND = "unsupported_kind"
CODE_BLOB_UNAVAILABLE = "blob_unavailable"
CODE_OUTPUT_MISSING = "output_missing"
CODE_OUTPUT_CHANGED = "output_changed"


class JobBlobFetcher:
    """Скачивает блобы от имени идущей задачи: токен у каждой задачи свой, а кэш блобов общий."""

    def __init__(self, client: RunnerClient) -> None:
        self._client = client
        self._current: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
            "runner_current_job", default=None
        )

    @contextlib.contextmanager
    def bind(self, job_id: str, job_token: str) -> Iterator[None]:
        token = self._current.set((job_id, job_token))
        try:
            yield
        finally:
            self._current.reset(token)

    async def __call__(self, sha256: str) -> bytes:
        current = self._current.get()
        if current is None:
            raise RuntimeError("blob requested outside of a job")
        return await self._client.get_blob(current[0], current[1], sha256)


def _output_refs(data: JobResultData) -> tuple[ArtifactRef, ...]:
    """Файлы, которые вид задачи заявил выходом: только они уходят на сервер."""
    if isinstance(data, OfficeConvertResult):
        return (data.output,) if data.output is not None else ()
    if isinstance(data, PackResult):
        return (data.archive,)
    return ()


def _collect(root: Path, refs: tuple[ArtifactRef, ...]) -> tuple[OutputFile, ...]:
    found: list[OutputFile] = []
    for ref in refs:
        matched = collect_outputs(root, [glob.escape(ref.path)])
        if not matched:
            raise JobFailure.of(JobErrorCategory.internal, CODE_OUTPUT_MISSING, ref.path)
        if matched[0].ref != ref:
            raise JobFailure.of(JobErrorCategory.internal, CODE_OUTPUT_CHANGED, ref.path)
        found.append(matched[0])
    return tuple(found)


class HandlerJobExecutor:
    """`JobExecutor` поверх реестра обработчиков; репозиториев и базы у раннера нет."""

    def __init__(
        self,
        *,
        workspaces: RunnerWorkspaces,
        cache: BlobCache,
        fetcher: JobBlobFetcher,
        handlers: JobHandlerRegistry,
        outputs: IJobOutputs,
        cache_max_bytes: int,
    ) -> None:
        self._workspaces = workspaces
        self._cache = cache
        self._fetcher = fetcher
        self._handlers = handlers
        self._outputs = outputs
        self._cache_max_bytes = cache_max_bytes

    async def execute(self, envelope: JobEnvelope, ctx: JobContext) -> JobOutcome:
        spec = envelope.spec
        try:
            handler = self._handlers.get(spec.kind)
        except ValueError as exc:
            raise JobFailure.of(JobErrorCategory.unavailable, CODE_UNSUPPORTED_KIND, str(spec.kind)) from exc
        ctx.log(f"{spec.kind}: start")
        try:
            with self._fetcher.bind(str(spec.id), envelope.job_token):
                async with self._workspaces.open(str(spec.project_id), envelope.manifest) as workspace:
                    data = await handler.handle(
                        spec.payload,
                        HandlerContext(
                            job_id=spec.id,
                            project_id=spec.project_id,
                            actor=spec.actor,
                            locale=spec.locale,
                            workspace=workspace.root,
                            outputs=self._outputs,
                        ),
                    )
                    outputs = await asyncio.to_thread(_collect, workspace.root, _output_refs(data))
        except (BlobIntegrityError, RunnerApiError, RunnerUnreachable) as exc:
            raise JobFailure.of(JobErrorCategory.unavailable, CODE_BLOB_UNAVAILABLE, str(exc)) from exc
        keep = frozenset(entry.sha256 for entry in envelope.manifest if entry.sha256)
        await asyncio.to_thread(self._cache.evict, self._cache_max_bytes, keep)
        await asyncio.to_thread(self._workspaces.evict, frozenset({str(spec.project_id)}))
        ctx.log(f"{spec.kind}: done")
        return JobOutcome(JobResult(status=JobStatus.succeeded, data=data), outputs)
