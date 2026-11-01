"""Хранилище объектов в каталоге: локальная разработка, тесты и установки без S3."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from hse_doc_studio.core.storage.errors import ChecksumMismatchError, ObjectNotFoundError, ObjectStoreError
from hse_doc_studio.core.storage.keys import validate_key
from hse_doc_studio.core.storage.models import ObjectInfo, PresignedUrl
from hse_doc_studio.core.storage.ports import ByteRange, ObjectSource
from hse_doc_studio.infra.storage.checked import check_source

_TMP_DIR = ".tmp"
_COPY_CHUNK = 1024 * 1024


class FsObjectStore:
    def __init__(self, root: Path, *, max_object_bytes: int) -> None:
        self._root = root
        self._max_bytes = max_object_bytes

    def _path(self, key: str) -> Path:
        return self._root.joinpath(*validate_key(key).split("/"))

    def _info(self, key: str, path: Path, sha256: str | None = None) -> ObjectInfo:
        stat = path.stat()
        return ObjectInfo(
            key=key, size=stat.st_size, last_modified=datetime.fromtimestamp(stat.st_mtime, UTC), sha256=sha256
        )

    async def put(
        self,
        key: str,
        source: ObjectSource,
        *,
        content_type: str | None = None,
        sha256: str | None = None,
    ) -> ObjectInfo:
        path = self._path(key)
        return await asyncio.to_thread(self._write, key, path, source, sha256)

    def _write(self, key: str, path: Path, source: ObjectSource, expected: str | None) -> ObjectInfo:
        check_source(source, max_bytes=self._max_bytes, expected_sha256=expected)
        tmp_dir = self._root / _TMP_DIR
        tmp_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=tmp_dir)
        try:
            with os.fdopen(fd, "wb") as out:
                actual = _copy(source, out)
            if expected is not None and actual != expected:
                msg = "sha256 данных не совпал с заявленным"
                raise ChecksumMismatchError(msg)
            path.parent.mkdir(parents=True, exist_ok=True)
            Path(tmp_name).replace(path)
        except BaseException as exc:
            with contextlib.suppress(OSError):
                Path(tmp_name).unlink()
            if isinstance(exc, OSError):
                msg = f"не удалось записать объект {key}"
                raise ObjectStoreError(msg) from exc
            raise
        return self._info(key, path, actual)

    async def get(self, key: str, *, byte_range: ByteRange | None = None) -> bytes:
        path = self._path(key)
        return await asyncio.to_thread(self._read, path, byte_range)

    @staticmethod
    def _read(path: Path, byte_range: ByteRange | None) -> bytes:
        try:
            with path.open("rb") as handle:
                if byte_range is None:
                    return handle.read()
                start, end = byte_range
                handle.seek(start)
                return handle.read() if end is None else handle.read(max(0, end - start + 1))
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError) as exc:
            raise ObjectNotFoundError(path.name) from exc

    async def stream(self, key: str, *, chunk_size: int = _COPY_CHUNK) -> AsyncIterator[bytes]:
        path = self._path(key)
        try:
            handle = await asyncio.to_thread(path.open, "rb")
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError) as exc:
            raise ObjectNotFoundError(key) from exc
        try:
            while chunk := await asyncio.to_thread(handle.read, chunk_size):
                yield chunk
        finally:
            await asyncio.to_thread(handle.close)

    async def head(self, key: str) -> ObjectInfo | None:
        path = self._path(key)
        return await asyncio.to_thread(self._head, key, path)

    def _head(self, key: str, path: Path) -> ObjectInfo | None:
        if not path.is_file():
            return None
        return self._info(key, path)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(self._delete, path)

    def _delete(self, path: Path) -> None:
        with contextlib.suppress(FileNotFoundError, IsADirectoryError):
            path.unlink()
        parent = path.parent
        while parent != self._root and parent.is_relative_to(self._root):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    async def list_objects(self, prefix: str = "") -> list[ObjectInfo]:
        return await asyncio.to_thread(self._list, prefix)

    def _list(self, prefix: str) -> list[ObjectInfo]:
        found: list[ObjectInfo] = []
        for path in self._walk(self._root):
            key = path.relative_to(self._root).as_posix()
            if key.startswith(prefix):
                found.append(self._info(key, path))
        return sorted(found, key=lambda info: info.key)

    def _walk(self, folder: Path) -> Iterator[Path]:
        if not folder.is_dir():
            return
        for entry in folder.iterdir():
            if entry.name.startswith("."):
                continue
            if entry.is_dir() and not entry.is_symlink():
                yield from self._walk(entry)
            elif entry.is_file() and not entry.is_symlink():
                yield entry

    async def presign_get(self, key: str, *, expires_in_s: int = 300) -> PresignedUrl | None:
        validate_key(key)
        return None

    async def presign_put(
        self, key: str, *, expires_in_s: int = 300, content_type: str | None = None
    ) -> PresignedUrl | None:
        validate_key(key)
        return None

    async def check(self) -> None:
        await asyncio.to_thread(self._check)

    def _check(self) -> None:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=self._root):
                pass
        except OSError as exc:
            msg = f"каталог объектов недоступен на запись: {self._root}"
            raise ObjectStoreError(msg) from exc


def _copy(source: ObjectSource, out: BinaryIO) -> str:
    """Пишет источник и считает sha256 того, что реально записано: файл мог измениться после первой проверки."""
    digest = hashlib.sha256()
    if isinstance(source, bytes):
        digest.update(source)
        out.write(source)
        return digest.hexdigest()
    while chunk := source.read(_COPY_CHUNK):
        digest.update(chunk)
        out.write(chunk)
    return digest.hexdigest()
