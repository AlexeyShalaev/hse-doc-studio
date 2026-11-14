"""Порты Студии шаблонов: хранилище рабочих пространств, права раздела, файлы и git рабочего пространства."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.git_sync.entities import RemoteTarget
from hse_doc_studio.core.pack_studio.entities import (
    GrantSubjectKind,
    PackStudioGrant,
    PackTree,
    PackWorkspace,
    ReleasedVersions,
)
from hse_doc_studio.core.pack_studio.protection import Protection


class IPackWorkspaceRepository(Protocol):
    """Рабочие пространства. `owner_id` None в локальной установке (один человек), иначе id пользователя:
    чужое пространство неотличимо от несуществующего."""

    async def list(self, owner_id: str | None) -> list[PackWorkspace]: ...
    async def get(self, workspace_id: UUID, owner_id: str | None) -> PackWorkspace | None: ...
    async def count(self, owner_id: str | None) -> int: ...
    async def add(self, workspace: PackWorkspace) -> None: ...
    async def update(self, workspace: PackWorkspace) -> None:
        """Перезаписывает строку; удалённое тем временем пространство не воскрешает."""
        ...

    async def delete(self, workspace_id: UUID, owner_id: str | None) -> bool: ...


class IPackStudioGrantRepository(Protocol):
    """Право «Автор шаблонов» людям и группам организаций (сервер)."""

    async def has_grant(self, user_id: str) -> bool:
        """Право есть у самого человека или у одной из его групп."""
        ...

    async def list(self) -> list[PackStudioGrant]: ...
    async def subject_exists(self, kind: GrantSubjectKind, subject_id: str) -> bool: ...
    async def add(self, grant: PackStudioGrant) -> bool:
        """False, если у этого человека или группы право уже есть."""
        ...

    async def remove(self, grant_id: UUID) -> PackStudioGrant | None: ...


class IPackStudioSectionStore(Protocol):
    """Сохранённый выбор «раздел включён»: локально в настройках, на сервере в настройках установки."""

    async def get(self) -> bool | None: ...
    async def set(self, enabled: bool) -> None: ...


@dataclass(frozen=True)
class WorkspaceLimits:
    max_file_bytes: int
    max_read_bytes: int
    max_clone_bytes: int
    max_tree_bytes: int
    max_tree_files: int


class IPackWorkspaceFiles(Protocol):
    """Файлы под папкой паков `root`. Путь уже прошёл `validate_rel_path`; символьные ссылки на пути
    отвергаются (`path_not_allowed`), запись атомарная."""

    def read(self, root: Path, path: str, *, max_bytes: int) -> bytes: ...
    def write(self, root: Path, path: str, content: bytes) -> None: ...
    def delete(self, root: Path, path: str) -> bool:
        """True, если удалена папка (вместе с содержимым), False для файла; нет пути: `file_not_found`."""
        ...

    def is_dir(self, root: Path, path: str) -> bool: ...
    def registries(self, root: Path) -> tuple[str, ...]: ...
    def released_on_disk(self, root: Path) -> ReleasedVersions: ...
    def tree(self, root: Path, protection: Protection, *, max_files: int) -> PackTree: ...
    def check_packs_root(self, root: Path) -> None:
        """Папка паков пуста или в ней есть хотя бы один пак (`pack.yaml`); иначе `not_a_pack_repo`."""
        ...

    def measure(self, root: Path, limits: WorkspaceLimits) -> None:
        """`workspace_too_large`, если под папкой паков больше файлов или байт, чем позволено."""
        ...


@dataclass(frozen=True)
class WorkspaceDirs:
    """Папки git-пространства: `git` хранилище (вне дерева), `tree` рабочее дерево с частичной выборкой."""

    root: Path
    git: Path
    tree: Path


ProgressFn = Callable[[float, str], None]


class IPackWorkspaceGit(Protocol):
    """Частичный закалённый клон репозитория паков поверх сетевого git Студии (`IGitRemoteRunner`)."""

    async def clone(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, branch: str, packs_path: str, limits: WorkspaceLimits
    ) -> str:
        """Пустое хранилище, выборка без блобов, разреженное дерево только с папкой паков. Возвращает вершину базы."""
        ...

    async def fetch(self, dirs: WorkspaceDirs, target: RemoteTarget, *, branch: str, limits: WorkspaceLimits) -> str:
        """Свежая вершина базовой ветки в `refs/remotes/origin/<ветка>`; рабочее дерево не трогается."""
        ...

    async def released(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, branch: str, packs_path: str
    ) -> ReleasedVersions:
        """Выпущенные версии по реестрам базовой ветки (D10)."""
        ...
