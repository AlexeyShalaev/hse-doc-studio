"""git по HTTPS (Smart HTTP) и служебные вызовы `/git/-/*`: сервер Студии как git-remote (раздел 7).

Маршруты лежат вне `/api/v1` и работают только в серверном режиме при включённом `GitRemoteConfig.enabled`,
иначе 404. Подлинность проверяет сам маршрут: только персональный токен с git-scope (S16), cookie не читаются.
Отказы для `git` уходят текстом: клиент печатает тело `text/plain` строками `remote:`.
"""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from hse_doc_studio.api.config import settings
from hse_doc_studio.api.observability.client_ip import client_ip
from hse_doc_studio.api.rate_limit import enforce
from hse_doc_studio.api.schemas.git_remote import GitServerInfo, GitWhoami, GitWhoamiToken, GitWhoamiUser
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.git_remote.entities import GitService
from hse_doc_studio.core.git_remote.protocols import IGitSmartHttp
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.rate_limit import GIT_AUTH_FAIL, GIT_HTTP
from hse_doc_studio.infra.git_remote.smart_http import git_protocol
from hse_doc_studio.use_cases.git_remote.auth import (
    AUTH_REALM,
    AuthorizeGitServiceUC,
    GitAccess,
    GitConcurrency,
    GitFetchAudit,
    GitHttpAuthenticator,
    GitHttpError,
    GitHttpErrorKind,
    GitPrincipal,
)

GIT_PREFIX = "/git"
_SPOOL_MEMORY = 8 * 1024 * 1024
_CHUNK = 64 * 1024
_NO_CACHE = {"Cache-Control": "no-cache, max-age=0, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
_STATUS = {
    GitHttpErrorKind.unauthorized: 401,
    GitHttpErrorKind.scope_missing: 403,
    GitHttpErrorKind.forbidden: 403,
    GitHttpErrorKind.not_found: 404,
}


def require_git_remote() -> None:
    """Сервер не включил git по HTTPS или это локальная Студия: маршрутов нет."""
    if settings.mode is not StudioMode.server or not settings.git_remote.enabled:
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(prefix=GIT_PREFIX, tags=["git-remote"], dependencies=[Depends(require_git_remote)])


def _text(status: int, message: str, headers: dict[str, str] | None = None) -> PlainTextResponse:
    return PlainTextResponse(message.rstrip("\n") + "\n", status_code=status, headers={**_NO_CACHE, **(headers or {})})


def git_error_response(exc: GitHttpError) -> PlainTextResponse:
    headers = {"WWW-Authenticate": AUTH_REALM} if exc.kind is GitHttpErrorKind.unauthorized else None
    return _text(_STATUS[exc.kind], exc.message, headers)


def _project_id(repo: str) -> UUID | None:
    if not repo.endswith(".git"):
        return None
    try:
        return UUID(repo.removesuffix(".git"))
    except ValueError:
        return None


async def _container_get[T](request: Request, kind: type[T]) -> T:
    found: T = await request.state.dishka_container.get(kind)
    return found


async def _smart_http(request: Request) -> IGitSmartHttp:
    smart: IGitSmartHttp = await request.state.dishka_container.get(IGitSmartHttp)
    return smart


async def authenticate(request: Request) -> GitPrincipal:
    """Токен из Basic или Bearer; неудача считается по IP (GIT_AUTH_FAIL), успех по человеку (GIT_HTTP)."""
    authenticator = await _container_get(request, GitHttpAuthenticator)
    ip = client_ip(request)
    try:
        principal = await authenticator.authenticate({k.lower(): v for k, v in request.headers.items()}, ip)
    except GitHttpError as exc:
        if exc.kind is GitHttpErrorKind.unauthorized and "authorization" in request.headers:
            await enforce(request, GIT_AUTH_FAIL, f"ip:{ip}")
        raise
    await enforce(request, GIT_HTTP, f"user:{principal.user_id}")
    set_current_actor(principal.actor)
    return principal


def _rate_limited(exc: IdentityError) -> PlainTextResponse:
    headers = {"Retry-After": str(exc.retry_after_s)} if exc.retry_after_s else None
    return _text(
        429,
        localized_error("Слишком много запросов git. Повторите позже.", "Too many git requests. Try later."),
        headers,
    )


@router.get("/-/info", response_model=GitServerInfo)
async def git_server_info() -> GitServerInfo:
    """Публичная визитка: по ней локальная Студия узнаёт сервер Студии (провайдер `hse_studio`)."""
    return GitServerInfo(server="hse-doc-studio", version=settings.get_app_version(), device_flow=True, api="/api/v1")


@router.get("/-/whoami", response_model=GitWhoami)
async def git_whoami(request: Request) -> Response:
    try:
        principal = await authenticate(request)
    except GitHttpError as exc:
        return _json_error(exc)
    except IdentityError as exc:
        return _rate_limited(exc)
    users: IUserRepository = await request.state.dishka_container.get(IUserRepository)
    user = await users.get(principal.user_id)
    token = principal.token
    body = GitWhoami(
        user=GitWhoamiUser(id=principal.user_id, name=user.name if user else "", email=user.email if user else ""),
        scopes=sorted(scope.value for scope in token.scopes if scope.value.startswith("git:")),
        token=GitWhoamiToken(id=token.id, name=token.name, expires_at=token.expires_at),
    )
    return JSONResponse(body.model_dump(mode="json"), headers={"Cache-Control": "no-store"})


def _json_error(exc: GitHttpError) -> JSONResponse:
    code = {
        GitHttpErrorKind.unauthorized: IdentityErrorCode.auth_required,
        GitHttpErrorKind.scope_missing: IdentityErrorCode.git_scope_missing,
        GitHttpErrorKind.forbidden: IdentityErrorCode.forbidden,
        GitHttpErrorKind.not_found: IdentityErrorCode.not_found,
    }[exc.kind]
    headers = {"WWW-Authenticate": AUTH_REALM} if exc.kind is GitHttpErrorKind.unauthorized else None
    return JSONResponse({"detail": exc.message, "code": code.value}, status_code=_STATUS[exc.kind], headers=headers)


async def _authorize(request: Request, repo: str, service: GitService) -> GitAccess:
    project_id = _project_id(repo)
    principal = await authenticate(request)
    if project_id is None:
        raise GitHttpError(
            GitHttpErrorKind.not_found, localized_error("Репозиторий не найден.", "Repository not found.")
        )
    uc = await _container_get(request, AuthorizeGitServiceUC)
    return await uc.execute(principal, project_id, service)


@router.get("/{repo}/info/refs")
async def git_info_refs(
    request: Request,
    repo: Annotated[str, Path()],
    service: Annotated[str | None, Query()] = None,
) -> Response:
    if service not in {GitService.upload_pack.value, GitService.receive_pack.value}:
        return _text(
            403,
            localized_error(
                "Нужен git 2.31 или новее (протокол Smart HTTP).", "git 2.31 or newer is required (Smart HTTP)."
            ),
        )
    kind = GitService(service)
    try:
        access = await _authorize(request, repo, kind)
    except GitHttpError as exc:
        return git_error_response(exc)
    except IdentityError as exc:
        return _rate_limited(exc)
    if kind is GitService.receive_pack:
        refusal = await _receive_refusal(request, access)
        if refusal is not None:
            return refusal
    smart = await _smart_http(request)
    body = await smart.advertise(kind, access.git_dir, protocol=git_protocol(request.headers.get("git-protocol")))
    return Response(body, media_type=f"application/x-{kind.value}-advertisement", headers=_NO_CACHE)


async def _receive_refusal(_request: Request, _access: GitAccess) -> Response | None:
    return _text(
        403, localized_error("Сервер пока не принимает отправку изменений.", "The server does not accept pushes yet.")
    )


def _too_large(request: Request) -> bool:
    length = request.headers.get("content-length")
    return length is not None and length.isdigit() and int(length) > settings.git_remote.max_push_bytes


class _BodyTooLargeError(Exception):
    pass


async def _spool(request: Request) -> tempfile.SpooledTemporaryFile[bytes]:
    """Тело целиком до ответа: StreamingResponse сам слушает `receive` и съел бы куски тела у процесса git.

    До 8 МБ в памяти, дальше во временном файле; сжатое тело больше предела отвергается сразу.
    """
    spool: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MEMORY)  # noqa: SIM115
    size = 0
    try:
        async for chunk in request.stream():
            size += len(chunk)
            if size > settings.git_remote.max_push_bytes:
                raise _BodyTooLargeError
            spool.write(chunk)
    except BaseException:
        spool.close()
        raise
    spool.seek(0)
    return spool


async def _replay(spool: tempfile.SpooledTemporaryFile[bytes]) -> AsyncIterator[bytes]:
    try:
        while chunk := spool.read(_CHUNK):
            yield chunk
    finally:
        spool.close()


def _gzip(request: Request) -> bool:
    return request.headers.get("content-encoding", "").strip().lower() in {"gzip", "x-gzip"}


async def _released(stream: AsyncIterator[bytes], concurrency: GitConcurrency, user_id: str) -> AsyncIterator[bytes]:
    try:
        async for chunk in stream:
            yield chunk
    finally:
        concurrency.release(user_id)


def _busy() -> PlainTextResponse:
    return _text(
        429,
        localized_error(
            "Слишком много одновременных запросов git. Повторите позже.",
            "Too many concurrent git requests. Try again later.",
        ),
    )


@router.post("/{repo}/git-upload-pack")
async def git_upload_pack(request: Request, repo: Annotated[str, Path()]) -> Response:
    try:
        access = await _authorize(request, repo, GitService.upload_pack)
    except GitHttpError as exc:
        return git_error_response(exc)
    except IdentityError as exc:
        return _rate_limited(exc)
    if _too_large(request):
        return _text(413, localized_error("Запрос слишком большой.", "The request is too large."))
    try:
        spool = await _spool(request)
    except _BodyTooLargeError:
        return _text(413, localized_error("Запрос слишком большой.", "The request is too large."))
    concurrency = await _container_get(request, GitConcurrency)
    if not concurrency.try_acquire(access.principal.user_id):
        spool.close()
        return _busy()
    smart = await _smart_http(request)
    await (await _container_get(request, GitFetchAudit)).record_fetch(access)
    stream = smart.rpc(
        GitService.upload_pack,
        access.git_dir,
        _replay(spool),
        gzip=_gzip(request),
        protocol=git_protocol(request.headers.get("git-protocol")),
    )
    return StreamingResponse(
        _released(stream, concurrency, access.principal.user_id),
        media_type="application/x-git-upload-pack-result",
        headers=_NO_CACHE,
    )


@router.post("/{repo}/git-receive-pack")
async def git_receive_pack(request: Request, repo: Annotated[str, Path()]) -> Response:
    try:
        access = await _authorize(request, repo, GitService.receive_pack)
    except GitHttpError as exc:
        return git_error_response(exc)
    except IdentityError as exc:
        return _rate_limited(exc)
    refusal = await _receive_refusal(request, access)
    return refusal or _text(403, "")
