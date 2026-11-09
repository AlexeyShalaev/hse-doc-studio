"""Руководители и авторы проекта: тот же сценарий `UpdateProjectUC`, что у PATCH проекта в вебе.

Права те же, что у маршрута (PROJECT_SETTINGS и запрет записи в проект «только для чтения»), их проверяет
`CallMcpToolUC` по таблице каталога. Здесь только разбор аргументов: поля человека дополняют текущие значения,
список авторов заменяет текущий целиком, а у авторов, узнанных по slug или месту в списке, сохраняются поля,
которых в аргументах нет (почта, тема, комплект и мета team-проекта). `author` меняет одного автора, не трогая
список: в командном проекте его выбирают по slug. Пустая строка очищает поле, пустое ФИО руководителя убирает
его из проекта. Новый автор командного проекта приходит без комплекта (managed=false), как при добавлении автора
в настройках: папку автора материализует включение комплекта. Каждое изменение пишется в аудит.

Схемы и разбор людей здесь же переиспользует `create_project` (тот же формат автора и руководителя).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import PersonRole, ToolKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.normalize import is_valid_email
from hse_doc_studio.core.mcp.protocols import IMcpChangeAudit
from hse_doc_studio.core.team import is_team
from hse_doc_studio.core.value_objects import Author, Person
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError, McpTool, json_result, project_schema
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.projects.update_project import UpdateProjectInput, UpdateProjectUC

PEOPLE_AUDIT_ACTION = "project.people_update"
_PERSON_FIELDS = ("supervisor", "co_supervisor", "academic_supervisor")
_MAX_AUTHORS = 20
_MAX_TEXT = 300


def person_schema(description: str) -> dict[str, Any]:
    return {
        "type": "object",
        "description": description,
        "properties": {
            "name": {"type": "string", "description": "ФИО, например «С. А. Шершаков»"},
            "title": {"type": "string", "description": "Должность, например «доцент департамента ...»"},
            "degree": {"type": "string", "description": "Учёная степень или звание, например «канд. техн. наук»"},
            "role": {
                "type": "string",
                "enum": [r.value for r in PersonRole],
                "description": "university: из университета, company: от компании",
            },
        },
    }


def _person_schema(who: str) -> dict[str, Any]:
    return person_schema(
        f"{who}: переданные поля заменяют текущие, остальные сохраняются. Пустая строка очищает "
        "должность или степень, пустое ФИО убирает человека из проекта."
    )


_AUTHOR_FIELDS: dict[str, Any] = {
    "name": {"type": "string", "description": "ФИО"},
    "group": {"type": "string", "description": "Группа, например «БПИ221»; пустая строка очищает"},
    "email": {"type": "string", "description": "E-mail; пустая строка очищает"},
    "slug": {"type": "string", "description": "slug существующего автора из get_project"},
    "topic": {"type": "string", "description": "Тема автора в командном проекте; пустая строка очищает"},
}

_SPEC = ToolSpec(
    name="set_project_people",
    description=(
        "Изменить руководителей и авторов проекта: они попадают на титульный лист, в заявку и заявление. "
        "Передай только то, что меняешь; пустая строка очищает поле. author меняет одного автора: в командном "
        "проекте выбери его по slug из get_project, в одиночном меняется первый автор. authors заменяет список "
        "целиком; новый автор командного проекта появляется без комплекта (managed=false). topic: тема автора "
        "в командном проекте. Убрать руководителя: clear или пустое name. "
        'Пример: {"supervisor": {"name": "С. А. Шершаков", "degree": "канд. техн. наук"}, '
        '"author": {"group": "МПИ251", "email": "ivanov@edu.hse.ru"}}'
    ),
    parameters=project_schema(
        {
            "supervisor": _person_schema("Научный руководитель"),
            "co_supervisor": _person_schema("Соруководитель"),
            "academic_supervisor": _person_schema("Академический руководитель программы"),
            "author": {
                "type": "object",
                "description": "Один автор: переданные поля заменяют текущие, остальные сохраняются",
                "properties": _AUTHOR_FIELDS,
            },
            "authors": {
                "type": "array",
                "description": "Полный список авторов по порядку; первый идёт на титульный лист",
                "items": {"type": "object", "properties": _AUTHOR_FIELDS, "required": ["name"]},
            },
            "clear": {
                "type": "array",
                "items": {"type": "string", "enum": list(_PERSON_FIELDS)},
                "description": "Кого убрать из проекта",
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


def _email(raw: Mapping[str, object], where: str) -> str | None:
    value = _text(raw, "email", where)
    if value and not is_valid_email(value):
        raise ArgumentError(
            localized_error(f"{where}.email: неверный адрес {value!r}", f"{where}.email: invalid address {value!r}")
        )
    return value


def merge_person(current: Person | None, raw: object, where: str) -> Person | None:
    """Поля из аргумента поверх текущего человека; роль по умолчанию university, пустое ФИО: человека нет."""
    if not isinstance(raw, Mapping):
        raise ArgumentError(localized_error(f"{where}: ожидается объект", f"{where}: an object is expected"))
    name = _text(raw, "name", where)
    if name == "":
        return None
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


@dataclasses.dataclass(frozen=True)
class AuthorItem:
    """Автор из аргумента. None у текстового поля: не передано, пустая строка: очистить."""

    name: str
    group: str | None
    email: str | None
    slug: str | None
    topic: str | None


def author_items(raw: object) -> list[AuthorItem]:
    """Авторы из аргумента `authors`: непустой список объектов с ФИО, не длиннее _MAX_AUTHORS."""
    if not isinstance(raw, list) or not raw:
        raise ArgumentError(
            localized_error("authors: нужен непустой список авторов", "authors: a non-empty list is expected")
        )
    if len(raw) > _MAX_AUTHORS:
        raise ArgumentError(
            localized_error(f"authors: не больше {_MAX_AUTHORS} авторов", f"authors: at most {_MAX_AUTHORS} authors")
        )
    items: list[AuthorItem] = []
    for index, item in enumerate(raw):
        where = f"authors[{index}]"
        if not isinstance(item, Mapping):
            raise ArgumentError(localized_error(f"{where}: ожидается объект", f"{where}: an object is expected"))
        name = _text(item, "name", where)
        if not name:
            raise ArgumentError(localized_error(f"{where}: укажите ФИО (name)", f"{where}: specify the name"))
        items.append(
            AuthorItem(
                name=name,
                group=_text(item, "group", where),
                email=_email(item, where),
                slug=_text(item, "slug", where) or None,
                topic=_text(item, "topic", where),
            )
        )
    return items


def merge_authors(current: Sequence[Author], raw: object, *, team: bool = False) -> list[Author]:
    """Новый список авторов. Автор узнаётся по slug, а без slug по месту в списке, если там не узнанный по slug.

    `team`: проект командный, тогда новый автор приходит без комплекта, как из настроек в вебе.
    """
    items = author_items(raw)
    by_slug = {a.slug: a for a in current if a.slug}
    claimed = {item.slug for item in items if item.slug in by_slug}
    result: list[Author] = []
    for index, item in enumerate(items):
        base = by_slug.get(item.slug) if item.slug else None
        if base is None and item.slug is None and index < len(current) and current[index].slug not in claimed:
            base = current[index]
        if base is None:
            # Новый автор: slug team-проекта выведет сценарий из фамилии, чужой slug из аргументов не берём.
            result.append(
                Author(
                    name=item.name,
                    group=item.group or None,
                    email=item.email or None,
                    topic=item.topic or None,
                    managed=not team,
                )
            )
            continue
        result.append(
            dataclasses.replace(
                base,
                name=item.name,
                group=_replaced(item.group, base.group),
                email=_replaced(item.email, base.email),
                topic=_replaced(item.topic, base.topic),
            )
        )
    return result


def _replaced(value: str | None, current: str | None) -> str | None:
    """Новое значение текстового поля: None сохраняет текущее, пустая строка очищает."""
    return current if value is None else (value or None)


def update_author(project: Project, raw: object) -> list[Author]:
    """Список авторов, где один изменён: по slug, а в одиночном проекте без slug первый (или новый)."""
    where = "author"
    if not isinstance(raw, Mapping):
        raise ArgumentError(localized_error(f"{where}: ожидается объект", f"{where}: an object is expected"))
    name, group, email = _text(raw, "name", where), _text(raw, "group", where), _email(raw, where)
    slug, topic = _text(raw, "slug", where), _text(raw, "topic", where)
    if name is None and group is None and email is None and topic is None:
        raise ArgumentError(
            localized_error(
                f"{where}: передайте name, group, email или topic", f"{where}: pass name, group, email or topic"
            )
        )
    if name == "":
        raise ArgumentError(localized_error(f"{where}.name: ФИО нельзя очистить", f"{where}.name: cannot be cleared"))
    authors = list(project.authors)
    index = _author_index(project, slug)
    if index is None:
        if not name:
            raise ArgumentError(localized_error(f"{where}: укажите ФИО (name)", f"{where}: specify the name"))
        return [Author(name=name, group=group or None, email=email or None, topic=topic or None)]
    base = authors[index]
    authors[index] = dataclasses.replace(
        base,
        name=name or base.name,
        group=_replaced(group, base.group),
        email=_replaced(email, base.email),
        topic=_replaced(topic, base.topic),
    )
    return authors


def _author_index(project: Project, slug: str | None) -> int | None:
    """Место автора в списке; None: в одиночном проекте авторов ещё нет."""
    if slug:
        for index, author in enumerate(project.authors):
            if author.slug == slug:
                return index
        known = ", ".join(a.slug for a in project.authors if a.slug) or "-"
        raise ArgumentError(
            localized_error(
                f"author.slug: нет автора {slug!r}, есть: {known}", f"author.slug: no author {slug!r}, known: {known}"
            )
        )
    if is_team(project):
        raise ArgumentError(
            localized_error(
                "author: в командном проекте укажите slug автора из get_project",
                "author: in a team project pass the author's slug from get_project",
            )
        )
    return 0 if project.authors else None


def _cleared(args: Mapping[str, object]) -> set[str]:
    raw = args.get("clear") or []
    if not isinstance(raw, list) or any(c not in _PERSON_FIELDS for c in raw):
        raise ArgumentError(
            localized_error(
                "clear: список из supervisor, co_supervisor и academic_supervisor",
                "clear: a list of supervisor, co_supervisor and academic_supervisor",
            )
        )
    for field in raw:
        if args.get(field) is not None:
            raise ArgumentError(
                localized_error(f"{field}: нельзя одновременно задать и убрать", f"{field}: cannot both set and clear")
            )
    return set(raw)


def _authors_change(project: Project, args: Mapping[str, object]) -> list[Author] | None:
    """Новый список авторов из `authors` (весь список) или `author` (один автор); None — авторов не меняют."""
    whole, single = args.get("authors"), args.get("author")
    if whole is not None and single is not None:
        raise ArgumentError(localized_error("передайте author или authors, не оба", "pass author or authors, not both"))
    if whole is not None:
        return merge_authors(project.authors, whole, team=is_team(project))
    if single is not None:
        return update_author(project, single)
    return None


def _person_view(person: Person | None) -> dict[str, object] | None:
    if person is None:
        return None
    return {"name": person.name, "role": person.role.value, "title": person.title, "degree": person.degree}


def _authors_view(authors: Sequence[Author]) -> list[dict[str, object]]:
    return [
        {"name": a.name, "group": a.group, "email": a.email, "slug": a.slug, "topic": a.topic, "managed": a.managed}
        for a in authors
    ]


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
                "academic_supervisor": _person_view(updated.academic_supervisor),
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
        authors = _authors_change(project, args)
        if authors is not None:
            changes["authors"] = authors
        if not changes:
            raise ArgumentError(
                localized_error(
                    "передайте supervisor, co_supervisor, academic_supervisor, author, authors или clear",
                    "pass supervisor, co_supervisor, academic_supervisor, author, authors or clear",
                )
            )
        return changes
