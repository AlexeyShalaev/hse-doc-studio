"""git по HTTPS (Smart HTTP) и служебные вызовы `/git/-/*`: сервер Студии как git-remote (раздел 7).

Маршруты лежат вне `/api/v1` и работают только в серверном режиме при включённом `GitRemoteConfig.enabled`,
иначе 404. Подлинность проверяет сам маршрут: только персональный токен с git-scope (S16), cookie не читаются.
Отказы для `git` уходят текстом: клиент печатает тело `text/plain` строками `remote:`.
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, BinaryIO, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import ValidationError

from hse_doc_studio.api.artifact_mapping import map_artifact
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.device_mapping import map_builds, map_overview
from hse_doc_studio.api.observability.client_ip import client_ip
from hse_doc_studio.api.rate_limit import enforce
from hse_doc_studio.api.schemas.artifacts import PdfUploadResponse
from hse_doc_studio.api.schemas.builds import ProjectBuildsResponse
from hse_doc_studio.api.schemas.devices import DevicesOverviewResponse, HeartbeatRequest, HeartbeatResponse
from hse_doc_studio.api.schemas.git_remote import (
    GitProject,
    GitProjectPage,
    GitServerInfo,
    GitWhoami,
    GitWhoamiToken,
    GitWhoamiUser,
)
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.artifacts.entities import ArtifactError, ArtifactErrorCode
from hse_doc_studio.core.builds.entities import BuildStamp
from hse_doc_studio.core.devices.entities import DEVICE_ID_RE
from hse_doc_studio.core.git_remote.entities import GitService
from hse_doc_studio.core.git_remote.protocols import GitRpcOutcome, IGitSmartHttp
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.entities import TokenScope
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.listing import DEFAULT_LIMIT, MAX_LIMIT, Window
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.rate_limit import GIT_AUTH_FAIL, GIT_HTTP
from hse_doc_studio.infra.git_remote.smart_http import git_protocol
from hse_doc_studio.use_cases.artifacts.builds import GitProjectGate, OpenCloudBuildPdfUC, ProjectBuildsUC
from hse_doc_studio.use_cases.artifacts.pdf import PdfUploadMeta, PdfUploadResult, UploadProjectPdfUC
from hse_doc_studio.use_cases.devices.service import DevicesOverviewUC, RecordHeartbeatUC, TooManyDevicesError
from hse_doc_studio.use_cases.git_remote.auth import (
    AUTH_REALM,
    AuthorizeGitServiceUC,
    GitAccess,
    GitConcurrency,
    GitDenial,
    GitFetchAudit,
    GitHttpAuthenticator,
    GitHttpError,
    GitHttpErrorKind,
    GitPrincipal,
    denial_message,
)
from hse_doc_studio.use_cases.git_remote.projects import ListGitProjectsUC
from hse_doc_studio.use_cases.git_remote.receive import (
    ProjectBusyError,
    PushSession,
    ReceivePushUC,
    project_busy_message,
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
    return _text(_STATUS[exc.kind], denial_message(exc.reason), headers)


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


@router.get("/-/projects", response_model=GitProjectPage)
async def git_projects(
    request: Request,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Response:
    """Проекты, которые локальная Студия может клонировать этим токеном (S21)."""
    try:
        principal = await authenticate(request)
    except GitHttpError as exc:
        return _json_error(exc)
    except IdentityError as exc:
        return _rate_limited(exc)
    uc = await _container_get(request, ListGitProjectsUC)
    found = await uc.execute(
        principal.actor,
        q=q,
        window=Window(limit=limit, offset=offset),
        can_write=principal.has(TokenScope.git_write),
    )
    page = GitProjectPage(
        items=[
            GitProject(
                id=str(item.id),
                name=item.name,
                owner_name=item.owner_name,
                role=item.role.value,
                can_push=item.can_push,
                clone_url=item.clone_url,
                updated_at=item.updated_at,
            )
            for item in found.items
        ],
        total=found.total,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(page.model_dump(mode="json"), headers={"Cache-Control": "no-store"})


_PRESENCE_BODY_LIMIT = 64 * 1024


async def _presence_body(request: Request) -> HeartbeatRequest | JSONResponse:
    """Тело сигнала после проверки токена: не больше предела и по контракту (иначе 413 или 422)."""
    length = request.headers.get("content-length")
    too_large = JSONResponse({"detail": "Request body is too large", "code": "presence_too_large"}, status_code=413)
    if length is not None and length.isdigit() and int(length) > _PRESENCE_BODY_LIMIT:
        return too_large
    raw = await request.body()
    if len(raw) > _PRESENCE_BODY_LIMIT:
        return too_large
    try:
        return HeartbeatRequest.model_validate_json(raw)
    except ValidationError:
        return JSONResponse({"detail": "Invalid presence report", "code": "presence_invalid"}, status_code=422)


@router.post("/-/presence", response_model=HeartbeatResponse)
async def git_presence(request: Request) -> Response:
    """Сигнал присутствия локальной Студии (docs/design/connected-devices.md): метаданные по тому же токену."""
    try:
        principal = await authenticate(request)
    except GitHttpError as exc:
        return _json_error(exc)
    except IdentityError as exc:
        return _rate_limited(exc)
    body = await _presence_body(request)
    if isinstance(body, JSONResponse):
        return body
    uc = await _container_get(request, RecordHeartbeatUC)
    try:
        receipt = await uc.execute(principal.user_id, principal.token.id, body.to_report())
    except TooManyDevicesError:
        return JSONResponse(
            {"detail": "Too many devices on this account", "code": "too_many_devices"},
            status_code=409,
            headers=_NO_CACHE,
        )
    reply = HeartbeatResponse(
        interval_s=receipt.interval_s, online_window_s=receipt.online_window_s, server_time=receipt.server_time
    )
    return JSONResponse(reply.model_dump(mode="json"), headers=_NO_CACHE)


@router.get("/-/presence/overview", response_model=DevicesOverviewResponse)
async def git_presence_overview(
    request: Request,
    device_id: Annotated[str, Query(min_length=32, max_length=32)],
    project_id: UUID | None = None,
) -> Response:
    """Как облако видит эту Студию и кто ещё из участников проекта сейчас работает локально."""
    try:
        principal = await authenticate(request)
    except GitHttpError as exc:
        return _json_error(exc)
    except IdentityError as exc:
        return _rate_limited(exc)
    if not DEVICE_ID_RE.fullmatch(device_id):
        return JSONResponse({"detail": "Invalid device id", "code": "device_id_invalid"}, status_code=422)
    uc = await _container_get(request, DevicesOverviewUC)
    found = await uc.execute(principal.actor, device_id, project_id)
    return JSONResponse(map_overview(found).model_dump(mode="json"), headers=_NO_CACHE)


@router.get("/-/projects/{project_id}/builds", response_model=ProjectBuildsResponse)
async def git_project_builds(request: Request, project_id: UUID) -> Response:
    """Статус сборок проекта для локальной Студии: облачная и выгруженная сборки по документам, коммит и свежесть."""
    try:
        principal = await authenticate(request)
        await (await _container_get(request, GitProjectGate)).require(principal.actor, project_id)
        found = await (await _container_get(request, ProjectBuildsUC)).execute(project_id)
    except GitHttpError as exc:
        return _json_error(exc)
    except IdentityError as exc:
        return _rate_limited(exc)
    except ArtifactError as exc:
        return _artifact_error(exc)
    body = map_builds(found, settings.artifacts.max_pdf_bytes)
    return JSONResponse(body.model_dump(mode="json"), headers=_NO_CACHE)


@router.get("/-/projects/{project_id}/documents/{doc_id}/pdf")
async def git_cloud_pdf(request: Request, project_id: UUID, doc_id: Annotated[str, Path(max_length=128)]) -> Response:
    """PDF последней облачной сборки документа: токен с чтением исходников. Тот же отпечаток: 304 без тела."""
    uc = await _container_get(request, OpenCloudBuildPdfUC)
    try:
        principal = await authenticate(request)
        stamp = await uc.stamp(principal.actor, project_id, doc_id)
        headers = _pdf_headers(stamp)
        known = request.headers.get("if-none-match", "").strip('"')
        if stamp.sha256 and known == stamp.sha256:
            return Response(status_code=304, headers=headers)
        concurrency = await _container_get(request, GitConcurrency)
        if not concurrency.try_acquire(principal.user_id):
            return _busy()
        try:
            pdf = await uc.read(project_id, stamp)
        finally:
            concurrency.release(principal.user_id)
    except GitHttpError as exc:
        return _json_error(exc)
    except IdentityError as exc:
        return _rate_limited(exc)
    except ArtifactError as exc:
        return _artifact_error(exc)
    return Response(
        content=pdf.content,
        media_type="application/pdf",
        headers={**_pdf_headers(stamp), "X-Content-SHA256": pdf.sha256, "ETag": f'"{pdf.sha256}"'},
    )


def _pdf_headers(stamp: BuildStamp) -> dict[str, str]:
    headers = {**_NO_CACHE, "X-Built-At": stamp.finished_at.isoformat()}
    if stamp.source_commit:
        headers["X-Source-Commit"] = stamp.source_commit
    if stamp.pages:
        headers["X-Pages"] = str(stamp.pages)
    if stamp.sha256:
        headers["X-Content-SHA256"] = stamp.sha256
        headers["ETag"] = f'"{stamp.sha256}"'
    return headers


_ARTIFACT_STATUS = {
    ArtifactErrorCode.too_large: 413,
    ArtifactErrorCode.not_pdf: 415,
    ArtifactErrorCode.checksum_mismatch: 422,
    ArtifactErrorCode.unknown_document: 404,
    ArtifactErrorCode.forbidden: 403,
    ArtifactErrorCode.not_found: 404,
    ArtifactErrorCode.read_only: 423,
}


def _artifact_error(exc: ArtifactError) -> JSONResponse:
    return JSONResponse(
        {"detail": exc.message, "code": exc.code.value}, status_code=_ARTIFACT_STATUS[exc.code], headers=_NO_CACHE
    )


@router.put("/-/projects/{project_id}/documents/{doc_id}/pdf", response_model=PdfUploadResponse)
async def git_upload_pdf(  # noqa: PLR0913 — параметры запроса одной выгрузки
    request: Request,
    project_id: UUID,
    doc_id: Annotated[str, Path(max_length=128)],
    sha256: Annotated[str | None, Query(pattern="^[0-9a-fA-F]{64}$")] = None,
    name: Annotated[str | None, Query(max_length=255)] = None,
    pages: Annotated[int | None, Query(ge=1, le=100_000)] = None,
    commit: Annotated[str | None, Query(max_length=64, pattern="^[0-9a-fA-F]*$")] = None,
    built_at: Annotated[datetime | None, Query()] = None,
) -> Response:
    """PDF локальной сборки как артефакт проекта (docs/design/local-sync.md, P2): токен с `git:write`, право сборки."""
    uc = await _container_get(request, UploadProjectPdfUC)
    try:
        principal = await _writer(request)
        # Права проверяются до чтения тела: чужой не заставит сервер принять сотню мегабайт.
        await uc.authorize(principal.actor, project_id, doc_id)
        if _body_over(request, uc.max_bytes):
            raise uc.too_large()
        concurrency = await _container_get(request, GitConcurrency)
        if not concurrency.try_acquire(principal.user_id):
            return _busy()
        meta = PdfUploadMeta(
            sha256=sha256,
            file_name=name,
            pages=pages,
            source_commit=commit,
            built_at=built_at,
            client_name=principal.token.client_name or principal.token.name,
        )
        try:
            result = await _receive_pdf(request, uc, principal, project_id, doc_id, meta)
        finally:
            concurrency.release(principal.user_id)
    except GitHttpError as exc:
        return _json_error(exc)
    except IdentityError as exc:
        return _rate_limited(exc)
    except _BodyTooLargeError:
        return _artifact_error(uc.too_large())
    except ArtifactError as exc:
        return _artifact_error(exc)
    body = PdfUploadResponse(artifact=map_artifact(result.artifact), created=result.created)
    return JSONResponse(body.model_dump(mode="json"), status_code=201 if result.created else 200, headers=_NO_CACHE)


async def _writer(request: Request) -> GitPrincipal:
    principal = await authenticate(request)
    if not principal.has(TokenScope.git_write):
        raise GitHttpError(GitHttpErrorKind.scope_missing, GitDenial.pdf_scope)
    return principal


async def _receive_pdf(  # noqa: PLR0913 — состояние одного приёма
    request: Request,
    uc: UploadProjectPdfUC,
    principal: GitPrincipal,
    project_id: UUID,
    doc_id: str,
    meta: PdfUploadMeta,
) -> PdfUploadResult:
    spool = await _spool(request, uc.max_bytes)
    try:
        # SpooledTemporaryFile читается и перематывается как обычный двоичный файл.
        return await uc.execute(principal.actor, project_id, doc_id, cast("BinaryIO", spool), meta)
    finally:
        spool.close()


def _body_over(request: Request, limit: int) -> bool:
    length = request.headers.get("content-length")
    return length is not None and length.isdigit() and int(length) > limit


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
        raise GitHttpError(GitHttpErrorKind.not_found, GitDenial.not_found)
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
        if kind is GitService.receive_pack:
            await (await _container_get(request, ReceivePushUC)).advertise(access)
    except GitHttpError as exc:
        return git_error_response(exc)
    except IdentityError as exc:
        return _rate_limited(exc)
    except ProjectBusyError:
        return _text(409, project_busy_message())
    smart = await _smart_http(request)
    body = await smart.advertise(kind, access.git_dir, protocol=git_protocol(request.headers.get("git-protocol")))
    return Response(body, media_type=f"application/x-{kind.value}-advertisement", headers=_NO_CACHE)


def _too_large(request: Request) -> bool:
    length = request.headers.get("content-length")
    return length is not None and length.isdigit() and int(length) > settings.git_remote.max_push_bytes


class _BodyTooLargeError(Exception):
    pass


async def _spool(request: Request, limit: int | None = None) -> tempfile.SpooledTemporaryFile[bytes]:
    """Тело целиком до ответа: StreamingResponse сам слушает `receive` и съел бы куски тела у процесса git.

    До 8 МБ в памяти, дальше во временном файле; тело больше предела (по умолчанию размер push) отвергается сразу.
    """
    max_bytes = settings.git_remote.max_push_bytes if limit is None else limit
    spool: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MEMORY)  # noqa: SIM115
    size = 0
    try:
        async for chunk in request.stream():
            size += len(chunk)
            if size > max_bytes:
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
    """Отправка: проверки и снимок веб-правок до запуска git, политика путей в хуке pre-receive (раздел 7.3)."""
    try:
        access = await _authorize(request, repo, GitService.receive_pack)
    except GitHttpError as exc:
        return git_error_response(exc)
    except IdentityError as exc:
        return _rate_limited(exc)
    try:
        spool = await _spool(request)
    except _BodyTooLargeError:
        return _text(413, localized_error("Отправка слишком большая.", "The push is too large."))
    concurrency = await _container_get(request, GitConcurrency)
    user_id = access.principal.user_id
    if not concurrency.try_acquire(user_id):
        spool.close()
        return _busy()
    uc = await _container_get(request, ReceivePushUC)
    try:
        session = await uc.begin(access)
    except ProjectBusyError:
        spool.close()
        concurrency.release(user_id)
        return _text(409, project_busy_message())
    except BaseException:
        spool.close()
        concurrency.release(user_id)
        raise
    smart = await _smart_http(request)
    outcome: list[GitRpcOutcome] = []
    stream = smart.rpc(
        GitService.receive_pack,
        access.git_dir,
        _replay(spool),
        gzip=_gzip(request),
        protocol=git_protocol(request.headers.get("git-protocol")),
        extra_config=session.hook.extra_config,
        extra_env=session.hook.extra_env,
        outcome=outcome,
    )
    return StreamingResponse(
        _received(stream, uc, session, outcome, concurrency, user_id),
        media_type="application/x-git-receive-pack-result",
        headers=_NO_CACHE,
    )


async def _received(  # noqa: PLR0913 — состояние одного приёма
    stream: AsyncIterator[bytes],
    uc: ReceivePushUC,
    session: PushSession,
    outcome: list[GitRpcOutcome],
    concurrency: GitConcurrency,
    user_id: str,
) -> AsyncIterator[bytes]:
    try:
        async for chunk in stream:
            yield chunk
    finally:
        try:
            await asyncio.shield(uc.finish(session, outcome[0] if outcome else None))
        finally:
            concurrency.release(user_id)
