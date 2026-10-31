"""Локальная Студия как клиент сервера Студии: вход по коду устройства, кто я, список проектов (раздел 7.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from hse_doc_studio.core.git_sync.secret import Secret


class StudioServerErrorCode:
    unreachable = "git_server_unreachable"
    not_studio = "git_server_not_studio"
    url_invalid = "git_server_url_invalid"
    unauthorized = "auth_failed"


class StudioServerError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class StudioServerTarget:
    """Куда идти: корень сервера (`https://host[:port]`) и PEM своего CA или закреплённого сертификата."""

    base_url: str
    ca_file: Path | None = None


@dataclass(frozen=True)
class DeviceGrant:
    device_code: str = field(repr=False)
    user_code: str
    verification_uri_complete: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class DeviceTokenReply:
    """Ответ опроса: токен (один раз) или код ожидания или отказа по RFC 8628."""

    access_token: Secret | None = None
    error: str | None = None
    expires_in: int | None = None
    scope: str = ""


@dataclass(frozen=True)
class StudioAccount:
    user_id: str
    name: str
    scopes: tuple[str, ...]
    expires_at: datetime | None


@dataclass(frozen=True)
class StudioProject:
    id: str
    name: str
    owner_name: str
    role: str
    can_push: bool
    clone_url: str
    updated_at: datetime | None


@dataclass(frozen=True)
class StudioProjectPage:
    items: tuple[StudioProject, ...]
    total: int
    limit: int
    offset: int


class IStudioServerClient(Protocol):
    async def info(self, target: StudioServerTarget) -> str:
        """Версия сервера; не Студия: `git_server_not_studio`, нет связи: `git_server_unreachable`."""
        ...

    async def device_code(self, target: StudioServerTarget, client_name: str) -> DeviceGrant: ...
    async def device_token(self, target: StudioServerTarget, device_code: str) -> DeviceTokenReply: ...
    async def whoami(self, target: StudioServerTarget, token: Secret) -> StudioAccount:
        """401: `StudioServerError(auth_failed)`."""
        ...

    async def projects(
        self, target: StudioServerTarget, token: Secret, *, q: str | None, limit: int, offset: int
    ) -> StudioProjectPage: ...
