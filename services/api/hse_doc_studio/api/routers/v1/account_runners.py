"""Мои раннеры (`/api/v1/account/runners*`, `/account/runner-tokens*`): свои машины, которые собирают свои проекты.

Только сервер; сессия или персональный токен со scope `api`. Чужой раннер или токен неотличим от
несуществующего (404). Секреты есть только в ответах на создание токена и смену токена раннера.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.rate_limit import enforce, enforce_ip
from hse_doc_studio.api.runner_commands import (
    registration_command,
    registration_docker_command,
    runner_token_command,
    studio_base_url,
)
from hse_doc_studio.api.schemas.personal_runners import (
    CreateMyRunnerTokenRequest,
    MyRunner,
    MyRunnerAiEndpoint,
    MyRunnerRotated,
    MyRunnerToken,
    MyRunnerTokenCreated,
    RunnerPairingDecisionRequest,
    RunnerPairingInfo,
    UpdateMyRunnerRequest,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.jobs.admin import runner_status
from hse_doc_studio.core.jobs.errors import RunnerNotFoundError
from hse_doc_studio.core.jobs.pairing import RunnerPairing
from hse_doc_studio.core.jobs.runners import RegistrationToken, Runner
from hse_doc_studio.core.rate_limit import RUNNER_PAIRING
from hse_doc_studio.use_cases.jobs.pairing import RunnerPairingService
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry

router = APIRouter(dependencies=[Depends(require_server_mode)])

_NO_STORE = {"Cache-Control": "no-store"}


def _account_actor() -> Actor:
    """Вошедший человек по сессии или токену; гостевая ссылка своих раннеров не имеет."""
    actor = current_actor()
    if actor is None or not actor.id:
        raise IdentityError(IdentityErrorCode.auth_required)
    if actor.source not in (ActorSource.session, ActorSource.pat):
        raise IdentityError(IdentityErrorCode.forbidden)
    return actor


async def _registry(request: Request) -> RunnerRegistry:
    return await request.state.dishka_container.get(RunnerRegistry)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def my_runner_view(runner: Runner, *, running_jobs: int, personal_enabled: bool, now: datetime) -> MyRunner:
    return MyRunner(
        id=runner.id,
        name=runner.name,
        state=runner_status(runner, now, personal_enabled=personal_enabled).value,
        host_kind=runner.host_kind.value,
        tags=sorted(runner.tags),
        concurrency=runner.concurrency,
        ai_concurrency=runner.ai_concurrency,
        version=runner.version,
        created_at=runner.created_at,
        last_seen_at=runner.last_seen_at,
        last_seen_ip=runner.last_seen_ip,
        paused=runner.paused,
        revoked=runner.revoked_at is not None,
        running_jobs=running_jobs,
        ai_endpoints=[MyRunnerAiEndpoint(name=e.name, flavor=e.flavor.value) for e in runner.ai_endpoints],
        features=sorted(runner.features),
    )


async def _views(registry: RunnerRegistry, runners: list[Runner]) -> list[MyRunner]:
    counts = await registry.running_jobs({r.id for r in runners})
    enabled = (await registry.personal_settings()).enabled
    now = datetime.now(UTC)
    return [my_runner_view(r, running_jobs=counts[r.id], personal_enabled=enabled, now=now) for r in runners]


def _token_view(token: RegistrationToken) -> MyRunnerToken:
    return MyRunnerToken(
        id=token.id,
        label=token.label,
        created_at=token.created_at,
        expires_at=token.expires_at,
        used=token.uses >= token.max_uses,
        revoked=token.revoked_at is not None,
    )


@router.get("/account/runners", response_model=list[MyRunner])
async def list_my_runners(request: Request, response: Response) -> list[MyRunner]:
    response.headers.update(_NO_STORE)
    registry = await _registry(request)
    return await _views(registry, await registry.list_my_runners(_account_actor()))


@router.patch("/account/runners/{runner_id}", response_model=MyRunner)
async def update_my_runner(runner_id: str, body: UpdateMyRunnerRequest, request: Request) -> MyRunner:
    registry = await _registry(request)
    try:
        runner = await registry.update_my_runner(_account_actor(), runner_id, name=body.name, paused=body.paused)
    except RunnerNotFoundError as exc:
        raise _not_found() from exc
    (view,) = await _views(registry, [runner])
    return view


@router.post("/account/runners/{runner_id}/rotate-token", response_model=MyRunnerRotated)
async def rotate_my_runner_token(runner_id: str, request: Request, response: Response) -> MyRunnerRotated:
    response.headers.update(_NO_STORE)
    registry = await _registry(request)
    try:
        rotated = await registry.rotate_my_token(_account_actor(), runner_id)
    except RunnerNotFoundError as exc:
        raise _not_found() from exc
    (view,) = await _views(registry, [rotated.runner])
    return MyRunnerRotated(
        runner=view,
        runner_token=rotated.secret,
        command=runner_token_command(studio_base_url(request), rotated.secret),
    )


@router.delete("/account/runners/{runner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_runner(runner_id: str, request: Request) -> Response:
    try:
        await (await _registry(request)).revoke_my_runner(_account_actor(), runner_id)
    except RunnerNotFoundError as exc:
        raise _not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/account/runner-tokens", response_model=list[MyRunnerToken])
async def list_my_runner_tokens(request: Request, response: Response) -> list[MyRunnerToken]:
    response.headers.update(_NO_STORE)
    return [_token_view(t) for t in await (await _registry(request)).list_personal_tokens(_account_actor())]


@router.post("/account/runner-tokens", response_model=MyRunnerTokenCreated, status_code=status.HTTP_201_CREATED)
async def create_my_runner_token(
    body: CreateMyRunnerTokenRequest, request: Request, response: Response
) -> MyRunnerTokenCreated:
    """Секрет `hsrt_…` и команды запуска показываются один раз."""
    response.headers.update(_NO_STORE)
    created = await (await _registry(request)).create_personal_token(
        _account_actor(), label=body.label, ttl=timedelta(hours=body.ttl_hours)
    )
    base = studio_base_url(request)
    return MyRunnerTokenCreated(
        token=_token_view(created.token),
        secret=created.secret,
        command=registration_command(base, created.secret),
        docker_command=registration_docker_command(base, created.secret),
    )


@router.delete("/account/runner-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_runner_token(token_id: str, request: Request) -> Response:
    try:
        await (await _registry(request)).revoke_personal_token(_account_actor(), token_id)
    except RunnerNotFoundError as exc:
        raise _not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _pairing_view(pairing: RunnerPairing) -> RunnerPairingInfo:
    return RunnerPairingInfo(
        user_code=pairing.user_code,
        name=pairing.name,
        host_kind=pairing.host_kind.value,
        requested_at=pairing.created_at,
        expires_at=pairing.expires_at,
        client_ip=pairing.client_ip,
        status=pairing.status.value,
    )


async def _pairing_service(request: Request, actor: Actor) -> RunnerPairingService:
    # Неверные коды тоже считаются: подбирать чужой код и по человеку, и по адресу дорого.
    await enforce(request, RUNNER_PAIRING, f"user:{actor.id}")
    await enforce_ip(request, RUNNER_PAIRING)
    return await request.state.dishka_container.get(RunnerPairingService)


@router.get("/account/runner-pairings/{user_code}", response_model=RunnerPairingInfo)
async def get_runner_pairing(user_code: str, request: Request, response: Response) -> RunnerPairingInfo:
    response.headers.update(_NO_STORE)
    actor = _account_actor()
    return _pairing_view(await (await _pairing_service(request, actor)).info(actor, user_code))


@router.post("/account/runner-pairings/{user_code}", response_model=RunnerPairingInfo)
async def decide_runner_pairing(
    user_code: str, body: RunnerPairingDecisionRequest, request: Request
) -> RunnerPairingInfo:
    actor = _account_actor()
    service = await _pairing_service(request, actor)
    return _pairing_view(await service.decide(actor, user_code, approve=body.decision == "approve"))
