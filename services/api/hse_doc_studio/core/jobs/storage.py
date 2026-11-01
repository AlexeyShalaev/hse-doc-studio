"""Порты хранилища задач сервера: входные блобы, приём выходов и лог.

Блобы адресуются хешем sha256. Выход принимается в три шага: заявка, загрузка, проверка при завершении.
Реализации подставляются снаружи: файловая лежит рядом с api, объектное хранилище заменит её без изменений
протокола раннера.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.jobs.files import ArtifactRef

# Потолки по умолчанию; настраиваются в JobsConfig и отдельны от квоты проекта.
DEFAULT_MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_LOG_BYTES = 8 * 1024 * 1024
BLOB_CHUNK_BYTES = 1024 * 1024


class IJobBlobStore(Protocol):
    """Входные блобы манифеста по хешу."""

    async def exists(self, sha256: str) -> bool: ...

    async def url_for(self, sha256: str) -> str | None:
        """Подписанная ссылка на чтение; `None` значит, что отдаёт сам API."""
        ...

    async def open(self, sha256: str) -> AsyncIterator[bytes]:
        """Поток содержимого; `BlobMissingError` бросается до первого чанка."""
        ...


class IJobOutputIngest(Protocol):
    """Единый шов приёма выходов: ключи только своей задачи и попытки, размер и хеш проверяются."""

    async def announce(self, job_id: UUID, attempt: int, artifact: ArtifactRef) -> str | None:
        """Принять заявку и вернуть подписанную ссылку на загрузку или `None` (грузить через API).

        Размер выше потолка отвергается `ArtifactInvalidError`.
        """
        ...

    async def put(self, job_id: UUID, attempt: int, sha256: str, chunks: AsyncIterator[bytes]) -> None:
        """Принять поток по заявленному хешу; несовпадение размера или хеша это `ArtifactInvalidError`."""
        ...

    async def commit(self, job_id: UUID, attempt: int, artifacts: Sequence[ArtifactRef]) -> None:
        """Проверить, что каждый выход заявлен и загружен с тем же размером и хешем; иначе `ArtifactInvalidError`."""
        ...

    async def discard(self, job_id: UUID) -> None:
        """Стереть всё принятое по задаче (отмена, исчерпанные попытки)."""
        ...


class IJobLogSink(Protocol):
    async def append(self, job_id: UUID, attempt: int, seq: int, lines: Sequence[str]) -> bool:
        """Дописать порцию; порция с уже принятым `seq` игнорируется и даёт `False`."""
        ...
