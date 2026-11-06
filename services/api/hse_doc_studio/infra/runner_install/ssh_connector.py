"""SSH на asyncssh: рукопожатие без входа, вход с закреплённым ключом хоста, выполнение команд.

Ключ хоста сверяется самим asyncssh до отправки пароля или подписи (`known_hosts` из одного ключа), поэтому
учётные данные не уходят на хост с другим ключом. Конфигурация клиента (`~/.ssh/config`), агент и проброс
отключены: Студия подключается ровно так, как указал админ.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import asyncssh

from hse_doc_studio.core.runner_install.ssh import (
    HostKey,
    ISshSession,
    SshAuth,
    SshAuthKind,
    SshError,
    SshResult,
    SshTarget,
)

CONNECT_TIMEOUT_S = 15.0
MAX_OUTPUT = 64 * 1024


def _host_key_of(key: asyncssh.SSHKey) -> HostKey:
    return HostKey(
        key_type=key.get_algorithm(),
        fingerprint=key.get_fingerprint("sha256"),
        public_key=key.export_public_key("openssh").decode("ascii").strip(),
    )


def _clip(text: str) -> str:
    return text if len(text) <= MAX_OUTPUT else text[:MAX_OUTPUT] + "\n[output truncated]"


def _scrub(text: str, *secrets: str) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


class AsyncSshSession:
    def __init__(self, conn: asyncssh.SSHClientConnection, secrets: tuple[str, ...]) -> None:
        self._conn = conn
        self._secrets = secrets

    async def run(self, command: str, *, stdin: str | None = None, timeout: float = 120.0) -> SshResult:
        # Без входа stdin закрывается сразу: иначе команда, читающая stdin, висит до таймаута.
        feed: dict[str, Any] = {"stdin": asyncssh.DEVNULL} if stdin is None else {"input": stdin}
        try:
            done = await self._conn.run(
                command, check=False, timeout=timeout, encoding="utf-8", errors="replace", **feed
            )
        except (TimeoutError, asyncio.TimeoutError, asyncssh.TimeoutError) as exc:
            raise SshError("command_timeout") from exc
        except (asyncssh.Error, OSError) as exc:
            raise SshError("connection_lost", _scrub(str(exc), *self._secrets)) from exc
        return SshResult(
            code=done.exit_status if isinstance(done.exit_status, int) else 255,
            stdout=_clip(_scrub(str(done.stdout or ""), *self._secrets)),
            stderr=_clip(_scrub(str(done.stderr or ""), *self._secrets)),
        )

    async def close(self) -> None:
        self._conn.close()
        with contextlib.suppress(TimeoutError, asyncio.TimeoutError, OSError):
            await asyncio.wait_for(self._conn.wait_closed(), timeout=5)


class AsyncSshConnector:
    async def fetch_host_key(self, address: str, port: int) -> HostKey:
        try:
            key = await asyncio.wait_for(asyncssh.get_server_host_key(address, port, config=None), CONNECT_TIMEOUT_S)
        except (TimeoutError, asyncio.TimeoutError, OSError, asyncssh.Error) as exc:
            raise SshError("unreachable", type(exc).__name__) from exc
        if key is None:
            raise SshError("no_host_key")
        return _host_key_of(key)

    async def connect(self, address: str, target: SshTarget, auth: SshAuth, expected: HostKey) -> ISshSession:
        options = self._options(target, auth, expected)
        secrets = (auth.secret.reveal(), auth.passphrase.reveal() if auth.passphrase else "")
        try:
            conn = await asyncio.wait_for(asyncssh.connect(address, target.port, **options), CONNECT_TIMEOUT_S * 2)
        except asyncssh.HostKeyNotVerifiable as exc:
            raise SshError("host_key_mismatch") from exc
        except asyncssh.PermissionDenied as exc:
            raise SshError("auth_failed") from exc
        except (TimeoutError, asyncio.TimeoutError, OSError) as exc:
            raise SshError("unreachable", type(exc).__name__) from exc
        except asyncssh.Error as exc:
            raise SshError("ssh_failed", _scrub(str(exc), *secrets)) from exc
        return AsyncSshSession(conn, secrets)

    @staticmethod
    def _options(target: SshTarget, auth: SshAuth, expected: HostKey) -> dict[str, Any]:
        pinned = asyncssh.import_public_key(expected.public_key)
        options: dict[str, Any] = {
            "username": target.username,
            "known_hosts": ([pinned], [], []),
            "config": None,
            "agent_path": None,
            "agent_forwarding": False,
            "login_timeout": CONNECT_TIMEOUT_S,
            "keepalive_interval": 15,
            "server_host_key_algs": [expected.key_type],
        }
        if auth.kind is SshAuthKind.password:
            options.update(
                password=auth.secret.reveal(), client_keys=None, preferred_auth="password,keyboard-interactive"
            )
        else:
            try:
                key = asyncssh.import_private_key(
                    auth.secret.reveal(), auth.passphrase.reveal() if auth.passphrase else None
                )
            except asyncssh.KeyEncryptionError as exc:
                raise SshError("bad_passphrase") from exc
            except asyncssh.KeyImportError as exc:
                raise SshError("bad_private_key") from exc
            options.update(client_keys=[key], password=None, preferred_auth="publickey")
        return options
