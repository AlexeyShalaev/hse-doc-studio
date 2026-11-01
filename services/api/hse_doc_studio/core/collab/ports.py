"""Порты совместной правки: текст файла проекта, сброс комнат перед операциями над папкой, события комнаты."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class TextSnapshot:
    text: str
    etag: str


class ITextStore(Protocol):
    """Текст файла проекта. Запись идёт тем же путём, что сохранение из редактора: блокировка папки, квота,
    правочный коммит. Файл не текстовый (не UTF-8) или больше предела: чтение даёт None."""

    async def read(self, project_id: UUID, path: str) -> TextSnapshot | None: ...

    async def etag(self, project_id: UUID, path: str) -> str | None:
        """Версия файла на диске; None, если файла нет."""
        ...

    async def write(self, project_id: UUID, path: str, text: str) -> str:
        """Записывает файл и возвращает его новую версию."""
        ...

    async def record_external(self, project_id: UUID, path: str) -> None:
        """Фиксирует правочным коммитом то, что лежит на диске сейчас: чужую версию перед слиянием."""
        ...

    async def folder(self, project_id: UUID) -> Path | None:
        """Папка проекта на сервере; None, если проекта нет."""
        ...


class IFolderFlush(Protocol):
    """Сбрасывает несохранённый текст открытых комнат папки на диск перед операцией над ней."""

    async def flush_folder(self, folder: Path) -> None: ...
