"""Клонирование проекта из удалённого репозитория в новую папку.

Папка проверяется до первой сетевой команды, а скачанное дерево до того, как оно попадёт в папку: если
в вершине ветки нет проекта Студии, лежит чужой путь или такой проект уже зарегистрирован, рабочее дерево
остаётся нетронутым. Операция идёт в фоне (фазы download, verify, register); при любом отказе и при отмене
убирается только то, что создала она сама: папка, которой не было, или лишнее в пустой папке с одними
скрытыми файлами. Папку с чужими файлами клонирование не принимает вовсе.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.git_sync.entities import (
    CloneResult,
    CloneWarningCode,
    GitOperation,
    GitOperationError,
    OperationKind,
    OperationPhase,
    OperationStatus,
    RemoteTarget,
    SchemaAccess,
    StoreRemoteConfig,
    SyncState,
    SyncWarning,
    TreeEntry,
)
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.incoming import ensure_incoming_fits
from hse_doc_studio.core.git_sync.merge.paths import collision_groups, is_safe_entry
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import (
    IGitCloneStore,
    IGitCredentialRepository,
    IGitOperationRegistry,
    IGitRemoteRegistry,
    IGitRepoReader,
    IGitSyncStateRepository,
    IGitTransport,
    ILocalAuthorProfile,
    IRemoteProjectCheck,
)
from hse_doc_studio.core.git_sync.remote_project import (
    PROJECT_FILE,
    RemoteProject,
    is_loadable_project,
    parse_remote_project,
    remote_required_studio,
    remote_schema_access,
)
from hse_doc_studio.core.git_sync.url import RemoteKind, RemoteUrl, parse_remote_url
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import IProjectRepository, ITemplateRepository
from hse_doc_studio.core.vcs.constants import vcs_exclude_for
from hse_doc_studio.use_cases.git_sync.blocking import finish_before_cancel
from hse_doc_studio.use_cases.git_sync.probe_remote import (
    choose_remote_branch,
    raise_probe_error,
    require_http_consent,
    valid_branch,
)
from hse_doc_studio.use_cases.git_sync.status import TRACKING_PREFIX
from hse_doc_studio.use_cases.template_update.base_service import TemplateBaseService

logger = structlog.get_logger()

# Проверка «проект уже открыт» и запись в список идут одним шагом в цикле; замок свой на каждый цикл событий.
_REGISTER_LOCKS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = weakref.WeakKeyDictionary()


def _register_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _REGISTER_LOCKS.get(loop)
    if lock is None:
        lock = _REGISTER_LOCKS[loop] = asyncio.Lock()
    return lock


_STUDIO_DIR = ".hse-studio"
_GITATTRIBUTES = ".gitattributes"
_LFS_FILTER = "filter=lfs"
_LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"
# Указатель LFS занимает около ста тридцати байт; файлы крупнее указателями быть не могут.
_LFS_POINTER_MAX_BYTES = 1024
_MAX_REPORTED_PATHS = 20


@dataclass
class CloneProjectInput:
    url: str
    folder: str
    credential_id: UUID | None = None
    branch: str | None = None
    # Имя нужно клиенту, чтобы предложить папку; проект называется так, как записан в репозитории.
    name: str | None = None
    # Согласие человека на открытый http для этого адреса; политика сервера его не заменяет.
    insecure_http: bool = False


@dataclass(frozen=True)
class CloneRemote:
    """Куда проект смотрит после клонирования; у проекта из переносного файла удалённого репозитория нет."""

    url: RemoteUrl
    credential_id: UUID | None
    insecure_http: bool


@dataclass(frozen=True)
class FolderPlan:
    """Что было на диске до клонирования: по этому и решается, что убирать при отказе."""

    folder: Path
    # Самый верхний каталог из созданных клонированием; None, если папка уже была.
    created_root: Path | None
    preexisting: frozenset[str]


@dataclass(frozen=True)
class _Verified:
    project: RemoteProject
    version: TemplateVersion | None
    access: SchemaAccess
    required_studio: str | None
    warnings: tuple[SyncWarning, ...]


_FOLDER_PROBLEMS: dict[str, tuple[str, str]] = {
    "not_a_folder": ("это не папка", "it is not a folder"),
    "not_empty": ("в ней есть файлы", "it contains files"),
    "has_project": ("в ней уже есть служебная папка проекта", "it already holds a project service folder"),
    "inside_project": ("она лежит внутри другого проекта", "it is inside another project"),
    "registered": ("в этой папке уже открыт проект", "a project is already open in this folder"),
    "collides": (
        "файлы репозитория совпали бы с тем, что в ней уже лежит",
        "the repository files would collide with what is already there",
    ),
}


def _folder_not_empty(reason: str, folder: Path) -> GitSyncError:
    ru, en = _FOLDER_PROBLEMS[reason]
    return GitSyncError(
        GitErrorCode.folder_not_empty,
        localized_error(
            f"Папка {folder} не подходит для проекта: {ru}", f"The folder {folder} cannot hold a project: {en}"
        ),
    )


def _is_lfs_pointer(content: bytes | None) -> bool:
    return content is not None and content.startswith(_LFS_POINTER_PREFIX)


class CloneProjectUC:
    def __init__(
        self,
        *,
        project_repo: IProjectRepository,
        locator: IProjectLocator,
        template_repo: ITemplateRepository,
        base_service: TemplateBaseService | None,
        clone_store: IGitCloneStore,
        state_repo: IGitSyncStateRepository,
        reader: IGitRepoReader,
        transport: IGitTransport,
        credentials: IGitCredentialRepository,
        profile: ILocalAuthorProfile,
        operations: IGitOperationRegistry,
        registry: IGitRemoteRegistry,
        policy: GitSyncPolicy,
        project_check: IRemoteProjectCheck,
        clone_timeout_s: float,
    ) -> None:
        self._projects = project_repo
        self._locator = locator
        self._templates = template_repo
        self._base_service = base_service
        self._store = clone_store
        self._states = state_repo
        self._reader = reader
        self._transport = transport
        self._credentials = credentials
        self._profile = profile
        self._operations = operations
        self._registry = registry
        self._policy = policy
        self._project_check = project_check
        self._timeout_s = clone_timeout_s

    async def execute(self, inp: CloneProjectInput) -> GitOperation:
        """Проверяет всё, что можно проверить без сети, и запускает клонирование в фоне."""
        url = await self._checked_input(inp)
        plan = await self.plan_folder(inp.folder)
        operation = self._operations.begin(OperationKind.clone, project_id=None, folder=plan.folder)
        self.start(operation.id, plan, lambda: self._clone(operation.id, url, plan, inp))
        return operation

    def start(self, operation_id: str, plan: FolderPlan, work: Callable[[], Awaitable[CloneResult]]) -> None:
        """Запускает клонирование в фоне. Итог и уборка папки при отказе или отмене остаются за ним."""
        task = asyncio.create_task(self._run(operation_id, plan, work))
        self._operations.attach_task(operation_id, task)

    async def _checked_input(self, inp: CloneProjectInput) -> RemoteUrl:
        self._policy.require_enabled()
        if self._profile.get() is None:
            raise git_error(GitErrorCode.profile_required)
        url = parse_remote_url(
            inp.url, allow_http=self._policy.allow_insecure_http, allow_local=self._policy.allow_local_remotes
        )
        require_http_consent(url, insecure_http=inp.insecure_http, local_ok=self._policy.allow_local_remotes)
        if inp.credential_id is not None and await self._credentials.get(inp.credential_id) is None:
            raise git_error(GitErrorCode.credentials_missing)
        if inp.branch:
            valid_branch(inp.branch)
        return url

    async def plan_folder(self, raw: str) -> FolderPlan:
        """Папка годится под новый проект: пуста (с точностью до скрытых файлов), не внутри проекта и не занята."""
        taken = {known.resolve() for known in await self._locator.list_all()}
        return await asyncio.to_thread(self._plan_folder, raw, taken)

    def _plan_folder(self, raw: str, taken: set[Path]) -> FolderPlan:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            raise ValueError(localized_error("Укажите полный путь к папке", "Specify the full path of the folder"))
        folder = path.resolve()
        self._check_folder_free(folder, taken)
        if folder.exists():
            return FolderPlan(folder, None, frozenset(entry.name for entry in folder.iterdir()))
        created_root = folder
        for parent in folder.parents:
            if parent.exists():
                break
            created_root = parent
        return FolderPlan(folder, created_root, frozenset())

    @staticmethod
    def _check_folder_free(folder: Path, taken: set[Path]) -> None:
        if folder.exists():
            if not folder.is_dir():
                raise _folder_not_empty("not_a_folder", folder)
            names = [entry.name for entry in folder.iterdir()]
            if not all(name.startswith(".") for name in names):
                raise _folder_not_empty("not_empty", folder)
            if _STUDIO_DIR in names:
                raise _folder_not_empty("has_project", folder)
        if any((parent / _STUDIO_DIR / "project.json").exists() for parent in folder.parents):
            raise _folder_not_empty("inside_project", folder)
        if folder in taken:
            raise _folder_not_empty("registered", folder)

    async def _run(self, operation_id: str, plan: FolderPlan, work: Callable[[], Awaitable[CloneResult]]) -> None:
        try:
            result = await work()
        except asyncio.CancelledError:
            await self._cleanup(plan)
            self._operations.finish(operation_id, status=OperationStatus.cancelled)
            raise
        except GitSyncError as exc:
            await self._cleanup(plan)
            self._operations.finish(
                operation_id, status=OperationStatus.failed, error=GitOperationError(exc.code, exc.detail)
            )
            return
        except Exception:
            logger.exception("git clone failed", folder=str(plan.folder))
            await self._cleanup(plan)
            error = git_error(GitErrorCode.git_error)
            self._operations.finish(
                operation_id, status=OperationStatus.failed, error=GitOperationError(error.code, error.detail)
            )
            return
        self._operations.finish(operation_id, result=result)

    async def _clone(self, operation_id: str, url: RemoteUrl, plan: FolderPlan, inp: CloneProjectInput) -> CloneResult:
        folder = plan.folder
        # Открытый http сюда доходит только с согласием человека (`_checked_input`): его и запоминает remote.
        target = RemoteTarget(url, inp.credential_id, insecure_http=url.kind is RemoteKind.http)
        self._operations.update(operation_id, phase=OperationPhase.download)
        probe = await self._transport.probe(target)
        raise_probe_error(probe)
        if probe.empty:
            raise git_error(GitErrorCode.not_a_studio_project)
        branch = valid_branch(choose_remote_branch(inp.branch, probe))
        if branch not in probe.branches:
            raise git_error(GitErrorCode.branch_missing)

        await finish_before_cancel(self.init_store, folder, branch)
        git_dir = folder / _STUDIO_DIR / "git"
        await self._transport.fetch(
            git_dir,
            target,
            branch=branch,
            timeout_s=self._timeout_s,
            on_progress=lambda percent, _line: self._operations.update(operation_id, percent=percent),
        )
        remote = CloneRemote(url, inp.credential_id, target.insecure_http)
        return await self.adopt(operation_id, plan, branch=branch, ref=f"{TRACKING_PREFIX}{branch}", remote=remote)

    async def adopt(
        self, operation_id: str, plan: FolderPlan, *, branch: str, ref: str, remote: CloneRemote | None
    ) -> CloneResult:
        """Скачанная ветка лежит в `ref` пустого хранилища: проверить её и развернуть проект в папке.

        Общее для клонирования с сервера и из переносного файла (`remote=None`: удалённого репозитория нет).
        """
        folder = plan.folder
        self._operations.update(operation_id, phase=OperationPhase.verify)
        known = await self._locator.list_all()
        verified = await asyncio.to_thread(self._verify, plan, ref, known)

        # Дальше дерево разворачивается в папку: прерывать это на полпути нельзя.
        self._operations.update(operation_id, phase=OperationPhase.register, cancellable=False)
        await asyncio.to_thread(self._store.write_exclude, folder, vcs_exclude_for(verified.version))
        await asyncio.to_thread(self._store.checkout, folder, branch, ref)
        if remote is not None:
            await asyncio.to_thread(
                self._persist, folder, remote.url, branch, remote.credential_id, remote.insecure_http
            )
        await self._register(folder, verified.project.id)
        await asyncio.to_thread(self._ensure_template_base, folder, verified)
        if remote is not None:
            self._registry.add(folder)
        logger.info(
            "project cloned",
            project_id=str(verified.project.id),
            host=remote.url.host if remote else None,
            branch=branch,
        )
        return CloneResult(
            project_id=verified.project.id,
            folder=str(folder),
            access=verified.access,
            required_studio=verified.required_studio,
            warnings=verified.warnings,
        )

    def init_store(self, folder: Path, branch: str) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self._store.init(folder, branch)

    def _verify(self, plan: FolderPlan, tracking: str, known: list[Path]) -> _Verified:
        """Проверка вершины скачанной ветки до того, как её дерево тронет папку."""
        folder = plan.folder
        if self._reader.rev_parse(folder, tracking) is None:
            raise git_error(GitErrorCode.branch_missing)
        raw = self._reader.read_files(folder, tracking, [PROJECT_FILE]).get(PROJECT_FILE)
        project = self._remote_project(raw)
        existing = self._registered_folder(project.id, known)
        if existing is not None:
            raise self._exists_error(existing)
        entries = self._reader.tree_entries(folder, tracking)
        self._check_paths(entries, plan)
        # Дерево разворачивается в папку целиком: гигантский блоб отвергается, пока он не лёг на диск.
        ensure_incoming_fits(entries, self._policy)
        version = self._templates.get_version(project.pack_id, project.template_id, project.template_version)
        warnings: list[SyncWarning] = []
        access = SchemaAccess(remote_schema_access(project.schema).value)
        if version is None:
            warnings.append(SyncWarning(CloneWarningCode.template_missing))
            if access is SchemaAccess.full:
                access = SchemaAccess.read_only
        lfs = self._lfs_pointers(folder, tracking, entries)
        if lfs:
            warnings.append(SyncWarning(CloneWarningCode.lfs_pointers, lfs))
        return _Verified(
            project=project,
            version=version,
            access=access,
            required_studio=remote_required_studio(project, template_available=version is not None),
            warnings=tuple(warnings),
        )

    def _remote_project(self, raw: bytes | None) -> RemoteProject:
        project = parse_remote_project(raw) if raw is not None else None
        if raw is None or project is None:
            raise git_error(GitErrorCode.not_a_studio_project)
        if remote_schema_access(project.schema) is SchemaAccess.full and not is_loadable_project(
            raw, self._project_check
        ):
            # Данные схемы этой Студии, которые загрузчик не разберёт: после клонирования проект не открылся бы.
            raise git_error(GitErrorCode.not_a_studio_project)
        return project

    async def _register(self, folder: Path, project_id: UUID) -> None:
        """Проверка «такой проект уже открыт» и запись в список одним шагом.

        Два клонирования одного репозитория в разные папки оба проходили проверку в `_verify`, пока ни одно не
        успело записаться, и в списке оказывались две папки с одним id: поиск по id попадал в любую из них.
        """
        async with _register_lock():
            known = await self._locator.list_all()
            existing = await asyncio.to_thread(self._registered_folder, project_id, known)
            if existing is not None:
                raise self._exists_error(existing)
            await self._locator.register(folder)

    @staticmethod
    def _exists_error(existing: Path) -> GitSyncError:
        return GitSyncError(
            GitErrorCode.project_exists,
            localized_error(
                f"Этот проект уже открыт в Студии: {existing}",
                f"This project is already open in the Studio: {existing}",
            ),
            folder=str(existing),
        )

    def _registered_folder(self, project_id: UUID, folders: list[Path]) -> Path | None:
        for known in folders:
            existing = self._projects.get(known)
            if existing is not None and existing.id == project_id:
                return known
        return None

    @staticmethod
    def _check_paths(entries: list[TreeEntry], plan: FolderPlan) -> None:
        """Чужое дерево не должно записать ничего за пределы проекта, в служебные каталоги и поверх чужих файлов."""
        unsafe = [entry.path for entry in entries if not is_safe_entry(entry.path, entry.mode)]
        if unsafe:
            shown = ", ".join(unsafe[:_MAX_REPORTED_PATHS])
            raise git_error(
                GitErrorCode.git_error,
                tail=localized_error(
                    f"В репозитории есть небезопасные пути или ссылки: {shown}",
                    f"The repository contains unsafe paths or links: {shown}",
                ),
            )
        top_level = {entry.path.split("/", 1)[0] for entry in entries}
        if top_level & plan.preexisting:
            raise _folder_not_empty("collides", plan.folder)
        CloneProjectUC._check_name_collisions(entries, plan.folder)

    @staticmethod
    def _check_name_collisions(entries: list[TreeEntry], folder: Path) -> None:
        """Имена, которые эта файловая система считает одним файлом, при разворачивании дерева слились бы.

        Один из двух файлов тихо не появился бы на диске, а дерево осталось бы с вечной правкой. Проверка идёт
        только на файловой системе, которая действительно сводит имена: на Linux оба файла лягут как есть.
        """
        groups = collision_groups(entry.path for entry in entries)
        if not groups or not _folds_names(folder):
            return
        shown = "; ".join(" и ".join(group) for group in groups[:_MAX_REPORTED_PATHS])
        shown_en = "; ".join(" and ".join(group) for group in groups[:_MAX_REPORTED_PATHS])
        raise git_error(
            GitErrorCode.git_error,
            tail=localized_error(
                f"В репозитории есть файлы, имена которых эта файловая система не различает: {shown}",
                f"The repository has files whose names this file system does not tell apart: {shown_en}",
            ),
        )

    def _lfs_pointers(self, folder: Path, tracking: str, entries: list[TreeEntry]) -> tuple[str, ...]:
        """Файлы, которые в репозитории заменены указателями LFS: Студия их не скачивает, и документ не соберётся."""
        attributes = self._reader.read_files(folder, tracking, [_GITATTRIBUTES]).get(_GITATTRIBUTES)
        if attributes is None or _LFS_FILTER not in attributes.decode("utf-8", errors="replace"):
            return ()
        small = [e.path for e in entries if e.kind == "blob" and (e.size or 0) <= _LFS_POINTER_MAX_BYTES]
        contents = self._reader.read_files(folder, tracking, small)
        return tuple(path for path in small if _is_lfs_pointer(contents.get(path)))[:_MAX_REPORTED_PATHS]

    def _persist(
        self, folder: Path, url: RemoteUrl, branch: str, credential_id: UUID | None, insecure_http: bool
    ) -> None:
        self._store.write_remote(
            folder,
            StoreRemoteConfig(
                url=url.display_url, credential_id=credential_id, local_branch=branch, remote_branch=branch
            ),
        )
        now = datetime.now(UTC)
        self._states.save(
            folder,
            SyncState(
                local_branch=branch,
                remote_branch=branch,
                credential_id=credential_id,
                insecure_http=insecure_http,
                last_fetch_at=now,
                last_fetch_ok_at=now,
            ),
        )

    def _ensure_template_base(self, folder: Path, verified: _Verified) -> None:
        """База обновления шаблона нужна первому обновлению, но не клонированию: сбой её не отменяет проект."""
        if self._base_service is None or verified.version is None or verified.access is not SchemaAccess.full:
            return
        try:
            project: Project | None = self._projects.get(folder)
            if project is not None:
                self._base_service.load_or_reconstruct(project, verified.version, persist=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("template base not recorded on clone", folder=str(folder), exc=str(exc))

    async def _cleanup(self, plan: FolderPlan) -> None:
        """Убирает созданное клонированием; всё, что было в папке до него, остаётся на месте."""
        try:
            await self._locator.unregister(plan.folder)
        except Exception as exc:  # noqa: BLE001 — уборка не должна терять исходную причину отказа
            logger.warning("clone cleanup: unregister failed", folder=str(plan.folder), exc=str(exc))
        self._remove_created(plan)

    @staticmethod
    def _remove_created(plan: FolderPlan) -> None:
        try:
            if plan.created_root is not None:
                # Убирается только то, что создала эта операция: соседний клон в той же новой папке не трогается.
                shutil.rmtree(plan.folder, ignore_errors=True)
                _remove_empty_parents(plan.folder.parent, plan.created_root)
                return
            if not plan.folder.is_dir():
                return
            for entry in plan.folder.iterdir():
                if entry.name in plan.preexisting:
                    continue
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("clone cleanup failed", folder=str(plan.folder), exc=str(exc))


def _remove_empty_parents(start: Path, root: Path) -> None:
    """Убирает пустые каталоги от `start` вверх до `root` включительно; непустой останавливает подъём."""
    current = start
    while current == root or root in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        if current == root:
            return
        current = current.parent


def _folds_names(folder: Path) -> bool:
    """Сводит ли файловая система под `folder` регистр или форму Юникода в именах (macOS, Windows)."""
    probe = folder / f".hse-name-probe-{uuid4().hex[:8]}-\u00e9a"
    try:
        probe.write_bytes(b"")
    except OSError:
        return False
    try:
        # NFD-запись той же буквы и верхний регистр: на регистро- и нормализационно-чувствительной ФС их нет.
        variants = (probe.with_name(probe.name.upper()), probe.with_name(probe.name.replace("\u00e9", "e\u0301")))
        return any(variant.exists() for variant in variants)
    finally:
        probe.unlink(missing_ok=True)


_UNSAFE_NAME = re.compile(r"[^\w.-]+", re.UNICODE)
_MAX_NAME_CHARS = 60


class GetCloneDefaultsUC:
    """Папка по умолчанию для клона: свободное имя рядом с остальными проектами.

    На сервере папку выбирает сервер: это свободный `<uuid>` под корнем томов проектов, а не имя по названию.
    """

    def __init__(self, default_projects_dir: Path, locator: IProjectLocator, *, uuid_names: bool = False) -> None:
        self._root = default_projects_dir
        self._locator = locator
        self._uuid_names = uuid_names

    async def execute(self, name: str | None) -> Path:
        taken = {known.resolve() for known in await self._locator.list_all()}
        return await asyncio.to_thread(self._free_folder, name, taken)

    def _free_folder(self, name: str | None, taken: set[Path]) -> Path:
        if self._uuid_names:
            while True:
                candidate = self._root / str(uuid4())
                if not candidate.exists() and candidate.resolve() not in taken:
                    return candidate
        slug = _UNSAFE_NAME.sub("-", (name or "").strip()).strip("-.")[:_MAX_NAME_CHARS] or "project"
        candidate = self._root / slug
        suffix = 2
        while candidate.exists() or candidate.resolve() in taken:
            candidate = self._root / f"{slug}-{suffix}"
            suffix += 1
        return candidate
