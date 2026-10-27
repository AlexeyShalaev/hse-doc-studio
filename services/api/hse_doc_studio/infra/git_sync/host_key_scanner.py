"""Чтение ключей хоста через `ssh-keyscan`. Ключу при этом никто не доверяет: решает человек.

Команда запускается списком аргументов, адрес уже проверен разбором, а перед ним стоит `--`.
Отпечатки считаются здесь, в Python, а не берутся из вывода утилиты.
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import subprocess

from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.egress import IEgressPolicy
from hse_doc_studio.core.git_sync.entities import ScannedHostKey
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.host_keys import DEFAULT_SSH_PORT, key_fingerprint, parse_key_fields
from hse_doc_studio.infra.git_sync.egress_guard import authorize_git_host
from hse_doc_studio.infra.vcs.git_env import base_git_env

_KEY_TYPES = "ed25519,ecdsa,rsa"
# ssh-keyscan сам ждёт `-T`; этот запас нужен на случай, когда он зависает после соединения.
_KILL_MARGIN_S = 5.0


def parse_keyscan(output: str) -> list[ScannedHostKey]:
    """Ключи из вывода ssh-keyscan: строки `<имя> <тип> <base64>`, комментарии и мусор пропускаются."""
    keys: list[ScannedHostKey] = []
    seen: set[tuple[str, str]] = set()
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 3 or fields[0].startswith("#"):
            continue
        parsed = parse_key_fields(fields[1], fields[2])
        if parsed is None or parsed in seen:
            continue
        seen.add(parsed)
        keys.append(ScannedHostKey(parsed[0], parsed[1], key_fingerprint(parsed[1])))
    return keys


class SshKeyscanScanner:
    def __init__(self, config: GitConfig, egress: IEgressPolicy | None = None) -> None:
        self._config = config
        self._egress = egress

    async def scan(self, host: str, port: int | None) -> list[ScannedHostKey]:
        await authorize_git_host(self._egress, host, port)
        binary = shutil.which(self._config.ssh_keyscan_binary)
        if binary is None:
            raise git_error(GitErrorCode.ssh_unavailable)
        timeout = self._config.scan_timeout_s
        wait = str(int(max(timeout, 1)))
        argv = [binary, "-T", wait, "-p", str(port or DEFAULT_SSH_PORT), "-t", _KEY_TYPES, "--", host]
        env = {key: value for key, value in base_git_env().items() if key == "PATH"}
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
            )
        except OSError:
            raise git_error(GitErrorCode.ssh_unavailable) from None
        try:
            async with asyncio.timeout(timeout + _KILL_MARGIN_S):
                stdout, _ = await process.communicate()
        except TimeoutError:
            await self._kill(process)
            raise git_error(GitErrorCode.timeout) from None
        except asyncio.CancelledError:
            await self._kill(process)
            raise
        keys = parse_keyscan(stdout.decode("utf-8", errors="replace"))
        if not keys:
            raise git_error(GitErrorCode.offline)
        return keys

    @staticmethod
    async def _kill(process: asyncio.subprocess.Process) -> None:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await process.wait()
