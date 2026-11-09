"""HTTP-вид отказов маршрута подписания (docs/design/signing-route.md, 8.1): тело `{detail, code}` и поля рядом.

- `RouteInputError` (маршрут собран неверно) 400;
- `RouteConflictError` 409, кроме `not_participant`: не участнику маршрут не раскрывается (404 `not_found`);
  `doc_changed` и `doc_on_route` несут `docs`, `route_blocked` несёт `blockers`;
- `SigningKeyError` отказ подписи ключом при «Отправить и подписать»: 400 (`passphrase_required`,
  `sign_failed`) или 403 (`forbidden`, чужой слот).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.core.signing_route.entities import RouteConflictError, RouteInputError
from hse_doc_studio.core.signing_route.readiness import Blocker, DocChangedError, RouteBlockedError
from hse_doc_studio.core.signing_route.repositories import DocumentOnRouteError


class SigningKeyError(Exception):
    """Подпись ключом Студии не удалась: код и статус для ответа, текст уже на языке интерфейса."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def blocker_body(blocker: Blocker) -> dict[str, Any]:
    return {
        "code": blocker.code.value,
        "doc_id": blocker.doc_id,
        "slot_id": blocker.slot_id,
        "participant_id": str(blocker.participant_id) if blocker.participant_id is not None else None,
    }


async def _input_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RouteInputError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    return JSONResponse(status_code=400, content={"detail": str(exc), "code": exc.code})


async def _conflict_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RouteConflictError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    if exc.code == "not_participant":
        return JSONResponse(status_code=404, content={"detail": str(exc), "code": "not_found"})
    body: dict[str, Any] = {"detail": str(exc), "code": exc.code}
    if isinstance(exc, DocChangedError | DocumentOnRouteError):
        body["docs"] = list(exc.doc_ids)
    if isinstance(exc, RouteBlockedError):
        body["blockers"] = [blocker_body(b) for b in exc.blockers]
    return JSONResponse(status_code=409, content=body)


async def _key_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, SigningKeyError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    return JSONResponse(status_code=exc.status, content={"detail": str(exc), "code": exc.code})


def install_signing_route_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RouteInputError, _input_handler)
    app.add_exception_handler(RouteConflictError, _conflict_handler)
    app.add_exception_handler(SigningKeyError, _key_handler)
