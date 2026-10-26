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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

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
from hse_doc_studio.core.git_sync.merge.paths import is_safe_entry
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
)
from hse_doc_studio.core.git_sync.remote_project import (
    PROJECT_FILE,
    RemoteProject,
    parse_remote_project,
    remote_required_studio,
    remote_schema_access,
)
from hse_doc_studio.core.git_sync.url import RemoteKind, RemoteUrl, parse_remote_url
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.core.vcs.constants import vcs_exclude_for
from hse_doc_studio.use_cases.git_sync.probe_remote import choose_remote_branch, raise_probe_error, valid_branch
from hse_doc_studio.use_cases.git_sync.status import TRACKING_PREFIX
from hse_doc_studio.use_cases.template_update.base_service import TemplateBaseService

logger = structlog.get_logger()

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


@dataclass(frozen=True)
class _FolderPlan:
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
        project_index_repo: IProjectIndexRepository,
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
        clone_timeout_s: float,
    ) -> None:
        self._projects = project_repo
        self._index = project_index_repo
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
        self._timeout_s = clone_timeout_s

    async def execute(self, inp: CloneProjectInput) -> GitOperation:
        """Проверяет всё, что можно проверить без сети, и запускает клонирование в фоне."""
        url = self._checked_input(inp)
        plan = await asyncio.to_thread(self._plan_folder, inp.folder)
        operation = self._operations.begin(OperationKind.clone, project_id=None, folder=plan.folder)
        task = asyncio.create_task(self._run(operation.id, url, plan, inp))
        self._operations.attach_task(operation.id, task)
        return operation

    def _checked_input(self, inp: CloneProjectInput) -> RemoteUrl:
        if not self._policy.enabled:
            raise git_error(GitErrorCode.git_unavailable)
        if self._profile.get() is None:
            raise git_error(GitErrorCode.profile_required)
        url = parse_remote_url(
            inp.url, allow_http=self._policy.allow_insecure_http, allow_local=self._policy.allow_local_remotes
        )
        if inp.credential_id is not None and self._credentials.get(inp.credential_id) is None:
            raise git_error(GitErrorCode.credentials_missing)
        if inp.branch:
            valid_branch(inp.branch)
        return url

    def _plan_folder(self, raw: str) -> _FolderPlan:
        """Папка годится под новый проект: пуста (с точностью до скрытых файлов), не внутри проекта и не занята."""
        path = Path(raw).expanduser()
        if not path.is_absolute():
            raise ValueError(localized_error("Укажите полный путь к папке", "Specify the full path of the folder"))
        folder = path.resolve()
        self._check_folder_free(folder)
        if folder.exists():
            return _FolderPlan(folder, None, frozenset(entry.name for entry in folder.iterdir()))
        created_root = folder
        for parent in folder.parents:
            if parent.exists():
                break
            created_root = parent
        return _FolderPlan(folder, created_root, frozenset())

    def _check_folder_free(self, folder: Path) -> None:
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
        if folder in {known.resolve() for known in self._index.list_known()}:
            raise _folder_not_empty("registered", folder)

    async def _run(self, operation_id: str, url: RemoteUrl, plan: _FolderPlan, inp: CloneProjectInput) -> None:
        try:
            result = await self._clone(operation_id, url, plan, inp)
        except asyncio.CancelledError:
            self._cleanup(plan)
            self._operations.finish(operation_id, status=OperationStatus.cancelled)
            raise
        except GitSyncError as exc:
            self._cleanup(plan)
            self._operations.finish(
                operation_id, status=OperationStatus.failed, error=GitOperationError(exc.code, exc.detail)
            )
            return
        except Exception:
            logger.exception("git clone failed", folder=str(plan.folder))
            self._cleanup(plan)
            error = git_error(GitErrorCode.git_error)
            self._operations.finish(
                operation_id, status=OperationStatus.failed, error=GitOperationError(error.code, error.detail)
            )
            return
        self._operations.finish(operation_id, result=result)

    async def _clone(self, operation_id: str, url: RemoteUrl, plan: _FolderPlan, inp: CloneProjectInput) -> CloneResult:
        folder = plan.folder
        # Открытый http проверяется как разрешённый политикой: отдельного согласия у клонирования нет.
        target = RemoteTarget(url, inp.credential_id, insecure_http=url.kind is RemoteKind.http)
        self._operations.update(operation_id, phase=OperationPhase.download)
        probe = await self._transport.probe(target)
        raise_probe_error(probe)
        if probe.empty:
            raise git_error(GitErrorCode.not_a_studio_project)
        branch = valid_branch(choose_remote_branch(inp.branch, probe))
        if branch not in probe.branches:
            raise git_error(GitErrorCode.branch_missing)

        await asyncio.to_thread(folder.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self._store.init, folder, branch)
        git_dir = folder / _STUDIO_DIR / "git"
        await self._transport.fetch(
            git_dir,
            target,
            branch=branch,
            timeout_s=self._timeout_s,
            on_progress=lambda percent, _line: self._operations.update(operation_id, percent=percent),
        )

        self._operations.update(operation_id, phase=OperationPhase.verify)
        verified = await asyncio.to_thread(self._verify, plan, branch)

        # Дальше дерево разворачивается в папку: прерывать это на полпути нельзя.
        self._operations.update(operation_id, phase=OperationPhase.register, cancellable=False)
        await asyncio.to_thread(self._store.write_exclude, folder, vcs_exclude_for(verified.version))
        await asyncio.to_thread(self._store.checkout, folder, branch)
        await asyncio.to_thread(self._persist, folder, url, branch, inp.credential_id, target.insecure_http)
        self._index.register(folder)
        await asyncio.to_thread(self._ensure_template_base, folder, verified)
        self._registry.add(folder)
        logger.info("project cloned", project_id=str(verified.project.id), host=url.host, branch=branch)
        return CloneResult(
            project_id=verified.project.id,
            folder=str(folder),
            access=verified.access,
            required_studio=verified.required_studio,
            warnings=verified.warnings,
        )

    def _verify(self, plan: _FolderPlan, branch: str) -> _Verified:
        """Проверка вершины скачанной ветки до того, как её дерево тронет папку."""
        folder = plan.folder
        tracking = f"{TRACKING_PREFIX}{branch}"
        if self._reader.rev_parse(folder, tracking) is None:
            raise git_error(GitErrorCode.branch_missing)
        raw = self._reader.read_files(folder, tracking, [PROJECT_FILE]).get(PROJECT_FILE)
        project = parse_remote_project(raw) if raw is not None else None
        if project is None:
            raise git_error(GitErrorCode.not_a_studio_project)
        existing = self._registered_folder(project.id)
        if existing is not None:
            raise GitSyncError(
                GitErrorCode.project_exists,
                localized_error(
                    f"Этот проект уже открыт в Студии: {existing}",
                    f"This project is already open in the Studio: {existing}",
                ),
                folder=str(existing),
            )
        entries = self._reader.tree_entries(folder, tracking)
        self._check_paths(entries, plan)
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

    def _registered_folder(self, project_id: UUID) -> Path | None:
        for known in self._index.list_known():
            existing = self._projects.get(known)
            if existing is not None and existing.id == project_id:
                return known
        return None

    @staticmethod
    def _check_paths(entries: list[TreeEntry], plan: _FolderPlan) -> None:
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

    def _cleanup(self, plan: _FolderPlan) -> None:
        """Убирает созданное клонированием; всё, что было в папке до него, остаётся на месте."""
        try:
            self._index.unregister(plan.folder)
            if plan.created_root is not None:
                shutil.rmtree(plan.created_root, ignore_errors=True)
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


_UNSAFE_NAME = re.compile(r"[^\w.-]+", re.UNICODE)
_MAX_NAME_CHARS = 60


class GetCloneDefaultsUC:
    """Папка по умолчанию для клона: свободное имя рядом с остальными проектами."""

    def __init__(self, default_projects_dir: Path, project_index_repo: IProjectIndexRepository) -> None:
        self._root = default_projects_dir
        self._index = project_index_repo

    async def execute(self, name: str | None) -> Path:
        return await asyncio.to_thread(self._free_folder, name)

    def _free_folder(self, name: str | None) -> Path:
        slug = _UNSAFE_NAME.sub("-", (name or "").strip()).strip("-.")[:_MAX_NAME_CHARS] or "project"
        taken = {known.resolve() for known in self._index.list_known()}
        candidate = self._root / slug
        suffix = 2
        while candidate.exists() or candidate.resolve() in taken:
            candidate = self._root / f"{slug}-{suffix}"
            suffix += 1
        return candidate
