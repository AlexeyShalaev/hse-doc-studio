"""Обмен проектом без сервера: выгрузка в файл bundle, слияние чужого файла и новый проект из файла.

Файл несёт одну ветку проекта целиком, при желании под паролем. Принимается он тем же путём, что и ветка
с сервера: ветка кладётся в `refs/hse/bundle/<ветка>`, и дальше работает общий план слияния и применение
(`SyncProjectUC.import_ref`), только без выборки и без отправки. Конфликты экран решает так же, как после
синхронизации, поэтому ссылка живёт, пока сессия открыта, и убирается при решении или отказе.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.git_sync.bundle_header import BundleHeader
from hse_doc_studio.core.git_sync.entities import (
    CloneResult,
    GitOperation,
    GitOperationError,
    OperationKind,
    OperationPhase,
    OperationStatus,
    SyncOutcome,
    SyncResult,
)
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import (
    IGitBundleService,
    IGitMergeCommitter,
    IGitOperationRegistry,
    ILocalAuthorProfile,
)
from hse_doc_studio.core.git_sync.refs import bundle_ref
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.vcs.errors import VcsInvalidRefError
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks
from hse_doc_studio.core.vcs.refs import validate_ref_name
from hse_doc_studio.use_cases.git_sync.blocking import finish_before_cancel
from hse_doc_studio.use_cases.git_sync.clone_project import CloneProjectUC, FolderPlan
from hse_doc_studio.use_cases.git_sync.local_gate import LocalSyncGate
from hse_doc_studio.use_cases.git_sync.start_sync import StartSyncOutput
from hse_doc_studio.use_cases.git_sync.sync_apply import ApplyKind, ApplyOutcome, SyncApplier
from hse_doc_studio.use_cases.git_sync.sync_project import SyncProjectUC
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()

_UPLOAD_NAME = "upload"
_CHUNK = 1024 * 1024
# Рабочие папки, оставшиеся после обрыва (перезапуск посреди операции), убираются через сутки.
_STALE_AFTER_S = 24 * 3600
_MAX_LISTED_AUTO = 200
_NAME_UNSAFE = re.compile(r"[^\w.-]+", re.UNICODE)
_NAME_LIMIT = 60
_PREFERRED_BRANCHES = ("main", "master")
_OUTCOMES = {
    ApplyKind.nothing: SyncOutcome.up_to_date,
    ApplyKind.fast_forward: SyncOutcome.fast_forwarded,
    ApplyKind.merged: SyncOutcome.merged,
    ApplyKind.conflicts: SyncOutcome.conflicts,
}


@dataclass(frozen=True)
class StoredUpload:
    """Принятый файл и папка, которая вместе с ним уйдёт: владеет ими тот, кому они переданы."""

    path: Path
    workdir: Path


class BundleScratch:
    """Рабочие папки переносных файлов: загрузки, расшифрованные копии и файлы на выдачу."""

    def __init__(self, root: Path, max_bytes: int) -> None:
        self._root = root
        self._max_bytes = max_bytes

    @property
    def root(self) -> Path:
        return self._root

    def new_dir(self) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        self._sweep()
        workdir = self._root / uuid4().hex
        workdir.mkdir(mode=0o700)
        return workdir

    @staticmethod
    def discard(workdir: Path) -> None:
        shutil.rmtree(workdir, ignore_errors=True)

    async def receive(self, read: Callable[[int], Awaitable[bytes]]) -> StoredUpload:
        """Складывает загрузку в свою папку, не давая ей перерасти предел. При отказе папка убирается."""
        workdir = await asyncio.to_thread(self.new_dir)
        path = workdir / _UPLOAD_NAME
        try:
            await self._copy(read, path)
        except BaseException:
            self.discard(workdir)
            raise
        return StoredUpload(path, workdir)

    async def _copy(self, read: Callable[[int], Awaitable[bytes]], path: Path) -> None:
        size = 0
        with path.open("wb") as target:
            while chunk := await read(_CHUNK):
                size += len(chunk)
                if size > self._max_bytes:
                    limit = self._max_bytes // (1024 * 1024)
                    raise GitSyncError(
                        GitErrorCode.bundle_invalid,
                        localized_error(
                            f"Файл больше допустимого размера ({limit} МБ)",
                            f"The file is larger than the allowed size ({limit} MB)",
                        ),
                    )
                await asyncio.to_thread(target.write, chunk)

    def _sweep(self) -> None:
        horizon = time.time() - _STALE_AFTER_S
        for entry in self._root.iterdir():
            with suppress(OSError):
                if entry.is_dir() and entry.stat().st_mtime < horizon:
                    shutil.rmtree(entry, ignore_errors=True)


def choose_branch(header: BundleHeader, preferred: str | None) -> str:
    """Ветка файла, которую принимает Студия: единственная, своя или main и master. Иначе файл не подходит."""
    names = sorted({head.branch for head in header.branches if head.branch is not None and _usable(head.branch)})
    if len(names) == 1:
        return names[0]
    for name in (preferred, *_PREFERRED_BRANCHES):
        if name in names:
            return name
    raise git_error(GitErrorCode.bundle_invalid)


def _usable(branch: str) -> bool:
    try:
        validate_ref_name(branch)
    except VcsInvalidRefError:
        return False
    return True


# --- выгрузка -----------------------------------------------------------------------------------------------


@dataclass
class ExportBundleInput:
    project_id: UUID
    password: Secret | None = None


@dataclass(frozen=True)
class ExportedBundle:
    path: Path
    filename: str
    size: int
    workdir: Path


class ExportBundleUC:
    def __init__(
        self,
        *,
        get_project: GetProjectUC,
        gate: LocalSyncGate,
        applier: SyncApplier,
        bundles: IGitBundleService,
        locks: IVcsFolderLocks,
        scratch: BundleScratch,
    ) -> None:
        self._get_project = get_project
        self._gate = gate
        self._applier = applier
        self._bundles = bundles
        self._locks = locks
        self._scratch = scratch

    async def execute(self, inp: ExportBundleInput) -> ExportedBundle:
        project = (await self._get_project.execute(GetProjectInput(project_id=inp.project_id))).project
        workdir = await asyncio.to_thread(self._scratch.new_dir)
        try:
            return await self._export(project, workdir, inp.password)
        except BaseException:
            self._scratch.discard(workdir)
            raise

    async def _export(self, project: Project, workdir: Path, password: Secret | None) -> ExportedBundle:
        filename = _filename(project.name, bool(password))
        final = workdir / filename
        plain = workdir / "plain.bundle" if password else final
        # Несохранённое попадает в историю под блокировкой, а сама упаковка идёт без неё: `git bundle create` только
        # читает ссылки и объекты (неизменяемые), а блокировка на минуты остановила бы каждое сохранение в редакторе.
        async with self._locks.for_folder(project.folder):
            branch = await asyncio.to_thread(self._gate.check, project, needs_profile=False)
            await asyncio.to_thread(self._applier.snapshot, project)
        await self._bundles.create_bundle(project.folder, branch=branch, dest=plain)
        if password:
            # Шифрование долгое, а папке оно не нужно: блокировка уже отпущена.
            await finish_before_cancel(self._bundles.encrypt_bundle, plain, final, password)
            plain.unlink(missing_ok=True)
        logger.info("bundle exported", project_id=str(project.id), branch=branch, encrypted=bool(password))
        return ExportedBundle(final, filename, final.stat().st_size, workdir)


def _filename(name: str, encrypted: bool) -> str:
    slug = _NAME_UNSAFE.sub("-", name.strip()).strip("-.")[:_NAME_LIMIT] or "project"
    stamp = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M")
    return f"{slug}-{stamp}.bundle" + (".hseenc" if encrypted else "")


# --- слияние чужого файла -----------------------------------------------------------------------------------


@dataclass
class ImportBundleInput:
    project_id: UUID
    upload: StoredUpload
    password: Secret | None = None


class ImportBundleUC:
    """Принимает файл в проект. Работа идёт в фоне: операция `bundle_import`, итог тот же, что у синхронизации."""

    def __init__(
        self,
        *,
        get_project: GetProjectUC,
        gate: LocalSyncGate,
        sync: SyncProjectUC,
        applier: SyncApplier,
        bundles: IGitBundleService,
        committer: IGitMergeCommitter,
        operations: IGitOperationRegistry,
        scratch: BundleScratch,
    ) -> None:
        self._get_project = get_project
        self._gate = gate
        self._sync = sync
        self._applier = applier
        self._bundles = bundles
        self._committer = committer
        self._operations = operations
        self._scratch = scratch

    async def execute(self, inp: ImportBundleInput) -> StartSyncOutput:
        """Проверяет всё, что можно сказать сразу, и запускает слияние. Рабочая папка с этого момента его."""
        try:
            project = (await self._get_project.execute(GetProjectInput(project_id=inp.project_id))).project
            branch = await asyncio.to_thread(self._gate.check, project, needs_profile=True, refuse_open_merge=True)
            await asyncio.to_thread(self._bundles.check_upload, inp.upload.path, inp.password)
            operation = self._operations.begin(
                OperationKind.bundle_import, project_id=project.id, folder=project.folder
            )
        except BaseException:
            self._scratch.discard(inp.upload.workdir)
            raise
        task = asyncio.create_task(
            self._run(project, operation.id, branch, inp), name=f"git-bundle-import-{operation.id}"
        )
        self._operations.attach_task(operation.id, task)
        return StartSyncOutput(operation_id=operation.id)

    async def _run(self, project: Project, operation_id: str, branch: str, inp: ImportBundleInput) -> None:
        try:
            result = await self._import(project, operation_id, branch, inp)
        except asyncio.CancelledError:
            self._operations.finish(operation_id, status=OperationStatus.cancelled)
            raise
        except GitSyncError as exc:
            self._operations.finish(
                operation_id, status=OperationStatus.failed, error=GitOperationError(exc.code, exc.detail)
            )
        except Exception:
            logger.exception("bundle import failed", project_id=str(project.id))
            error = git_error(GitErrorCode.git_error)
            self._operations.finish(
                operation_id, status=OperationStatus.failed, error=GitOperationError(error.code, error.detail)
            )
        else:
            self._operations.finish(operation_id, result=result)
        finally:
            self._scratch.discard(inp.upload.workdir)

    async def _import(self, project: Project, operation_id: str, branch: str, inp: ImportBundleInput) -> SyncResult:
        folder = project.folder
        self._operations.update(operation_id, phase=OperationPhase.verify, cancellable=True)
        plain = await finish_before_cancel(self._bundles.unpack, inp.upload.path, inp.upload.workdir, inp.password)
        header = await asyncio.to_thread(self._bundles.read_header, plain)
        await self._bundles.verify(folder, plain)
        theirs_branch = choose_branch(header, branch)
        ref = bundle_ref(theirs_branch)
        self._operations.update(operation_id, phase=OperationPhase.fetch)
        try:
            tip = await self._bundles.stage_branch(folder, plain, branch=theirs_branch, ref=ref)
            await asyncio.to_thread(self._applier.ensure_remote_mergeable, project, tip)
            applied = await self._sync.import_ref(project, operation_id, uuid4().hex[:12], ref)
        except GitSyncError as exc:
            self._drop(folder, ref)
            if exc.code is GitErrorCode.unrelated_histories:
                # Усыновить историю без общего предка из файла нельзя: выбора, как при подключении, здесь нет.
                raise git_error(GitErrorCode.unrelated_histories, can_adopt=False) from exc
            raise
        except BaseException:
            self._drop(folder, ref)
            raise
        logger.info("bundle imported", project_id=str(project.id), outcome=applied.kind.value, pulled=applied.pulled)
        return _result(applied)

    def _drop(self, folder: Path, ref: str) -> None:
        with suppress(Exception):
            self._committer.delete_ref(folder, ref)


def _result(applied: ApplyOutcome) -> SyncResult:
    return SyncResult(
        outcome=_OUTCOMES[applied.kind],
        pulled_commits=applied.pulled,
        merge_commit=applied.merge_commit,
        files_changed=applied.files_changed,
        auto=applied.auto[:_MAX_LISTED_AUTO],
        conflicts=applied.conflicts,
        warnings=applied.warnings,
    )


# --- новый проект из файла ----------------------------------------------------------------------------------


@dataclass
class CloneFromBundleInput:
    upload: StoredUpload
    folder: str
    password: Secret | None = None


class CloneFromBundleUC:
    """Новый проект из файла: те же шаги, что у клонирования с сервера, но объекты берутся из файла."""

    def __init__(
        self,
        *,
        clone: CloneProjectUC,
        bundles: IGitBundleService,
        committer: IGitMergeCommitter,
        operations: IGitOperationRegistry,
        profile: ILocalAuthorProfile,
        policy: GitSyncPolicy,
        scratch: BundleScratch,
    ) -> None:
        self._clone = clone
        self._bundles = bundles
        self._committer = committer
        self._operations = operations
        self._profile = profile
        self._policy = policy
        self._scratch = scratch

    async def execute(self, inp: CloneFromBundleInput) -> GitOperation:
        try:
            self._policy.require_enabled()
            if self._profile.get() is None:
                raise git_error(GitErrorCode.profile_required)
            plan = await asyncio.to_thread(self._clone.plan_folder, inp.folder)
            await asyncio.to_thread(self._bundles.check_upload, inp.upload.path, inp.password)
            operation = self._operations.begin(OperationKind.clone, project_id=None, folder=plan.folder)
        except BaseException:
            self._scratch.discard(inp.upload.workdir)
            raise
        self._clone.start(operation.id, plan, lambda: self._run(operation.id, plan, inp))
        return operation

    async def _run(self, operation_id: str, plan: FolderPlan, inp: CloneFromBundleInput) -> CloneResult:
        folder = plan.folder
        ref: str | None = None
        try:
            self._operations.update(operation_id, phase=OperationPhase.download, cancellable=True)
            plain = await finish_before_cancel(self._bundles.unpack, inp.upload.path, inp.upload.workdir, inp.password)
            header = await asyncio.to_thread(self._bundles.read_header, plain)
            branch = choose_branch(header, None)
            await finish_before_cancel(self._clone.init_store, folder, branch)
            self._operations.update(operation_id, phase=OperationPhase.verify)
            await self._bundles.verify(folder, plain)
            ref = bundle_ref(branch)
            await self._bundles.stage_branch(folder, plain, branch=branch, ref=ref)
            result = await self._clone.adopt(operation_id, plan, branch=branch, ref=ref, remote=None)
        finally:
            self._scratch.discard(inp.upload.workdir)
        # Ветка из файла нужна была только развёртыванию; проект уже стоит на своей ветке.
        with suppress(Exception):
            self._committer.delete_ref(folder, ref)
        return result
