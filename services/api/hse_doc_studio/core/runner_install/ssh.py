"""Установка раннера по SSH: цель, способ входа, ключ хоста, сведения об ОС и порты соединения и хранилища.

Секреты (пароль, закрытый ключ, passphrase) живут только в `Secret`: он не печатается, не копируется и не
сериализуется. В сущностях ниже, которые уходят в ответы API и журнал, секретов нет вовсе.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from hse_doc_studio.core.git_sync.secret import Secret


class SshAuthKind(StrEnum):
    password = "password"  # noqa: S105 — имя способа входа, не секрет
    key = "key"


@dataclass(frozen=True, slots=True)
class SshTarget:
    host: str
    port: int
    username: str
    sudo: bool = False


@dataclass(frozen=True, slots=True)
class SshAuth:
    kind: SshAuthKind
    secret: Secret = field(repr=False)
    passphrase: Secret | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class HostKey:
    """Ключ хоста: отпечаток показывается админу, открытый ключ закрепляет соединение (известен до входа)."""

    key_type: str
    fingerprint: str
    public_key: str


@dataclass(frozen=True, slots=True)
class RemoteSystem:
    os: str
    arch: str
    distro: str
    has_docker: bool
    docker_usable: bool
    has_systemd: bool
    is_root: bool


@dataclass(frozen=True, slots=True)
class SshResult:
    code: int
    stdout: str
    stderr: str


class SshError(Exception):
    """Соединение или команда не удались. `code` переводится, `detail` очищен от секретов."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


class ISshSession(Protocol):
    async def run(self, command: str, *, stdin: str | None = None, timeout: float = 120.0) -> SshResult: ...

    async def close(self) -> None: ...


class ISshConnector(Protocol):
    async def fetch_host_key(self, address: str, port: int) -> HostKey:
        """Только рукопожатие: учётные данные не отправляются."""
        ...

    async def connect(self, address: str, target: SshTarget, auth: SshAuth, expected: HostKey) -> ISshSession:
        """Вход на хост по IP; ключ хоста сверяется с `expected` до отправки учётных данных (host_key_mismatch)."""
        ...


@dataclass(frozen=True, slots=True)
class SavedSshCredential:
    """Запись о сохранённом доступе: факт наличия и метаданные цели, значения секрета здесь нет."""

    id: str
    label: str
    host: str
    port: int
    username: str
    sudo: bool
    auth_kind: SshAuthKind
    host_key: HostKey
    created_by: str
    created_at: datetime
    last_used_at: datetime | None = None
    runner_name: str | None = None


class ISshCredentialRepository(Protocol):
    async def add(self, credential: SavedSshCredential, auth: SshAuth) -> None: ...

    async def list(self) -> list[SavedSshCredential]: ...

    async def get(self, credential_id: str) -> SavedSshCredential | None: ...

    async def get_auth(self, credential_id: str) -> SshAuth | None:
        """Расшифрованные данные для входа; вызывается только установкой в один клик."""
        ...

    async def delete(self, credential_id: str) -> bool: ...

    async def mark_used(self, credential_id: str, at: datetime, runner_name: str | None) -> None: ...
