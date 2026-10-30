"""`/api/admin`: раннеры и токены их регистрации. Гард и префикс задаёт `make_admin_router`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status

from hse_doc_studio.api.config import settings
from hse_doc_studio.api.schemas.runner_admin import (
    CreatedRegistrationTokenResponse,
    CreateRegistrationTokenRequest,
    RegistrationTokenInfo,
    RotatedRunnerTokenResponse,
    RunnerInfo,
    UpdateRunnerRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.jobs.admin import runner_status
from hse_doc_studio.core.jobs.errors import RunnerNotFoundError
from hse_doc_studio.core.jobs.runners import RegistrationToken, Runner
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry

router = APIRouter()


def _token_info(token: RegistrationToken) -> RegistrationTokenInfo:
    return RegistrationTokenInfo(
        id=token.id,
        label=token.label,
        created_at=token.created_at,
        expires_at=token.expires_at,
        max_uses=token.max_uses,
        uses=token.uses,
        revoked=token.revoked_at is not None,
    )


def _runner_info(runner: Runner) -> RunnerInfo:
    return RunnerInfo(
        id=runner.id,
        name=runner.name,
        status=runner_status(runner, datetime.now(UTC)).value,
        tags=sorted(runner.tags),
        concurrency=runner.concurrency,
        resource_class=runner.resource_class,
        version=runner.version,
        created_at=runner.created_at,
        last_seen_at=runner.last_seen_at,
        paused=runner.paused,
        revoked=runner.revoked_at is not None,
    )


def _command(request: Request, secret: str) -> str:
    """Команда запуска раннера: адрес Студии берётся из public_url, иначе из запроса админа."""
    base = (settings.auth.public_url or str(request.base_url)).rstrip("/")
    return f"HSE_RUNNER__API_URL={base} HSE_RUNNER__TOKEN={secret} hse-doc-studio runner"


async def _registry(request: Request) -> RunnerRegistry:
    return await request.state.dishka_container.get(RunnerRegistry)


def _not_found(_exc: RunnerNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


@router.post("/runner-tokens", response_model=CreatedRegistrationTokenResponse, status_code=status.HTTP_201_CREATED)
async def create_registration_token(
    body: CreateRegistrationTokenRequest, request: Request
) -> CreatedRegistrationTokenResponse:
    created = await (await _registry(request)).create_registration_token(
        require_actor(), label=body.label, ttl=timedelta(hours=body.ttl_hours), max_uses=body.max_uses
    )
    return CreatedRegistrationTokenResponse(
        token=_token_info(created.token),
        secret=created.secret,
        command=_command(request, created.secret),
    )


@router.get("/runner-tokens", response_model=list[RegistrationTokenInfo])
async def list_registration_tokens(request: Request) -> list[RegistrationTokenInfo]:
    return [_token_info(t) for t in await (await _registry(request)).list_registration_tokens(require_actor())]


@router.delete("/runner-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_registration_token(token_id: str, request: Request) -> Response:
    try:
        await (await _registry(request)).revoke_registration_token(require_actor(), token_id)
    except RunnerNotFoundError as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/runners", response_model=list[RunnerInfo])
async def list_runners(request: Request) -> list[RunnerInfo]:
    return [_runner_info(r) for r in await (await _registry(request)).list_runners(require_actor())]


@router.patch("/runners/{runner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_runner(runner_id: str, body: UpdateRunnerRequest, request: Request) -> Response:
    try:
        await (await _registry(request)).set_paused(require_actor(), runner_id, body.paused)
    except RunnerNotFoundError as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/runners/{runner_id}/rotate-token", response_model=RotatedRunnerTokenResponse)
async def rotate_runner_token(runner_id: str, request: Request) -> RotatedRunnerTokenResponse:
    try:
        rotated = await (await _registry(request)).rotate_token(require_actor(), runner_id)
    except RunnerNotFoundError as exc:
        raise _not_found(exc) from exc
    return RotatedRunnerTokenResponse(
        runner=_runner_info(rotated.runner),
        runner_token=rotated.secret,
        command=_command(request, rotated.secret),
    )


@router.delete("/runners/{runner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_runner(runner_id: str, request: Request) -> Response:
    try:
        await (await _registry(request)).revoke(require_actor(), runner_id)
    except RunnerNotFoundError as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
