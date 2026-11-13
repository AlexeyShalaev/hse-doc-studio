"""HTTP-вид отказов маршрута подписания (docs/design/signing-route.md, 8.1): тело `{detail, code}` и поля рядом.

- `RouteInputError` (маршрут собран неверно) 400;
- `RouteConflictError` 409, кроме `not_participant`: не участнику маршрут не раскрывается (404 `not_found`);
  `doc_changed` и `doc_on_route` несут `docs`, `route_blocked` несёт `blockers`, `participant_not_skippable`
  несёт `reason` и `slots` (обязательные пары, которые мешают; пусто при других причинах), `resets_signatures`
  несёт `resets` (`[{doc_id, slot_id, name}]`: ЭП, которые сбросит правка меток даты, 14.6);
- `SigningKeyError` отказ подписи ключом Студии («Отправить и подписать», «Согласовать и подписать», «Подписать»,
  плашка из ключа): 400 (`passphrase_required`, `passphrase_invalid`, `sign_failed`), 409 (`key_not_found`) или 403
  (`server_keys_forbidden`, `forbidden` за чужой слот или другого подписанта на плашке). У `sign_failed` отправки
  поле `sent: true`: маршрут отправлен, не поставлена только подпись отправителя.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.core.signing_route.entities import (
    ParticipantNotSkippableError,
    ResetsSignaturesError,
    RouteConflictError,
    RouteInputError,
)
from hse_doc_studio.core.signing_route.readiness import Blocker, DocChangedError, RouteBlockedError
from hse_doc_studio.core.signing_route.repositories import DocumentOnRouteError


class SigningKeyError(Exception):
    """Подпись ключом Студии не удалась: код и статус для ответа, текст уже на языке интерфейса."""

    def __init__(self, status: int, code: str, message: str, *, extra: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        # Поля ответа рядом с `code` (например, `sent` у отказа подписи после отправки).
        self.extra = dict(extra or {})


def blocker_body(blocker: Blocker) -> dict[str, Any]:
    other = blocker.other_route
    return {
        "code": blocker.code.value,
        "doc_id": blocker.doc_id,
        "slot_id": blocker.slot_id,
        "participant_id": str(blocker.participant_id) if blocker.participant_id is not None else None,
        "other_route": None
        if other is None
        else {
            "id": str(other.route_id),
            "profile": {"id": other.profile_id, "name": dict(other.profile_name)},
            "status": other.status.value,
        },
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
    if isinstance(exc, ParticipantNotSkippableError):
        body["reason"] = exc.reason.value
        body["slots"] = [{"doc_id": pair.doc_id, "slot_id": pair.slot_id} for pair in exc.slots]
    if isinstance(exc, ResetsSignaturesError):
        body["resets"] = [{"doc_id": r.doc_id, "slot_id": r.slot_id, "name": r.name} for r in exc.resets]
    return JSONResponse(status_code=409, content=body)


async def _key_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, SigningKeyError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    return JSONResponse(status_code=exc.status, content={"detail": str(exc), "code": exc.code, **exc.extra})


def install_signing_route_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RouteInputError, _input_handler)
    app.add_exception_handler(RouteConflictError, _conflict_handler)
    app.add_exception_handler(SigningKeyError, _key_handler)
