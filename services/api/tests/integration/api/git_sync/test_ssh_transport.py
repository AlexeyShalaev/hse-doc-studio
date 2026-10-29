"""ssh-адреса через настоящий git и подставной ssh (`fake_ssh`): параметры, ключ на диске, ключи хоста, отмена."""

from __future__ import annotations

import asyncio
import os
import time
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
from hse_doc_studio.infra.git_sync.git_capabilities import GitCapabilities
from hse_doc_studio.infra.git_sync.git_remote_runner import GitRemoteRunner
from hse_doc_studio.infra.git_sync.git_transport import GitTransport
from hse_doc_studio.infra.git_sync.key_store import KeyFileStore
from hse_doc_studio.infra.git_sync.known_hosts import FileKnownHostsStore
from hse_doc_studio.infra.git_sync.ssh_keys import Ed25519KeyGenerator

from tests.fixtures.git_remote import FakeSsh
from tests.unit.core.git_sync.test_host_keys import GITHUB_ED25519

pytestmark = pytest.mark.skipif(os.name != "posix", reason="ssh keys and process groups are posix-only")

_OTHER = "AAAAC3NzaC1lZDI1NTE5AAAAIGk1Zq6mYQdkYxjqU4tUq0h8Y1m7X6uQ0mHk2m9o3a4B"
_HOST = "git.example.org"


class _Scanner:
    def __init__(self) -> None:
        self.keys = [ScannedHostKey("ssh-ed25519", GITHUB_ED25519, key_fingerprint(GITHUB_ED25519))]

    async def scan(self, host: str, port: int | None) -> list[ScannedHostKey]:
        return self.keys


@dataclass
class SshStack:
    transport: GitTransport
    known_hosts: FileKnownHostsStore
    scanner: _Scanner
    credentials: JsonGitCredentialRepository
    ssh: FakeSsh
    config: GitConfig

    async def add_key(self, *, host: str = _HOST, port: int | None = None) -> UUID:
        generated = Ed25519KeyGenerator().generate("test")
        credential = GitCredential(
            id=uuid4(),
            kind=GitCredentialKind.ssh_key,
            label="Тестовый ключ",
            host=host,
            username="git",
            status=CredentialStatus.unverified,
            created_at=datetime(2026, 10, 26, tzinfo=timezone.utc),
            public_key=generated.public_key,
            fingerprint_sha256=generated.fingerprint_sha256,
            port=port,
        )
        await self.credentials.add(credential, generated.private_key)
        return credential.id

    async def trust(self, host: str = _HOST, port: int | None = None, blob: str = GITHUB_ED25519) -> None:
        await self.known_hosts.trust(host, port, [ScannedHostKey("ssh-ed25519", blob, key_fingerprint(blob))])


@pytest.fixture
def ssh_stack(tmp_path: Path, fake_ssh: FakeSsh) -> SshStack:
    data = tmp_path / "data"
    credentials = JsonGitCredentialRepository(data, FernetSecretCipher(KeyFileStore(data / "secrets" / "k.json")))
    config = GitConfig(ssh_binary=str(fake_ssh.path), probe_timeout_s=20.0)
    known_hosts = FileKnownHostsStore(data)
    scanner = _Scanner()
    runner = GitRemoteRunner(
        config,
        credentials,
        local_mode=True,
        capabilities=GitCapabilities(ssh_binary=str(fake_ssh.path)),
        known_hosts=known_hosts,
        scanner=scanner,
    )
    return SshStack(GitTransport(runner, config), known_hosts, scanner, credentials, fake_ssh, config)


def _target(credential_id: UUID | None, raw: str = f"ssh://git@{_HOST}/hse/course.git") -> RemoteTarget:
    return RemoteTarget(parse_remote_url(raw), credential_id=credential_id)


def _ssh_argv(call: dict[str, object]) -> list[str]:
    argv = call["argv"]
    assert isinstance(argv, list)
    return [str(part) for part in argv]


def _option(argv: list[str], name: str) -> str | None:
    prefix = f"{name}="
    return next((part.removeprefix(prefix) for part in argv if part.startswith(prefix)), None)


async def test__probe__unknown_host__host_key_unknown_with_fingerprints_and_no_ssh(ssh_stack: SshStack) -> None:
    probe = await ssh_stack.transport.probe(_target(await ssh_stack.add_key()))

    assert probe.ok is False
    assert probe.error is not None
    assert probe.error.code is GitErrorCode.host_key_unknown
    assert [(k.type, k.fingerprint_sha256) for k in probe.host_keys] == [
        ("ssh-ed25519", key_fingerprint(GITHUB_ED25519))
    ]
    assert ssh_stack.ssh.calls() == []


async def test__probe__trusted_host__ssh_gets_the_hardened_options_and_a_private_key_that_is_removed(
    ssh_stack: SshStack,
) -> None:
    await ssh_stack.trust()
    ssh_stack.ssh.mode("auth_failed")

    probe = await ssh_stack.transport.probe(_target(await ssh_stack.add_key()))

    assert probe.error is not None
    assert probe.error.code is GitErrorCode.auth_failed
    (call,) = ssh_stack.ssh.calls()
    argv = _ssh_argv(call)
    assert argv[:2] == ["-F", os.devnull]
    expected = {
        "StrictHostKeyChecking": "yes",
        "IdentitiesOnly": "yes",
        "BatchMode": "yes",
        "IdentityAgent": "none",
        "ProxyCommand": "none",
        "PasswordAuthentication": "no",
        "GlobalKnownHostsFile": os.devnull,
    }
    assert {name: _option(argv, name) for name in expected} == expected
    assert _option(argv, "UserKnownHostsFile") == str(ssh_stack.known_hosts.file_path())
    assert f"git@{_HOST}" in argv
    key = call["key"]
    assert isinstance(key, dict)
    assert (key["mode"], key["dir_mode"]) == ("0o600", "0o700")
    assert not Path(str(key["dir"])).exists()
    env = call["env"]
    assert isinstance(env, list)
    assert "SSH_AUTH_SOCK" not in env


async def test__probe__port_in_the_address__reaches_ssh_and_known_hosts_entry_is_per_port(ssh_stack: SshStack) -> None:
    await ssh_stack.trust()
    credential = await ssh_stack.add_key(port=2222)
    target = _target(credential, f"ssh://git@{_HOST}:2222/hse/course.git")

    first = await ssh_stack.transport.probe(target)
    await ssh_stack.trust(port=2222)
    second = await ssh_stack.transport.probe(target)

    assert first.error is not None
    assert first.error.code is GitErrorCode.host_key_unknown
    assert second.error is not None
    assert second.error.code is GitErrorCode.auth_failed
    (call,) = ssh_stack.ssh.calls()
    argv = _ssh_argv(call)
    assert argv[argv.index("-p") + 1] == "2222"


async def test__probe__host_key_changed_reported_by_ssh__both_fingerprints(ssh_stack: SshStack) -> None:
    await ssh_stack.trust()
    ssh_stack.scanner.keys = [ScannedHostKey("ssh-ed25519", _OTHER, key_fingerprint(_OTHER))]
    ssh_stack.ssh.mode("host_changed")

    probe = await ssh_stack.transport.probe(_target(await ssh_stack.add_key()))

    assert probe.error is not None
    assert probe.error.code is GitErrorCode.host_key_changed
    assert probe.host_keys == ()


async def test__probe__trust_then_ok_flow__unknown_then_trusted_then_reaches_the_server(ssh_stack: SshStack) -> None:
    credential = await ssh_stack.add_key()
    first = await ssh_stack.transport.probe(_target(credential))
    assert first.error is not None
    assert first.error.code is GitErrorCode.host_key_unknown

    await ssh_stack.known_hosts.trust(_HOST, None, ssh_stack.scanner.keys)
    ssh_stack.ssh.mode("network")
    second = await ssh_stack.transport.probe(_target(credential))

    assert second.error is not None
    assert second.error.code is GitErrorCode.offline
    assert len(ssh_stack.ssh.calls()) == 1


async def test__probe__cancelled_while_ssh_hangs__key_file_removed_and_ssh_killed(ssh_stack: SshStack) -> None:
    await ssh_stack.trust()
    ssh_stack.ssh.mode("hang")
    task = asyncio.create_task(ssh_stack.transport.probe(_target(await ssh_stack.add_key())))
    call = await asyncio.to_thread(ssh_stack.ssh.wait_for_call)
    key = call["key"]
    assert isinstance(key, dict)
    assert Path(str(key["key"])).exists()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not Path(str(key["dir"])).exists()
    pid = int(call["pid"])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("ssh outlived the cancelled operation")


async def test__probe__hanging_ssh_hits_the_timeout__key_file_removed(ssh_stack: SshStack, tmp_path: Path) -> None:
    await ssh_stack.trust()
    ssh_stack.ssh.mode("hang")
    ssh_stack.config.probe_timeout_s = 3
    probe = await ssh_stack.transport.probe(_target(await ssh_stack.add_key()))

    assert probe.error is not None
    assert probe.error.code is GitErrorCode.timeout
    (call,) = ssh_stack.ssh.calls()
    key = call["key"]
    assert isinstance(key, dict)
    assert not Path(str(key["dir"])).exists()


async def test__probe__ssh_address_without_a_key__asks_for_the_host_first_then_for_a_key(ssh_stack: SshStack) -> None:
    first = await ssh_stack.transport.probe(_target(None))
    await ssh_stack.trust()
    second = await ssh_stack.transport.probe(_target(None))

    assert first.error is not None
    assert second.error is not None
    assert (first.error.code, second.error.code) == (GitErrorCode.host_key_unknown, GitErrorCode.credentials_missing)
    assert ssh_stack.ssh.calls() == []
