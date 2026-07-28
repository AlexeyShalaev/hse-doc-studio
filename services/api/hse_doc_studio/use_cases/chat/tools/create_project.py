from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import EngineType, Lang, ProjectKind, ProjectStaffing, ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.value_objects import Author
from hse_doc_studio.use_cases.projects.create_project import CreateProjectInput, CreateProjectUC

_SPEC = ToolSpec(
    name="create_project",
    description=(
        "Создать новый проект из шаблона. Перед вызовом узнай допустимые pack_id/template_id/version "
        "через list_templates, а недостающие данные (название, папку) спроси у пользователя через ask_user. "
        "kind: research|project, staffing: solo|team, lang: ru|en, engine: xelatex|lualatex|pdflatex."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Название проекта"},
            "folder": {"type": "string", "description": "Абсолютный путь к папке проекта (будет создана)"},
            "pack_id": {"type": "string"},
            "template_id": {"type": "string"},
            "version": {"type": "string", "description": "Версия шаблона (из list_templates)"},
            "lang": {"type": "string", "enum": ["ru", "en"]},
            "kind": {"type": "string", "enum": ["research", "project"]},
            "staffing": {"type": "string", "enum": ["solo", "team"]},
            "engine": {"type": "string", "enum": ["xelatex", "lualatex", "pdflatex"]},
            "author_name": {"type": "string", "description": "ФИО автора (необязательно)"},
        },
        "required": ["name", "folder", "pack_id", "template_id", "version"],
    },
)

_E = TypeVar("_E", ProjectKind, ProjectStaffing, Lang, EngineType)


def _enum_or(value: object, enum_cls: type[_E], default: _E) -> _E:
    try:
        return enum_cls(str(value).strip().lower())
    except ValueError:
        return default


def _str(value: object) -> str:
    return str(value).strip() if value is not None else ""


class CreateProjectTool:
    def __init__(self, create_project_uc: CreateProjectUC) -> None:
        self._create = create_project_uc

    def definition(self) -> ToolDefinition:
        # Side-effecting (writes files, registers a project), so exec + approval-gated.
        # App-level (no current project needed) → requires_project=False.
        return ToolDefinition(
            spec=_SPEC, kind=ToolKind.exec_, handler=self, weak_model_safe=True, requires_project=False
        )

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        name = _str(args.get("name"))
        folder = _str(args.get("folder"))
        pack_id = _str(args.get("pack_id"))
        template_id = _str(args.get("template_id"))
        version = _str(args.get("version"))
        if not (name and folder and pack_id and template_id and version):
            return ToolResult.error(
                "name, folder, pack_id, template_id and version are required (see list_templates)"
                if lang == Lang.en
                else "нужны name, folder, pack_id, template_id и version (см. list_templates)"
            )

        author_name = _str(args.get("author_name"))
        authors = [Author(name=author_name)] if author_name else []
        meta: dict[str, Any] = {}
        try:
            out = await self._create.execute(
                CreateProjectInput(
                    folder=Path(folder),
                    pack_id=pack_id,
                    template_id=template_id,
                    version=version,
                    name=name,
                    kind=_enum_or(args.get("kind"), ProjectKind, ProjectKind.research),
                    staffing=_enum_or(args.get("staffing"), ProjectStaffing, ProjectStaffing.solo),
                    lang=_enum_or(args.get("lang"), Lang, Lang.ru),
                    engine=_enum_or(args.get("engine"), EngineType, EngineType.xelatex),
                    authors=authors,
                    supervisor=None,
                    co_supervisor=None,
                    meta=meta,
                )
            )
        except (ValueError, NotFoundError) as exc:
            return ToolResult.error(str(exc))
        project = out.project
        return ToolResult.ok(
            f"project «{project.name}» created (id {project.id}, folder {project.folder})"
            if lang == Lang.en
            else f"проект «{project.name}» создан (id {project.id}, папка {project.folder})"
        )
