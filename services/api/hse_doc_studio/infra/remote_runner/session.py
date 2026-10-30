"""Шов между супервизором и циклом раннера: супервизор не знает ни контейнера раннера, ни протокола.

Сессия это один запуск цикла с одними настройками. Смена настроек, отзыв или выход из приложения
заканчивают сессию; супервизор открывает новую, если переключатель включён.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from hse_doc_studio.core.remote_runner import RemoteAiEndpointChoice


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
    # Сервер отказал по другой причине (предел раннеров, несовместимый протокол): код сервера в detail.
    refused = "runner_refused"


class RunnerSessionFatal(Exception):  # noqa: N818 — исход сессии, а не сбой кода
    """Сессия не может продолжаться: повтор с теми же учётными данными ничего не даст."""

    def __init__(self, code: SessionFatalCode, detail: str = "") -> None:
        super().__init__(detail or code.value)
        self.code = code
        self.detail = detail or code.value


@dataclass(frozen=True)
class LocalAiEndpoint:
    """ИИ-адрес для облака: имя и вид уходят на сервер, адрес и ключ остаются в процессе Студии."""

    name: str
    provider_id: str
    # Адрес для запроса из этого процесса (в контейнере loopback переписан на шлюз хоста).
    base_url: str
    # Адрес, как его ввёл человек: его и показываем.
    display_url: str
    flavor: str
    api_key: Callable[[], str | None] = field(default=lambda: None, compare=False)


@dataclass(frozen=True)
class RunnerSessionSpec:
    server_url: str
    # Токен регистрации, пока личности нет; после регистрации личность лежит в data_dir/identity.json.
    registration_token: str | None
    name: str
    concurrency: int
    data_dir: Path
    tex_image: str
    # Без Docker или без образа тег tex не объявляется: сборки LaTeX тогда идут на общие раннеры.
    tex_available: bool
    # False: сейчас сборки не брать (идёт локальная сборка или нет Docker).
    gate: Callable[[], bool] = field(default=lambda: True, compare=False)
    ai_endpoints: tuple[LocalAiEndpoint, ...] = ()


class IRunnerEnvironment(Protocol):
    """Что супервизор узнаёт о машине: Docker, образ TeX и занятость локальных сборок."""

    async def docker_available(self) -> bool: ...
    async def tex_image(self) -> str: ...
    async def image_present(self, image: str) -> bool: ...
    def local_busy(self) -> bool: ...


class IRunnerSessionListener(Protocol):
    def on_session_state(self, state: SessionState) -> None: ...
    def on_registered(self) -> None: ...


class IRunnerSession(Protocol):
    @property
    def running_jobs(self) -> int: ...

    async def run(self) -> None:
        """До остановки; `RunnerSessionFatal`, когда сервер отказал окончательно."""
        ...

    def request_stop(self) -> None: ...

    async def reannounce(self, ai_endpoints: tuple[LocalAiEndpoint, ...]) -> None:
        """Сообщить серверу новый список ИИ-адресов без перезапуска цикла."""
        ...


AiEndpointResolver = Callable[[tuple[RemoteAiEndpointChoice, ...]], Awaitable[tuple[LocalAiEndpoint, ...]]]

RunnerSessionFactory = Callable[
    [RunnerSessionSpec, IRunnerSessionListener], AbstractAsyncContextManager[IRunnerSession]
]
