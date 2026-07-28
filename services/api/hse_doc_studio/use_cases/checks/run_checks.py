from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import CheckEngine
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISettingsRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import CheckResolutionService, ProjectTemplateService
from hse_doc_studio.core.team import doc_base_dir
from hse_doc_studio.core.value_objects import CheckResult, ChecksOverride
from hse_doc_studio.infra.checks.runner import CheckRunner
from hse_doc_studio.infra.languagetool.container_manager import LanguageToolContainerManager
from hse_doc_studio.use_cases.languagetool.list_languagetool_images import (
    resolve_active_languagetool_image,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class RunChecksInput:
    project_id: UUID
    doc_id: str
    include_external: bool = True


@dataclass
class RunChecksOutput:
    results: list[CheckResult]


class RunChecksUC:
    """Run source-based checks for a document WITHOUT compiling.

    Resolves the document's effective rules and runs every engine that works
    from the `.tex` sources on disk (regex, structural, reference_check,
    python, tex_command_count, file_exists, and — optionally —
    external/LanguageTool). The `log_parse` engine is skipped because it needs
    a build log.

    This powers live normative checks while typing: no multi-minute docker
    build, just the static analysers over the current files. It does NOT
    mutate the project (no dynamic-include regeneration) so it is safe to call
    on a debounce.

    For a document with `custom_file` set, there is no `.tex` source to
    analyse — the source-dependent engines are suppressed (same custom_mode
    behaviour as a compile), leaving only `file_exists`.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        check_resolution_service: CheckResolutionService,
        check_runner: CheckRunner,
        lt_manager: LanguageToolContainerManager,
        settings_repo: ISettingsRepository,
    ) -> None:
        self._get_project_uc = GetProjectUC(project_repo, project_index_repo)
        self._template_repo = template_repo
        self._template_service = template_service
        self._check_resolution_service = check_resolution_service
        self._check_runner = check_runner
        self._lt_manager = lt_manager
        self._settings_repo = settings_repo

    def _resolve_source_file(self, project: Project, doc: Document, version: TemplateVersion) -> str:
        if doc.custom_file is not None:
            # Кастомный файл — нет `.tex`-исходника и лога сборки, резолвить
            # через пак нечего; ниже это же используется, чтобы подавить
            # LaTeX-зависимые движки вместо прогона их по чужому файлу.
            return doc.custom_file.stored_path
        source_file, _ = self._template_service.resolve_instance_source(project, doc, version)
        return source_file

    async def execute(self, inp: RunChecksInput) -> RunChecksOutput:
        project = (await self._get_project_uc.execute(GetProjectInput(project_id=inp.project_id))).project

        doc = next((d for d in project.documents if d.id == inp.doc_id), None)
        if doc is None:
            raise NotFoundError(
                localized_error(
                    f"Документ {inp.doc_id!r} не найден в проекте {inp.project_id}",
                    f"Document {inp.doc_id!r} not found in project {inp.project_id}",
                )
            )

        version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        if version is None:
            version_ref = f"{project.lock.pack_id}/{project.lock.template_id}/{project.lock.version}"
            raise NotFoundError(
                localized_error(
                    f"Версия шаблона не найдена: {version_ref}", f"Template version not found: {version_ref}"
                )
            )

        doc_def = self._template_service.find_definition(version, doc)
        if doc_def is None:
            raise NotFoundError(
                localized_error(
                    f"Определение документа {doc.def_id!r} не найдено в версии шаблона",
                    f"Document definition {doc.def_id!r} not found in template version",
                )
            )

        source_file = self._resolve_source_file(project, doc, version)
        doc_def_checks = doc_def.checks

        # `applies_to` пака перечисляет id определений → def_id.
        rules_with_severity = self._check_resolution_service.resolve(
            rules=list(version.rules),
            doc_id=doc.def_id,
            version_cfg=version.checks_config,
            doc_definition_checks=doc_def_checks,
            project_override=project.checks_override,
            doc_override=doc.checks_override,
            user_override=ChecksOverride(),
        )

        skip_engines = {CheckEngine.log_parse}
        if not inp.include_external:
            skip_engines.add(CheckEngine.external)
        rules_with_severity = [(rule, sev) for rule, sev in rules_with_severity if rule.engine not in skip_engines]

        needs_external = (
            doc.custom_file is None
            and inp.include_external
            and any(rule.engine == CheckEngine.external for rule, _ in rules_with_severity)
        )
        if needs_external:
            await self._lt_manager.ensure_running(resolve_active_languagetool_image(self._settings_repo))

        results = await asyncio.to_thread(
            self._check_runner.run_all,
            rules_with_severity=rules_with_severity,
            project_folder=project.folder,
            doc_id=inp.doc_id,
            source_file=source_file,
            log_content=None,
            base_dir=doc_base_dir(project, doc),
            custom_mode=doc.custom_file is not None,
        )

        ignored_ids = (
            set(version.checks_config.disabled)
            | set(doc_def_checks.disabled)
            | set(project.checks_override.disabled)
            | set(doc.checks_override.disabled)
        )
        if ignored_ids:
            results = [r for r in results if r.rule_id not in ignored_ids]

        return RunChecksOutput(results=results)
