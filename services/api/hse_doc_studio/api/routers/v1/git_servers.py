"""Серверы HSE Doc Studio в локальной Студии (раздел 7.5): вход по коду, подключённые серверы, их проекты.

Область `local_only`: на сервере маршрутов нет (404).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response, status

from hse_doc_studio.api.schemas.git_remote import (
    GitProject,
    GitProjectPage,
    GitServerItem,
    GitServerList,
    GitServerLogin,
    GitServerLoginRequest,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_remote.client import StudioServerError, StudioServerErrorCode
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.listing import DEFAULT_LIMIT, MAX_LIMIT
from hse_doc_studio.use_cases.git_sync.studio_servers import StudioServerLogin, StudioServersService

router = APIRouter()

_CODES = {
    StudioServerErrorCode.url_invalid: IdentityErrorCode.git_server_url_invalid,
    StudioServerErrorCode.not_studio: IdentityErrorCode.git_server_not_studio,
    StudioServerErrorCode.unreachable: IdentityErrorCode.git_server_unreachable,
}


def _mapped(exc: StudioServerError) -> Exception:
    if exc.code == StudioServerErrorCode.unauthorized:
        return GitSyncError(GitErrorCode.auth_failed)
    return IdentityError(_CODES.get(exc.code, IdentityErrorCode.git_server_unreachable))


async def _service(request: Request) -> StudioServersService:
    service: StudioServersService = await request.state.dishka_container.get(StudioServersService)
    return service


def _login(login: StudioServerLogin) -> GitServerLogin:
    return GitServerLogin(
        login_id=login.login_id,
        server_url=login.server_url,
        state=login.state,
        user_code=login.user_code,
        verification_uri_complete=login.verification_uri_complete,
        expires_at=login.expires_at,
        credential_id=str(login.credential_id) if login.credential_id else None,
        code=login.code,
    )


@router.post("/git/servers/login", response_model=GitServerLogin)
async def start_git_server_login(body: GitServerLoginRequest, request: Request) -> GitServerLogin:
    try:
        login = await (await _service(request)).start_login(body.server_url, body.client_name)
    except StudioServerError as exc:
        raise _mapped(exc) from None
    return _login(login)


@router.get("/git/servers/login/{login_id}", response_model=GitServerLogin)
async def get_git_server_login(login_id: str, request: Request) -> GitServerLogin:
    try:
        return _login((await _service(request)).get_login(login_id))
    except NotFoundError:
        raise IdentityError(IdentityErrorCode.not_found) from None


@router.delete("/git/servers/login/{login_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_git_server_login(login_id: str, request: Request) -> Response:
    (await _service(request)).cancel_login(login_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/git/servers", response_model=GitServerList)
async def list_git_servers(request: Request) -> GitServerList:
    items = await (await _service(request)).list_servers()
    return GitServerList(
        items=[
            GitServerItem(
                credential_id=str(item.credential_id),
                server_url=item.server_url,
                host=item.host,
                account_name=item.account_name,
                scopes=[s for s in item.scopes if s in ("git:read", "git:write")],
                expires_at=item.expires_at,
                state=item.state,
            )
            for item in items
        ]
    )


@router.get("/git/servers/{credential_id}/projects", response_model=GitProjectPage)
async def list_git_server_projects(
    credential_id: UUID,
    request: Request,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GitProjectPage:
    try:
        page = await (await _service(request)).list_projects(credential_id, q=q, limit=limit, offset=offset)
    except NotFoundError:
        raise IdentityError(IdentityErrorCode.not_found) from None
    except StudioServerError as exc:
        raise _mapped(exc) from None
    return GitProjectPage(
        items=[
            GitProject(
                id=p.id,
                name=p.name,
                owner_name=p.owner_name,
                role=p.role,
                can_push=p.can_push,
                clone_url=p.clone_url,
                updated_at=p.updated_at,
            )
            for p in page.items
        ],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.delete("/git/servers/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def forget_git_server(credential_id: UUID, request: Request) -> Response:
    try:
        await (await _service(request)).forget(credential_id)
    except NotFoundError:
        raise IdentityError(IdentityErrorCode.not_found) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
