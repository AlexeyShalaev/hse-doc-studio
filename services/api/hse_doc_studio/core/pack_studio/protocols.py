"""Порты Студии шаблонов: хранилище рабочих пространств, права раздела, файлы и git рабочего пространства."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from hse_doc_studio.core.git_sync.entities import RemoteTarget
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.pack_studio.entities import (
    GrantSubjectKind,
    PackStudioGrant,
    PackTree,
    PackWorkspace,
    ReleasedVersions,
)
from hse_doc_studio.core.pack_studio.git_flow import (
    CiReport,
    ForkRef,
    HostingRepo,
    MergeOutcome,
    PullRequestRef,
    PushOutcome,
    RepoPermissions,
    WorkGitStatus,
)
from hse_doc_studio.core.pack_studio.protection import Protection
from hse_doc_studio.core.vcs.entities import VcsAuthor


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

    # ── срез T6: ветка, коммит, отправка, слияние базы ──

    async def status(self, dirs: WorkspaceDirs, *, base_branch: str, packs_path: str) -> WorkGitStatus:
        """Ветка, вершина, правки после коммита и отличия от базы под папкой паков; без сети."""
        ...

    async def local_branches(self, dirs: WorkspaceDirs) -> tuple[str, ...]: ...

    async def create_branch(self, dirs: WorkspaceDirs, *, name: str) -> None:
        """Новая ветка на текущей вершине; правки на диске остаются как есть."""
        ...

    async def switch_branch(self, dirs: WorkspaceDirs, target: RemoteTarget, *, name: str, fetch: bool) -> str:
        """Переход на ветку (дерево чистое). `fetch`: ветки нет локально, она берётся с сервера. Возвращает вершину."""
        ...

    async def commit(self, dirs: WorkspaceDirs, *, packs_path: str, message: str, author: VcsAuthor) -> str | None:
        """Все правки под папкой паков одним коммитом от имени автора; None, если коммитить нечего."""
        ...

    async def push(
        self,
        dirs: WorkspaceDirs,
        target: RemoteTarget,
        *,
        branch: str,
        push_options: Sequence[str] = (),
    ) -> PushOutcome:
        """Рабочая ветка в `refs/heads/<branch>` адреса `target` (сам репозиторий или форк). Без принудительной."""
        ...

    async def merge_base(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str, author: VcsAuthor, message: str
    ) -> MergeOutcome:
        """Свежая база (уже выбранная) сливается в текущую ветку; конфликт отменяет слияние и называет файлы."""
        ...

    async def reset_to_base(self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str) -> str:
        """Дерево на вершину базы без ветки, правки на диске отбрасываются. Возвращает вершину."""
        ...

    async def base_registries(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str, paths: Sequence[str]
    ) -> dict[str, str]:
        """Тексты файлов базовой ветки по путям от корня репозитория (реестры выпусков для проверки 4.5)."""
        ...

    async def diff(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str, packs_path: str, max_bytes: int
    ) -> tuple[str, bool]:
        """Единый diff пространства от базы (коммиты и правки на диске) и признак, что он обрезан."""
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


# ── срез T6: проверки перед отправкой, хостинг, служебный доступ ─────────────


@dataclass(frozen=True)
class CheckFinding:
    """Находка `pack check` (4.4): путь от папки паков пространства."""

    severity: str
    check: str
    path: str
    message: str


@dataclass(frozen=True)
class VersionClassInfo:
    """Класс версии по классификатору (7.2) относительно предыдущей выпущенной."""

    path: str
    base: str
    minimum: str
    suggested: str
    by_number: str | None
    headline: Mapping[str, str]
    reasons: tuple[Mapping[str, str], ...]


@dataclass(frozen=True)
class PackCheckReport:
    findings: tuple[CheckFinding, ...] = ()
    classes: tuple[VersionClassInfo, ...] = ()

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    @property
    def ok(self) -> bool:
        return self.errors == 0


@dataclass(frozen=True)
class VersionNotes:
    """Заметки версии для описания PR: `changes` по языкам."""

    changes: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


class IPackChecker(Protocol):
    """`hse-doc-studio pack check` в процессе (T2): lint, `releases check`, схемы, классификатор, сверка с базой."""

    def check(self, root: Path, scopes: Sequence[str], base_registries: Mapping[str, str]) -> PackCheckReport:
        """`scopes` каталоги от папки паков (шаблоны и паки); `base_registries` тексты `releases.yaml` базы по
        пути каталога шаблона от папки паков (нет ключа: шаблона в базе нет)."""
        ...

    def notes(self, root: Path, version_dir: str) -> VersionNotes: ...


class IPackHosting(Protocol):
    """API хостинга git для рабочего пространства (D8, 4.4). Токен берётся по доступу цели и наружу не выходит.

    Отказ в правах на запрос на слияние это `PackStudioError(pr_permission_missing)`, сбой связи `GitSyncError`.
    """

    async def permissions(self, repo: HostingRepo, target: RemoteTarget) -> RepoPermissions: ...

    async def fork(self, repo: HostingRepo, target: RemoteTarget, *, create: bool) -> ForkRef | None:
        """Форк пользователя токена (GitHub): найденный или созданный; None, если его нет и создать нельзя."""
        ...

    async def open_pull_request(
        self, repo: HostingRepo, target: RemoteTarget, *, head: str, base: str, title: str, body: str
    ) -> PullRequestRef:
        """GitHub REST `POST /repos/{o}/{r}/pulls`; уже открытый из той же ветки находится и возвращается."""
        ...

    async def ci_status(self, repo: HostingRepo, target: RemoteTarget, *, sha: str, branch: str | None) -> CiReport: ...


@dataclass(frozen=True)
class ServiceAccess:
    """Служебный доступ репозитория паков (4.2): токен уровня установки для методистов без аккаунта на хостинге."""

    id: UUID
    url: str
    host: str
    port: int | None
    repo_key: str
    label: str
    created_at: datetime
    token_family: str | None = None
    created_by: str | None = None
    created_by_name: str | None = None


class IServiceAccessRepository(Protocol):
    """Служебные доступы (только сервер). Секрет шифруется и наружу отдаётся только `secret`."""

    async def list(self) -> list[ServiceAccess]: ...
    async def get(self, access_id: UUID) -> ServiceAccess | None: ...
    async def find(self, repo_key: str) -> ServiceAccess | None: ...
    async def add(self, access: ServiceAccess, secret: Secret) -> bool:
        """False, если у репозитория служебный доступ уже есть."""
        ...

    async def delete(self, access_id: UUID) -> ServiceAccess | None: ...
    async def secret(self, access_id: UUID) -> Secret | None: ...
