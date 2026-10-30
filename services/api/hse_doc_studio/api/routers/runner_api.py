"""Протокол раннера `/api/runner/v1` (серверный режим). Подлинность проверяет сам маршрут по своему токену."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Request, Response
from fastapi.responses import StreamingResponse

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.observability.client_ip import client_ip
from hse_doc_studio.api.rate_limit import enforce_ip
from hse_doc_studio.api.runner_auth import JOB_TOKEN_HEADER, authenticated_runner, bearer_secret
from hse_doc_studio.api.runner_commands import studio_base_url
from hse_doc_studio.api.schemas.runner import (
    ArtifactRefBody,
    ArtifactUploadRequestBody,
    ArtifactUploadResponseBody,
    BlobLocationBody,
    BlobNeedRequestBody,
    BlobNeedResponseBody,
    CompleteRequestBody,
    CompleteResponseBody,
    HeartbeatRequestBody,
    HeartbeatResponseBody,
    LogBatchBody,
    PollRequestBody,
    PollResponseBody,
    RunnerAnnounceRequestBody,
    RunnerAnnounceResponseBody,
    RunnerPairPollRequestBody,
    RunnerPairPollResponseBody,
    RunnerPairStartRequestBody,
    RunnerPairStartResponseBody,
    RunnerRegisterRequestBody,
    RunnerRegisterResponseBody,
)
from hse_doc_studio.core.jobs.codec import encode_poll_response
from hse_doc_studio.core.jobs.errors import ArtifactInvalidError
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.relay import AiEndpointFlavor
from hse_doc_studio.core.jobs.runners import DeclaredAiEndpoint, Runner, RunnerHostKind
from hse_doc_studio.core.jobs.wire import (
    DEFAULT_HEARTBEAT_S,
    DEFAULT_LEASE_S,
    MAX_POLL_WAIT_S,
    RUNNER_API_PREFIX,
    ArtifactUploadRequest,
    BlobNeedRequest,
    CompleteRequest,
    LogBatch,
    PollRequest,
    RunnerAnnounceRequest,
    RunnerRegisterRequest,
)
from hse_doc_studio.core.rate_limit import AUTH_IP
from hse_doc_studio.use_cases.jobs.pairing import RunnerPairingService
from hse_doc_studio.use_cases.jobs.runner_io import RunnerJobIoService
from hse_doc_studio.use_cases.jobs.runner_jobs import RunnerJobService
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry

_SHA256_PATTERN = r"^[0-9a-f]{64}$"

router = APIRouter(prefix=RUNNER_API_PREFIX, tags=["runner"], dependencies=[Depends(require_server_mode)])


@router.post("/register", response_model=RunnerRegisterResponseBody)
async def register_runner(body: RunnerRegisterRequestBody, request: Request) -> RunnerRegisterResponseBody:
    """Раннер приходит с токеном регистрации и получает постоянный токен; перебор токенов режется по IP."""
    await enforce_ip(request, AUTH_IP)
    registry = await request.state.dishka_container.get(RunnerRegistry)
    registered = await registry.register(
        bearer_secret(request),
        RunnerRegisterRequest(
            name=body.name,
            protocol=body.protocol,
            version=body.version,
            tags=frozenset(body.tags),
            concurrency=body.concurrency,
            resource_class=body.resource_class,
        ),
    )
    return RunnerRegisterResponseBody(
        runner_id=registered.runner.id,
        runner_token=registered.secret,
        lease_s=DEFAULT_LEASE_S,
        heartbeat_s=DEFAULT_HEARTBEAT_S,
        max_poll_wait_s=MAX_POLL_WAIT_S,
    )


@router.post("/announce", response_model=RunnerAnnounceResponseBody)
async def announce_runner(
    body: RunnerAnnounceRequestBody, request: Request, runner: Runner = Depends(authenticated_runner)
) -> RunnerAnnounceResponseBody:
    """Возможности, теги, слоты и ИИ-адреса (только имена); ответ несёт пересечение возможностей."""
    registry = await request.state.dishka_container.get(RunnerRegistry)
    response = await registry.announce(
        runner,
        RunnerAnnounceRequest(
            name=body.name,
            version=body.version,
            tags=frozenset(body.tags),
            concurrency=body.concurrency,
            ai_concurrency=body.ai_concurrency,
            host_kind=RunnerHostKind(body.host_kind),
            features=frozenset(body.features),
            ai_endpoints=tuple(
                DeclaredAiEndpoint(name=e.name, flavor=AiEndpointFlavor(e.flavor)) for e in body.ai_endpoints
            ),
        ),
        client_ip(request),
    )
    return RunnerAnnounceResponseBody(
        runner_id=response.runner_id,
        server_features=sorted(response.server_features),
        owner_kind=response.owner_kind.value,
        paused=response.paused,
        relay_keepalive_s=response.relay_keepalive_s,
    )


@router.post("/offline", status_code=204)
async def runner_offline(request: Request, runner: Runner = Depends(authenticated_runner)) -> Response:
    """Раннер уходит: ждущие его сборки сразу идут на общие раннеры."""
    await (await request.state.dishka_container.get(RunnerRegistry)).go_offline(runner)
    return Response(status_code=204)


@router.post("/deregister", status_code=204)
async def deregister_runner(request: Request, runner: Runner = Depends(authenticated_runner)) -> Response:
    """Раннер отзывает сам себя (отключение от сервера); необратимо."""
    await (await request.state.dishka_container.get(RunnerRegistry)).deregister(runner)
    return Response(status_code=204)


PAIRING_PAGE = "/settings/runners/pair"


@router.post("/pair/start", response_model=RunnerPairStartResponseBody)
async def start_runner_pairing(body: RunnerPairStartRequestBody, request: Request) -> RunnerPairStartResponseBody:
    """Код устройства для локальной Студии; человек подтверждает user_code на сайте. Перебор режется по IP."""
    await enforce_ip(request, AUTH_IP)
    service = await request.state.dishka_container.get(RunnerPairingService)
    started = await service.start(body.name, RunnerHostKind(body.host_kind), client_ip(request))
    page = studio_base_url(request) + PAIRING_PAGE
    return RunnerPairStartResponseBody(
        device_code=started.device_code,
        user_code=started.user_code,
        verification_uri=page,
        verification_uri_complete=f"{page}?code={started.user_code}",
        expires_in=started.expires_in,
        interval=started.interval,
    )


@router.post("/pair/poll", response_model=RunnerPairPollResponseBody)
async def poll_runner_pairing(body: RunnerPairPollRequestBody, request: Request) -> RunnerPairPollResponseBody:
    """Состояние сопряжения; токен регистрации приходит ровно один раз, при `approved`."""
    polled = await (await request.state.dishka_container.get(RunnerPairingService)).poll(body.device_code)
    status = "expired" if polled.status.value == "delivered" else polled.status.value
    return RunnerPairPollResponseBody(status=status, registration_token=polled.registration_token)


@router.post("/poll", response_model=PollResponseBody)
async def poll_job(
    body: PollRequestBody, request: Request, runner: Runner = Depends(authenticated_runner)
) -> dict[str, object]:
    """Долгий опрос: ответ сразу, как появилась подходящая задача, иначе `envelope: null` через `wait_s`."""
    service = await request.state.dishka_container.get(RunnerJobService)
    response = await service.poll(
        runner,
        PollRequest(wait_s=body.wait_s, free_slots=body.free_slots, free_ai_slots=body.free_ai_slots),
        gone=request.is_disconnected,
    )
    return encode_poll_response(response)


@router.post("/jobs/{job_id}/heartbeat", response_model=HeartbeatResponseBody)
async def heartbeat_job(
    job_id: UUID,
    body: HeartbeatRequestBody,
    request: Request,
    runner: Runner = Depends(authenticated_runner),
    job_token: str = Header(alias=JOB_TOKEN_HEADER),
) -> HeartbeatResponseBody:
    """Продлевает аренду; `cancel: true` доставляет раннеру отмену или таймаут."""
    service = await request.state.dishka_container.get(RunnerJobService)
    beat = await service.heartbeat(runner, job_id, body.attempt, job_token)
    return HeartbeatResponseBody(cancel=beat.cancel, lease_until=beat.lease_until)


def _artifact_ref(body: ArtifactRefBody) -> ArtifactRef:
    """Путь выхода приходит от недоверенного раннера: невалидный путь это 422 `artifact_invalid`, а не 500."""
    try:
        return ArtifactRef(path=body.path, sha256=body.sha256, size=body.size)
    except ValueError as exc:
        raise ArtifactInvalidError(f"invalid artifact path {body.path!r}: {exc}") from exc


async def _io(request: Request) -> RunnerJobIoService:
    return await request.state.dishka_container.get(RunnerJobIoService)


@router.post("/jobs/{job_id}/log", status_code=204)
async def append_job_log(
    job_id: UUID,
    body: LogBatchBody,
    request: Request,
    runner: Runner = Depends(authenticated_runner),
    job_token: str = Header(alias=JOB_TOKEN_HEADER),
) -> Response:
    """Порция живого лога; повтор с тем же `seq` принимается и игнорируется."""
    await (await _io(request)).append_log(
        runner, job_id, job_token, LogBatch(attempt=body.attempt, seq=body.seq, lines=tuple(body.lines))
    )
    return Response(status_code=204)


@router.post("/jobs/{job_id}/blobs/need", response_model=BlobNeedResponseBody)
async def need_job_blobs(
    job_id: UUID,
    body: BlobNeedRequestBody,
    request: Request,
    runner: Runner = Depends(authenticated_runner),
    job_token: str = Header(alias=JOB_TOKEN_HEADER),
) -> BlobNeedResponseBody:
    """Где взять блобы манифеста; хеш вне манифеста этой задачи отклоняется."""
    response = await (await _io(request)).need_blobs(
        runner, job_id, job_token, BlobNeedRequest(attempt=body.attempt, sha256=tuple(body.sha256))
    )
    return BlobNeedResponseBody(blobs=[BlobLocationBody(sha256=b.sha256, url=b.url) for b in response.blobs])


@router.get("/jobs/{job_id}/blobs/{sha256}", response_class=StreamingResponse)
async def get_job_blob(
    job_id: UUID,
    request: Request,
    sha256: str = Path(pattern=_SHA256_PATTERN),
    runner: Runner = Depends(authenticated_runner),
    job_token: str = Header(alias=JOB_TOKEN_HEADER),
) -> StreamingResponse:
    """Содержимое блоба потоком, когда подписанной ссылки нет."""
    chunks = await (await _io(request)).open_blob(runner, job_id, job_token, sha256)
    return StreamingResponse(chunks, media_type="application/octet-stream")


@router.post("/jobs/{job_id}/artifacts", response_model=ArtifactUploadResponseBody)
async def announce_job_artifact(
    job_id: UUID,
    body: ArtifactUploadRequestBody,
    request: Request,
    runner: Runner = Depends(authenticated_runner),
    job_token: str = Header(alias=JOB_TOKEN_HEADER),
) -> ArtifactUploadResponseBody:
    """Заявка на выход: размер и хеш фиксируются, пока не загружен ни один байт."""
    artifact = _artifact_ref(body.artifact)
    response = await (await _io(request)).announce_artifact(
        runner, job_id, job_token, ArtifactUploadRequest(attempt=body.attempt, artifact=artifact)
    )
    return ArtifactUploadResponseBody(url=response.url)


@router.put("/jobs/{job_id}/artifacts/{sha256}", status_code=204)
async def put_job_artifact(
    job_id: UUID,
    request: Request,
    sha256: str = Path(pattern=_SHA256_PATTERN),
    runner: Runner = Depends(authenticated_runner),
    job_token: str = Header(alias=JOB_TOKEN_HEADER),
) -> Response:
    """Выход потоком через API: тело не накапливается в памяти, хеш и размер сверяются по заявке."""
    await (await _io(request)).put_artifact(runner, job_id, job_token, sha256, request.stream())
    return Response(status_code=204)


@router.post("/jobs/{job_id}/complete", response_model=CompleteResponseBody)
async def complete_job(
    job_id: UUID,
    body: CompleteRequestBody,
    request: Request,
    runner: Runner = Depends(authenticated_runner),
    job_token: str = Header(alias=JOB_TOKEN_HEADER),
) -> CompleteResponseBody:
    """Итог попытки; устаревшая попытка получает 409 `stale_attempt`, а её выходы не принимаются."""
    response = await (await _io(request)).complete(
        runner,
        job_id,
        job_token,
        CompleteRequest(
            attempt=body.attempt,
            result=body.result.model_dump(mode="json"),
            artifacts=tuple(_artifact_ref(a) for a in body.artifacts),
        ),
    )
    return CompleteResponseBody(accepted=response.accepted)
