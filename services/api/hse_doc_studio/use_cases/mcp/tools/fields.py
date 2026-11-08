"""list_project_fields: поля шаблона для проекта, как их показывают настройки, с текущими значениями.

Определения берутся из того же описания версии шаблона, что отдаёт каталог интерфейсу (`ITemplateRepository`),
проект читается тем же `GetProjectUC`, что и `get_project`. Право то же, что у просмотра проекта (PROJECT_VIEW).
"""

from __future__ import annotations

from typing import Any

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.catalog import DocumentDefinition, MetaFieldDef
from hse_doc_studio.core.enums import RequiredAt, ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.value_objects import Person
from hse_doc_studio.use_cases.mcp.tools._base import McpTool, json_result, project_schema
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.projects.project_fields import ProjectField, list_project_fields, project_documents

_SPEC = ToolSpec(
    name="list_project_fields",
    description=(
        "Поля проекта из описания шаблона: ключ, подпись, текущее значение, допустимые значения или подсказка, "
        "обязательность и документы, где поле печатается. Задать поле: set_project_meta, людей: "
        "set_project_people. unknown_meta: ключи, которых шаблон не знает и не печатает. Пример ответа: "
        '{"key": "udc", "label": "Код УДК", "value": null, "required": true, "required_at": "finalize", '
        '"printed_in": [{"id": "report", "name": "Отчёт"}]}'
    ),
    parameters=project_schema({}),
)


def _pick(value: dict[str, str] | None, lang: str) -> str | None:
    if not value:
        return None
    return value.get(lang) or value.get("ru") or value.get("en") or next(iter(value.values()), None)


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _value(value: object) -> object:
    if isinstance(value, Person):
        return {"name": value.name, "role": value.role.value, "title": value.title, "degree": value.degree}
    return value


def _field_view(field: ProjectField, names: dict[str, str], lang: str) -> dict[str, Any]:
    definition: MetaFieldDef = field.definition
    required = definition.required_at is not RequiredAt.never
    view: dict[str, Any] = {
        "key": field.key,
        "label": _pick(definition.label, lang) or field.key,
        "type": str(definition.type),
        "value": _value(field.value),
        "required": required,
        "required_at": str(definition.required_at),
        "missing": required and _blank(field.value),
        "printed_in": [{"id": doc_id, "name": names.get(doc_id, doc_id)} for doc_id in field.printed_in],
        "set_with": "set_project_people" if field.is_person else "set_project_meta",
    }
    if definition.options:
        view["options"] = list(definition.options)
    hint = _pick(definition.help, lang)
    if hint:
        view["hint"] = hint
    if definition.placeholder:
        view["example"] = definition.placeholder
    if definition.default is not None:
        view["default"] = definition.default
    if definition.group:
        view["group"] = definition.group
    if field.author_values:
        view["author_values"] = field.author_values
    return view


def _doc_name(doc: DocumentDefinition, lang: str) -> str:
    return _pick(doc.name, lang) or doc.id


class ListProjectFieldsTool(McpTool):
    spec = _SPEC
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        project = (
            await (await self._deps.get(GetProjectUC)).execute(GetProjectInput(project_id=ctx.project_id))
        ).project
        templates = await self._deps.get(ITemplateRepository)  # type: ignore[type-abstract]  # порт из контейнера
        lock = project.lock
        version = templates.get_version(lock.pack_id, lock.template_id, lock.version)
        if version is None:
            ref = f"{lock.pack_id}/{lock.template_id}/{lock.version}"
            raise NotFoundError(
                localized_error(f"Версия шаблона не найдена: {ref}", f"Template version not found: {ref}")
            )
        version_dir = templates.version_dir(lock.pack_id, lock.template_id, lock.version)
        fields = list_project_fields(project, version, version_dir / "files" if version_dir is not None else None)
        lang = current_interface_language().value
        names = {doc.id: _doc_name(doc, lang) for doc in project_documents(project, version)}
        # Ключи project.meta, которых шаблон не описывает: документы их не печатают, убрать можно через unset.
        described = set(version.meta_fields)
        unknown = {key: value for key, value in project.meta.items() if key not in described}
        return json_result(
            {
                "template": f"{lock.pack_id}/{lock.template_id}/{lock.version}",
                "fields": [_field_view(field, names, lang) for field in fields],
                "unknown_meta": unknown,
            }
        )
