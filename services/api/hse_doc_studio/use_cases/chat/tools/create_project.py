from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, TypeVar

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import EngineType, Lang, ProjectKind, ProjectStaffing, ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.team import RESERVED_SLUGS, is_team, is_valid_slug, managed_authors
from hse_doc_studio.core.value_objects import Author, Person
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError
from hse_doc_studio.use_cases.mcp.tools.people import author_items, merge_person, person_schema
from hse_doc_studio.use_cases.projects.create_project import CreateProjectInput, CreateProjectUC

_AUTHOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "ФИО, например «Иванов Иван Иванович»"},
        "group": {"type": "string", "description": "Группа, например «БПИ221»"},
        "email": {"type": "string", "description": "E-mail"},
        "topic": {
            "type": "string",
            "description": "Тема автора в командном проекте (его часть работы); обязательна у ведомого автора",
        },
        "slug": {
            "type": "string",
            "description": "Папка автора в командном проекте: a-z, 0-9, _; по умолчанию из фамилии",
        },
        "managed": {
            "type": "boolean",
            "description": "Командный проект: вести ли комплект документов автора здесь (по умолчанию да)",
        },
    },
    "required": ["name"],
}
_CREATE_PERSON = "необязательно, можно задать позже через set_project_people"

_COMMON_PROPERTIES: dict[str, Any] = {
    "name": {"type": "string", "description": "Название проекта"},
    "pack_id": {"type": "string"},
    "template_id": {"type": "string"},
    "version": {"type": "string", "description": "Версия шаблона (из list_templates)"},
    "lang": {"type": "string", "enum": ["ru", "en"]},
    "kind": {"type": "string", "enum": ["research", "project"]},
    "staffing": {
        "type": "string",
        "enum": ["solo", "team"],
        "description": "solo: один автор, team: командный проект; по умолчанию team, если авторов больше одного",
    },
    "engine": {"type": "string", "enum": ["xelatex", "lualatex", "pdflatex"]},
    "author_name": {"type": "string", "description": "ФИО единственного автора (необязательно; иначе authors)"},
    "authors": {
        "type": "array",
        "description": "Авторы по порядку, первый идёт на титульный лист; больше одного: командный проект",
        "items": _AUTHOR_SCHEMA,
    },
    "shared_enabled": {
        "type": "boolean",
        "description": "Командный проект: вести ли общие документы команды (по умолчанию да)",
    },
    "supervisor": {**person_schema(f"Научный руководитель: {_CREATE_PERSON}"), "required": ["name"]},
    "co_supervisor": {**person_schema(f"Соруководитель: {_CREATE_PERSON}"), "required": ["name"]},
    "academic_supervisor": {
        **person_schema(f"Академический руководитель программы: {_CREATE_PERSON}"),
        "required": ["name"],
    },
}
_FOLDER_PROPERTY: dict[str, Any] = {
    "type": "string",
    "description": "Абсолютный путь к папке проекта (будет создана)",
}
_TAIL = (
    "Авторы: authors (name, group, email, topic, slug, managed), для одного автора хватит author_name. "
    "Несколько авторов: командный проект (staffing team), как в мастере создания. Шаблон должен поддерживать "
    "командный режим (team в list_templates), у каждого ведомого автора (managed, по умолчанию да) нужна тема "
    "topic, ведомым должен быть хотя бы один, slug папки автора по умолчанию выводится из фамилии. "
    "shared_enabled: вести ли общие документы команды. Руководители supervisor, co_supervisor и "
    "academic_supervisor необязательны. "
    "kind: research|project, staffing: solo|team, lang: ru|en, engine: xelatex|lualatex|pdflatex."
)


def create_project_spec(*, server_mode: bool) -> ToolSpec:
    """Схема зависит от режима: на общем сервере папку выделяет сервер, поэтому поля folder в ней нет."""
    if server_mode:
        return ToolSpec(
            name="create_project",
            description=(
                "Создать новый проект из шаблона. Перед вызовом узнай допустимые pack_id/template_id/version "
                "через list_templates, а недостающее название уточни у пользователя. Папку проекта выбирает "
                "сервер. " + _TAIL
            ),
            parameters={
                "type": "object",
                "properties": dict(_COMMON_PROPERTIES),
                "required": ["name", "pack_id", "template_id", "version"],
            },
        )
    return ToolSpec(
        name="create_project",
        description=(
            "Создать новый проект из шаблона. Перед вызовом узнай допустимые pack_id/template_id/version "
            "через list_templates, а недостающие данные (название, папку) уточни у пользователя. " + _TAIL
        ),
        parameters={
            "type": "object",
            "properties": {"name": _COMMON_PROPERTIES["name"], "folder": _FOLDER_PROPERTY, **_COMMON_PROPERTIES},
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


@dataclass(frozen=True)
class _People:
    """Люди и состав нового проекта, разобранные так же, как их собирает мастер создания в вебе."""

    staffing: ProjectStaffing
    authors: list[Author]
    shared_enabled: bool
    supervisor: Person | None
    co_supervisor: Person | None
    academic_supervisor: Person | None
    meta: dict[str, Any]


def _people(args: Mapping[str, object]) -> _People:
    authors = _authors(args)
    staffing = _staffing(args, authors)
    if staffing == ProjectStaffing.team:
        _check_team(authors)
    else:
        # Одиночному проекту командные поля не нужны: комплект единственного автора ведётся всегда.
        authors = [replace(a, managed=True) for a in authors]
    # Как мастер: группа для титульного листа и проверок (meta.group) берётся у первого автора, у кого она есть.
    group = next((a.group for a in authors if a.group), None)
    return _People(
        staffing=staffing,
        authors=authors,
        shared_enabled=_flag(args, "shared_enabled", "shared_enabled") if staffing == ProjectStaffing.team else True,
        supervisor=_person(args, "supervisor"),
        co_supervisor=_person(args, "co_supervisor"),
        academic_supervisor=_person(args, "academic_supervisor"),
        meta={"group": group} if group else {},
    )


def _authors(args: Mapping[str, object]) -> list[Author]:
    """Авторы из `authors` или, как раньше, единственный автор из `author_name` (а то и никого)."""
    raw = args.get("authors")
    author_name = _str(args.get("author_name"))
    if raw is None:
        return [Author(name=author_name)] if author_name else []
    if author_name:
        raise ArgumentError(
            localized_error("передайте author_name или authors, не оба", "pass author_name or authors, not both")
        )
    items = author_items(raw)  # тот же разбор автора, что у set_project_people; raw уже проверен как список
    entries: list[Mapping[str, object]] = raw if isinstance(raw, list) else []
    return [
        Author(
            name=item.name,
            group=item.group or None,
            email=item.email or None,
            slug=item.slug,
            topic=item.topic or None,
            managed=_flag(entry, "managed", f"authors[{index}].managed"),
        )
        for index, (item, entry) in enumerate(zip(items, entries, strict=True))
    ]


def _flag(raw: Mapping[str, object], key: str, where: str) -> bool:
    """Флаг true/false; по умолчанию true, как в мастере создания."""
    value = raw.get(key)
    if value is None:
        return True
    if not isinstance(value, bool):
        raise ArgumentError(localized_error(f"{where}: ожидается true или false", f"{where}: true or false expected"))
    return value


def _person(args: Mapping[str, object], field: str) -> Person | None:
    raw = args.get(field)
    return None if raw is None else merge_person(None, raw, field)


def _staffing(args: Mapping[str, object], authors: list[Author]) -> ProjectStaffing:
    """Явный staffing или, как в мастере, по числу авторов: больше одного означает командный проект."""
    derived = ProjectStaffing.team if len(authors) > 1 else ProjectStaffing.solo
    staffing = _enum_or(args.get("staffing"), ProjectStaffing, derived) if args.get("staffing") else derived
    if staffing == ProjectStaffing.solo and len(authors) > 1:
        raise ArgumentError(
            localized_error(
                "у одиночного проекта один автор: для нескольких авторов нужен командный проект (staffing team)",
                "a solo project has one author: several authors need a team project (staffing team)",
            )
        )
    return staffing


def _check_team(authors: list[Author]) -> None:
    """Проверки шага «Авторы» мастера; поддержку шаблоном, число авторов и вывод slug проверяет сценарий."""
    slugs = [a.slug for a in authors if a.slug]
    for slug in slugs:
        if not is_valid_slug(slug) or slug in RESERVED_SLUGS:
            raise ArgumentError(
                localized_error(
                    f"slug {slug!r}: латиница в нижнем регистре, цифры и _, с буквы; "
                    f"нельзя {', '.join(sorted(RESERVED_SLUGS))}",
                    f"slug {slug!r}: lowercase latin letters, digits and _, starting with a letter; "
                    f"not {', '.join(sorted(RESERVED_SLUGS))}",
                )
            )
    duplicates = sorted({s for s in slugs if slugs.count(s) > 1})
    if duplicates:
        raise ArgumentError(
            localized_error(f"slug повторяется: {', '.join(duplicates)}", f"duplicate slug: {', '.join(duplicates)}")
        )
    without_topic = [a.name for a in authors if a.managed and not a.topic]
    if without_topic:
        raise ArgumentError(
            localized_error(
                f"у ведомого автора нужна тема (topic): {', '.join(without_topic)}",
                f"a managed author needs a topic: {', '.join(without_topic)}",
            )
        )
    if not any(a.managed for a in authors):
        raise ArgumentError(
            localized_error("хотя бы один автор должен быть ведомым (managed)", "at least one author must be managed")
        )


class CreateProjectTool:
    def __init__(self, create_project_uc: CreateProjectUC) -> None:
        self._create = create_project_uc
        self._server_mode = create_project_uc.server_allocates_folder

    def definition(self) -> ToolDefinition:
        # Side-effecting (writes files, registers a project), so exec + approval-gated.
        # App-level (no current project needed) → requires_project=False.
        return ToolDefinition(
            spec=create_project_spec(server_mode=self._server_mode),
            kind=ToolKind.exec_,
            handler=self,
            weak_model_safe=True,
            requires_project=False,
        )

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        name = _str(args.get("name"))
        # На общем сервере папку выделяет сервер: присланное клиентом поле folder не используется.
        folder = "" if self._server_mode else _str(args.get("folder"))
        pack_id = _str(args.get("pack_id"))
        template_id = _str(args.get("template_id"))
        version = _str(args.get("version"))
        if not (name and pack_id and template_id and version and (folder or self._server_mode)):
            return ToolResult.error(_missing_message(lang, server_mode=self._server_mode))

        try:
            people = _people(args)
            out = await self._create.execute(
                CreateProjectInput(
                    folder=Path(folder) if folder else None,
                    pack_id=pack_id,
                    template_id=template_id,
                    version=version,
                    name=name,
                    kind=_enum_or(args.get("kind"), ProjectKind, ProjectKind.research),
                    staffing=people.staffing,
                    lang=_enum_or(args.get("lang"), Lang, Lang.ru),
                    engine=_enum_or(args.get("engine"), EngineType, EngineType.xelatex),
                    authors=people.authors,
                    supervisor=people.supervisor,
                    co_supervisor=people.co_supervisor,
                    academic_supervisor=people.academic_supervisor,
                    meta=people.meta,
                    shared_enabled=people.shared_enabled,
                )
            )
        except (ValueError, NotFoundError) as exc:
            return ToolResult.error(str(exc))
        return ToolResult.ok(_created_message(out.project, lang))


def _created_message(project: Project, lang: Lang) -> str:
    if lang == Lang.en:
        text = f"project «{project.name}» created (id {project.id}, folder {project.folder})"
    else:
        text = f"проект «{project.name}» создан (id {project.id}, папка {project.folder})"
    if not is_team(project):
        return text
    # slug нужен дальше: set_project_people выбирает автора командного проекта по нему.
    sets = ", ".join(f"{a.slug} ({a.name})" for a in managed_authors(project)) or "-"
    return text + (f"; author sets: {sets}" if lang == Lang.en else f"; комплекты авторов: {sets}")


def _missing_message(lang: Lang, *, server_mode: bool) -> str:
    if server_mode:
        return (
            "name, pack_id, template_id and version are required (see list_templates)"
            if lang == Lang.en
            else "нужны name, pack_id, template_id и version (см. list_templates)"
        )
    return (
        "name, folder, pack_id, template_id and version are required (see list_templates)"
        if lang == Lang.en
        else "нужны name, folder, pack_id, template_id и version (см. list_templates)"
    )
