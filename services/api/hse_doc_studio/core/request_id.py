"""Сквозной идентификатор текущего HTTP-запроса; наследуется задачами, созданными внутри запроса.

Ставит его `RequestIdMiddleware` (api), читают слои ниже: журнал писем связывает строку с логами api.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_request_id: ContextVar[str | None] = ContextVar("hse_request_id", default=None)


def current_request_id() -> str | None:
    """Идентификатор запроса или None вне запроса (фоновая задача лидера, старт сервера)."""
    return _request_id.get()


def set_request_id(value: str | None) -> Token[str | None]:
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)
