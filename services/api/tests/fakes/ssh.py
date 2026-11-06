"""SSH на подмене: хост с заданным ключом, паролем и ответами на команды; хранилище доступов в памяти."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from hse_doc_studio.core.egress import EgressBlockedError, EgressBlockReason, EgressPurpose, EgressTarget
from hse_doc_studio.core.runner_install import (
    HostKey,
    SavedSshCredential,
    SshAuth,
    SshError,
    SshResult,
    SshTarget,
)

LINUX_RECON = "os=Linux\narch=x86_64\nuid=0\ndistro=ubuntu\nhas_docker=1\ndocker_ok=1\nsystemd=1\n"
HOST_KEY = HostKey("ssh-ed25519", "SHA256:abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG", "ssh-ed25519 AAAAC3Nza fake")


@dataclass
class Call:
    command: str
    stdin: str | None


@dataclass
class FakeHost:
    """Один удалённый хост: что он отвечает на команды и какие вызовы получил."""

    host_key: HostKey = HOST_KEY
    password: str | None = "right-password"
    recon: str = LINUX_RECON
    calls: list[Call] = field(default_factory=list)
    connects: list[tuple[str, SshTarget, HostKey]] = field(default_factory=list)
    fail_on: dict[str, SshResult] = field(default_factory=dict)
    inactive_for: int = 0
    unreachable: bool = False

    def handle(self, command: str, stdin: str | None) -> SshResult:
        self.calls.append(Call(command, stdin))
        for needle, result in self.fail_on.items():
            if needle in command:
                return result
        if command == "sh -s":
            return SshResult(0, self.recon, "")
        if command.startswith("systemctl is-active"):
            if self.inactive_for > 0:
                self.inactive_for -= 1
                return SshResult(3, "", "")
            return SshResult(0, "active\n", "")
        return SshResult(0, "ok\n", "")


class FakeSession:
    def __init__(self, host: FakeHost) -> None:
        self._host = host
        self.closed = False

    async def run(self, command: str, *, stdin: str | None = None, timeout: float = 120.0) -> SshResult:
        return self._host.handle(command, stdin)

    async def close(self) -> None:
        self.closed = True


class FakeConnector:
    def __init__(self, host: FakeHost | None = None) -> None:
        self.host = host or FakeHost()
        self.sessions: list[FakeSession] = []
        self.fetched: list[tuple[str, int]] = []

    async def fetch_host_key(self, address: str, port: int) -> HostKey:
        self.fetched.append((address, port))
        if self.host.unreachable:
            raise SshError("unreachable")
        return self.host.host_key

    async def connect(self, address: str, target: SshTarget, auth: SshAuth, expected: HostKey) -> FakeSession:
        self.host.connects.append((address, target, expected))
        if expected.fingerprint != self.host.host_key.fingerprint:
            raise SshError("host_key_mismatch")
        if auth.secret.reveal() != self.host.password and auth.kind.value == "password":
            raise SshError("auth_failed")
        session = FakeSession(self.host)
        self.sessions.append(session)
        return session


class FakeEgress:
    """Политика: имя -> адреса; частные и метаданные закрыты, как у настоящей политики."""

    def __init__(
        self, table: dict[str, tuple[str, ...]] | None = None, blocked: dict[str, EgressBlockReason] | None = None
    ) -> None:
        self.table = table or {"srv.example.org": ("203.0.113.10",)}
        self.blocked = blocked or {}
        self.asked: list[tuple[str, int | None, EgressPurpose]] = []

    async def authorize(
        self, host: str, port: int | None = None, *, purpose: EgressPurpose = EgressPurpose.user
    ) -> EgressTarget:
        self.asked.append((host, port, purpose))
        if host in self.blocked:
            raise EgressBlockedError(host, self.blocked[host])
        if host not in self.table:
            raise OSError("name not resolved")
        return EgressTarget(host, port, self.table[host])


class InMemorySshCredentials:
    def __init__(self) -> None:
        self.items: dict[str, tuple[SavedSshCredential, SshAuth]] = {}
        self.used: list[tuple[str, str | None]] = []

    async def add(self, credential: SavedSshCredential, auth: SshAuth) -> None:
        self.items[credential.id] = (credential, auth)

    async def list(self) -> list[SavedSshCredential]:
        return [c for c, _ in self.items.values()]

    async def get(self, credential_id: str) -> SavedSshCredential | None:
        found = self.items.get(credential_id)
        return found[0] if found else None

    async def get_auth(self, credential_id: str) -> SshAuth | None:
        found = self.items.get(credential_id)
        return found[1] if found else None

    async def delete(self, credential_id: str) -> bool:
        return self.items.pop(credential_id, None) is not None

    async def mark_used(self, credential_id: str, at: datetime, runner_name: str | None) -> None:
        self.used.append((credential_id, runner_name))


def find_call(host: FakeHost, needle: str) -> Call:
    return next(c for c in host.calls if needle in c.command)


__all__ = ["FakeConnector", "FakeEgress", "FakeHost", "InMemorySshCredentials", "find_call"]
