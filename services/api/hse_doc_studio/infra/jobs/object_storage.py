"""Порты хранилища задач (`IJobBlobStore`, `IJobOutputIngest`) поверх объектного хранилища.

Блобы манифеста лежат там же, куда их кладёт загрузчик манифестов проекта, а выходы принимает общий шов
`core.storage.ingest`: ключи только своей пары (проект, задача), размер и sha256 сверяются. Протокол раннера
знает выход по хешу, а ключ в хранилище строится по пути, поэтому заявка пишет маленькую запись «хеш -> пути».
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import BinaryIO, cast
from uuid import UUID

from hse_doc_studio.core.jobs.errors import ArtifactInvalidError, BlobMissingError, QueuedJobNotFoundError
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.core.storage.errors import ObjectStoreError
from hse_doc_studio.core.storage.ingest import OutputRejectedError, OutputSpec, output_prefix
from hse_doc_studio.core.storage.keys import is_sha256
from hse_doc_studio.core.storage.manifest import IBlobRegistry
from hse_doc_studio.core.storage.ports import IBlobStore, IObjectStore
from hse_doc_studio.infra.storage.job_output_ingest import ObjectJobOutputIngest

_SPOOL_BYTES = 8 * 1024 * 1024
_ANNOUNCE_PREFIX = "announce/"


@dataclass(frozen=True)
class _Announced:
    size: int
    paths: tuple[str, ...]


class ObjectJobBlobStore:
    """Входные блобы задачи: те же объекты, что кладёт загрузчик манифеста проекта."""

    def __init__(self, blobs: IBlobStore, registry: IBlobRegistry | None = None) -> None:
        self._blobs = blobs
        self._registry = registry

    async def exists(self, sha256: str) -> bool:
        if not is_sha256(sha256):
            return False
        if await self._blobs.head(sha256) is not None:
            return True
        # Реестр считает блоб загруженным, а объекта нет (бакет восстановили старее базы): без записи
        # следующая сборка манифеста догрузит файл, иначе каждая сборка с ним падала бы с blob_missing.
        if self._registry is not None:
            await self._registry.forget([sha256])
        return False

    async def url_for(self, sha256: str) -> str | None:
        link = await self._blobs.presign_get(sha256)
        return None if link is None else link.url

    async def open(self, sha256: str) -> AsyncIterator[bytes]:
        if not await self.exists(sha256):
            raise BlobMissingError(f"blob {sha256} is missing")
        return self._blobs.stream(sha256)


class AnnouncedJobOutputIngest:
    """Выходы задачи в объектном хранилище; проект задачи берётся из очереди, а не из запроса раннера."""

    def __init__(self, queue: IJobQueue, store: IObjectStore, ingest: ObjectJobOutputIngest) -> None:
        self._queue = queue
        self._store = store
        self._ingest = ingest

    async def announce(self, job_id: UUID, attempt: int, artifact: ArtifactRef) -> str | None:
        project = await self._project(job_id)
        spec = OutputSpec(path=artifact.path, size=artifact.size, sha256=artifact.sha256)
        try:
            (upload,) = await self._ingest.begin(project, str(job_id), [spec])
        except OutputRejectedError as exc:
            raise ArtifactInvalidError(str(exc)) from exc
        announced = await self._announced(project, job_id, attempt, artifact.sha256)
        if announced is not None and announced.size != artifact.size:
            raise ArtifactInvalidError(f"artifact {artifact.sha256} was announced with another size")
        paths = sorted({*(announced.paths if announced else ()), artifact.path})
        await self._store.put(
            self._marker_key(project, job_id, attempt, artifact.sha256),
            json.dumps({"size": artifact.size, "paths": paths}).encode(),
        )
        return None if upload.url is None else upload.url.url

    async def put(self, job_id: UUID, attempt: int, sha256: str, chunks: AsyncIterator[bytes]) -> None:
        project = await self._project(job_id)
        announced = await self._announced(project, job_id, attempt, sha256)
        if announced is None:
            raise ArtifactInvalidError(f"artifact {sha256} was not announced")
        expected = announced.size
        with tempfile.SpooledTemporaryFile(max_size=_SPOOL_BYTES) as spool:
            size = 0
            async for chunk in chunks:
                size += len(chunk)
                if size > expected:
                    raise ArtifactInvalidError(f"artifact {sha256} is larger than announced")
                spool.write(chunk)
            for path in announced.paths:
                spool.seek(0)
                spec = OutputSpec(path=path, size=expected, sha256=sha256)
                try:
                    await self._ingest.put(project, str(job_id), spec, cast(BinaryIO, spool))
                except OutputRejectedError as exc:
                    raise ArtifactInvalidError(str(exc)) from exc

    async def commit(self, job_id: UUID, attempt: int, artifacts: Sequence[ArtifactRef]) -> None:
        del attempt
        project = await self._project(job_id)
        specs = [OutputSpec(path=a.path, size=a.size, sha256=a.sha256) for a in artifacts]
        try:
            await self._fill_duplicates(project, str(job_id), specs)
            await self._ingest.commit(project, str(job_id), specs)
        except OutputRejectedError as exc:
            raise ArtifactInvalidError(str(exc)) from exc

    async def discard(self, job_id: UUID) -> None:
        project = await self._project(job_id)
        for prefix in (output_prefix(project, str(job_id)), self._marker_prefix(project, job_id)):
            for info in await self._store.list_objects(prefix):
                await self._store.delete(info.key)

    async def _fill_duplicates(self, project: str, job_id: str, specs: Sequence[OutputSpec]) -> None:
        """Два пути с одним содержимым раннер может залить один раз: недостающий выход копируем с соседнего."""
        uploads = await self._ingest.begin(project, job_id, specs)
        keys = {spec.path: upload.key for spec, upload in zip(specs, uploads, strict=True)}
        present: dict[str, str] = {}
        missing: list[OutputSpec] = []
        for spec in specs:
            if await self._store.head(keys[spec.path]) is None:
                missing.append(spec)
            else:
                present.setdefault(spec.sha256, keys[spec.path])
        for spec in missing:
            source_key = present.get(spec.sha256)
            if source_key is None:
                continue
            with tempfile.SpooledTemporaryFile(max_size=_SPOOL_BYTES) as spool:
                async for chunk in self._store.stream(source_key):
                    spool.write(chunk)
                spool.seek(0)
                await self._ingest.put(project, job_id, spec, cast(BinaryIO, spool))

    async def _project(self, job_id: UUID) -> str:
        job = await self._queue.get(job_id)
        if job is None:
            raise QueuedJobNotFoundError(f"job {job_id} not found")
        return str(job.project_id)

    @staticmethod
    def _marker_prefix(project: str, job_id: UUID) -> str:
        return f"{_ANNOUNCE_PREFIX}{project}/{job_id}/"

    def _marker_key(self, project: str, job_id: UUID, attempt: int, sha256: str) -> str:
        return f"{self._marker_prefix(project, job_id)}{attempt}/{sha256}.json"

    async def _announced(self, project: str, job_id: UUID, attempt: int, sha256: str) -> _Announced | None:
        if not is_sha256(sha256):
            return None
        try:
            raw = await self._store.get(self._marker_key(project, job_id, attempt, sha256))
        except ObjectStoreError:
            return None
        data = json.loads(raw)
        return _Announced(size=int(data["size"]), paths=tuple(data["paths"]))
