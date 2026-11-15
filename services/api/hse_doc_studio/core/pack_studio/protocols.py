"""Порты Студии шаблонов: хранилище рабочих пространств, права раздела, файлы и git рабочего пространства."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from hse_doc_studio.core.git_sync.entities import RemoteTarget
from hse_doc_studio.core.jobs.entities import JobSpec
from hse_doc_studio.core.jobs.protocols import IJobHooks
from hse_doc_studio.core.pack_studio.entities import (
    GrantSubjectKind,
    PackStudioGrant,
    PackTree,
    PackWorkspace,
    ReleasedVersions,
)
from hse_doc_studio.core.pack_studio.paths import VersionRef
from hse_doc_studio.core.pack_studio.preview import (
    MaterializedDoc,
    MaterializeRequest,
    PreviewBuild,
    PreviewInputs,
    VersionDescription,
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


YamlPath = tuple[str | int, ...]


class IYamlEditor(Protocol):
    """Точечные правки YAML по позициям узлов (D11): остальной текст, комментарии и выравнивание байт в байт.

    Невыполнимая правка (нет узла, значение не читается обратно) это `ValueError`.
    """

    def set_value(self, text: str, path: YamlPath, value: Any) -> str: ...
    def insert_item(self, text: str, path: YamlPath, index: int, value: Any) -> str: ...
    def delete(self, text: str, path: YamlPath) -> str: ...
    def move_item(self, text: str, path: YamlPath, src: int, dst: int) -> str: ...


# ── Предпросмотр (раздел 6, срез T7) ─────────────────────────────────────────


class IPackPreviewRenderer(Protocol):
    """Модель версии и синтетический проект. Разбор и рендер чужого пака идут в отдельном процессе с пределами
    (раздел 9): ошибка разбора это `PackStudioError(version_unreadable)`, ошибка рендера это `PreviewRenderError`."""

    async def inputs(self, root: Path, ref: VersionRef) -> PreviewInputs:
        """Дайджесты файлов версии, манифестов и примеров (в процессе api: только чтение байт, без разбора)."""
        ...

    async def describe(self, root: Path, ref: VersionRef) -> VersionDescription: ...

    async def materialize(
        self, root: Path, ref: VersionRef, request: MaterializeRequest, dest: Path
    ) -> MaterializedDoc: ...


@dataclass(frozen=True)
class CachedPreview:
    """Готовая сборка в кэше по ключу: PDF, журнал, якоря подписей, если шаблон их ставит."""

    key: str
    pages: int | None
    source_file: str
    has_anchors: bool


class IPreviewStore(Protocol):
    """Папки сборок, записи сборок, журналы и кэш PDF по ключу (`data_dir/pack-studio/previews`)."""

    def work_dir(self, build_id: UUID) -> Path:
        """Пустая папка синтетического проекта сборки (создаётся заново)."""
        ...

    def discard_work(self, build_id: UUID) -> None: ...
    def save(self, build: PreviewBuild) -> None: ...
    def load(self, build_id: UUID) -> PreviewBuild | None: ...
    def save_log(self, build_id: UUID, log: str) -> None: ...
    def read_log(self, build: PreviewBuild) -> str | None: ...
    def cached(self, key: str) -> CachedPreview | None: ...

    def keep(  # noqa: PLR0913 — что положить в кэш
        self, key: str, build_id: UUID, source_file: str, doc_id: str, log: str, pages: int | None
    ) -> CachedPreview | None:
        """Кладёт PDF (и якоря) из папки сборки в кэш; None, если PDF в папке нет."""
        ...

    def pdf(self, key: str) -> Path | None: ...
    def anchors(self, key: str) -> bytes | None: ...
    def prune(self) -> None:
        """Убирает старые записи, журналы, брошенные папки сборок и лишние записи кэша."""
        ...


class IPreviewDispatcher(Protocol):
    """Задачи `compile` сборок предпросмотра: обычная машина сборок (встроенный раннер локально, очередь и раннеры
    на сервере), но папка синтетического проекта живёт вне тома проектов."""

    async def preflight(self, spec: JobSpec) -> None: ...
    def submit(self, spec: JobSpec, hooks: IJobHooks) -> None: ...
    async def cancel(self, job_id: UUID) -> bool: ...
    def is_active(self, job_id: UUID) -> bool: ...
