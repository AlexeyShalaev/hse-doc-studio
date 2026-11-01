"""Файловое хранилище задач сервера: входные блобы, принятые выходы и лог.

Раскладка под одним корнем: `blobs/<sha256>`, `outputs/<job_id>/<attempt>/<sha256>` и
`logs/<job_id>/<attempt>.log`. Выходы пишутся во временный файл и ставятся на место после проверки
размера и хеша. Объектное хранилище заменит этот класс за теми же портами.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import tempfile
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from threading import Lock
from uuid import UUID

from hse_doc_studio.core.jobs.errors import ArtifactInvalidError, BlobMissingError
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.storage import (
    BLOB_CHUNK_BYTES,
    DEFAULT_MAX_ARTIFACT_BYTES,
    DEFAULT_MAX_LOG_BYTES,
)

_HEX = frozenset("0123456789abcdef")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and set(value) <= _HEX


class FsJobBlobStore:
    def __init__(self, root: Path) -> None:
        self._dir = root / "blobs"

    def _path(self, sha256: str) -> Path:
        if not _is_sha256(sha256):
            raise BlobMissingError("malformed blob hash")
        return self._dir / sha256

    async def exists(self, sha256: str) -> bool:
        return _is_sha256(sha256) and await asyncio.to_thread(self._path(sha256).is_file)

    async def url_for(self, sha256: str) -> str | None:
        return None

    async def open(self, sha256: str) -> AsyncIterator[bytes]:
        path = self._path(sha256)
        if not await asyncio.to_thread(path.is_file):
            raise BlobMissingError(f"blob {sha256} is missing")
        return _read_chunks(path)

    async def store(self, data: bytes) -> str:
        """Кладёт блоб и возвращает его хеш; нужен тем, кто готовит вход задачи."""
        sha = hashlib.sha256(data).hexdigest()
        await asyncio.to_thread(self._write, sha, data)
        return sha

    def _write(self, sha: str, data: bytes) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        target = self._dir / sha
        if not target.exists():
            tmp = self._dir / f".{sha}.{os.getpid()}.tmp"
            tmp.write_bytes(data)
            tmp.chmod(0o444)
            tmp.replace(target)


async def _read_chunks(path: Path) -> AsyncIterator[bytes]:
    handle = await asyncio.to_thread(path.open, "rb")
    try:
        while chunk := await asyncio.to_thread(handle.read, BLOB_CHUNK_BYTES):
            yield chunk
    finally:
        await asyncio.to_thread(handle.close)


class FsJobOutputIngest:
    def __init__(self, root: Path, *, max_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES) -> None:
        self._dir = root / "outputs"
        self._max_bytes = max_bytes

    def _attempt_dir(self, job_id: UUID, attempt: int) -> Path:
        return self._dir / str(job_id) / str(attempt)

    async def announce(self, job_id: UUID, attempt: int, artifact: ArtifactRef) -> str | None:
        if not _is_sha256(artifact.sha256):
            raise ArtifactInvalidError("malformed artifact hash")
        if artifact.size > self._max_bytes:
            raise ArtifactInvalidError(f"artifact {artifact.path!r} is larger than {self._max_bytes} bytes")
        await asyncio.to_thread(self._write_announce, self._attempt_dir(job_id, attempt), artifact)
        return None

    @staticmethod
    def _write_announce(directory: Path, artifact: ArtifactRef) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{artifact.sha256}.size").write_text(str(artifact.size), encoding="ascii")

    async def put(self, job_id: UUID, attempt: int, sha256: str, chunks: AsyncIterator[bytes]) -> None:
        directory = self._attempt_dir(job_id, attempt)
        expected = await asyncio.to_thread(self._announced_size, directory, sha256)
        if expected is None:
            raise ArtifactInvalidError(f"artifact {sha256} was not announced")
        fd, tmp_name = await asyncio.to_thread(tempfile.mkstemp, dir=directory, prefix=".upload-")
        tmp = Path(tmp_name)
        digest = hashlib.sha256()
        size = 0
        try:
            with os.fdopen(fd, "wb") as handle:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > expected:
                        raise ArtifactInvalidError(f"artifact {sha256} is larger than announced")
                    digest.update(chunk)
                    await asyncio.to_thread(handle.write, chunk)
            if size != expected:
                raise ArtifactInvalidError(f"artifact {sha256} size {size} differs from announced {expected}")
            if digest.hexdigest() != sha256:
                raise ArtifactInvalidError(f"artifact content does not match sha256 {sha256}")
            await asyncio.to_thread(tmp.replace, directory / sha256)
        except BaseException:
            await asyncio.to_thread(tmp.unlink, missing_ok=True)
            raise

    @staticmethod
    def _announced_size(directory: Path, sha256: str) -> int | None:
        if not _is_sha256(sha256):
            return None
        marker = directory / f"{sha256}.size"
        return int(marker.read_text(encoding="ascii")) if marker.is_file() else None

    async def commit(self, job_id: UUID, attempt: int, artifacts: Sequence[ArtifactRef]) -> None:
        directory = self._attempt_dir(job_id, attempt)
        for artifact in artifacts:
            announced = await asyncio.to_thread(self._announced_size, directory, artifact.sha256)
            if announced is None or announced != artifact.size:
                raise ArtifactInvalidError(f"artifact {artifact.path!r} was not announced with this size")
            stored = await asyncio.to_thread(self._stored_size, directory / artifact.sha256)
            if stored != artifact.size:
                raise ArtifactInvalidError(f"artifact {artifact.path!r} is not uploaded")

    @staticmethod
    def _stored_size(path: Path) -> int | None:
        return path.stat().st_size if path.is_file() and not path.is_symlink() else None

    async def discard(self, job_id: UUID) -> None:
        await asyncio.to_thread(shutil.rmtree, self._dir / str(job_id), ignore_errors=True)

    def stored_path(self, job_id: UUID, attempt: int, sha256: str) -> Path:
        """Где лежит принятый выход; нужен применяющему результат."""
        return self._attempt_dir(job_id, attempt) / sha256


class FsJobLogSink:
    def __init__(self, root: Path, *, max_bytes: int = DEFAULT_MAX_LOG_BYTES) -> None:
        self._dir = root / "logs"
        self._max_bytes = max_bytes
        self._lock = Lock()

    async def append(self, job_id: UUID, attempt: int, seq: int, lines: Sequence[str]) -> bool:
        return await asyncio.to_thread(self._append, job_id, attempt, seq, lines)

    def _append(self, job_id: UUID, attempt: int, seq: int, lines: Sequence[str]) -> bool:
        directory = self._dir / str(job_id)
        log = directory / f"{attempt}.log"
        marker = directory / f"{attempt}.seq"
        with self._lock:
            directory.mkdir(parents=True, exist_ok=True)
            if marker.is_file() and seq <= int(marker.read_text(encoding="ascii")):
                return False
            room = self._max_bytes - (log.stat().st_size if log.is_file() else 0)
            text = "".join(f"{line}\n" for line in lines).encode("utf-8", errors="replace")[: max(room, 0)]
            if text:
                with log.open("ab") as handle:
                    handle.write(text)
            marker.write_text(str(seq), encoding="ascii")
        return True
