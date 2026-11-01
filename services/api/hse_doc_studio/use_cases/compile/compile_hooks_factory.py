from __future__ import annotations

from hse_doc_studio.core.enums import CompileStatus
from hse_doc_studio.core.jobs.artifacts import IArtifactStore
from hse_doc_studio.core.jobs.entities import JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.protocols import IJobHooks
from hse_doc_studio.core.repositories import (
    IChangeLogRepository,
    ICompileRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.use_cases.compile.compile_job_hooks import CompileJobHooks


class _RecoveredCompileHooks:
    """Хуки после рестарта api: итог уже мог быть записан до падения, и повторять его побочные эффекты нельзя.

    Журнал, снимок VCS и архив PDF не идемпотентны, поэтому при готовой записи (успех или сбой) или при
    удалённой записи итог не применяется второй раз.
    """

    def __init__(self, inner: CompileJobHooks, compile_repo: ICompileRepository) -> None:
        self._inner = inner
        self._compile_repo = compile_repo

    async def on_started(self, spec: JobSpec) -> bool:
        return await self._inner.on_started(spec)

    async def on_finished(self, spec: JobSpec, result: JobResult, log: str) -> None:
        record = await self._compile_repo.get_for_project(self._inner.project_folder, spec.id)
        if record is None or record.status in (CompileStatus.success, CompileStatus.failure):
            return
        await self._inner.on_finished(spec, result, log)


class CompileJobHooksFactory:
    """Хуки сборки для задачи, пережившей рестарт api: из спецификации с папкой проекта.

    Те же коллабораторы, что получает `TriggerCompileUC`; у остальных видов задач хуков нет.
    """

    def __init__(  # noqa: PLR0913
        self,
        compile_repo: ICompileRepository,
        project_repo: IProjectRepository,
        changelog_repo: IChangeLogRepository,
        template_repo: ITemplateRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
        artifacts: IArtifactStore,
    ) -> None:
        self._compile_repo = compile_repo
        self._project_repo = project_repo
        self._changelog_repo = changelog_repo
        self._template_repo = template_repo
        self._vcs_service = vcs_service
        self._vcs_locks = vcs_locks
        self._artifacts = artifacts

    def for_spec(self, spec: JobSpec) -> IJobHooks | None:
        if spec.kind is not JobKind.compile or spec.local_root is None:
            return None
        hooks = CompileJobHooks(
            compile_repo=self._compile_repo,
            project_repo=self._project_repo,
            changelog_repo=self._changelog_repo,
            template_repo=self._template_repo,
            vcs_service=self._vcs_service,
            vcs_locks=self._vcs_locks,
            artifacts=self._artifacts,
            project_folder=spec.local_root,
        )
        return _RecoveredCompileHooks(hooks, self._compile_repo)
