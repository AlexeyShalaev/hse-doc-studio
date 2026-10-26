"""Команда ssh для git: временный ключ и жёсткий набор параметров.

Закрытый ключ расшифровывается в каталог 0700 только на время одной команды и удаляется в `finally`,
в том числе при отмене и таймауте. Единственный шаг через оболочку это GIT_SSH_COMMAND, и он
собирается `shlex.join` из значений, которые сделали мы. Известные хосты берутся только из
известных хостов Студии: ~/.ssh, агент ssh, ProxyCommand и пароли отключены.
"""

from __future__ import annotations

import contextlib
import os
import shlex
import shutil
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import structlog

from hse_doc_studio.core.git_sync.secret import Secret

logger = structlog.get_logger()

KEY_DIR_PREFIX = "hse-ssh-"
_STALE_AFTER_S = 3600.0
_CONNECT_TIMEOUT_S = 15
_ALIVE_INTERVAL_S = 15
_ALIVE_COUNT = 4


def _escape_percent(text: str) -> str:
    """ssh разворачивает `%` в путях параметров: литерал пишется как `%%`."""
    return text.replace("%", "%%")


def _config_value(path: str) -> str:
    """Значение параметра `-o`: ssh разбирает его как строку конфига, пробелы требуют кавычек."""
    escaped = _escape_percent(path)
    return f'"{escaped}"' if any(ch.isspace() for ch in escaped) else escaped


def build_ssh_command(ssh_binary: str, *, key_file: Path, known_hosts: Path) -> str:
    options = [
        "IdentitiesOnly=yes",
        "BatchMode=yes",
        "StrictHostKeyChecking=yes",
        f"UserKnownHostsFile={_config_value(str(known_hosts))}",
        f"GlobalKnownHostsFile={os.devnull}",
        "IdentityAgent=none",
        "ProxyCommand=none",
        "ProxyJump=none",
        "PasswordAuthentication=no",
        "KbdInteractiveAuthentication=no",
        "ForwardAgent=no",
        "ForwardX11=no",
        "PermitLocalCommand=no",
        "VerifyHostKeyDNS=no",
        "UpdateHostKeys=no",
        "HashKnownHosts=no",
        f"ConnectTimeout={_CONNECT_TIMEOUT_S}",
        f"ServerAliveInterval={_ALIVE_INTERVAL_S}",
        f"ServerAliveCountMax={_ALIVE_COUNT}",
    ]
    argv = [ssh_binary, "-F", os.devnull, "-i", _escape_percent(str(key_file))]
    for option in options:
        argv += ["-o", option]
    return shlex.join(argv)


@contextlib.contextmanager
def temporary_key_file(private_key: Secret) -> Iterator[Path]:
    """Файл ключа с правами 0600 в новом каталоге 0700; каталог удаляется при выходе из блока."""
    directory = Path(tempfile.mkdtemp(prefix=KEY_DIR_PREFIX))
    try:
        path = directory / "id"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            text = private_key.reveal()
            handle.write(text if text.endswith("\n") else text + "\n")
        yield path
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def sweep_stale_key_dirs(*, older_than_s: float = _STALE_AFTER_S, root: Path | None = None) -> int:
    """Убрать каталоги ключей, оставшиеся от убитого процесса. Живую команду не трогает: берёт только старые."""
    base = root or Path(tempfile.gettempdir())
    removed = 0
    try:
        candidates = [item for item in base.iterdir() if item.name.startswith(KEY_DIR_PREFIX)]
    except OSError:
        return 0
    cutoff = time.time() - older_than_s
    for item in candidates:
        try:
            if item.is_symlink() or not item.is_dir() or item.stat().st_mtime > cutoff:
                continue
        except OSError:
            continue
        shutil.rmtree(item, ignore_errors=True)
        removed += 1
    if removed:
        logger.info("removed stale ssh key directories", count=removed)
    return removed
