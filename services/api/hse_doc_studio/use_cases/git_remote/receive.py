"""Приём push в проект сервера (раздел 7.3): замок папки, снимок веб-правок, политика путей, пост-обработка.

Сценарий разбит на две части вокруг процесса `git receive-pack`: `begin` до запуска (проверки, замок, снимок,
файл политики) и `finish` после (сдвиг ветки, согласование project.json, журнал, снятие замка). Поток между
ними ведёт маршрут, потому что ответ git стримится клиенту.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field

import structlog

from hse_doc_studio.core.access.context import current_actor, set_current_actor
from hse_doc_studio.core.enums import VcsCommitKind
from hse_doc_studio.core.git_remote.protocols import (
    GitRpcOutcome,
    IExternalChangeReconciler,
    IPushRuntime,
    PushHookSession,
)
from hse_doc_studio.core.git_remote.push_policy import PROJECT_JSON_PATH, push_policy_for
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.project_schema import PROJECT_SCHEMA_VERSION
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.use_cases.git_remote.auth import GitAccess
from hse_doc_studio.use_cases.projects.get_project_access import GetProjectAccessInput, GetProjectAccessUC

logger = structlog.get_logger()

MAX_BLOB_BYTES = 95 * 1024 * 1024


class ProjectBusyError(Exception):
    """Проект нельзя писать сейчас: обновление шаблона, синхронизация, только чтение или занят замок."""

    def __init__(self) -> None:
        super().__init__(
            localized_error(
                "Проект сейчас занят (обновление шаблона или синхронизация). Повторите позже.",
                "The project is busy (template update or sync). Try again later.",
            )
        )


@dataclass
class PushSession:
    access: GitAccess
    hook: PushHookSession
    head_before: str | None
    snapshot: str | None
    lock: AbstractAsyncContextManager[None]
    branch: str
    push_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass(frozen=True)
class PushLimits:
    max_push_bytes: int
    lock_wait_s: float


class ReceivePushUC:
    def __init__(  # noqa: PLR0913 — порты одного приёма
        self,
        project_access: GetProjectAccessUC,
        operations: IGitOperationRegistry,
        locks: IVcsFolderLocks,
        vcs: IVcsService,
        runtime: IPushRuntime,
        reconciler: IExternalChangeReconciler,
        audit: IAuditLog,
        limits: PushLimits,
    ) -> None:
        self._project_access = project_access
        self._operations = operations
        self._locks = locks
        self._vcs = vcs
        self._runtime = runtime
        self._reconciler = reconciler
        self._audit = audit
        self._limits = limits

    async def advertise(self, access: GitAccess) -> None:
        """Перед рекламой ссылок для push: снимок веб-правок под коротким замком.

        Клиент сравнивает свою ветку с рекламой до отправки: если правки браузера попадут в историю уже после
        рекламы, git отвергнет обновление как «incorrect old value». Снимок здесь даёт клиенту честную рекламу,
        и первый `git push` после `git pull` проходит.
        """
        lock = await self._acquire(access)
        try:
            await self._snapshot(access, uuid.uuid4().hex[:12])
        finally:
            await lock.__aexit__(None, None, None)

    async def _acquire(self, access: GitAccess) -> AbstractAsyncContextManager[None]:
        project = access.project
        state = await self._project_access.execute(GetProjectAccessInput(project_id=project.id))
        if not state.access.writable or self._operations.is_busy(project.folder):
            raise ProjectBusyError
        lock = self._locks.for_folder(project.folder)
        try:
            await asyncio.wait_for(lock.__aenter__(), timeout=self._limits.lock_wait_s)
        except TimeoutError:
            raise ProjectBusyError from None
        if self._operations.is_busy(project.folder):
            await lock.__aexit__(None, None, None)
            raise ProjectBusyError
        return lock

    async def begin(self, access: GitAccess) -> PushSession:
        project = access.project
        lock = await self._acquire(access)
        try:
            push_id = uuid.uuid4().hex[:12]
            snapshot = await self._snapshot(access, push_id)
            git_dir = access.git_dir
            branch = await self._runtime.branch(git_dir) or "master"
            policy = push_policy_for(
                access.acl,
                access.grant,
                branch=branch,
                max_blob_bytes=MAX_BLOB_BYTES,
                compat=(PROJECT_SCHEMA_VERSION, PROJECT_SCHEMA_VERSION),
            )
            hook = self._runtime.prepare(
                policy,
                git_dir=git_dir,
                work_tree=project.folder,
                actor_id=access.principal.user_id,
                lang=current_interface_language("en"),
                max_input_bytes=self._limits.max_push_bytes,
            )
            head = await self._runtime.head(git_dir)
        except BaseException:
            await lock.__aexit__(None, None, None)
            raise
        return PushSession(access, hook, head, snapshot, lock, branch, push_id)

    async def _snapshot(self, access: GitAccess, push_id: str) -> str | None:
        """Несохранённые веб-правки фиксируются от имени служебного бота: push строится на старом HEAD и тогда
        будет отвергнут как не перемотка, клиент сделает fetch и слияние (D13)."""
        project = access.project
        actor = current_actor()
        set_current_actor(None)
        try:
            if not self._vcs.is_initialized(project):
                return None
            commit = await asyncio.to_thread(
                lambda: self._vcs.commit(
                    project,
                    message=f"Правки в браузере перед приёмом push\n\nHse-Sync: server-push-{push_id}",
                    kind=VcsCommitKind.sync,
                )
            )
        finally:
            set_current_actor(actor)
        return commit.id if commit is not None else None

    async def finish(self, session: PushSession, outcome: GitRpcOutcome | None) -> None:
        """После процесса git: снять замок всегда; при сдвиге ветки согласовать состояние и записать журнал."""
        access = session.access
        try:
            self._runtime.cleanup(session.hook)
            head_after = await self._runtime.head(access.git_dir)
            moved = head_after is not None and head_after != session.head_before
            paths: list[str] = []
            if moved and session.head_before is not None and head_after is not None:
                paths = await self._runtime.changed_paths(access.git_dir, session.head_before, head_after)
            if moved:
                with contextlib.suppress(Exception):
                    await self._reconciler.after_external_change(
                        access.project.id, access.project.folder, project_json_changed=PROJECT_JSON_PATH in paths
                    )
            await self._audit.record(
                "git.push",
                actor_id=access.principal.user_id,
                target=str(access.project.id),
                details={
                    "old": session.head_before,
                    "new": head_after,
                    "branch": session.branch,
                    "paths": len(paths),
                    "result": "accepted" if moved else "rejected",
                    "snapshot": session.snapshot,
                    "exit": outcome.returncode if outcome else None,
                },
            )
        finally:
            await session.lock.__aexit__(None, None, None)
