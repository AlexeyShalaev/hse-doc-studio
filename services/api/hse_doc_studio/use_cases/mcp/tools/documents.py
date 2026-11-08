"""Вариант документа (формат презентации и т. п.): тот же `UpdateDocumentUC`, что PATCH документа в вебе.

Право то же, что у маршрута (FILES_WRITE в области автора документа и запрет записи в проект «только для
чтения»), его проверяет `CallMcpToolUC` по таблице каталога. Допустимые варианты берутся из определения
документа в шаблоне проекта и фильтруются по языку проекта, как в настройках проекта. Смена пишется в аудит.
"""

from __future__ import annotations

from collections.abc import Sequence

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.catalog import DocumentDefinition, DocumentVariant
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.mcp.protocols import IMcpChangeAudit
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.use_cases.documents.update_document import (
    InvalidVariantError,
    UpdateDocumentInput,
    UpdateDocumentUC,
    selectable_variants,
)
from hse_doc_studio.use_cases.mcp.tools._base import (
    ArgumentError,
    McpTool,
    json_result,
    optional_text,
    project_schema,
    text_arg,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

VARIANT_AUDIT_ACTION = "document.variant_update"

_SPEC = ToolSpec(
    name="set_document_variant",
    description=(
        "Выбрать вариант документа, как переключатель «Форматы документов» в настройках проекта. Например, "
        "у презентации: pptx, beamer или reveal. Без variant только показывает текущий вариант и допустимые. "
        "Смена сбрасывает статус документа в черновик, файлы прежнего варианта остаются. Пример: "
        '{"doc_id": "presentation", "variant": "beamer"}.'
    ),
    parameters=project_schema(
        {
            "doc_id": {"type": "string", "description": "Документ из list_documents, например presentation"},
            "variant": {"type": "string", "description": "id варианта, например pptx, beamer, reveal"},
        },
        ("doc_id",),
    ),
)


def _label(variant: DocumentVariant) -> str:
    lang = current_interface_language().value
    return variant.label.get(lang) or next(iter(variant.label.values()), variant.id)


def _view(doc: Document, doc_def: DocumentDefinition, choices: Sequence[DocumentVariant]) -> dict[str, object]:
    current = doc.chosen_variant or doc_def.variants[0].id
    return {
        "doc_id": doc.id,
        "variant": current,
        "status": doc.status,
        "variants": [{"id": v.id, "label": _label(v), "current": v.id == current} for v in choices],
    }


def _allowed(choices: Sequence[DocumentVariant]) -> str:
    return ", ".join(v.id for v in choices)


class SetDocumentVariantTool(McpTool):
    spec = _SPEC
    kind = ToolKind.write

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        doc_id = text_arg(args, "doc_id")
        variant = optional_text(args, "variant")
        project = (
            await (await self._deps.get(GetProjectUC)).execute(GetProjectInput(project_id=ctx.project_id))
        ).project
        doc = next((d for d in project.documents if d.id == doc_id), None)
        if doc is None:
            ids = ", ".join(d.id for d in project.documents)
            raise ArgumentError(
                localized_error(
                    f"Документа {doc_id!r} нет в проекте; есть: {ids}",
                    f"No document {doc_id!r} in the project; there are: {ids}",
                )
            )
        doc_def = await self._definition(project, doc)
        choices = selectable_variants(project, doc_def)
        if variant is None:
            return json_result({**_view(doc, doc_def, choices), "changed": False})
        before = doc.chosen_variant
        try:
            updated = (
                await (await self._deps.get(UpdateDocumentUC)).execute(
                    UpdateDocumentInput(project_id=ctx.project_id, doc_id=doc_id, chosen_variant=variant)
                )
            ).document
        except InvalidVariantError as exc:
            raise ArgumentError(
                localized_error(
                    f"{exc} Допустимые варианты: {_allowed(choices)}.", f"{exc} Allowed variants: {_allowed(choices)}."
                )
            ) from exc
        changed = updated.chosen_variant != before
        if changed:
            audit = await self._deps.get(IMcpChangeAudit)  # type: ignore[type-abstract]  # порт из контейнера
            await audit.record(
                VARIANT_AUDIT_ACTION,
                target=str(ctx.project_id),
                details={
                    "via": "mcp",
                    "fields": ["chosen_variant"],
                    "doc_id": doc_id,
                    "before": before,
                    "after": updated.chosen_variant,
                },
            )
        return json_result({**_view(updated, doc_def, choices), "changed": changed})

    async def _definition(self, project: Project, doc: Document) -> DocumentDefinition:
        """Определение документа в версии шаблона проекта; без вариантов отказ, как у PATCH документа."""
        templates = await self._deps.get(ITemplateRepository)  # type: ignore[type-abstract]  # порт из контейнера
        lock = project.lock
        version = templates.get_version(lock.pack_id, lock.template_id, lock.version)
        doc_def = ProjectTemplateService().find_definition(version, doc) if version is not None else None
        if doc_def is None:
            raise NotFoundError(localized_error("Версия шаблона не найдена", "Template version not found"))
        if not doc_def.variants:
            raise ArgumentError(
                localized_error(f"У документа {doc.id!r} нет вариантов", f"Document {doc.id!r} has no variants")
            )
        return doc_def
