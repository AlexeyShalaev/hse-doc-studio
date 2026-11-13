"""Ввод и вывод задачи для раннера: лог, блобы манифеста, выходы и завершение с ограждением по попытке."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import structlog

from hse_doc_studio.core.jobs.codec import decode_result, encode
from hse_doc_studio.core.jobs.enums import JobKind, JobState, JobStatus
from hse_doc_studio.core.jobs.errors import (
    ArtifactInvalidError,
    BlobForbiddenError,
    BlobMissingError,
    JobNotRunningError,
    QueuedJobNotFoundError,
    StaleAttemptError,
)
from hse_doc_studio.core.jobs.queue import IJobQueue, QueuedJob
from hse_doc_studio.core.jobs.runners import IRunnerRepository, JobTokenSigner, Runner
from hse_doc_studio.core.jobs.storage import IJobBlobStore, IJobLogSink, IJobOutputIngest, RunnerStoragePolicy
from hse_doc_studio.core.jobs.wire import (
    FEATURE_BUILD_ANCHORS,
    ArtifactUploadRequest,
    ArtifactUploadResponse,
    BlobLocation,
    BlobNeedRequest,
    BlobNeedResponse,
    CompleteRequest,
    CompleteResponse,
    LogBatch,
)
from hse_doc_studio.core.signatures.anchors import POSITIONS_SUFFIX
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService

logger = structlog.get_logger()


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RunnerJobIoService:
    """Каждый вызов проверяет токен задачи, владение арендой и номер попытки раньше, чем что-либо принять."""

    def __init__(
        self,
        queue: IJobQueue,
        queue_service: JobQueueService,
        runners: IRunnerRepository,
        signer: JobTokenSigner,
        blobs: IJobBlobStore,
        outputs: IJobOutputIngest,
        logs: IJobLogSink,
        *,
        storage_policy: RunnerStoragePolicy | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._queue = queue
        self._service = queue_service
        self._runners = runners
        self._signer = signer
        self._blobs = blobs
        self._outputs = outputs
        self._logs = logs
        self._policy = storage_policy or RunnerStoragePolicy()
        self._clock = clock

    async def append_log(self, runner: Runner, job_id: UUID, job_token: str, batch: LogBatch) -> None:
        job = await self.authorize(runner, job_id, job_token, batch.attempt)
        await self._logs.append(job.id, job.attempt, batch.seq, batch.lines)

    async def need_blobs(
        self, runner: Runner, job_id: UUID, job_token: str, request: BlobNeedRequest
    ) -> BlobNeedResponse:
        """Ссылки на блобы манифеста; хоть один хеш вне манифеста отклоняет весь запрос."""
        job = await self.authorize(runner, job_id, job_token, request.attempt)
        allowed = _manifest_hashes(job)
        if any(sha not in allowed for sha in request.sha256):
            raise BlobForbiddenError("blob is not in the job manifest")
        audience = self._policy.audience_for(runner.scope)
        locations: list[BlobLocation] = []
        for sha in dict.fromkeys(request.sha256):
            if not await self._blobs.exists(sha):
                raise BlobMissingError(f"blob {sha} is missing")
            url = None if audience is None else await self._blobs.url_for(sha, audience)
            locations.append(BlobLocation(sha256=sha, url=url))
        return BlobNeedResponse(blobs=tuple(locations))

    async def open_blob(self, runner: Runner, job_id: UUID, job_token: str, sha256: str) -> AsyncIterator[bytes]:
        """Чужой для задачи хеш неотличим от отсутствующего блоба."""
        job = await self.authorize(runner, job_id, job_token)
        if sha256 not in _manifest_hashes(job):
            raise BlobMissingError(f"blob {sha256} is missing")
        return await self._blobs.open(sha256)

    async def announce_artifact(
        self, runner: Runner, job_id: UUID, job_token: str, request: ArtifactUploadRequest
    ) -> ArtifactUploadResponse:
        job = await self.authorize(runner, job_id, job_token, request.attempt)
        audience = self._policy.audience_for(runner.scope)
        url = await self._outputs.announce(job.id, job.attempt, request.artifact, audience)
        return ArtifactUploadResponse(url=url)

    async def put_artifact(
        self, runner: Runner, job_id: UUID, job_token: str, sha256: str, chunks: AsyncIterator[bytes]
    ) -> None:
        job = await self.authorize(runner, job_id, job_token)
        await self._outputs.put(job.id, job.attempt, sha256, chunks)

    async def complete(
        self, runner: Runner, job_id: UUID, job_token: str, request: CompleteRequest
    ) -> CompleteResponse:
        """Устаревшая попытка получает `StaleAttemptError`; выходы проверяются до смены состояния задачи."""
        job = await self.authorize(runner, job_id, job_token, request.attempt, require_running=False)
        if job.state is not JobState.running:
            raise StaleAttemptError(f"job {job_id} is already {job.state.value}")
        try:
            result = decode_result(job.kind, request.result)
        except (ValueError, KeyError, TypeError) as exc:
            raise ArtifactInvalidError(f"invalid job result: {exc!r}") from exc
        request = _without_undeclared(runner, job, request)
        await self._outputs.commit(job.id, job.attempt, request.artifacts)
        await self._service.complete(
            job.id,
            request.attempt,
            result.status,
            result={**request.result, "artifacts": encode(request.artifacts)},
            error_code=result.error.code if result.error is not None else None,
        )
        if result.status is not JobStatus.succeeded:
            await self._outputs.discard(job.id)
        return CompleteResponse(accepted=True)

    async def authorize(
        self, runner: Runner, job_id: UUID, job_token: str, attempt: int | None = None, *, require_running: bool = True
    ) -> QueuedJob:
        claims = self._signer.verify(job_token, self._clock(), job_id=str(job_id), runner_id=runner.id)
        job = await self._queue.get(job_id)
        if job is None:
            raise QueuedJobNotFoundError(f"job {job_id} not found")
        if job.runner_id is None or job.runner_id.hex != UUID(runner.id).hex:
            raise StaleAttemptError(f"job {job_id} is not leased to this runner")
        if attempt is not None and attempt != job.attempt:
            raise StaleAttemptError(f"job {job_id} is on attempt {job.attempt}, not {attempt}")
        if claims.attempt is not None and claims.attempt != job.attempt:
            raise StaleAttemptError(f"job token of job {job_id} belongs to attempt {claims.attempt}, not {job.attempt}")
        if require_running and job.state is not JobState.running:
            raise JobNotRunningError(f"job {job_id} is {job.state.value}")
        await self._runners.touch(runner.id, self._clock())
        return job


def _manifest_hashes(job: QueuedJob) -> frozenset[str]:
    manifest = job.payload.get("manifest", [])
    return frozenset(str(entry["sha256"]) for entry in manifest if entry.get("sha256"))


def _without_undeclared(runner: Runner, job: QueuedJob, request: CompleteRequest) -> CompleteRequest:
    """Файл позиций якорей принимается только от раннера, объявившего `build_anchors` (signing-route.md, 15.17.6).

    Такой раннер его и не шлёт; если всё же прислал, файл отбрасывается, а сборка не падает: якоря просто неизвестны.
    """
    if job.kind is not JobKind.compile or FEATURE_BUILD_ANCHORS in runner.features:
        return request
    kept = tuple(ref for ref in request.artifacts if not ref.path.endswith(POSITIONS_SUFFIX))
    if len(kept) == len(request.artifacts):
        return request
    logger.warning("undeclared build positions dropped", job_id=str(job.id), runner_id=runner.id)
    return replace(request, artifacts=kept)
