"""Локальная Студия как клиент сервера Студии: вход по коду устройства, кто я, список проектов (раздел 7.5)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from hse_doc_studio.core.git_sync.entities import GitCredential
from hse_doc_studio.core.git_sync.secret import Secret

# Происхождение доступа, полученного входом на сервер Студии по коду устройства.
DEVICE_ORIGIN = "device"


class StudioServerErrorCode:
    unreachable = "git_server_unreachable"
    not_studio = "git_server_not_studio"
    url_invalid = "git_server_url_invalid"
    unauthorized = "auth_failed"
    # Выгрузка PDF (docs/design/local-sync.md, P2): ответы сервера, по которым локальная Студия подбирает совет.
    pdf_forbidden = "pdf_forbidden"
    pdf_scope_missing = "pdf_scope_missing"
    pdf_too_large = "pdf_too_large"
    pdf_rejected = "pdf_rejected"
    pdf_unknown_document = "pdf_unknown_document"
    pdf_unsupported = "pdf_unsupported"


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

    async def upload_pdf(self, target: StudioServerTarget, token: Secret, upload: PdfUpload) -> PdfUploadReply:
        """Отказы сервера приходят как `StudioServerError` с кодами `pdf_*`; 401: `auth_failed`."""
        ...


@dataclass(frozen=True)
class PdfUpload:
    """Что выгружается: файл на диске и подпись к нему (всё, кроме `sha256`, необязательно)."""

    project_id: UUID
    doc_id: str
    path: Path
    sha256: str
    size: int
    name: str | None = None
    pages: int | None = None
    source_commit: str | None = None
    built_at: datetime | None = None


@dataclass(frozen=True)
class PdfUploadReply:
    artifact_id: str
    created: bool
    size: int


_CLONE_PATH_RE = re.compile(r"/git/(?P<id>[0-9a-fA-F-]{36})\.git/?$")


def studio_project_id(remote_url: str) -> UUID | None:
    """Идентификатор проекта на сервере Студии по адресу клонирования `<сервер>/git/<id>.git`; иначе None."""
    try:
        path = urlsplit(remote_url).path
    except ValueError:
        return None
    found = _CLONE_PATH_RE.search(path)
    if found is None:
        return None
    try:
        return UUID(found.group("id"))
    except ValueError:
        return None


def is_studio_remote(credential: GitCredential | None, remote_url: str) -> bool:
    """Проект подключён к серверу Студии: вход получен по коду устройства, а адрес это `<сервер>/git/<id>.git`."""
    return credential is not None and credential.origin == DEVICE_ORIGIN and studio_project_id(remote_url) is not None
