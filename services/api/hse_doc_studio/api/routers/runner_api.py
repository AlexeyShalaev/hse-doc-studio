"""Протокол раннера `/api/runner/v1` (серверный режим). Подлинность проверяет сам маршрут по своему токену."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.rate_limit import enforce_ip
from hse_doc_studio.api.runner_auth import JOB_TOKEN_HEADER, authenticated_runner, bearer_secret
from hse_doc_studio.api.schemas.runner import (
    HeartbeatRequestBody,
    HeartbeatResponseBody,
    PollRequestBody,
    PollResponseBody,
    RunnerRegisterRequestBody,
    RunnerRegisterResponseBody,
)
from hse_doc_studio.core.jobs.codec import encode_poll_response
from hse_doc_studio.core.jobs.runners import Runner
from hse_doc_studio.core.jobs.wire import (
    DEFAULT_HEARTBEAT_S,
    DEFAULT_LEASE_S,
    MAX_POLL_WAIT_S,
    RUNNER_API_PREFIX,
    PollRequest,
    RunnerRegisterRequest,
)
from hse_doc_studio.core.rate_limit import AUTH_IP
from hse_doc_studio.use_cases.jobs.runner_jobs import RunnerJobService
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry

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


@router.post("/poll", response_model=PollResponseBody)
async def poll_job(
    body: PollRequestBody, request: Request, runner: Runner = Depends(authenticated_runner)
) -> dict[str, object]:
    """Долгий опрос: ответ сразу, как появилась подходящая задача, иначе `envelope: null` через `wait_s`."""
    service = await request.state.dishka_container.get(RunnerJobService)
    response = await service.poll(runner, PollRequest(wait_s=body.wait_s, free_slots=body.free_slots))
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
