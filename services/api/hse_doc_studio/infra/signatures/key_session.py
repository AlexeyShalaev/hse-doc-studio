"""Временный каталог с закрытым ключом подписи: 0700, затирание содержимого и удаление на выходе."""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import structlog

logger = structlog.get_logger()

KEY_SESSION_PREFIX = "hse-signkey-"
_STALE_AFTER_S = 3600.0
_SHM = Path("/dev/shm")  # noqa: S108


def _base_dir() -> Path:
    """Предпочитаем память: ключ не попадает на диск, пока работает tmpfs."""
    return _SHM if _SHM.is_dir() and os.access(_SHM, os.W_OK) else Path(tempfile.gettempdir())


def wipe_dir(directory: Path) -> None:
    """Перезаписывает файлы нулями до удаления: освобождённый блок не хранит ключ."""
    for item in directory.rglob("*"):
        if item.is_symlink() or not item.is_file():
            continue
        with contextlib.suppress(OSError):
            size = item.stat().st_size
            with item.open("r+b") as handle:
                handle.write(b"\0" * size)
                handle.flush()
                os.fsync(handle.fileno())
    shutil.rmtree(directory, ignore_errors=True)


@contextlib.contextmanager
def key_directory(key_pem: bytes, cert_pem: bytes | None, *, root: Path | None = None) -> Iterator[Path]:
    """Каталог с key.pem и cert.pem на время блока. Исключение внутри блока каталог тоже убирает."""
    directory = Path(tempfile.mkdtemp(prefix=KEY_SESSION_PREFIX, dir=root or _base_dir()))
    try:
        os.chmod(directory, 0o700)
        fd = os.open(directory / "key.pem", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(key_pem)
        if cert_pem is not None:
            fd = os.open(directory / "cert.pem", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(cert_pem)
        yield directory
    finally:
        wipe_dir(directory)


def sweep_stale_key_sessions(*, older_than_s: float = _STALE_AFTER_S, root: Path | None = None) -> int:
    """Убрать каталоги ключей, оставшиеся от убитого процесса. Живую подпись не трогает: берёт только старые."""
    bases = [root] if root is not None else [_base_dir(), Path(tempfile.gettempdir())]
    cutoff = time.time() - older_than_s
    removed = 0
    for base in dict.fromkeys(bases):
        try:
            candidates = [item for item in base.iterdir() if item.name.startswith(KEY_SESSION_PREFIX)]
        except OSError:
            continue
        for item in candidates:
            try:
                if item.is_symlink() or not item.is_dir() or item.stat().st_mtime > cutoff:
                    continue
            except OSError:
                continue
            wipe_dir(item)
            removed += 1
    if removed:
        logger.info("removed stale signing key directories", count=removed)
    return removed
