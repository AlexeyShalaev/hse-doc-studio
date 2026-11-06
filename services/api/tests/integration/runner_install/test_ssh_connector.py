"""Настоящий asyncssh против сервера asyncssh в процессе: ключ хоста закрепляется до входа, пароль и ключ, команды."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import asyncssh
import pytest
import pytest_asyncio
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.runner_install import HostKey, SshAuth, SshAuthKind, SshError, SshTarget
from hse_doc_studio.infra.runner_install.ssh_connector import AsyncSshConnector

PASSWORD = "s3cret-pass"
USER = "deploy"


@dataclass
class ServerState:
    seen_credentials: list[tuple[str, str]] = field(default_factory=list)
    commands: list[tuple[str, str]] = field(default_factory=list)


class _Server(asyncssh.SSHServer):
    def __init__(self, state: ServerState, client_key: asyncssh.SSHKey) -> None:
        self._state = state
        self._client_key = client_key

    def begin_auth(self, username: str) -> bool:
        return True

    def password_auth_supported(self) -> bool:
        return True

    def validate_password(self, username: str, password: str) -> bool:
        self._state.seen_credentials.append((username, password))
        return username == USER and password == PASSWORD

    def public_key_auth_supported(self) -> bool:
        return True

    def validate_public_key(self, username: str, key: asyncssh.SSHKey) -> bool:
        self._state.seen_credentials.append((username, "key"))
        return username == USER and key.get_fingerprint() == self._client_key.get_fingerprint()


@dataclass
class World:
    port: int
    state: ServerState
    host_key: asyncssh.SSHKey
    client_key: asyncssh.SSHKey
    connector: AsyncSshConnector


@pytest_asyncio.fixture
async def world() -> AsyncIterator[World]:
    host_key = asyncssh.generate_private_key("ssh-ed25519")
    client_key = asyncssh.generate_private_key("ssh-ed25519")
    state = ServerState()

    async def handle(process: asyncssh.SSHServerProcess[Any]) -> None:
        stdin = await process.stdin.read()
        state.commands.append((str(process.command), stdin))
        if process.command == "boom":
            process.stderr.write("exploded\n")
            process.exit(3)
            return
        process.stdout.write(f"ran:{process.command}\n")
        process.exit(0)

    server = await asyncssh.create_server(
        lambda: _Server(state, client_key),
        "127.0.0.1",
        0,
        server_host_keys=[host_key],
        process_factory=handle,
    )
    port = server.sockets[0].getsockname()[1]
    try:
        yield World(port, state, host_key, client_key, AsyncSshConnector())
    finally:
        server.close()
        await server.wait_closed()


def _pinned(world: World) -> HostKey:
    key = world.host_key
    return HostKey(
        key.get_algorithm(), key.get_fingerprint("sha256"), key.export_public_key("openssh").decode().strip()
    )


def _password_auth(password: str = PASSWORD) -> SshAuth:
    return SshAuth(SshAuthKind.password, Secret(password))


def _target(world: World, username: str = USER) -> SshTarget:
    return SshTarget("127.0.0.1", world.port, username)


async def test__fetch_host_key__returns_fingerprint_without_sending_credentials(world: World) -> None:
    key = await world.connector.fetch_host_key("127.0.0.1", world.port)

    assert key == _pinned(world)
    assert key.fingerprint.startswith("SHA256:")
    assert world.state.seen_credentials == []


async def test__fetch_host_key__unreachable_port(world: World) -> None:
    with pytest.raises(SshError) as caught:
        await world.connector.fetch_host_key("127.0.0.1", 1)

    assert caught.value.code == "unreachable"


async def test__connect__password_runs_commands_with_stdin(world: World) -> None:
    session = await world.connector.connect("127.0.0.1", _target(world), _password_auth(), _pinned(world))
    try:
        ok = await session.run("hello", stdin="payload\n")
        failed = await session.run("boom")
    finally:
        await session.close()

    assert (ok.code, ok.stdout) == (0, "ran:hello\n")
    assert (failed.code, failed.stderr) == (3, "exploded\n")
    assert world.state.commands[0] == ("hello", "payload\n")


async def test__connect__private_key_with_passphrase(world: World) -> None:
    pem = world.client_key.export_private_key(passphrase="pp").decode()
    auth = SshAuth(SshAuthKind.key, Secret(pem), Secret("pp"))

    session = await world.connector.connect("127.0.0.1", _target(world), auth, _pinned(world))
    try:
        result = await session.run("whoami")
    finally:
        await session.close()

    assert result.stdout == "ran:whoami\n"


async def test__connect__wrong_passphrase_and_garbage_key_are_distinguished(world: World) -> None:
    pem = world.client_key.export_private_key(passphrase="pp").decode()

    with pytest.raises(SshError) as wrong:
        await world.connector.connect(
            "127.0.0.1", _target(world), SshAuth(SshAuthKind.key, Secret(pem), Secret("nope")), _pinned(world)
        )
    with pytest.raises(SshError) as garbage:
        await world.connector.connect(
            "127.0.0.1", _target(world), SshAuth(SshAuthKind.key, Secret("not a key")), _pinned(world)
        )

    assert wrong.value.code == "bad_passphrase"
    assert garbage.value.code == "bad_private_key"
    assert world.state.seen_credentials == []


async def test__connect__other_host_key_is_refused_before_any_credential_is_sent(world: World) -> None:
    other = asyncssh.generate_private_key("ssh-ed25519")
    pinned = HostKey(
        other.get_algorithm(), other.get_fingerprint("sha256"), other.export_public_key("openssh").decode().strip()
    )

    with pytest.raises(SshError) as caught:
        await world.connector.connect("127.0.0.1", _target(world), _password_auth(), pinned)

    assert caught.value.code == "host_key_mismatch"
    assert world.state.seen_credentials == []


async def test__connect__wrong_password_is_auth_failed_and_not_echoed(world: World) -> None:
    with pytest.raises(SshError) as caught:
        await world.connector.connect("127.0.0.1", _target(world), _password_auth("bad-pass-123"), _pinned(world))

    assert caught.value.code == "auth_failed"
    assert "bad-pass-123" not in repr(caught.value.detail)


async def test__run__output_has_secrets_scrubbed(world: World) -> None:
    session = await world.connector.connect("127.0.0.1", _target(world), _password_auth(), _pinned(world))
    try:
        result = await session.run(f"echo {PASSWORD}")
    finally:
        await session.close()

    assert PASSWORD not in result.stdout
    assert "***" in result.stdout


async def test__run__command_timeout(world: World) -> None:
    session = await world.connector.connect("127.0.0.1", _target(world), _password_auth(), _pinned(world))
    try:
        with pytest.raises(SshError) as caught:
            await session.run("slow", timeout=0.0001)
    finally:
        await session.close()

    assert caught.value.code in {"command_timeout", "connection_lost"}
