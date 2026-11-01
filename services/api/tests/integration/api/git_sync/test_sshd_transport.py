"""Настоящий ssh: непривилегированный sshd на 127.0.0.1 и настоящий ssh-keyscan.

Проверяет то, чего не видно на подставном ssh: что набор параметров принимает сам OpenSSH, что
подтверждённый ключ хоста пускает дальше, а подмена ключа останавливает до передачи данных.
Тест пропускается, если в системе нет sshd или ssh-keygen.
"""

from __future__ import annotations

import getpass
import os
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.entities import (
    CredentialStatus,
    GitCredential,
    GitCredentialKind,
    RemoteTarget,
    ScannedHostKey,
)
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.host_keys import key_fingerprint
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.infra.git_sync.credential_repository import JsonGitCredentialRepository
from hse_doc_studio.infra.git_sync.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.git_sync.git_remote_runner import GitRemoteRunner
from hse_doc_studio.infra.git_sync.git_transport import GitTransport
from hse_doc_studio.infra.git_sync.host_key_scanner import SshKeyscanScanner
from hse_doc_studio.infra.git_sync.key_store import KeyFileStore
from hse_doc_studio.infra.git_sync.known_hosts import FileKnownHostsStore
from hse_doc_studio.infra.git_sync.ssh_keys import Ed25519KeyGenerator
from hse_doc_studio.infra.vcs.git_env import base_git_env
from hse_doc_studio.use_cases.git_sync.hosts import TrustHostInput, TrustHostUC

from tests.fixtures.git_remote import make_bare_remote, seed_remote

pytestmark = pytest.mark.requires_sshd

_SSHD_NAMES = ("sshd", "/usr/sbin/sshd")


def _find_sshd() -> str | None:
    for name in _SSHD_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


@dataclass
class Sshd:
    port: int
    repo_path: Path
    authorized_keys: Path
    host_fingerprint: str


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def sshd(tmp_path: Path) -> Iterator[Sshd]:
    binary = _find_sshd()
    if binary is None or os.name != "posix" or shutil.which("ssh-keygen") is None or shutil.which("ssh") is None:
        pytest.skip("sshd, ssh or ssh-keygen is not installed")
    root = tmp_path / "sshd"
    root.mkdir(mode=0o700)
    host_key = root / "host_ed25519"
    subprocess.run(  # noqa: S603 — фиксированная команда подготовки теста
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(host_key)],  # noqa: S607
        check=True,
    )
    authorized = root / "authorized_keys"
    authorized.write_text("")
    authorized.chmod(0o600)
    port = _free_port()
    config = root / "sshd_config"
    config.write_text(
        f"Port {port}\nListenAddress 127.0.0.1\nHostKey {host_key}\nPidFile {root / 'sshd.pid'}\n"
        f"AuthorizedKeysFile {authorized}\nStrictModes no\nUsePAM no\nPasswordAuthentication no\n"
        f"KbdInteractiveAuthentication no\nPubkeyAuthentication yes\nAllowUsers {getpass.getuser()}\n"
        f"SetEnv PATH={base_git_env().get('PATH', os.defpath)}\n"
    )
    process = subprocess.Popen(  # noqa: S603 — sshd для теста на свободном порту
        [binary, "-f", str(config), "-D", "-e"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                if process.poll() is not None:
                    pytest.skip("sshd could not start without privileges")
                time.sleep(0.05)
        else:
            pytest.skip("sshd did not start in time")
        fingerprint = subprocess.run(  # noqa: S603
            ["ssh-keygen", "-lf", f"{host_key}.pub"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()[1]
        remote = make_bare_remote(root / "repo.git")
        seed_remote(remote, {"README.md": "# course\n"})
        yield Sshd(port, remote.path, authorized, fingerprint)
    finally:
        process.terminate()
        process.wait(timeout=10)


@dataclass
class Stack:
    transport: GitTransport
    known_hosts: FileKnownHostsStore
    trust: TrustHostUC
    credentials: JsonGitCredentialRepository
    server: Sshd

    async def add_key(self, *, authorize: bool) -> UUID:
        generated = Ed25519KeyGenerator().generate("hse-test")
        credential = GitCredential(
            id=uuid4(),
            kind=GitCredentialKind.ssh_key,
            label="Ключ теста",
            host="127.0.0.1",
            username="git",
            status=CredentialStatus.unverified,
            created_at=datetime(2026, 10, 26, tzinfo=timezone.utc),
            public_key=generated.public_key,
            fingerprint_sha256=generated.fingerprint_sha256,
            port=self.server.port,
        )
        await self.credentials.add(credential, generated.private_key)
        if authorize:
            self.server.authorized_keys.write_text(generated.public_key + "\n")
        return credential.id

    def target(self, credential_id: UUID | None) -> RemoteTarget:
        url = f"ssh://{getpass.getuser()}@127.0.0.1:{self.server.port}{self.server.repo_path}"
        return RemoteTarget(parse_remote_url(url), credential_id=credential_id)


@pytest.fixture
def stack(tmp_path: Path, sshd: Sshd) -> Stack:
    data = tmp_path / "data"
    credentials = JsonGitCredentialRepository(data, FernetSecretCipher(KeyFileStore(data / "secrets" / "k.json")))
    config = GitConfig()
    known_hosts = FileKnownHostsStore(data)
    scanner = SshKeyscanScanner(config)
    runner = GitRemoteRunner(config, credentials, local_mode=True, known_hosts=known_hosts, scanner=scanner)
    return Stack(GitTransport(runner, config), known_hosts, TrustHostUC(known_hosts, scanner), credentials, sshd)


async def test__ssh_remote__unknown_then_trusted_then_reads_the_repository(stack: Stack) -> None:
    credential = await stack.add_key(authorize=True)

    unknown = await stack.transport.probe(stack.target(credential))
    assert unknown.error is not None
    assert unknown.error.code is GitErrorCode.host_key_unknown
    assert [key.fingerprint_sha256 for key in unknown.host_keys] == [stack.server.host_fingerprint]

    await stack.trust.execute(TrustHostInput("127.0.0.1", stack.server.port, unknown.host_keys[0].fingerprint_sha256))
    probe = await stack.transport.probe(stack.target(credential))

    assert probe.ok, probe.error
    assert probe.branches == ("main",)
    assert probe.empty is False


async def test__ssh_remote__key_the_server_does_not_know__auth_failed(stack: Stack) -> None:
    credential = await stack.add_key(authorize=False)
    await stack.trust.execute(TrustHostInput("127.0.0.1", stack.server.port, stack.server.host_fingerprint))

    probe = await stack.transport.probe(stack.target(credential))

    assert probe.error is not None
    assert probe.error.code is GitErrorCode.auth_failed


async def test__ssh_remote__server_key_differs_from_the_trusted_one__host_key_changed(stack: Stack) -> None:
    credential = await stack.add_key(authorize=True)
    impostor = Ed25519KeyGenerator().generate("impostor").public_key.split()[1]
    await stack.known_hosts.trust(
        "127.0.0.1", stack.server.port, [ScannedHostKey("ssh-ed25519", impostor, key_fingerprint(impostor))]
    )

    probe = await stack.transport.probe(stack.target(credential))

    assert probe.error is not None
    assert probe.error.code is GitErrorCode.host_key_changed
