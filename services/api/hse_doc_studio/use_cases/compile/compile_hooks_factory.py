from __future__ import annotations

from hse_doc_studio.core.jobs.artifacts import IArtifactStore
from hse_doc_studio.core.jobs.entities import JobSpec
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
        return CompileJobHooks(
            compile_repo=self._compile_repo,
            project_repo=self._project_repo,
            changelog_repo=self._changelog_repo,
            template_repo=self._template_repo,
            vcs_service=self._vcs_service,
            vcs_locks=self._vcs_locks,
            artifacts=self._artifacts,
            project_folder=spec.local_root,
        )
