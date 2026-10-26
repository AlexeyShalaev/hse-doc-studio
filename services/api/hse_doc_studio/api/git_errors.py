"""HTTP-вид ошибок Git-синхронизации: тело `{detail, code, ...}` и статус по коду.

Статус зависит от того, кто должен что-то сделать. Неверный ввод даёт 422. Состояние, которое
исправляет пользователь (нет профиля, занята синхронизация, нужен доступ), даёт 409. Отказ
удалённой стороны (нет связи, не пустили) даёт 502: 401 и 403 намеренно не используются, чтобы
клиент не принял отказ GitHub за выход из Студии. Новый код ошибки обязан попасть в таблицу:
тест сверяет её со всем перечислением.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError

_INPUT = 422
_STATE = 409
_UPSTREAM = 502
_MISSING = 404
_UNAVAILABLE = 503

GIT_ERROR_STATUS: Mapping[GitErrorCode, int] = {
    GitErrorCode.url_invalid: _INPUT,
    GitErrorCode.url_scheme_forbidden: _INPUT,
    GitErrorCode.credential_invalid: _INPUT,
    GitErrorCode.invalid_resolution: _INPUT,
    GitErrorCode.unresolved_conflicts: _INPUT,
    GitErrorCode.unresolved_markers: _INPUT,
    GitErrorCode.bundle_invalid: _INPUT,
    GitErrorCode.bundle_password_required: _INPUT,
    GitErrorCode.bundle_password_wrong: _INPUT,
    GitErrorCode.bundle_prerequisites_missing: _INPUT,
    GitErrorCode.credential_in_use: _STATE,
    GitErrorCode.credential_host_mismatch: _STATE,
    GitErrorCode.credentials_missing: _STATE,
    GitErrorCode.secrets_unavailable: _STATE,
    GitErrorCode.store_untrusted: _STATE,
    GitErrorCode.profile_required: _STATE,
    GitErrorCode.host_key_changed: _STATE,
    GitErrorCode.branch_missing: _STATE,
    GitErrorCode.remote_exists: _STATE,
    GitErrorCode.not_a_studio_project: _STATE,
    GitErrorCode.unrelated_histories: _STATE,
    GitErrorCode.project_exists: _STATE,
    GitErrorCode.folder_not_empty: _STATE,
    GitErrorCode.sync_busy: _STATE,
    GitErrorCode.sync_busy_build: _STATE,
    GitErrorCode.off_branch: _STATE,
    GitErrorCode.sync_incomplete: _STATE,
    GitErrorCode.plan_outdated: _STATE,
    GitErrorCode.remote_schema_newer: _STATE,
    GitErrorCode.operation_not_cancellable: _STATE,
    GitErrorCode.no_conflicts: _MISSING,
    GitErrorCode.auth_failed: _UPSTREAM,
    GitErrorCode.forbidden_write: _UPSTREAM,
    GitErrorCode.sso_required: _UPSTREAM,
    GitErrorCode.not_found_or_no_access: _UPSTREAM,
    GitErrorCode.rate_limited: _UPSTREAM,
    GitErrorCode.host_key_unknown: _UPSTREAM,
    GitErrorCode.offline: _UPSTREAM,
    GitErrorCode.tls_error: _UPSTREAM,
    GitErrorCode.timeout: _UPSTREAM,
    GitErrorCode.remote_moved: _UPSTREAM,
    GitErrorCode.protected_branch: _UPSTREAM,
    GitErrorCode.large_file: _UPSTREAM,
    GitErrorCode.workflow_scope_missing: _UPSTREAM,
    GitErrorCode.email_privacy: _UPSTREAM,
    GitErrorCode.git_error: _UPSTREAM,
    GitErrorCode.ssh_unavailable: _UNAVAILABLE,
    GitErrorCode.git_unavailable: _UNAVAILABLE,
}

# Запросы, в теле которых лежит секрет: эхо входных данных в ответе проверки (`input`) вернуло бы токен.
_SECRET_BODY_PREFIXES = ("/api/v1/git/credentials",)


def git_error_body(exc: GitSyncError) -> dict[str, object]:
    return {"detail": exc.detail, "code": exc.code.value, **jsonable_encoder(exc.ctx)}


async def _git_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, GitSyncError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    return JSONResponse(status_code=GIT_ERROR_STATUS[exc.code], content=git_error_body(exc))


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    errors = exc.errors()
    if request.url.path.startswith(_SECRET_BODY_PREFIXES):
        errors = [{key: value for key, value in error.items() if key not in {"input", "ctx"}} for error in errors]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


def install_git_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(GitSyncError, _git_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
