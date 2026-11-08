"""Руководитель, соруководитель и авторы проекта: тот же сценарий `UpdateProjectUC`, что у PATCH проекта в вебе.

Права те же, что у маршрута (PROJECT_SETTINGS и запрет записи в проект «только для чтения»), их проверяет
`CallMcpToolUC` по таблице каталога. Здесь только разбор аргументов: поля человека дополняют текущие значения,
список авторов заменяет текущий целиком, а у авторов, узнанных по slug или месту в списке, сохраняются поля,
которых в аргументах нет (почта, тема, комплект и мета team-проекта). Каждое изменение пишется в аудит.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import PersonRole, ToolKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.mcp.protocols import IMcpChangeAudit
from hse_doc_studio.core.value_objects import Author, Person
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError, McpTool, json_result, project_schema
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.projects.update_project import UpdateProjectInput, UpdateProjectUC

PEOPLE_AUDIT_ACTION = "project.people_update"
_PERSON_FIELDS = ("supervisor", "co_supervisor")
_MAX_AUTHORS = 20
_MAX_TEXT = 300


def _person_schema(who: str) -> dict[str, Any]:
    return {
        "type": "object",
        "description": (
            f"{who}: переданные поля заменяют текущие, остальные сохраняются. Пустая строка очищает "
            "должность или степень."
        ),
        "properties": {
            "name": {"type": "string", "description": "ФИО"},
            "title": {"type": "string", "description": "Должность, например «доцент департамента ...»"},
            "degree": {"type": "string", "description": "Учёная степень или звание, например «канд. техн. наук»"},
            "role": {
                "type": "string",
                "enum": [r.value for r in PersonRole],
                "description": "university: из университета, company: от компании",
            },
        },
    }


_SPEC = ToolSpec(
    name="set_project_people",
    description=(
        "Изменить руководителя, соруководителя и авторов проекта: они попадают на титульный лист, в заявку "
        "и заявление. Передай только то, что меняешь. authors заменяет список целиком, первый автор идёт на "
        "титульный лист; у существующих авторов передай slug из get_project, чтобы сохранить их тему и "
        "комплект. Убрать соруководителя или руководителя: clear."
    ),
    parameters=project_schema(
        {
            "supervisor": _person_schema("Руководитель"),
            "co_supervisor": _person_schema("Соруководитель"),
            "authors": {
                "type": "array",
                "description": "Полный список авторов по порядку",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "ФИО"},
                        "group": {"type": "string", "description": "Группа, например «БПИ221»"},
                        "slug": {"type": "string", "description": "slug существующего автора из get_project"},
                    },
                    "required": ["name"],
                },
            },
            "clear": {
                "type": "array",
                "items": {"type": "string", "enum": list(_PERSON_FIELDS)},
                "description": "Кого убрать из проекта: supervisor, co_supervisor",
            },
        }
    ),
)


def _text(raw: Mapping[str, object], key: str, where: str) -> str | None:
    """None: ключа нет; строка (возможно пустая): новое значение."""
    if key not in raw or raw[key] is None:
        return None
    value = raw[key]
    if not isinstance(value, str):
        raise ArgumentError(localized_error(f"{where}.{key}: ожидается строка", f"{where}.{key}: a string is expected"))
    value = value.strip()
    if len(value) > _MAX_TEXT:
        raise ArgumentError(
            localized_error(
                f"{where}.{key}: не длиннее {_MAX_TEXT} символов", f"{where}.{key}: at most {_MAX_TEXT} characters"
            )
        )
    return value


def merge_person(current: Person | None, raw: object, where: str) -> Person:
    """Поля из аргумента поверх текущего человека; имя обязательно, роль по умолчанию university."""
    if not isinstance(raw, Mapping):
        raise ArgumentError(localized_error(f"{where}: ожидается объект", f"{where}: an object is expected"))
    name = _text(raw, "name", where)
    title = _text(raw, "title", where)
    degree = _text(raw, "degree", where)
    role_raw = _text(raw, "role", where)
    try:
        role = PersonRole(role_raw) if role_raw else (current.role if current else PersonRole.university)
    except ValueError:
        raise ArgumentError(
            localized_error(f"{where}.role: university или company", f"{where}.role: university or company")
        ) from None
    merged_name = name if name is not None else (current.name if current else "")
    if not merged_name:
        raise ArgumentError(localized_error(f"{where}: укажите ФИО (name)", f"{where}: specify the name"))
    return Person(
        name=merged_name,
        role=role,
        title=(title or None) if title is not None else (current.title if current else None),
        degree=(degree or None) if degree is not None else (current.degree if current else None),
    )


def _author_items(raw: object) -> list[tuple[str, str | None, str | None]]:
    """(ФИО, группа, slug) каждого автора из аргумента; группа None: не передана."""
    if not isinstance(raw, list) or not raw:
        raise ArgumentError(
            localized_error("authors: нужен непустой список авторов", "authors: a non-empty list is expected")
        )
    if len(raw) > _MAX_AUTHORS:
        raise ArgumentError(
            localized_error(f"authors: не больше {_MAX_AUTHORS} авторов", f"authors: at most {_MAX_AUTHORS} authors")
        )
    items: list[tuple[str, str | None, str | None]] = []
    for index, item in enumerate(raw):
        where = f"authors[{index}]"
        if not isinstance(item, Mapping):
            raise ArgumentError(localized_error(f"{where}: ожидается объект", f"{where}: an object is expected"))
        name = _text(item, "name", where)
        if not name:
            raise ArgumentError(localized_error(f"{where}: укажите ФИО (name)", f"{where}: specify the name"))
        items.append((name, _text(item, "group", where), _text(item, "slug", where) or None))
    return items


def merge_authors(current: Sequence[Author], raw: object) -> list[Author]:
    """Новый список авторов. Автор узнаётся по slug, а без slug по месту в списке, если там не узнанный по slug."""
    items = _author_items(raw)
    by_slug = {a.slug: a for a in current if a.slug}
    claimed = {slug for _, _, slug in items if slug in by_slug}
    result: list[Author] = []
    for index, (name, group, slug) in enumerate(items):
        base = by_slug.get(slug) if slug else None
        if base is None and slug is None and index < len(current) and current[index].slug not in claimed:
            base = current[index]
        if base is None:
            # Новый автор: slug team-проекта выведет сценарий из фамилии, чужой slug из аргументов не берём.
            result.append(Author(name=name, group=group or None))
            continue
        kept_group = (group or None) if group is not None else base.group
        result.append(dataclasses.replace(base, name=name, group=kept_group))
    return result


def _cleared(args: Mapping[str, object]) -> set[str]:
    raw = args.get("clear") or []
    if not isinstance(raw, list) or any(c not in _PERSON_FIELDS for c in raw):
        raise ArgumentError(
            localized_error(
                "clear: список из supervisor и co_supervisor", "clear: a list of supervisor and co_supervisor"
            )
        )
    for field in raw:
        if args.get(field) is not None:
            raise ArgumentError(
                localized_error(f"{field}: нельзя одновременно задать и убрать", f"{field}: cannot both set and clear")
            )
    return set(raw)


def _person_view(person: Person | None) -> dict[str, object] | None:
    if person is None:
        return None
    return {"name": person.name, "role": person.role.value, "title": person.title, "degree": person.degree}


def _authors_view(authors: Sequence[Author]) -> list[dict[str, object]]:
    return [{"name": a.name, "group": a.group, "slug": a.slug} for a in authors]


def _view(project: Project, field: str) -> object:
    if field == "authors":
        return _authors_view(project.authors)
    return _person_view(getattr(project, field))


class SetProjectPeopleTool(McpTool):
    spec = _SPEC
    kind = ToolKind.write

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        project = (
            await (await self._deps.get(GetProjectUC)).execute(GetProjectInput(project_id=ctx.project_id))
        ).project
        changes = self._changes(project, args)
        before = {field: _view(project, field) for field in changes}
        inp = UpdateProjectInput(project_id=ctx.project_id)
        for field, value in changes.items():
            setattr(inp, field, value)
        updated = (await (await self._deps.get(UpdateProjectUC)).execute(inp)).project
        after = {field: _view(updated, field) for field in changes}
        changed = [field for field in changes if before[field] != after[field]]
        if changed:
            audit = await self._deps.get(IMcpChangeAudit)  # type: ignore[type-abstract]  # порт из контейнера
            await audit.record(
                PEOPLE_AUDIT_ACTION,
                target=str(ctx.project_id),
                details={
                    "via": "mcp",
                    "fields": changed,
                    "before": {f: before[f] for f in changed},
                    "after": {f: after[f] for f in changed},
                },
            )
        return json_result(
            {
                "changed": changed,
                "authors": _authors_view(updated.authors),
                "supervisor": _person_view(updated.supervisor),
                "co_supervisor": _person_view(updated.co_supervisor),
            }
        )

    @staticmethod
    def _changes(project: Project, args: Mapping[str, object]) -> dict[str, object]:
        cleared = _cleared(args)
        changes: dict[str, object] = {}
        for field in _PERSON_FIELDS:
            raw = args.get(field)
            if field in cleared:
                changes[field] = None
            elif raw is not None:
                changes[field] = merge_person(getattr(project, field), raw, field)
        if args.get("authors") is not None:
            changes["authors"] = merge_authors(project.authors, args.get("authors"))
        if not changes:
            raise ArgumentError(
                localized_error(
                    "передайте supervisor, co_supervisor, authors или clear",
                    "pass supervisor, co_supervisor, authors or clear",
                )
            )
        return changes
