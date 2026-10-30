"""Шов между супервизором и циклом раннера: супервизор не знает ни контейнера раннера, ни протокола.

Сессия это один запуск цикла с одними настройками. Смена настроек, отзыв или выход из приложения
заканчивают сессию; супервизор открывает новую, если переключатель включён.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class SessionState(StrEnum):
    """Что цикл сообщает о связи с сервером."""

    connecting = "connecting"
    online = "online"
    paused = "paused"
    offline = "offline"


class SessionFatalCode(StrEnum):
    # Токен раннера отвергнут (отозван на сайте, сменён) или токен регистрации не годится.
    unauthorized = "runner_unauthorized"
    # Хозяин отключён или личные раннеры выключены в установке.
    disabled = "runner_disabled"


class RunnerSessionFatal(Exception):  # noqa: N818 — исход сессии, а не сбой кода
    """Сессия не может продолжаться: повтор с теми же учётными данными ничего не даст."""

    def __init__(self, code: SessionFatalCode, detail: str = "") -> None:
        super().__init__(detail or code.value)
        self.code = code


@dataclass(frozen=True)
class RunnerSessionSpec:
    server_url: str
    # Токен регистрации, пока личности нет; после регистрации личность лежит в data_dir/identity.json.
    registration_token: str | None
    name: str
    concurrency: int
    data_dir: Path


class IRunnerSessionListener(Protocol):
    def on_session_state(self, state: SessionState) -> None: ...
    def on_registered(self, runner_id: str) -> None: ...


class IRunnerSession(Protocol):
    @property
    def running_jobs(self) -> int: ...

    async def run(self) -> None:
        """До остановки; `RunnerSessionFatal`, когда сервер отказал окончательно."""
        ...

    def request_stop(self) -> None: ...


RunnerSessionFactory = Callable[
    [RunnerSessionSpec, IRunnerSessionListener], AbstractAsyncContextManager[IRunnerSession]
]
