"""Том проектов сервера: папка проекта это projects_root/<project_id>, имя папки равно id.

Все серверные чтения и записи файлов проекта идут через `safe_open`: путь внутри проекта
проходит по компонентам без перехода по симлинкам, поэтому ссылка внутри проекта не выведет наружу.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO, Literal, Protocol
from uuid import UUID

OpenMode = Literal["rb", "wb", "ab", "r+b"]


class UnsafePathError(ValueError):
    """Путь выходит за том или проходит через симлинк."""


class IProjectVolume(Protocol):
    @property
    def root(self) -> Path: ...

    def path_of(self, project_id: UUID | str) -> Path:
        """Папка проекта; id обязан быть каноническим UUID, иначе UnsafePathError."""
        ...

    def id_of(self, folder: Path) -> UUID:
        """Id проекта по его папке без обращения к БД; чужая папка, симлинк или не-UUID дают UnsafePathError."""
        ...

    def resolve_workspace(self, workspace_path: str) -> Path:
        """Папка по относительному workspace_path из таблицы projects."""
        ...

    def exists(self, project_id: UUID | str) -> bool: ...

    def allocate(self, project_id: UUID | str) -> Path:
        """Создаёт пустую папку проекта; повторное выделение того же id отказывает FileExistsError."""
        ...

    def remove(self, project_id: UUID | str) -> None:
        """Удаляет папку проекта целиком; симлинк внутри удаляется как ссылка, цель не трогается."""
        ...

    def safe_open(self, folder: Path, relative: str, mode: OpenMode = "rb", *, make_parents: bool = False) -> IO[bytes]:
        """Открывает файл внутри папки проекта, не следуя симлинкам ни в одном компоненте пути."""
        ...
