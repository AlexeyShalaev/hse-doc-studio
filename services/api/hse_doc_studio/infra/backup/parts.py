"""Загрузка части: поток открытого текста → шифрование во временный файл → хранилище → проверка чтением обратно."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import tempfile
from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import BinaryIO

from hse_doc_studio.core.backup.crypto import EncryptingWriter
from hse_doc_studio.core.backup.destinations import object_key
from hse_doc_studio.core.backup.entities import ManifestPart
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.backup.protocols import IPartProducer
from hse_doc_studio.core.storage.ports import IObjectStore


def _new_temp(tmp_dir: Path) -> tuple[BinaryIO, Path]:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="part-", suffix=".enc", dir=tmp_dir)
    return os.fdopen(fd, "w+b"), Path(name)


class PartUploader:
    def __init__(self, tmp_dir: Path) -> None:
        self._tmp_dir = tmp_dir

    async def upload(
        self, store: IObjectStore, base: str, producer: IPartProducer, key: bytes
    ) -> tuple[ManifestPart, dict[str, int]]:
        handle, path = await asyncio.to_thread(_new_temp, self._tmp_dir)
        try:
            with handle:
                writer = EncryptingWriter(handle, key)
                notes = await producer.produce(writer)
                stats = await asyncio.to_thread(writer.close)
                handle.flush()
                handle.seek(0)
                target = object_key(base, producer.name)
                await store.put(target, handle, sha256=stats.cipher_sha256)
            await _verify_remote(store, target, stats.cipher_size, stats.cipher_sha256)
        finally:
            with contextlib.suppress(OSError):
                path.unlink()
        part = ManifestPart(
            name=producer.name,
            size=stats.cipher_size,
            sha256=stats.cipher_sha256,
            plain_size=stats.plain_size,
            plain_sha256=stats.plain_sha256,
        )
        return part, notes


async def _verify_remote(store: IObjectStore, key: str, size: int, sha256: str) -> None:
    digest = hashlib.sha256()
    total = 0
    async for chunk in store.stream(key):
        digest.update(chunk)
        total += len(chunk)
    if total != size or digest.hexdigest() != sha256:
        raise BackupError(
            BackupErrorCode.integrity, f"{key}: what was read back from the destination differs from what was written"
        )


class _TempFile:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: BinaryIO | None = None

    def __enter__(self) -> BinaryIO:
        self._handle = self._path.open("rb")
        return self._handle

    def __exit__(self, *exc: object) -> None:
        if self._handle is not None:
            self._handle.close()
        with contextlib.suppress(OSError):
            self._path.unlink()


class PartFetcher:
    def __init__(self, tmp_dir: Path) -> None:
        self._tmp_dir = tmp_dir

    async def fetch(self, store: IObjectStore, key: str, part: ManifestPart) -> AbstractContextManager[BinaryIO]:
        handle, path = await asyncio.to_thread(_new_temp, self._tmp_dir)
        digest = hashlib.sha256()
        total = 0
        try:
            with handle:
                async for chunk in store.stream(key):
                    digest.update(chunk)
                    total += len(chunk)
                    await asyncio.to_thread(handle.write, chunk)
            if total != part.size or digest.hexdigest() != part.sha256:
                raise BackupError(BackupErrorCode.integrity, f"{part.name}: size or sha256 differs from the manifest")
        except BaseException:
            with contextlib.suppress(OSError):
                path.unlink()
            raise
        return _TempFile(path)


def iter_chunks(source: BinaryIO, size: int = 1024 * 1024) -> Iterator[bytes]:
    while chunk := source.read(size):
        yield chunk
