"""Протокол раннера `/api/runner/v1` (серверный режим). Подлинность проверяет сам маршрут по своему токену."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.rate_limit import enforce_ip
from hse_doc_studio.api.runner_auth import bearer_secret
from hse_doc_studio.api.schemas.runner import RunnerRegisterRequestBody, RunnerRegisterResponseBody
from hse_doc_studio.core.jobs.wire import (
    DEFAULT_HEARTBEAT_S,
    DEFAULT_LEASE_S,
    MAX_POLL_WAIT_S,
    RUNNER_API_PREFIX,
    RunnerRegisterRequest,
)
from hse_doc_studio.core.rate_limit import AUTH_IP
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
