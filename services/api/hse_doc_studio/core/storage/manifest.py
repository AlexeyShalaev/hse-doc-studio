"""Манифест входа задачи: порты реестра блобов и загрузчика, типизированные отказы по лимитам."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.jobs.files import ManifestFile
from hse_doc_studio.core.storage.errors import ObjectStoreError

DEFAULT_MAX_FILE_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_JOB_BYTES = 1024 * 1024 * 1024
# Файл, изменённый свежее этого окна, мог быть изменён ещё раз в ту же долю секунды: кэшу хеша он не верен.
RACY_WINDOW_NS = 2_000_000_000


class ManifestError(ObjectStoreError):
    """Манифест нельзя собрать; у каждого отказа свой тип и код для ответа пользователю."""

    code = "manifest_error"


class ManifestFileTooLargeError(ManifestError):
    code = "manifest_file_too_large"

    def __init__(self, path: str, size: int, limit: int) -> None:
        super().__init__(f"файл {path} ({size} байт) больше предела {limit} байт")
        self.path = path
        self.size = size
        self.limit = limit


class ManifestTooLargeError(ManifestError):
    code = "manifest_too_large"

    def __init__(self, total: int, limit: int) -> None:
        super().__init__(f"вход задачи ({total} байт) больше предела {limit} байт")
        self.total = total
        self.limit = limit


class ManifestFileMissingError(ManifestError):
    code = "manifest_file_missing"

    def __init__(self, path: str) -> None:
        super().__init__(f"файла нет в проекте: {path}")
        self.path = path


class ManifestFileChangedError(ManifestError):
    code = "manifest_file_changed"

    def __init__(self, path: str) -> None:
        super().__init__(f"файл изменился во время загрузки: {path}")
        self.path = path


class ManifestUnsafePathError(ManifestError):
    code = "manifest_unsafe_path"

    def __init__(self, path: str) -> None:
        super().__init__(f"недопустимый путь в манифесте: {path}")
        self.path = path


@dataclass(frozen=True)
class ManifestLimits:
    """Предел файла и всего входа задачи; не зависят от квоты проекта и согласованы с ней: проект больше
    предела задачи собирается через выбор файлов планировщиком или получает ManifestTooLargeError."""

    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_job_bytes: int = DEFAULT_MAX_JOB_BYTES


@dataclass(frozen=True)
class HashCacheEntry:
    mtime_ns: int
    size: int
    sha256: str


@dataclass(frozen=True)
class UnreferencedBlob:
    sha256: str
    size: int


class IBlobRegistry(Protocol):
    """Реестр блобов в БД: наличие проверяется без обращения к хранилищу, давность ссылок решает GC."""

    async def touch(self, shas: Collection[str], now: datetime) -> set[str]:
        """Продлевает жизнь известным блобам и возвращает их: проверка наличия и защита от GC одним шагом."""
        ...

    async def record(self, blobs: Mapping[str, int], now: datetime) -> None:
        """Заносит блобы (sha256 -> размер) или продлевает жизнь уже занесённым."""
        ...

    async def known(self, shas: Collection[str]) -> set[str]: ...

    async def hash_cache(self, project_id: UUID, paths: Collection[str]) -> dict[str, HashCacheEntry]: ...

    async def store_hash_cache(self, project_id: UUID, entries: Mapping[str, HashCacheEntry]) -> None: ...

    async def reap(
        self,
        older_than: datetime,
        limit: int,
        remove: Callable[[str], Awaitable[None]],
        *,
        keep: Collection[str] = (),
    ) -> list[UnreferencedBlob]:
        """Удаляет блобы, на которые не ссылались с момента older_than (кроме keep), самые давние первыми.

        Строка блокируется на время удаления объекта: параллельный touch ждёт и после коммита не находит блоб,
        поэтому догрузит его заново. Запись стирается только у тех, чей объект удалён без ошибки.
        """
        ...


class IBlobUploader(Protocol):
    async def ensure(
        self, project_id: UUID, folder: Path, paths: Sequence[str], limits: ManifestLimits | None = None
    ) -> list[ManifestFile]:
        """Манифест файлов проекта: хеширует (с кэшем по mtime и размеру) и догружает недостающие блобы."""
        ...


class ILiveBlobSource(Protocol):
    """Блобы, нужные задачам, которые ещё не завершены: GC их не трогает, как бы давно ни ссылались."""

    async def live_blobs(self) -> set[str]: ...
