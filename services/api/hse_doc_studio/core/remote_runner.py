"""Локальная Студия как личный раннер сервера: настройки, состояние и порты супервизора.

Только локальный режим. Пока переключатель выключен, Студия в сеть не ходит; включённая, она
сопрягается с аккаунтом на сервере (код устройства или токен регистрации) и собирает облачные
проекты своего хозяина локальным Docker тем же циклом, что консольный раннер.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit

# Пределы, которые проверяют и api, и супервизор: в настройках не может оказаться то, что не прошло бы запрос.
REMOTE_RUNNER_MAX_CONCURRENCY = 4
REMOTE_RUNNER_NAME_MAX = 128
# Имя ИИ-адреса раннера: то же правило, что у сервера (`ENDPOINT_NAME_RE` протокола).
AI_ENDPOINT_NAME_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,31}$"
# http разрешён только для сервера на этой же машине: токен раннера иначе шёл бы по сети открытым текстом.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_LOCAL_SUFFIXES = (".local", ".lan", ".internal", ".home.arpa", ".localhost")
# Управляемая Ollama и любой OpenAI-совместимый адрес; облачные виды (claude, openai) сервер вызывает сам.
_CLOUD_FLAVORS = {"ollama": "ollama", "openai_compat": "openai"}


class RemoteRunnerState(StrEnum):
    off = "off"
    unpaired = "unpaired"
    pairing = "pairing"
    connecting = "connecting"
    online = "online"
    paused = "paused"
    offline = "offline"
    revoked = "revoked"
    disabled = "disabled"
    error = "error"


class RemoteRunnerDocker(StrEnum):
    ok = "ok"
    missing = "missing"


class RemoteRunnerTexImage(StrEnum):
    ready = "ready"
    missing = "missing"


class RemoteRunnerErrorCode(StrEnum):
    url_invalid = "remote_runner_url_invalid"
    unreachable = "remote_runner_unreachable"
    disabled = "remote_runner_disabled"


class RemoteRunnerDetail(StrEnum):
    """Пояснение к состоянию для интерфейса (`detail_code`): почему Студия не собирает."""

    unreachable = "remote_runner_unreachable"
    pairing_denied = "pairing_denied"
    pairing_expired = "pairing_expired"
    token_rejected = "token_rejected"  # noqa: S105 — код причины, не секрет
    runner_disabled = "runner_disabled"
    runner_revoked = "runner_revoked"
    crashed = "crashed"


class RemoteRunnerError(Exception):
    """Отказ локального API облачных сборок: код из `RemoteRunnerErrorCode`, текст для журнала."""

    def __init__(self, code: RemoteRunnerErrorCode, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class RemoteAiEndpointChoice:
    """Локальный провайдер, открытый для облака под именем `name`."""

    name: str
    provider_id: str


@dataclass(frozen=True)
class RemoteRunnerSettings:
    enabled: bool = False
    server_url: str | None = None
    # None: имя компьютера.
    name: str | None = None
    concurrency: int = 1
    yield_to_local: bool = True
    ai_endpoints: tuple[RemoteAiEndpointChoice, ...] = ()


@dataclass(frozen=True)
class RemoteRunnerSettingsPatch:
    """Частичная правка настроек: None значит «не менять». Накладывается под замком супервизора,
    чтобы параллельное сопряжение или другой запрос не перетёрлись устаревшей копией."""

    enabled: bool | None = None
    server_url: str | None = None
    name: str | None = None
    concurrency: int | None = None
    yield_to_local: bool | None = None
    ai_endpoints: tuple[RemoteAiEndpointChoice, ...] | None = None

    def merged(self, current: RemoteRunnerSettings) -> RemoteRunnerSettings:
        return RemoteRunnerSettings(
            enabled=current.enabled if self.enabled is None else self.enabled,
            server_url=current.server_url if self.server_url is None else self.server_url,
            name=current.name if self.name is None else self.name,
            concurrency=current.concurrency if self.concurrency is None else self.concurrency,
            yield_to_local=current.yield_to_local if self.yield_to_local is None else self.yield_to_local,
            ai_endpoints=current.ai_endpoints if self.ai_endpoints is None else self.ai_endpoints,
        )


@dataclass(frozen=True)
class RemoteRunnerPairing:
    """Идущее сопряжение: код, который человек подтверждает на сайте."""

    user_code: str
    verification_uri_complete: str
    expires_at: datetime


@dataclass(frozen=True)
class RemoteAiEndpointInfo:
    """Открытый для облака адрес: имя и вид уходят на сервер, адрес и ключ остаются здесь."""

    name: str
    provider_id: str
    flavor: str
    url: str
    # Дошёл ли адрес до сервера (`/announce` с согласованной ретрансляцией). Пока нет, интерфейс
    # не выдаёт выбранные модели за уже открытые облаку: старый сервер или выключенные личные раннеры.
    announced: bool = False


@dataclass(frozen=True)
class RemoteRunnerStatusInfo:
    settings: RemoteRunnerSettings
    state: RemoteRunnerState
    paired: bool = False
    runner_id: str | None = None
    runner_name: str | None = None
    detail_code: str | None = None
    running_jobs: int = 0
    docker: RemoteRunnerDocker = RemoteRunnerDocker.ok
    tex_image: RemoteRunnerTexImage = RemoteRunnerTexImage.ready
    ai_endpoints: tuple[RemoteAiEndpointInfo, ...] = field(default=())
    pairing: RemoteRunnerPairing | None = None


class IRemoteRunnerSettingsStore(Protocol):
    async def load(self) -> RemoteRunnerSettings: ...
    async def save(self, settings: RemoteRunnerSettings) -> None: ...


class IRemoteRunnerSupervisor(Protocol):
    """Владеет циклом раннера в процессе локального api; все изменения настроек идут через него."""

    def status(self) -> RemoteRunnerStatusInfo: ...
    async def apply(self, settings: RemoteRunnerSettings) -> None: ...
    async def apply_patch(self, patch: RemoteRunnerSettingsPatch) -> None: ...
    async def start_pairing(self, server_url: str, name: str) -> None: ...
    async def cancel_pairing(self) -> None: ...
    async def use_token(self, server_url: str, token: str) -> None: ...
    async def unpair(self) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...


def normalize_server_url(raw: str) -> str:
    """Адрес сервера без хвостового `/`; https, http только для этой же машины.

    Путь допустим (сервер за префиксом прокси), запрос, фрагмент и логин в адресе нет: токен
    раннера уходит в заголовке, а не в адресе.
    """
    value = raw.strip()
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port_ok = parts.port is None or parts.port > 0
    except ValueError as exc:
        raise RemoteRunnerError(RemoteRunnerErrorCode.url_invalid, "server address is not a valid URL") from exc
    if not host or not port_ok or parts.query or parts.fragment or parts.username or parts.password:
        raise RemoteRunnerError(RemoteRunnerErrorCode.url_invalid, "server address must be scheme://host[:port][/path]")
    if parts.scheme == "https" or (parts.scheme == "http" and _is_loopback(host)):
        return value.rstrip("/")
    raise RemoteRunnerError(
        RemoteRunnerErrorCode.url_invalid, "server address must use https (http only for localhost)"
    )


def is_local_network_url(url: str) -> bool:
    """Адрес модели в своей сети: loopback, частная сеть или имя без публичного домена.

    Облаку открываются только такие адреса: модель в публичном интернете сервер вызовет и без раннера,
    а ретрансляция туда только прятала бы, кто ходит наружу. Имя не разрешается (без ввода-вывода):
    одно слово (`gpu`), `.local`, `.lan`, `.internal`, `.home.arpa` и `host.docker.internal` считаются своей сетью.
    """
    try:
        host = (urlsplit(url.strip()).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host in _LOOPBACK_HOSTS or "." not in host or host.endswith(_LOCAL_SUFFIXES)
    return address.is_loopback or address.is_private


def cloud_flavor(provider_type: str, base_url: str) -> str | None:
    """Вид ИИ-адреса для облака по локальному провайдеру; None, если провайдер облаку не открывается.

    Управляемая Ollama открывается всегда, OpenAI-совместимый адрес только в своей сети.
    """
    flavor = _CLOUD_FLAVORS.get(provider_type)
    if flavor is None or (provider_type != "ollama" and not is_local_network_url(base_url)):
        return None
    return flavor


def _is_loopback(host: str) -> bool:
    if host.lower() in _LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
