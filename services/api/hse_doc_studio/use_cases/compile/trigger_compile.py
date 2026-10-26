from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import structlog

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import CompileRecord, Project
from hse_doc_studio.core.enums import CheckEngine, CompileStatus, DocumentStatus
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.jobs.artifacts import IArtifactStore
from hse_doc_studio.core.jobs.entities import CheckPlan, CompileJobPayload, JobSpec, job_tags
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.repositories import (
    IChangeLogRepository,
    ICompileRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import CheckResolutionService, ProjectTemplateService
from hse_doc_studio.core.team import doc_base_dir
from hse_doc_studio.core.template_materializer import ITemplateMaterializer
from hse_doc_studio.core.value_objects import ChecksOverride
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.use_cases.compile.compile_job_hooks import CompileJobHooks

logger = structlog.get_logger()


@dataclass
class TriggerCompileInput:
    project_id: uuid.UUID
    doc_id: str


@dataclass
class TriggerCompileOutput:
    compile_id: uuid.UUID


def _find_project(
    project_id: uuid.UUID,
    project_repo: IProjectRepository,
    project_index_repo: IProjectIndexRepository,
) -> tuple[Path, Project] | tuple[None, None]:
    known_folders = project_index_repo.list_known()
    for folder in known_folders:
        try:
            project = project_repo.get(folder)
            if project is not None and project.id == project_id:
                return folder, project
        except Exception as exc:
            logger.warning(
                "trigger_compile: error loading project",
                folder=str(folder),
                exc=str(exc),
            )
    return None, None


class TriggerCompileUC:
    def __init__(  # noqa: PLR0913
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        compile_repo: ICompileRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        check_resolution_service: CheckResolutionService,
        changelog_repo: IChangeLogRepository,
        dispatcher: IJobDispatcher,
        materializer: ITemplateMaterializer,
        artifacts: IArtifactStore,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._compile_repo = compile_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._check_resolution_service = check_resolution_service
        self._changelog_repo = changelog_repo
        self._dispatcher = dispatcher
        self._materializer = materializer
        self._artifacts = artifacts
        self._vcs_service = vcs_service
        self._vcs_locks = vcs_locks

    async def execute(self, inp: TriggerCompileInput) -> TriggerCompileOutput:  # noqa: C901
        project_folder, project = _find_project(inp.project_id, self._project_repo, self._project_index_repo)
        if project is None or project_folder is None:
            raise NotFoundError(
                localized_error(f"Проект {inp.project_id} не найден", f"Project not found: {inp.project_id}")
            )

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

        # Join с паком — строго по def_id: в team-проекте doc.id несёт суффикс
        # владельца ("vkr--shalaev") и с id определения не совпадает.
        doc_def = self._template_service.find_definition(version, doc)
        if doc_def is None:
            raise NotFoundError(
                localized_error(
                    f"Определение документа {doc.def_id!r} не найдено в версии шаблона",
                    f"Document definition {doc.def_id!r} not found in template version",
                )
            )

        # Re-render dynamic includes (common/meta.tex etc.) from the CURRENT
        # project state before xelatex runs. This is what makes editable data
        # (author/supervisor names, group, NDA, …) reach the PDF on every build
        # without re-rendering — or clobbering — the user's own .tex files.
        self._materializer.regenerate_dynamic_includes(project, version)
        # If NDA was toggled on after creation, materialise its files now
        # (idempotent — never overwrites the student's edited copies).
        self._materializer.instantiate_nda(project, version)

        # A custom-file document has an arbitrary user-uploaded file as its one
        # true source — it bypasses chosen_variant/variants resolution entirely
        # (resolve_instance_source resolves via chosen_variant, which does not
        # apply here) and is always copy-only, exactly like an `engine: none`
        # variant today.
        engine = project.lock.engine
        needs_compile = True
        if doc.custom_file is not None:
            source_file = doc.custom_file.stored_path
            needs_compile = False
        else:
            # Путь от корня проекта с префиксом базы владельца (team:
            # "shalaev/vkr/vkr.tex", shared — "shared/…"; solo — как в паке).
            source_file, _output_file = self._template_service.resolve_instance_source(project, doc, version)

            # A chosen variant may declare its own engine — or `engine: none`, a
            # copy-only artifact (pptx / reveal HTML) that is NOT a LaTeX source
            # and must never be fed to xelatex (that fails with "Missing
            # \begin{document}" on the binary .pptx, leaving the doc permanently
            # red). Copy-only variants skip compilation AND the docker preflight:
            # the rendered file already is the deliverable.
            if doc_def.variants:
                chosen_variant_def = next(
                    (v for v in doc_def.variants if v.id == doc.chosen_variant),
                    doc_def.variants[0],
                )
                if chosen_variant_def.engine is None:
                    needs_compile = False
                else:
                    engine = chosen_variant_def.engine

        compile_id = uuid.uuid4()
        payload = CompileJobPayload(
            doc_id=inp.doc_id,
            def_id=doc.def_id,
            source_file=source_file,
            engine=engine,
            base_dir=doc_base_dir(project, doc),
            needs_compile=needs_compile,
            custom_mode=doc.custom_file is not None,
            default_passes=version.engine_config.passes,
            check_plan=self._check_plan(project, doc.def_id, doc.checks_override, version, doc_def.checks),
        )
        spec = JobSpec(
            id=compile_id,
            kind=JobKind.compile,
            tags=job_tags(JobKind.compile, payload),
            project_id=project.id,
            actor=current_actor() or Actor.local(),
            locale=current_interface_language(),
            payload=payload,
            local_root=project_folder,
        )
        # Образ LaTeX не установлен или Docker недоступен: отказ до записи сборки.
        # Скачивание многогигабайтного образа отдельное действие пользователя
        # (Настройки → Образы → «Установить»): клик по «Сборке» не должен молча
        # превращаться в долгую загрузку. Copy-only варианты проверки не требуют.
        await self._dispatcher.preflight(spec)

        now = datetime.now(tz=timezone.utc)
        record = CompileRecord(
            id=compile_id,
            project_folder=project_folder,
            doc_id=inp.doc_id,
            engine=engine,
            status=CompileStatus.pending,
            started_at=now,
            finished_at=None,
            log="",
            output_path=None,
            check_results=[],
            pages=None,
        )
        self._compile_repo.save(record)

        doc_index = project.documents.index(doc)
        project.documents[doc_index] = replace(doc, status=DocumentStatus.building, last_compile_id=compile_id)
        self._project_repo.save(project)

        self._dispatcher.submit(
            spec,
            CompileJobHooks(
                compile_repo=self._compile_repo,
                project_repo=self._project_repo,
                changelog_repo=self._changelog_repo,
                template_repo=self._template_repo,
                vcs_service=self._vcs_service,
                vcs_locks=self._vcs_locks,
                artifacts=self._artifacts,
                project_folder=project_folder,
            ),
        )

        return TriggerCompileOutput(compile_id=compile_id)

    def _check_plan(
        self,
        project: Project,
        def_id: str,
        doc_checks_override: ChecksOverride,
        version: TemplateVersion,
        doc_def_checks: ChecksOverride,
    ) -> CheckPlan:
        # Скоупинг правил (`applies_to`) в паке перечисляет id ОПРЕДЕЛЕНИЙ —
        # резолвим по def_id, а не по id инстанса.
        rules_with_severity = self._check_resolution_service.resolve(
            rules=list(version.rules),
            doc_id=def_id,
            version_cfg=version.checks_config,
            doc_definition_checks=doc_def_checks,
            project_override=project.checks_override,
            doc_override=doc_checks_override,
            user_override=ChecksOverride(),
        )
        # Отдельно проигнорированные находки снимаются после проверок: id вида
        # `lt:<RULE>` в каталоге не объявлены, поэтому сопоставляются по rule_id.
        ignored_ids = (
            set(version.checks_config.disabled)
            | set(doc_def_checks.disabled)
            | set(project.checks_override.disabled)
            | set(doc_checks_override.disabled)
        )
        return CheckPlan(
            rules_with_severity=tuple(rules_with_severity),
            ignored_rule_ids=frozenset(ignored_ids),
            needs_languagetool=any(rule.engine == CheckEngine.external for rule, _ in rules_with_severity),
        )
