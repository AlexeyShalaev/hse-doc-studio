"""Недоступная база как `503 db_unavailable`: клиент отличает «база лежит, повторите» от ошибки в коде.

Сбой соединения, таймаут пула и обрыв драйвера без обработчика дали бы text/plain 500 с трейсбеком на
каждый запрос. Остальные ошибки БД (нарушение ограничений, неверный SQL) остаются 500: это ошибки кода.
Ставится только в серверном режиме: в локальном sqlalchemy может не быть, а ConnectionError там чужой.
"""

from __future__ import annotations

import traceback

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)

DB_UNAVAILABLE_CODE = "db_unavailable"
RETRY_AFTER_S = 5
_STATUS = 503
_DB_MODULES = ("/asyncpg/", "/sqlalchemy/")


def _raised_by_db_driver(exc: BaseException) -> bool:
    """Общие ConnectionError и TimeoutError считаем сбоем БД, только если их подняли asyncpg или sqlalchemy."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if any(any(m in frame.filename for m in _DB_MODULES) for frame in traceback.extract_tb(current.__traceback__)):
            return True
        current = current.__cause__ or current.__context__
    return False


async def _db_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError  # noqa: PLC0415
    from sqlalchemy.exc import TimeoutError as PoolTimeoutError  # noqa: PLC0415

    db_error = isinstance(exc, (OperationalError, InterfaceError, PoolTimeoutError)) or (
        isinstance(exc, DBAPIError) and exc.connection_invalidated
    )
    if not db_error and not _raised_by_db_driver(exc):
        raise exc  # чужой ConnectionError или TimeoutError: обычная 500
    logger.warning("db_unavailable", path=request.url.path, exc_type=type(exc).__name__)
    return JSONResponse(
        status_code=_STATUS,
        content={"detail": "Database is unavailable, retry later", "code": DB_UNAVAILABLE_CODE},
        headers={"Retry-After": str(RETRY_AFTER_S)},
    )


def install_db_error_handlers(app: FastAPI) -> None:
    from sqlalchemy.exc import InterfaceError, OperationalError  # noqa: PLC0415
    from sqlalchemy.exc import TimeoutError as PoolTimeoutError  # noqa: PLC0415

    for exc_type in (OperationalError, InterfaceError, PoolTimeoutError, ConnectionError, TimeoutError):
        app.add_exception_handler(exc_type, _db_unavailable_handler)
