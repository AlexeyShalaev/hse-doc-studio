from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.documents.list_documents import (
    DocumentListEntry,
    ListDocumentsInput,
    ListDocumentsUC,
)

_SPEC = ToolSpec(
    name="list_documents",
    description=(
        "Список документов комплекта проекта: идентификатор (doc_id), статус, выбранный вариант, "
        "путь исходника и (в командном проекте) автор-владелец. В командном проекте личные документы "
        "имеют id вида 'vkr--ivanov', общие (например общее ТЗ) — обычный id. "
        "Используй, чтобы узнать доступные документы перед сборкой, проверками или ссылками на них."
    ),
    parameters={"type": "object", "properties": {}},
)


class ListDocumentsTool:
    def __init__(self, list_documents_uc: ListDocumentsUC) -> None:
        self._list = list_documents_uc

    def definition(self) -> ToolDefinition:
        return ToolDefinition(spec=_SPEC, kind=ToolKind.read, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        out = await self._list.execute(ListDocumentsInput(project_id=ctx.project_id))
        if not out.entries:
            return ToolResult.ok("the project has no documents" if lang == Lang.en else "в проекте нет документов")
        header = "Project documents:\n" if lang == Lang.en else "Документы проекта:\n"
        return ToolResult.ok(header + "\n".join(_format(e, lang) for e in out.entries))


def _format(entry: DocumentListEntry, lang: Lang) -> str:
    doc = entry.document
    source = f" [{entry.source_file}]" if entry.source_file else ""
    if lang == Lang.en:
        variant = f", variant {doc.chosen_variant}" if doc.chosen_variant else ""
        owner = f", owner: {entry.owner_name}" if entry.owner_name else ""
        return f"- {doc.id}: status {doc.status}{variant}{owner}{source}"
    variant = f", вариант {doc.chosen_variant}" if doc.chosen_variant else ""
    owner = f", автор: {entry.owner_name}" if entry.owner_name else ""
    return f"- {doc.id}: статус {doc.status}{variant}{owner}{source}"
