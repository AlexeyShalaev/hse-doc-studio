"""Порты хранилища задач сервера: входные блобы, приём выходов и лог.

Блобы адресуются хешем sha256. Выход принимается в три шага: заявка, загрузка, проверка при завершении.
Реализации подставляются снаружи: файловая лежит рядом с api, объектное хранилище заменит её без изменений
протокола раннера.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.routing import RunnerScope
from hse_doc_studio.core.storage.models import LinkAudience

# Потолки по умолчанию; настраиваются в JobsConfig и отдельны от квоты проекта.
DEFAULT_MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_LOG_BYTES = 8 * 1024 * 1024
BLOB_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class RunnerStoragePolicy:
    """Как раннер ходит в объектное хранилище: по внутреннему адресу, по публичному или через API.

    Раннер в сети сервера получает ссылки на внутренний адрес. Раннер вне сети (по умолчанию личный) получает
    ссылки на публичный адрес, а в режиме proxy ссылок не получает вовсе и обменивается файлами через API.
    """

    shared_outside: bool = False
    outside_via_api: bool = False

    def audience_for(self, scope: RunnerScope) -> LinkAudience | None:
        """Кому подписывать ссылки раннера; `None` значит, что ссылок нет и файлы идут через API."""
        if scope is RunnerScope.shared and not self.shared_outside:
            return LinkAudience.internal
        return None if self.outside_via_api else LinkAudience.outside


class IJobBlobStore(Protocol):
    """Входные блобы манифеста по хешу."""

    async def exists(self, sha256: str) -> bool: ...

    async def url_for(self, sha256: str, audience: LinkAudience = LinkAudience.outside) -> str | None:
        """Подписанная для адреса получателя ссылка на чтение; `None` значит, что отдаёт сам API."""
        ...

    async def open(self, sha256: str) -> AsyncIterator[bytes]:
        """Поток содержимого; `BlobMissingError` бросается до первого чанка."""
        ...


class IJobOutputIngest(Protocol):
    """Единый шов приёма выходов: ключи только своей задачи и попытки, размер и хеш проверяются."""

    async def announce(
        self, job_id: UUID, attempt: int, artifact: ArtifactRef, audience: LinkAudience | None = LinkAudience.outside
    ) -> str | None:
        """Принять заявку и вернуть подписанную для адреса получателя ссылку на загрузку или `None` (грузить через API).

        `audience=None` значит, что ссылку выдавать нельзя: файл пойдёт через API.

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


class IJobLogReader(Protocol):
    """Чтение принятого лога задачи: итог для записи сборки и живой хвост для потока."""

    async def read(self, job_id: UUID, *, max_bytes: int) -> str:
        """Лог всех попыток по порядку; сверх `max_bytes` теряется начало (итог и ошибки в конце)."""
        ...

    async def read_from(self, job_id: UUID, attempt: int, offset: int) -> tuple[str, int]:
        """Новые строки попытки с байтового смещения и следующее смещение; только целые строки."""
        ...
