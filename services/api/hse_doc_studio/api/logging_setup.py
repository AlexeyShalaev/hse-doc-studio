"""Настройка журнала процесса API.

Без явной настройки structlog печатает исключения через rich-трассировку с локальными переменными
каждого кадра (rich приходит транзитивно через fastapi[standard]). Пароль пакета и ключи доступа лежат
в локальных переменных функций, через которые проходит `logger.exception`, и попали бы в stdout и
`docker logs`. Поэтому трассировка выводится обычным текстом без локалей.
"""

from __future__ import annotations

import logging
import re
import sys

import structlog

# Токен ссылки доступа в адресе (`/s/hsl_…`, `/api/v1/links/hsl_…`) в журнал не попадает (T2).
_LINK_TOKEN = re.compile(r"hsl_[A-Za-z0-9_\-]+")
LINK_TOKEN_MASK = "hsl_****"  # noqa: S105 — маска в журнале, не секрет


def mask_link_tokens(text: str) -> str:
    return _LINK_TOKEN.sub(LINK_TOKEN_MASK, text)


class LinkTokenMaskFilter(logging.Filter):
    """Маскирует токены ссылок в записях журнала доступа uvicorn (путь лежит в `args`)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(mask_link_tokens(a) if isinstance(a, str) else a for a in record.args)
        if isinstance(record.msg, str):
            record.msg = mask_link_tokens(record.msg)
        return True


def install_access_log_mask() -> None:
    """Фильтр на журнал доступа uvicorn: путь запроса с токеном ссылки пишется как `hsl_****`."""
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, LinkTokenMaskFilter) for f in access.filters):
        access.addFilter(LinkTokenMaskFilter())


def configure_logging(*, use_json: bool = False) -> None:
    """Те же процессоры, что у structlog по умолчанию, но трассировка простая и без значений переменных.

    Время местное и цвета только в терминале, как у structlog без настройки: в файле и `docker logs` нет ни UTC, ни
    escape-кодов.

    ``use_json`` (HSE_STUDIO__LOGGING__USE_JSON) включает одну JSON-строку на запись для сборщиков логов; исключение
    в ней тоже обычным текстом без локалей.
    """
    install_access_log_mask()
    if use_json:
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.JSONRenderer(),
            ]
        )
        return
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            structlog.dev.ConsoleRenderer(
                colors=sys.stdout.isatty(), exception_formatter=structlog.dev.plain_traceback
            ),
        ]
    )
