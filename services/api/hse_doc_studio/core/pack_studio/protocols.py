"""Порты Студии шаблонов: хранилище рабочих пространств, права раздела, файлы и git рабочего пространства."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import UUID

from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.core.git_sync.entities import RemoteTarget
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.jobs.entities import JobSpec
from hse_doc_studio.core.jobs.protocols import IJobHooks
from hse_doc_studio.core.pack_studio.checks_form import ChecksConfig, ChecksFileView, ChecksOp
from hse_doc_studio.core.pack_studio.entities import (
    GrantSubjectKind,
    PackDiagnostic,
    PackEditorHints,
    PackStudioGrant,
    PackTree,
    PackWorkspace,
    ReleasedVersions,
)
from hse_doc_studio.core.pack_studio.git_flow import (
    CiReport,
    ForkRef,
    HostingAccount,
    HostingRepo,
    MergeOutcome,
    PullRequestRef,
    PullRequestState,
    PushOutcome,
    RepoPermissions,
    WorkGitStatus,
)
from hse_doc_studio.core.pack_studio.model import FileChange, LibraryDocument, ModelAction, VersionModel
from hse_doc_studio.core.pack_studio.outcome.lint import LintFinding
from hse_doc_studio.core.pack_studio.paths import VersionRef
from hse_doc_studio.core.pack_studio.places import PlaceOp, VersionPlaces
from hse_doc_studio.core.pack_studio.preview import (
    MaterializedDoc,
    MaterializeRequest,
    PreviewBuild,
    PreviewCheck,
    PreviewInputs,
    VersionDescription,
)
from hse_doc_studio.core.pack_studio.protection import Protection
from hse_doc_studio.core.pack_studio.scaffold import (
    CopySource,
    NewPack,
    NewTemplate,
    ScaffoldResult,
    ScaffoldSource,
    SourcePack,
)
from hse_doc_studio.core.pack_studio.sign_check import PageLayout, Rect
from hse_doc_studio.core.pack_studio.submission import SubmissionOp, VersionSubmission
from hse_doc_studio.core.pack_studio.versions import (
    BaseRegistry,
    CreatedVersion,
    MovedVersion,
    NewVersionOptions,
    ReleasedVersionView,
    TemplateRef,
    VersionNotesInput,
    VersionState,
)
from hse_doc_studio.core.signatures.anchors import BuildAnchors
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

    def version_manifests(self, root: Path, ref: VersionRef, *, max_bytes: int) -> dict[str, bytes]:
        """Тексты манифестов версии для `revision` результата (срез O2): `version.yaml` и `files/<документ>/doc.yaml`
        (пути от каталога версии), файлы наборов данных `examples/<имя>` (от каталога шаблона). Ссылки и файлы больше
        `max_bytes` пропускаются; нет каталога версии: `version_not_found`."""
        ...

    def template_files(self, root: Path, pack: str, template: str, folder: str, *, max_bytes: int) -> dict[str, bytes]:
        """Обычные файлы папки `folder` шаблона (`scenarios`, `examples`) без вложенных папок и ссылок:
        имя -> содержимое. Нет папки: пусто; файл больше `max_bytes` пропускается (срез O6)."""
        ...

    def template_versions(self, root: Path, pack: str, template: str) -> tuple[str, ...]:
        """Имена каталогов версий шаблона на диске; нет шаблона: `version_not_found` (срез O6)."""
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

    async def status(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str, packs_path: str
    ) -> WorkGitStatus:
        """Ветка, вершина, правки после коммита и свои отличия под папкой паков: от точки расхождения с базой
        (`base...HEAD` плюс правки на диске), поэтому отставание от базы правками не считается. Сеть (доступ `target`)
        только чтобы догрузить блоб частичного клона, без которого локальный git не может ответить."""
        ...

    async def local_branches(self, dirs: WorkspaceDirs) -> tuple[str, ...]: ...

    async def create_branch(self, dirs: WorkspaceDirs, *, name: str) -> None:
        """Новая ветка на текущей вершине; правки на диске остаются как есть."""
        ...

    async def switch_branch(self, dirs: WorkspaceDirs, target: RemoteTarget, *, name: str, fetch: bool) -> str:
        """Переход на ветку (дерево чистое). `fetch`: ветки нет локально, она берётся с сервера. Возвращает вершину."""
        ...

    async def commit(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, packs_path: str, message: str, author: VcsAuthor
    ) -> str | None:
        """Все правки под папкой паков одним коммитом от имени автора; None, если коммитить нечего. `target` как у
        `status`: только для догрузки недостающего блоба."""
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

    async def advance_to_base(self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str) -> str:
        """Чистое дерево без ветки на свежую вершину базы (уже выбранной), без принудительного checkout: правку,
        которую он перезаписал бы, git не трогает и отказывает. Возвращает вершину."""
        ...

    async def base_registries(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str, paths: Sequence[str]
    ) -> dict[str, str]:
        """Тексты файлов базовой ветки по путям от корня репозитория (реестры выпусков для проверки 4.5)."""
        ...

    async def diff(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str, packs_path: str, max_bytes: int
    ) -> tuple[str, bool]:
        """Единый diff своих правок от точки расхождения с базой (коммиты и правки на диске) и признак обрезки."""
        ...

    # ── срез T10: мастер «Новая версия» ──

    async def restore_from_base(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str, paths: Sequence[str]
    ) -> None:
        """Каталоги рабочего дерева (пути от корня репозитория) ровно как в базовой ветке: лишние файлы уходят,
        содержимое берётся из базы (блобы частичного клона подгружаются по сети). Коммит не делается."""
        ...

    async def branch_paths(self, dirs: WorkspaceDirs, *, base_branch: str) -> tuple[str, ...]:
        """Срез T22: пути от корня репозитория, которые коммиты рабочей ветки меняют от точки расхождения с базой
        (`base...HEAD`), без фильтра по папке паков: так сервер видит правки вне неё."""
        ...

    # ── срез O2: чтение версии из коммита без checkout ──

    async def revision_sha(self, dirs: WorkspaceDirs, *, name: GitRevisionName, base_branch: str) -> str | None:
        """Коммит `head` (последний коммит ветки) или `base` (вершина базовой ветки); None, если такого коммита нет.
        Только деревья и ссылки, блобы не читаются."""
        ...

    async def revision_files(
        self,
        dirs: WorkspaceDirs,
        target: RemoteTarget,
        *,
        sha: str,
        prefixes: Sequence[str],
        max_files: int,
        max_bytes: int,
    ) -> dict[str, bytes]:
        """Обычные файлы коммита `sha` под путями `prefixes` (от корня репозитория): путь -> содержимое как в git.
        Недостающие блобы частичного клона догружаются сетью с доступом `target`; больше `max_files` файлов или
        `max_bytes` байт это `workspace_too_large`."""
        ...


# Откуда читается версия из git (срез O2): последний коммит ветки или вершина базовой ветки.
GitRevisionName = Literal["head", "base"]

YamlPath = tuple[str | int, ...]


class IYamlEditor(Protocol):
    """Точечные правки YAML по позициям узлов (D11): остальной текст, комментарии и выравнивание байт в байт.

    Невыполнимая правка (нет узла, значение не читается обратно) это `ValueError`.
    """

    def set_value(self, text: str, path: YamlPath, value: Any) -> str: ...
    def insert_item(self, text: str, path: YamlPath, index: int, value: Any) -> str: ...
    def delete(self, text: str, path: YamlPath) -> str: ...
    def move_item(self, text: str, path: YamlPath, src: int, dst: int) -> str: ...


class IPackPlaces(Protocol):
    """Места подписей и метки даты в `version.yaml` версии (срез T9): модель и правки точечными правками YAML.

    `document` id документа сборки предпросмотра, `anchors` её якоря (None: неизвестны). Невыполнимая правка это
    `PlaceEditError`, нечитаемый манифест это `ValueError`.
    """

    def describe(self, text: str, *, document: str | None, anchors: BuildAnchors | None) -> VersionPlaces: ...

    def apply(
        self, text: str, ops: Sequence[PlaceOp], *, document: str | None, anchors: BuildAnchors | None
    ) -> str: ...


class IPackVersionModel(Protocol):
    """Модель версии для форм (срезы T11 и T12): манифесты как данные, файлы документов, где печатается поле.

    Пути от папки паков `root` уже прошли проверку; `version_dir` это каталог версии. Невыполнимая правка или
    операция это `ModelEditError`, нечитаемый манифест версии `ValueError`.
    """

    def describe(self, root: Path, version_dir: str) -> VersionModel: ...

    def check_edit(self, root: Path, version_dir: str, file: str, before: str, after: str) -> None:
        """Правка `file` (от каталога версии: `version.yaml`, `files/<id>/doc.yaml`) не добавила находок лоадера
        и схемы; иначе `ModelEditError` с первой новой находкой."""
        ...

    def plan(self, root: Path, version_dir: str, action: ModelAction) -> tuple[FileChange, ...]:
        """Записи и удаления файлов операции; сами файлы не трогает."""
        ...

    def library(self, root: Path) -> tuple[LibraryDocument, ...]:
        """Документы-заготовки: последняя версия каждого шаблона пространства."""
        ...


class IPackSubmission(Protocol):
    """Профили сдачи и порядок маршрута в `version.yaml` (срез T13): модель и правки точечными правками YAML.

    Невыполнимая правка или правка, после которой лоадер или схема не поймут профиль, это `SubmissionEditError`;
    нечитаемый манифест это `ValueError`.
    """

    def describe(self, text: str) -> VersionSubmission: ...

    def apply(self, text: str, ops: Sequence[SubmissionOp]) -> str: ...


class IPackChecksForm(Protocol):
    """Файлы правил `checks/*.yaml` и `checks_version` версии (срез T14): модель и правки точечными правками YAML.

    `prefix` это имя файла без `.yaml` (префикс id правил). Невыполнимая правка или правка, после которой лоадер
    выбросит правило, это `ChecksEditError`; нечитаемый файл это `ValueError`.
    """

    def describe_file(self, text: str, prefix: str) -> ChecksFileView: ...

    def apply_file(self, text: str, ops: Sequence[ChecksOp]) -> str: ...

    def describe_config(self, text: str) -> ChecksConfig: ...

    def apply_config(self, text: str, config: ChecksConfig) -> str: ...


class IPackInspector(Protocol):
    """Проверки и подсказки редактора поверх файлов рабочего пространства, в процессе и без TeX (срез T8).

    Пути от папки паков `root` уже прошли `validate_rel_path`. Jinja пака только разбирается (песочница T3), не
    исполняется.
    """

    def lint_version(self, root: Path, version_dir: str, *, released: bool) -> tuple[PackDiagnostic, ...]:
        """`pack_lint` версии и схемы её манифестов (`version.yaml`, `doc.yaml`); у выпущенной ошибки схемы это
        предупреждения: её каталог неизменен, исправляется новой версией."""
        ...

    def check_manifest(self, root: Path, path: str) -> tuple[PackDiagnostic, ...] | None:
        """Схема манифеста вне версии (`pack.yaml`, `template.yaml`, `releases.yaml`); None: файл не манифест."""
        ...

    def hints(self, root: Path, version_dir: str) -> PackEditorHints:
        """Поля анкеты и макросы `\\hse...` динамических инклудов версии для автодополнения."""
        ...


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

    async def pull_request_state(self, repo: HostingRepo, target: RemoteTarget, number: int) -> PullRequestState | None:
        """Срез T22: открыт, слит или закрыт PR (GitHub); None, если хостинг не сказал."""
        ...

    async def account(self, repo: HostingRepo, target: RemoteTarget) -> HostingAccount | None:
        """Чей токен цели (`GET /user` GitHub, проверка служебного доступа); None, если хостинг его не принял или не
        умеет."""
        ...


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


# ── Предпросмотр (раздел 6, срез T7) ─────────────────────────────────────────


class IPackPreviewRenderer(Protocol):
    """Модель версии и синтетический проект. Разбор и рендер чужого пака идут в отдельном процессе с пределами
    (раздел 9): ошибка разбора это `PackStudioError(version_unreadable)`, ошибка рендера это `PreviewRenderError`."""

    async def inputs(self, root: Path, ref: VersionRef) -> PreviewInputs:
        """Дайджесты файлов версии, манифестов и примеров (в процессе api: только чтение байт, без разбора)."""
        ...

    async def describe(self, root: Path, ref: VersionRef) -> VersionDescription: ...

    async def describe_files(self, files: Mapping[str, bytes], ref: VersionRef) -> VersionDescription:
        """Модель версии по файлам, прочитанным из git (пути от папки паков), без checkout: файлы кладутся во
        временную папку, дальше тот же разбор в отдельном процессе, что у рабочего дерева."""
        ...

    async def materialize(
        self, root: Path, ref: VersionRef, request: MaterializeRequest, dest: Path
    ) -> MaterializedDoc: ...


class IPackJinjaProbe(Protocol):
    """Правила линтера результата по файлам шаблонов (`jinja-fail-open`, `jinja-unknown-meta-key`): рендер шаблонов
    рабочего дерева в отдельном процессе с пределами времени и памяти. Сбой процесса это `PreviewRenderError`."""

    async def probe(self, root: Path, ref: VersionRef, today: date) -> tuple[LintFinding, ...]: ...


@dataclass(frozen=True)
class CachedPreview:
    """Готовая сборка в кэше по ключу: PDF, журнал, якоря подписей, если шаблон их ставит."""

    key: str
    pages: int | None
    source_file: str
    has_anchors: bool
    # Находки проверок, если сборка шла с ними (срез T14).
    checks: tuple[PreviewCheck, ...] | None = None


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
        self,
        key: str,
        build_id: UUID,
        source_file: str,
        doc_id: str,
        log: str,
        pages: int | None,
        checks: tuple[PreviewCheck, ...] | None = None,
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


# ── Мастер «Новая версия» (раздел 7, срез T10) ───────────────────────────────


class IPackVersions(Protocol):
    """Копия, номер, класс, заметки и выпуск версии шаблона над папкой паков `root` (в процессе, без TeX).

    `registry` выпущенные в базовой ветке версии шаблона (D10). Отказы это `PackStudioError`: `version_not_found`,
    `version_taken` (с `suggested`), `version_number_invalid`, `class_softer_than_changes`, `lint_failed`.
    """

    def options(self, root: Path, template: TemplateRef, registry: BaseRegistry) -> NewVersionOptions: ...

    def state(self, root: Path, ref: VersionRef, registry: BaseRegistry) -> VersionState: ...

    def create(  # noqa: PLR0913 — шаг 1 мастера
        self,
        root: Path,
        template: TemplateRef,
        *,
        base: str | None,
        to: str | None,
        update_class: TemplateUpdateClass | None,
        registry: BaseRegistry,
        today: date,
    ) -> CreatedVersion: ...

    def save_notes(self, root: Path, ref: VersionRef, notes: VersionNotesInput) -> None: ...

    def renumber(self, root: Path, ref: VersionRef, to: str, registry: BaseRegistry, today: date) -> MovedVersion:
        """Черновик на другой номер; запись выпуска в ветке снимается."""
        ...

    def move_edits(
        self, root: Path, ref: VersionRef, to: str | None, registry: BaseRegistry, today: date
    ) -> MovedVersion:
        """Изменённый выпущенный каталог копируется в новый черновик, реестр рабочего дерева берёт записи базы."""
        ...

    def release(  # noqa: PLR0913 — шаг «Выпустить»
        self,
        root: Path,
        ref: VersionRef,
        *,
        kind: TemplateUpdateClass | None,
        set_default: bool,
        registry: BaseRegistry,
        today: date,
    ) -> ReleasedVersionView: ...


class MarkKind(StrEnum):
    """Что нарисовано поверх страницы: рамка подписи, метка даты, линия якоря, предложенная рамка, рамка с ошибкой."""

    sign = "sign"
    date = "date"
    anchor = "anchor"
    suggested = "suggested"
    problem = "problem"


@dataclass(frozen=True)
class Mark:
    kind: MarkKind
    rect: Rect
    label: str = ""


class IPdfPages(Protocol):
    """Страницы PDF предпросмотра для мест подписей (pack-studio-mcp.md, 4.5): разбор, растр и картинка с рамками.

    Номера страниц с единицы, всё в мм от левого верхнего угла. `ink` доля тёмных пикселей под рамкой без линий и без
    закрашенных `blank`; None, если страницы нет.
    """

    def page_count(self, data: bytes) -> int: ...

    def layouts(self, data: bytes, pages: Sequence[int]) -> dict[int, PageLayout]: ...

    def ink(self, data: bytes, boxes: Sequence[tuple[int, Rect, Sequence[Rect]]], dpi: int) -> list[float | None]: ...

    def render(self, data: bytes, page: int, dpi: int, marks: Sequence[Mark]) -> bytes: ...


class IPdfTextReader(Protocol):
    """Текст PDF сборки предпросмотра по страницам (для MCP `pack_preview_read`): текст и число страниц."""

    def read(self, data: bytes, *, pages: Sequence[int] | None, max_chars: int) -> tuple[str, int]: ...


class IPackScaffolder(Protocol):
    """Пак и шаблон с нуля над папкой паков `root` (раздел 8, срез T15): заготовка «Минимальный» или копия версии.

    Каталог собирается во временной папке рядом и переносится целиком: при отказе ничего не остаётся. Отказы это
    `PackStudioError`: `pack_id_taken`, `template_id_taken`, `pack_not_found`, `version_not_found`.
    """

    def sources(self, root: Path) -> tuple[SourcePack, ...]:
        """Паки пространства с шаблонами и версиями: из чего можно сделать копию."""
        ...

    def pack_dirs(self, root: Path) -> frozenset[str]:
        """Папки паков пространства в свёрнутом регистре (заняты для нового id)."""
        ...

    def workspace_source(self, root: Path, source: ScaffoldSource) -> CopySource: ...

    def create_pack(
        self, root: Path, pack: NewPack, *, version: str, today: date, source: CopySource | None
    ) -> ScaffoldResult: ...

    def create_template(  # noqa: PLR0913 — пак, шаблон, номер и источник
        self, root: Path, pack: str, template: NewTemplate, *, version: str, today: date, source: CopySource | None
    ) -> ScaffoldResult: ...
