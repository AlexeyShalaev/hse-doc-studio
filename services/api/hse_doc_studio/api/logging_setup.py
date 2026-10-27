"""Настройка журнала процесса API.

Без явной настройки structlog печатает исключения через rich-трассировку с локальными переменными
каждого кадра (rich приходит транзитивно через fastapi[standard]). Пароль пакета и ключи доступа лежат
в локальных переменных функций, через которые проходит `logger.exception`, и попали бы в stdout и
`docker logs`. Поэтому трассировка выводится обычным текстом без локалей.
"""

from __future__ import annotations

import sys

import structlog


def configure_logging() -> None:
    """Те же процессоры, что у structlog по умолчанию, но трассировка простая и без значений переменных.

    Время местное и цвета только в терминале, как у structlog без настройки: в файле и `docker logs` нет ни UTC, ни
    escape-кодов.
    """
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
