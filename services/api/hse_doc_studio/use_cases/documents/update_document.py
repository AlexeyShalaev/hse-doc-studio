from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import DocumentDefinition
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import DocumentStatus
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.value_objects import ChecksOverride
from hse_doc_studio.infra.project_init.template_renderer import (
    TemplateRenderer,
    instantiate_missing_doc_files,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()

_MISSING = object()


class InvalidVariantError(ValueError):
    """Недопустимая смена варианта: у документа нет вариантов либо id неизвестен.

    Отдельный тип, чтобы роутер мог отдать 400 (плохой запрос), а не 404 —
    маппинг ValueError→404 в этом роутере зарезервирован за not-found.
    """


@dataclass
class UpdateDocumentInput:
    project_id: UUID
    doc_id: str
    checks_override: ChecksOverride | None = None
    chosen_variant: str | None = _MISSING  # type: ignore[assignment]


@dataclass
class UpdateDocumentOutput:
    document: Document


class UpdateDocumentUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_renderer: TemplateRenderer,
    ) -> None:
        self._project_repo = project_repo
        self._template_repo = template_repo
        self._template_renderer = template_renderer
        self._template_service = ProjectTemplateService()
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: UpdateDocumentInput) -> UpdateDocumentOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        doc = next((d for d in project.documents if d.id == inp.doc_id), None)
        if doc is None:
            raise NotFoundError(
                localized_error(
                    f"Документ {inp.doc_id!r} не найден в проекте {inp.project_id}",
                    f"Document '{inp.doc_id}' not found in project {inp.project_id}",
                )
            )

        if inp.checks_override is not None:
            doc.checks_override = inp.checks_override
        if inp.chosen_variant is not _MISSING:
            self._apply_variant(project, doc, inp.chosen_variant)

        project.updated_at = datetime.now(tz=timezone.utc)
        self._project_repo.save(project)

        logger.info(
            "document updated",
            project_id=str(inp.project_id),
            doc_id=inp.doc_id,
        )
        return UpdateDocumentOutput(document=doc)

    def _apply_variant(self, project: Project, doc: Document, requested: str | None) -> None:
        """Реальное переключение варианта (не просто запись поля).

        Валидирует id по определению пака; None — сброс к дефолту (первый
        вариант). Смена — lossless: файлы предыдущего варианта не удаляются,
        а ОТСУТСТВУЮЩИЕ файлы всех вариантов дока докладываются из пака
        (проекты, созданные до материализации всех вариантов, несут файлы
        только одного). Статус сбрасывается в draft — прошлые сборка/проверки
        принадлежали другому варианту.
        """
        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        if version is None:
            raise NotFoundError(localized_error("Версия шаблона не найдена", "Template version not found"))
        doc_def = self._template_service.find_definition(version, doc)
        if doc_def is None:
            raise NotFoundError(
                localized_error(
                    f"Определение документа для {doc.def_id!r} не найдено",
                    f"Document definition not found for {doc.def_id!r}",
                )
            )
        effective = _resolve_effective_variant(project, doc, doc_def, requested)
        if effective == doc.chosen_variant:
            return  # тот же вариант — no-op, статус не трогаем

        doc.chosen_variant = effective
        doc.status = DocumentStatus.draft
        # Best-effort материализация недостающих файлов варианта: сбой (нет
        # пака на диске и т.п.) не должен ронять PATCH — выбор уже применён.
        try:
            instantiate_missing_doc_files(
                project=project,
                version=version,
                template_repo=self._template_repo,
                renderer=self._template_renderer,
                doc=doc,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "variant switch: materialisation failed",
                doc_id=doc.id,
                variant=effective,
                exc=str(exc),
            )


def _resolve_effective_variant(
    project: Project,
    doc: Document,
    doc_def: DocumentDefinition,
    requested: str | None,
) -> str:
    """Проверить запрошенный вариант по определению пака и вернуть итоговый id.

    `None` — сброс к дефолту (первый вариант определения). Любой отказ —
    `InvalidVariantError` (→ 400): документ без вариантов, неизвестный id,
    либо вариант с ограничением по языку в проекте другого языка
    (IEEE/ISO-редакции — только en).
    """
    if not doc_def.variants:
        raise InvalidVariantError(
            localized_error(
                f"У документа {doc.def_id!r} нет вариантов",
                f"Document {doc.def_id!r} has no variants",
            )
        )
    variant_ids = [v.id for v in doc_def.variants]
    if requested is None:
        return variant_ids[0]
    if requested not in variant_ids:
        raise InvalidVariantError(
            localized_error(
                f"Неизвестный вариант {requested!r} для документа {doc.def_id!r}; допустимые: {variant_ids}",
                f"Unknown variant {requested!r} for document {doc.def_id!r}; allowed: {variant_ids}",
            )
        )
    variant = next(v for v in doc_def.variants if v.id == requested)
    if variant.supported_langs and str(project.lang) not in variant.supported_langs:
        raise InvalidVariantError(
            localized_error(
                f"Вариант {requested!r} недоступен в проекте на языке {project.lang!s}",
                f"Variant {requested!r} is not available for a {project.lang!s}-language project",
            )
        )
    return requested
