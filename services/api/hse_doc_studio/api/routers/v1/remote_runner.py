"""Облачные сборки локальной Студии: переключатель, сопряжение с аккаунтом сервера и состояние раннера.

Только локальный режим (`local_only`): на сервере маршрутов нет, гард отвечает 404.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.schemas.remote_runner import (
    RemoteRunnerAiEndpoint,
    RemoteRunnerPairingInfo,
    RemoteRunnerPairRequest,
    RemoteRunnerStatus,
    RemoteRunnerTokenRequest,
    UpdateRemoteRunnerRequest,
)
from hse_doc_studio.core.remote_runner import (
    IRemoteRunnerSupervisor,
    RemoteAiEndpointChoice,
    RemoteRunnerError,
    RemoteRunnerErrorCode,
    RemoteRunnerStatusInfo,
)
from hse_doc_studio.use_cases.remote_runner.update_remote_runner import UpdateRemoteRunnerInput, UpdateRemoteRunnerUC

router = APIRouter(route_class=SafeDishkaRoute)

_ERROR_STATUS: dict[RemoteRunnerErrorCode, int] = {
    RemoteRunnerErrorCode.url_invalid: 422,
    RemoteRunnerErrorCode.unreachable: 502,
    RemoteRunnerErrorCode.disabled: 409,
}
_INVALID = 422


def status_body(info: RemoteRunnerStatusInfo) -> RemoteRunnerStatus:
    settings = info.settings
    pairing = info.pairing
    return RemoteRunnerStatus(
        enabled=settings.enabled,
        server_url=settings.server_url,
        paired=info.paired,
        runner_id=info.runner_id,
        runner_name=info.runner_name,
        state=info.state.value,
        detail_code=info.detail_code,
        running_jobs=info.running_jobs,
        concurrency=settings.concurrency,
        yield_to_local=settings.yield_to_local,
        docker=info.docker.value,
        tex_image=info.tex_image.value,
        ai_endpoints=[
            RemoteRunnerAiEndpoint(
                name=e.name, provider_id=e.provider_id, flavor=e.flavor, url=e.url, announced=e.announced
            )
            for e in info.ai_endpoints
        ],
        pairing=(
            RemoteRunnerPairingInfo(
                user_code=pairing.user_code,
                verification_uri_complete=pairing.verification_uri_complete,
                expires_at=pairing.expires_at,
            )
            if pairing
            else None
        ),
    )


async def _respond(
    action: Callable[[], Awaitable[object]], supervisor: IRemoteRunnerSupervisor
) -> RemoteRunnerStatus | JSONResponse:
    """Действие и свежее состояние; отказ отдаётся телом `{detail, code}`, как у остальных ручек."""
    try:
        await action()
    except RemoteRunnerError as exc:
        return JSONResponse(status_code=_ERROR_STATUS[exc.code], content={"detail": exc.detail, "code": exc.code.value})
    except ValueError as exc:
        return JSONResponse(status_code=_INVALID, content={"detail": str(exc), "code": "input_invalid"})
    return status_body(supervisor.status())


@router.get("/remote-runner", response_model=RemoteRunnerStatus)
async def get_remote_runner(supervisor: FromDishka[IRemoteRunnerSupervisor]) -> RemoteRunnerStatus:
    return status_body(supervisor.status())


@router.put("/remote-runner", response_model=RemoteRunnerStatus)
async def update_remote_runner(
    payload: UpdateRemoteRunnerRequest,
    uc: FromDishka[UpdateRemoteRunnerUC],
    supervisor: FromDishka[IRemoteRunnerSupervisor],
) -> RemoteRunnerStatus | JSONResponse:
    data = UpdateRemoteRunnerInput(
        enabled=payload.enabled,
        server_url=payload.server_url,
        name=payload.name,
        concurrency=payload.concurrency,
        yield_to_local=payload.yield_to_local,
        ai_endpoints=(
            None
            if payload.ai_endpoints is None
            else tuple(RemoteAiEndpointChoice(name=e.name, provider_id=e.provider_id) for e in payload.ai_endpoints)
        ),
    )
    return await _respond(lambda: uc.execute(data), supervisor)


@router.post("/remote-runner/pair", response_model=RemoteRunnerStatus)
async def pair_remote_runner(
    payload: RemoteRunnerPairRequest, supervisor: FromDishka[IRemoteRunnerSupervisor]
) -> RemoteRunnerStatus | JSONResponse:
    return await _respond(lambda: supervisor.start_pairing(payload.server_url, payload.name), supervisor)


@router.post("/remote-runner/token", response_model=RemoteRunnerStatus)
async def use_remote_runner_token(
    payload: RemoteRunnerTokenRequest, supervisor: FromDishka[IRemoteRunnerSupervisor]
) -> RemoteRunnerStatus | JSONResponse:
    return await _respond(lambda: supervisor.use_token(payload.server_url, payload.token), supervisor)


@router.delete("/remote-runner/pairing", response_model=RemoteRunnerStatus)
async def cancel_remote_runner_pairing(
    supervisor: FromDishka[IRemoteRunnerSupervisor],
) -> RemoteRunnerStatus | JSONResponse:
    return await _respond(supervisor.cancel_pairing, supervisor)


@router.delete("/remote-runner", response_model=RemoteRunnerStatus)
async def unpair_remote_runner(supervisor: FromDishka[IRemoteRunnerSupervisor]) -> RemoteRunnerStatus | JSONResponse:
    return await _respond(supervisor.unpair, supervisor)
