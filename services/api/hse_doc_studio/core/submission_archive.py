"""Хранение архивов пакетов сдачи и журнал их скачиваний."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.storage.models import PresignedUrl

_ARCHIVE_MEDIA_TYPES = (
    (".zip", "application/zip"),
    (".tar.gz", "application/gzip"),
    (".7z", "application/x-7z-compressed"),
    (".rar", "application/vnd.rar"),
)


def archive_media_type(name: str) -> str:
    for ext, media_type in _ARCHIVE_MEDIA_TYPES:
        if name.endswith(ext):
            return media_type
    return "application/octet-stream"


class ISubmissionArchive(Protocol):
    """Серверный архив пакетов. Локальный режим его не использует: архив лежит рядом с проектом."""

    @property
    def enabled(self) -> bool: ...

    async def put(self, project_id: UUID, submission_id: UUID, archive: Path, content_type: str) -> str:
        """Кладёт архив в хранилище и возвращает его ключ."""
        ...

    async def size(self, key: str) -> int | None:
        """Размер архива; None, если объекта нет."""
        ...

    async def link(self, key: str) -> PresignedUrl | None:
        """Короткоживущая ссылка на скачивание; None, если хранилище ссылок не выдаёт.
        `FileNotFoundError`, если архива нет."""
        ...

    def stream(self, key: str) -> AsyncIterator[bytes]:
        """Содержимое кусками. `FileNotFoundError` при первом чтении, если архива нет."""
        ...


class ISubmissionAudit(Protocol):
    async def downloaded(self, actor: Actor | None, project_id: UUID, submission_id: UUID, *, via: str) -> None:
        """Записывает скачивание пакета сдачи в журнал аудита."""
        ...


class DisabledSubmissionArchive:
    """Локальный режим: архива в хранилище нет."""

    @property
    def enabled(self) -> bool:
        return False

    async def put(self, project_id: UUID, submission_id: UUID, archive: Path, content_type: str) -> str:
        raise NotImplementedError

    async def size(self, key: str) -> int | None:
        return None

    async def link(self, key: str) -> PresignedUrl | None:
        return None

    def stream(self, key: str) -> AsyncIterator[bytes]:
        raise NotImplementedError


class NoSubmissionAudit:
    """Локальный режим: журнала аудита нет."""

    async def downloaded(self, actor: Actor | None, project_id: UUID, submission_id: UUID, *, via: str) -> None:
        return None
