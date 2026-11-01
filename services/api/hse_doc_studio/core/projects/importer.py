"""Перенос проекта из локальной Студии на сервер: разбор архива, отчёт и порты.

Архив чужой, поэтому сначала он проверяется целиком (`inspect`), и только потом что-то пишется на том.
Любое сомнение (путь наружу, симлинк, шифрование, неверный размер) отклоняет архив целиком: частично
распакованный чужой проект на общем томе хуже отказа.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.projects.volume import IProjectVolume
from hse_doc_studio.core.repositories import IChatRepository


class ProjectImportCode(StrEnum):
    archive_invalid = "archive_invalid"
    archive_unsafe = "archive_unsafe"
    too_large = "too_large"
    no_project = "no_project"
    project_newer = "project_newer"
    unavailable = "unavailable"


class ProjectImportError(Exception):
    """Архив не принят. `message` написан для человека на языке интерфейса."""

    def __init__(self, code: ProjectImportCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ImportWarningCode(StrEnum):
    # Адрес удалённого репозитория остался, а доступа к нему на сервере нет.
    remote_needs_access = "remote_needs_access"
    # Записи сборок и сдач локальны (пути на диске автора): пересоберите документы на сервере.
    records_skipped = "records_skipped"
    # Хуки и чужие настройки хранилища версий убраны.
    store_hardened = "store_hardened"
    # Служебные файлы систем (.DS_Store, __MACOSX) в проект не попали.
    junk_skipped = "junk_skipped"
    # Чаты не удалось прочитать; проект перенесён без них.
    chats_unreadable = "chats_unreadable"


@dataclass(frozen=True)
class ImportWarning:
    code: ImportWarningCode
    detail: str = ""


@dataclass(frozen=True)
class ImportLimits:
    """Пределы приёма: считаются по заявленным размерам и ещё раз по байтам, реально прочитанным при распаковке."""

    max_unpacked_bytes: int
    max_files: int = 50_000


@dataclass(frozen=True)
class ArchiveManifest:
    """Что архив говорит о проекте, не распаковываясь на том."""

    project_id: UUID
    name: str
    has_remote: bool
    files: int
    unpacked_bytes: int
    junk: int
    records: int
    prefix: str = ""


@dataclass(frozen=True)
class ExtractedProject:
    files: int
    bytes: int


class IProjectArchive(Protocol):
    def inspect(self, archive: Path, limits: ImportLimits) -> ArchiveManifest:
        """Проверяет архив целиком и читает project.json; бросает ProjectImportError."""
        ...

    def extract(
        self, archive: Path, manifest: ArchiveManifest, volume: IProjectVolume, folder: Path
    ) -> ExtractedProject:
        """Раскладывает проверенный архив в пустую папку проекта через `volume.safe_open`."""
        ...

    def harden_store(self, folder: Path) -> int:
        """Приводит хранилище версий к белому списку настроек; возвращает число убранного."""
        ...


class ILocalHistoryReader(Protocol):
    """Чтение и очистка чатов, приехавших в архиве. Читает форматом локальной Студии."""

    def has_chats(self, folder: Path) -> bool: ...

    async def transfer_chats(self, folder: Path, project_id: UUID, target: IChatRepository) -> int:
        """Переносит чаты в репозиторий сервера `target` (IChatRepository) и возвращает число чатов."""
        ...

    def discard_chats(self, folder: Path) -> None: ...


@dataclass
class ImportReport:
    project_id: UUID
    name: str
    id_regenerated: bool
    files: int
    bytes: int
    chats: int = 0
    warnings: list[ImportWarning] = field(default_factory=list)
