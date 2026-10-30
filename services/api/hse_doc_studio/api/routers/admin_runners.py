"""`/api/admin`: раннеры и токены их регистрации. Гард и префикс задаёт `make_admin_router`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from hse_doc_studio.api.config import settings
from hse_doc_studio.api.schemas.admin import (
    Page,
    PageParams,
    PickerList,
    PickerParams,
    page_params,
    picker_list,
    picker_params,
    search_param,
    sort_param,
)
from hse_doc_studio.api.schemas.runner_admin import (
    CreatedRegistrationTokenResponse,
    CreateRegistrationTokenRequest,
    RegistrationTokenInfo,
    RegistrationTokenStatusName,
    RotatedRunnerTokenResponse,
    RunnerInfo,
    RunnerStatusName,
    RunnerSummaryInfo,
    UpdateRunnerRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.jobs.admin import (
    REGISTRATION_TOKEN_SORT_FIELDS,
    RUNNER_SORT_FIELDS,
    RegistrationTokenQuery,
    RegistrationTokenStatus,
    RunnerQuery,
    RunnerStatus,
    runner_status,
)
from hse_doc_studio.core.jobs.errors import RunnerNotFoundError
from hse_doc_studio.core.jobs.runners import RegistrationToken, Runner
from hse_doc_studio.core.listing import SortKey
from hse_doc_studio.use_cases.admin.ops_runners import (
    ListRegistrationTokensUC,
    ListRunnersUC,
    PickRunnersUC,
    RunnerSummaryUC,
)
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}
_RUNNER_SORT = sort_param(allowed=RUNNER_SORT_FIELDS, default="status")
_TOKEN_SORT = sort_param(allowed=REGISTRATION_TOKEN_SORT_FIELDS, default="-created_at")


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


def _runner_info(runner: Runner, now: datetime | None = None) -> RunnerInfo:
    return RunnerInfo(
        id=runner.id,
        name=runner.name,
        status=runner_status(runner, now or datetime.now(UTC)).value,
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


async def _uc[T](request: Request, kind: type[T]) -> T:
    return await request.state.dishka_container.get(kind)


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


@router.get("/runner-tokens", response_model=Page[RegistrationTokenInfo])
async def list_registration_tokens(
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Depends(search_param)],
    sort: Annotated[SortKey, Depends(_TOKEN_SORT)],
    token_status: Annotated[list[RegistrationTokenStatusName] | None, Query(alias="status")] = None,
) -> Page[RegistrationTokenInfo]:
    response.headers.update(_NO_STORE)
    page = await (await _uc(request, ListRegistrationTokensUC)).execute(
        require_actor(),
        RegistrationTokenQuery(
            q=q,
            statuses=frozenset(RegistrationTokenStatus(s) for s in token_status or ()),
            sort=sort,
            window=params.window,
        ),
    )
    return params.page([_token_info(t) for t in page.items], page.total)


@router.delete("/runner-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_registration_token(token_id: str, request: Request) -> Response:
    try:
        await (await _registry(request)).revoke_registration_token(require_actor(), token_id)
    except RunnerNotFoundError as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/runners", response_model=Page[RunnerInfo])
async def list_runners(
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Depends(search_param)],
    sort: Annotated[SortKey, Depends(_RUNNER_SORT)],
    runner_state: Annotated[list[RunnerStatusName] | None, Query(alias="status")] = None,
    tag: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    resource_class: Annotated[str | None, Query(min_length=1, max_length=32)] = None,
    outdated: Annotated[bool | None, Query()] = None,
) -> Page[RunnerInfo]:
    response.headers.update(_NO_STORE)
    found = await (await _uc(request, ListRunnersUC)).execute(
        require_actor(),
        RunnerQuery(
            q=q,
            statuses=frozenset(RunnerStatus(s) for s in runner_state or ()),
            tag=tag,
            resource_class=resource_class,
            outdated=outdated,
            sort=sort,
            window=params.window,
        ),
    )
    return params.page([_runner_info(r, found.as_of) for r in found.page.items], found.page.total)


@router.get("/runners/summary", response_model=RunnerSummaryInfo)
async def runners_summary(request: Request, response: Response) -> RunnerSummaryInfo:
    response.headers.update(_NO_STORE)
    summary = await (await _uc(request, RunnerSummaryUC)).execute(require_actor())
    return RunnerSummaryInfo(
        online=summary.online,
        paused=summary.paused,
        stale=summary.stale,
        offline=summary.offline,
        revoked=summary.revoked,
        outdated=summary.outdated,
        newest_version=summary.newest_version,
    )


@router.get("/pickers/runners", response_model=PickerList)
async def pick_runners(
    request: Request,
    response: Response,
    params: Annotated[PickerParams, Depends(picker_params)],
    # Один раннер по id: имя для фильтра очереди, открытого по ссылке.
    item_id: Annotated[str | None, Query(alias="id", min_length=1, max_length=64)] = None,
) -> PickerList:
    response.headers.update(_NO_STORE)
    uc = await _uc(request, PickRunnersUC)
    return picker_list(await uc.execute(require_actor(), params.q, params.limit, item_id=item_id))


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
