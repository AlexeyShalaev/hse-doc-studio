"""Предпросмотр версии шаблона на тестовых данных (docs/design/template-studio.md, раздел 6, срез T7).

Чистая логика без ввода-вывода: переключатели комбинаций по модели версии (6.2), разбор примеров
`templates/<шаблон>/examples/*.yaml` и автонаборы без них (6.1), синтетический проект из набора и переключателей
(6.3, шаг 1) и ключ кэша сборки (6.3, шаг 4).

Переключатели поверх набора данных: набор задаёт имена и тексты, переключатели задают ветки. Комбинация это словарь
`{id переключателя: значение}`, все значения строки, чтобы её можно было положить в адрес страницы.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from hse_doc_studio.core.catalog import DocumentDefinition, MetaFieldDef, TemplateVersion
from hse_doc_studio.core.doc_dirs import def_source_dirs
from hse_doc_studio.core.enums import Lang, MetaFieldType, PersonRole, ProjectKind, ProjectStaffing, RequiredAt
from hse_doc_studio.core.pack_studio.outcome.predicates import document_in_scope
from hse_doc_studio.core.team import normalize_team_authors
from hse_doc_studio.core.value_objects import Author, Person

# Версия правил синтетического проекта и рендера: меняется, когда тот же вход начинает давать другой PDF.
PREVIEW_RENDER_SALT = "pack-preview/1"

SWITCH_LANG = "lang"
SWITCH_KIND = "kind"
SWITCH_STAFFING = "staffing"
SWITCH_SUPERVISOR = "supervisor"
SWITCH_CO_SUPERVISOR = "co_supervisor"
SWITCH_ACADEMIC = "academic_supervisor"
SWITCH_NDA = "nda"
META_SWITCH_PREFIX = "meta."
# Поля select и bool в переключателях: не больше пяти, остальные задаёт набор данных (6.2).
MAX_META_SWITCHES = 5

YES = "yes"
NO = "no"
SUPERVISOR_NONE = "none"
STAFFING_SOLO = "solo"
STAFFING_TEAMS = {"team2": 2, "team3": 3}

AUTO_PREFIX = "auto:"
AUTO_NORMAL = "auto:normal"
AUTO_LONG = "auto:long"
AUTO_EMPTY = "auto:empty"
# «Длинные значения»: каждое строковое поле в три раза длиннее, ловит переполнение строк титула.
LONG_FACTOR = 3

# Пределы разбора примера: пример пишет автор пака, текст попадает в TeX и в ключ кэша.
MAX_EXAMPLE_AUTHORS = 3
MAX_EXAMPLE_TEXT = 2000
MAX_EXAMPLE_META = 200


class PreviewStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (PreviewStatus.succeeded, PreviewStatus.failed, PreviewStatus.cancelled)


# Коды неудачи сборки предпросмотра сверх кодов сборки проекта (`core/compile/failure.py`).
RENDER_FAILED = "render_failed"
PREVIEW_INTERRUPTED = "interrupted"


class PreviewInputError(ValueError):
    """Запрос предпросмотра не подходит к версии: `field` это `document`, `example` или `combination.<id>`."""

    def __init__(self, field: str, value: str, reason: str) -> None:
        super().__init__(f"{field}={value!r}: {reason}")
        self.field = field
        self.value = value
        self.reason = reason


# ── Переключатели ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PreviewSwitch:
    """Переключатель комбинации. `label` есть только у полей анкеты (подпись поля из пака); у остальных
    подпись знает интерфейс по `id`."""

    id: str
    values: tuple[str, ...]
    default: str
    label: Mapping[str, str] | None = None


def version_kinds(version: TemplateVersion) -> tuple[str, ...]:
    """Виды работы версии: объединение `supported_kinds` документов в порядке перечисления."""
    kinds: list[str] = []
    for doc in version.documents:
        kinds.extend(kind for kind in doc.supported_kinds if kind not in kinds)
    known = {k.value for k in ProjectKind}
    return tuple(k for k in kinds if k in known) or (ProjectKind.research.value,)


def version_langs(version: TemplateVersion) -> tuple[str, ...]:
    known = {lang.value for lang in Lang}
    return tuple(code for code in version.langs if code in known) or (Lang.ru.value,)


def _staffing_values(version: TemplateVersion) -> tuple[str, ...]:
    values: list[str] = []
    if "solo" in version.supported_staffing:
        values.append(STAFFING_SOLO)
    if "team" in version.supported_staffing:
        values.extend(STAFFING_TEAMS)
    return tuple(values) or (STAFFING_SOLO,)


def _meta_switch(field_id: str, meta: MetaFieldDef) -> PreviewSwitch | None:
    if meta.type is MetaFieldType.bool_:
        default = YES if meta.default is True else NO
        return PreviewSwitch(f"{META_SWITCH_PREFIX}{field_id}", (NO, YES), default, dict(meta.label))
    if meta.type is MetaFieldType.select and meta.options:
        options = tuple(str(option) for option in meta.options)
        default = str(meta.default) if meta.default is not None and str(meta.default) in options else options[0]
        return PreviewSwitch(f"{META_SWITCH_PREFIX}{field_id}", options, default, dict(meta.label))
    return None


def switches_for(version: TemplateVersion, *, max_meta: int | None = MAX_META_SWITCHES) -> tuple[PreviewSwitch, ...]:
    """Переключатели версии (6.2): язык, вид, состав, люди проекта, NDA и до пяти полей select и bool.

    `max_meta` None: все поля select и bool (вводные вычислителя результата, раздел 2.1 дизайна: в нём все)."""
    langs = version_langs(version)
    kinds = version_kinds(version)
    staffing = _staffing_values(version)
    switches = [
        PreviewSwitch(SWITCH_LANG, langs, langs[0]),
        PreviewSwitch(SWITCH_KIND, kinds, kinds[0]),
        PreviewSwitch(SWITCH_STAFFING, staffing, staffing[0]),
        PreviewSwitch(
            SWITCH_SUPERVISOR,
            (PersonRole.university.value, PersonRole.company.value, SUPERVISOR_NONE),
            PersonRole.university.value,
        ),
        PreviewSwitch(SWITCH_CO_SUPERVISOR, (NO, YES), NO),
        PreviewSwitch(SWITCH_ACADEMIC, (YES, NO), YES),
    ]
    if version.nda is not None:
        switches.append(PreviewSwitch(SWITCH_NDA, (NO, YES), NO))
    meta_switches: list[PreviewSwitch] = []
    for field_id, meta in version.meta_fields.items():
        if max_meta is not None and len(meta_switches) >= max_meta:
            break
        if field_id == SWITCH_NDA and version.nda is not None:
            continue
        switch = _meta_switch(field_id, meta)
        if switch is not None:
            meta_switches.append(switch)
    return (*switches, *meta_switches)


def resolve_combination(
    switches: Iterable[PreviewSwitch], raw: Mapping[str, str], defaults: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Полная комбинация: значение из запроса, иначе из набора данных (если подходит), иначе по умолчанию.

    Незнакомый переключатель или значение не из списка это `PreviewInputError`.
    """
    known = {switch.id: switch for switch in switches}
    for key, value in raw.items():
        switch = known.get(key)
        if switch is None:
            raise PreviewInputError(f"combination.{key}", str(value), "unknown switch")
        if str(value) not in switch.values:
            raise PreviewInputError(f"combination.{key}", str(value), "value not allowed")
    fallback = defaults or {}
    combo: dict[str, str] = {}
    for switch in known.values():
        if switch.id in raw:
            combo[switch.id] = str(raw[switch.id])
        elif fallback.get(switch.id) in switch.values:
            combo[switch.id] = str(fallback[switch.id])
        else:
            combo[switch.id] = switch.default
    return combo


def combination_query(combo: Mapping[str, str]) -> str:
    """Канонический вид комбинации (`k=v&k=v` по алфавиту): ключ для адреса страницы и для логов."""
    return "&".join(f"{key}={combo[key]}" for key in sorted(combo))


# ── Наборы данных ──────────────────────────────────────────────────────────


class ExampleFormatError(ValueError):
    """Файл примера не того вида: текст ошибки показывается рядом с именем набора."""


@dataclass(frozen=True)
class ExamplePerson:
    name: str
    group: str = ""
    email: str = ""
    title: str = ""
    degree: str = ""
    role: PersonRole | None = None
    topic: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExampleData:
    """Набор данных синтетического проекта: тексты и люди; ветки задают переключатели.

    `defaults` это значения переключателей, которые набор предлагает сам (`lang`, `kind`, `staffing` в файле).
    """

    name: Mapping[str, str] = field(default_factory=dict)
    authors: tuple[ExamplePerson, ...] = ()
    supervisor: ExamplePerson | None = None
    co_supervisor: ExamplePerson | None = None
    academic_supervisor: ExamplePerson | None = None
    meta: Mapping[str, Any] = field(default_factory=dict)
    defaults: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PreviewExample:
    """Набор в списке: файл `examples/<id>.yaml` или автонабор `auto:*`; битый файл несёт `error`."""

    id: str
    source: str  # "file" | "auto"
    label: Mapping[str, str] | None
    data: ExampleData | None
    error: str | None = None


def _text(value: Any) -> str:
    if value is None or isinstance(value, bool | dict | list):
        return ""
    return str(value).strip()[:MAX_EXAMPLE_TEXT]


def _localized(value: Any) -> dict[str, str]:
    """`{ru: ..., en: ...}` или одна строка на все языки."""
    if isinstance(value, Mapping):
        return {str(k): _text(v) for k, v in value.items() if str(k) in {lang.value for lang in Lang} and _text(v)}
    text = _text(value)
    return {lang.value: text for lang in Lang} if text else {}


def _person(raw: Any, where: str) -> ExamplePerson | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return ExamplePerson(name=_text(raw)) if _text(raw) else None
    if not isinstance(raw, Mapping):
        raise ExampleFormatError(f"{where}: ожидается объект или строка")
    role_raw = _text(raw.get("role"))
    role = PersonRole(role_raw) if role_raw in {r.value for r in PersonRole} else None
    return ExamplePerson(
        name=_text(raw.get("name")),
        group=_text(raw.get("group")),
        email=_text(raw.get("email")),
        title=_text(raw.get("position") or raw.get("title")),
        degree=_text(raw.get("degree")),
        role=role,
        topic=_localized(raw.get("topic")),
    )


def _scalar_meta(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ExampleFormatError("meta: ожидается объект")
    meta: dict[str, Any] = {}
    for key, value in list(raw.items())[:MAX_EXAMPLE_META]:
        if isinstance(value, bool):
            meta[str(key)] = value
        elif isinstance(value, int | float | str):
            meta[str(key)] = _text(value)
    return meta


def parse_example(raw: Any) -> ExampleData:
    """Разбор `examples/<имя>.yaml` (6.1). Незнакомые ключи пропускаются; неверная форма это `ExampleFormatError`."""
    if not isinstance(raw, Mapping):
        raise ExampleFormatError("пример должен быть объектом YAML")
    authors_raw = raw.get("authors") or []
    if not isinstance(authors_raw, list):
        raise ExampleFormatError("authors: ожидается список")
    authors = tuple(
        person
        for index, item in enumerate(authors_raw[:MAX_EXAMPLE_AUTHORS])
        if (person := _person(item, f"authors[{index}]")) is not None and person.name
    )
    defaults = {key: _text(raw.get(key)) for key in (SWITCH_LANG, SWITCH_KIND, SWITCH_STAFFING) if _text(raw.get(key))}
    return ExampleData(
        name=_localized(raw.get("name")),
        authors=authors,
        supervisor=_person(raw.get("supervisor"), "supervisor"),
        co_supervisor=_person(raw.get("co_supervisor"), "co_supervisor"),
        academic_supervisor=_person(raw.get("academic_supervisor"), "academic_supervisor"),
        meta=_scalar_meta(raw.get("meta")),
        defaults=defaults,
    )


def example_label(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, Mapping):
        return None
    return _localized(raw.get("label")) or None


# Тексты синтетического проекта по языку проекта.
_NAMES: Mapping[str, str] = {
    "ru": "Контур согласования действий программного агента в учебной среде",
    "en": "An Approval Gate for Software Agents in a Teaching Environment",
}
_AUTHORS: Mapping[str, tuple[str, ...]] = {
    "ru": ("Иванов Иван Иванович", "Петрова Мария Сергеевна", "Сидоров Алексей Павлович"),
    "en": ("Ivan Ivanov", "Maria Petrova", "Alexey Sidorov"),
}
_GROUP = "БПИ221"


@dataclass(frozen=True)
class _People:
    name: str
    title: str
    degree: str = ""


_SUPERVISORS: Mapping[str, Mapping[str, _People]] = {
    "university": {
        "ru": _People("Петров Пётр Петрович", "доцент", "кандидат технических наук"),
        "en": _People("Petr Petrov", "Associate Professor", "PhD"),
    },
    "company": {
        "ru": _People("Смирнов Олег Игоревич", "ведущий разработчик, ООО «Пример»"),
        "en": _People("Oleg Smirnov", "Lead Developer, Example LLC"),
    },
    "co_supervisor": {
        "ru": _People("Кузнецова Анна Викторовна", "старший преподаватель"),
        "en": _People("Anna Kuznetsova", "Senior Lecturer"),
    },
    "academic_supervisor": {
        "ru": _People("Васильев Дмитрий Андреевич", "академический руководитель образовательной программы"),
        "en": _People("Dmitry Vasiliev", "Academic Supervisor of the Programme"),
    },
}


def _field_sample(meta: MetaFieldDef) -> Any | None:
    """Значение поля в «Обычном» наборе: `default`, иначе `placeholder`, у select первая опция."""
    if meta.type is MetaFieldType.bool_:
        return meta.default is True
    if meta.type is MetaFieldType.select:
        return meta.default if meta.default is not None else (meta.options[0] if meta.options else None)
    if meta.type in (MetaFieldType.string, MetaFieldType.font):
        if meta.default not in (None, ""):
            return str(meta.default)
        return meta.placeholder or None
    return None


def _normal_meta(version: TemplateVersion) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for field_id, field_def in version.meta_fields.items():
        value = _field_sample(field_def)
        if value is not None:
            meta[field_id] = value
    return meta


def _empty_meta(version: TemplateVersion) -> dict[str, Any]:
    """«Пустой»: только поля, обязательные при создании; остальное шаблон печатает плейсхолдерами `\\hseFill`."""
    return {
        field_id: value
        for field_id, field_def in version.meta_fields.items()
        if field_def.required_at is RequiredAt.create and (value := _field_sample(field_def)) is not None
    }


def _longer(text: str) -> str:
    return " ".join([text] * LONG_FACTOR) if text else text


def _long_meta(version: TemplateVersion) -> dict[str, Any]:
    meta = _normal_meta(version)
    for field_id, field_def in version.meta_fields.items():
        if field_def.type is MetaFieldType.string and isinstance(meta.get(field_id), str):
            meta[field_id] = _longer(meta[field_id])
    return meta


def auto_examples(version: TemplateVersion) -> tuple[PreviewExample, ...]:
    """Три набора без файлов (6.1): «Обычный», «Длинные значения», «Пустой»."""
    normal = ExampleData(name=dict(_NAMES), meta=_normal_meta(version))
    long_names = {lang: _longer(text) for lang, text in _NAMES.items()}
    long_data = ExampleData(name=long_names, meta=_long_meta(version))
    empty = ExampleData(name=dict(_NAMES), meta=_empty_meta(version), defaults={})
    return (
        PreviewExample(AUTO_NORMAL, "auto", {"ru": "Обычный", "en": "Typical"}, normal),
        PreviewExample(AUTO_LONG, "auto", {"ru": "Длинные значения", "en": "Long values"}, long_data),
        PreviewExample(AUTO_EMPTY, "auto", {"ru": "Пустой", "en": "Empty"}, empty),
    )


# ── Синтетический проект ───────────────────────────────────────────────────


@dataclass(frozen=True)
class SyntheticProject:
    """Данные проекта предпросмотра (6.3, шаг 1); из них синтетический `Project` строит рендер в песочнице."""

    name: str
    lang: Lang
    kind: ProjectKind
    staffing: ProjectStaffing
    authors: tuple[Author, ...]
    supervisor: Person | None
    co_supervisor: Person | None
    academic_supervisor: Person | None
    meta: Mapping[str, Any]
    # День, на который считаются `build.year` и поля `auto`: входит в ключ кэша.
    today: date

    def canonical(self) -> dict[str, Any]:
        """Плоский вид для ключа кэша и тестов: порядок ключей не важен, значения JSON."""

        def person(p: Person | None) -> dict[str, str] | None:
            if p is None:
                return None
            return {"name": p.name, "role": p.role.value, "title": p.title or "", "degree": p.degree or ""}

        return {
            "name": self.name,
            "lang": self.lang.value,
            "kind": self.kind.value,
            "staffing": self.staffing.value,
            "authors": [
                {
                    "name": a.name,
                    "group": a.group or "",
                    "email": a.email or "",
                    "slug": a.slug or "",
                    "topic": a.topic or "",
                    "managed": a.managed,
                }
                for a in self.authors
            ],
            "supervisor": person(self.supervisor),
            "co_supervisor": person(self.co_supervisor),
            "academic_supervisor": person(self.academic_supervisor),
            "meta": {k: self.meta[k] for k in sorted(self.meta)},
            "today": self.today.isoformat(),
        }


def _pick(localized: Mapping[str, str], lang: str, fallback: str) -> str:
    return localized.get(lang) or next(iter(localized.values()), "") or fallback


def _authors(example: ExampleData, staffing: str, lang: str, group: str, empty: bool) -> list[Author]:
    count = STAFFING_TEAMS.get(staffing, 1)
    pool = _AUTHORS.get(lang, _AUTHORS["ru"])
    authors: list[Author] = []
    for index in range(count):
        given = example.authors[index] if index < len(example.authors) else None
        name = given.name if given is not None else pool[index % len(pool)]
        author_group = given.group if given is not None and given.group else ("" if empty else group)
        topic = _pick(given.topic, lang, "") if given is not None else ""
        authors.append(
            Author(
                name=name,
                group=author_group or None,
                email=(given.email or None) if given else None,
                topic=topic or None,
            )
        )
    if count > 1:
        return normalize_team_authors(authors)
    return authors


def _person_of(given: ExamplePerson | None, sample: _People, role: PersonRole, *, empty: bool) -> Person:
    name = given.name if given is not None and given.name else sample.name
    title = given.title if given is not None and given.title else ("" if empty else sample.title)
    degree = given.degree if given is not None and given.degree else ("" if empty else sample.degree)
    return Person(name=name, role=role, title=title or None, degree=degree or None)


def _sample(kind: str, lang: str) -> _People:
    by_lang = _SUPERVISORS[kind]
    return by_lang.get(lang) or by_lang["ru"]


def _meta_of(version: TemplateVersion, example: ExampleData, combo: Mapping[str, str]) -> dict[str, Any]:
    meta = dict(example.meta)
    for key, value in combo.items():
        if not key.startswith(META_SWITCH_PREFIX):
            continue
        field_id = key.removeprefix(META_SWITCH_PREFIX)
        field_def = version.meta_fields.get(field_id)
        if field_def is not None and field_def.type is MetaFieldType.bool_:
            meta[field_id] = value == YES
        else:
            meta[field_id] = value
    if version.nda is not None and SWITCH_NDA in combo:
        meta["nda"] = combo[SWITCH_NDA] == YES
    return meta


def synthetic_project(
    version: TemplateVersion, example: PreviewExample, combo: Mapping[str, str], today: date
) -> SyntheticProject:
    """Синтетический проект (6.3, шаг 1): набор задаёт имена и тексты, комбинация задаёт ветки."""
    data = example.data or ExampleData()
    empty = example.id == AUTO_EMPTY
    lang = combo.get(SWITCH_LANG, version_langs(version)[0])
    staffing = combo.get(SWITCH_STAFFING, STAFFING_SOLO)
    group = version.author_group_placeholder or _GROUP
    supervisor_choice = combo.get(SWITCH_SUPERVISOR, PersonRole.university.value)
    supervisor = None
    if supervisor_choice != SUPERVISOR_NONE:
        role = PersonRole(supervisor_choice)
        supervisor = _person_of(data.supervisor, _sample(role.value, lang), role, empty=empty)
    co_supervisor = None
    if combo.get(SWITCH_CO_SUPERVISOR) == YES:
        co_role = data.co_supervisor.role if data.co_supervisor and data.co_supervisor.role else PersonRole.university
        co_supervisor = _person_of(data.co_supervisor, _sample("co_supervisor", lang), co_role, empty=empty)
    academic = None
    if combo.get(SWITCH_ACADEMIC, YES) == YES:
        academic = _person_of(
            data.academic_supervisor, _sample("academic_supervisor", lang), PersonRole.university, empty=empty
        )
    project = SyntheticProject(
        name=_pick(data.name, lang, _NAMES.get(lang, _NAMES["ru"])),
        lang=Lang(lang),
        kind=ProjectKind(combo.get(SWITCH_KIND, version_kinds(version)[0])),
        staffing=ProjectStaffing.solo if staffing == STAFFING_SOLO else ProjectStaffing.team,
        authors=tuple(_authors(data, staffing, lang, group, empty)),
        supervisor=supervisor,
        co_supervisor=co_supervisor,
        academic_supervisor=academic,
        meta=_meta_of(version, data, combo),
        today=today,
    )
    return _lengthened(project) if example.id == AUTO_LONG else project


def _long_person(person: Person | None) -> Person | None:
    if person is None:
        return None
    return replace(
        person,
        name=_longer(person.name),
        title=_longer(person.title or "") or None,
        degree=_longer(person.degree or "") or None,
    )


def _lengthened(project: SyntheticProject) -> SyntheticProject:
    """«Длинные значения»: люди проекта тоже втрое длиннее (имя на титуле переносится первым)."""
    authors = tuple(replace(a, name=_longer(a.name), group=_longer(a.group or "") or None) for a in project.authors)
    return replace(
        project,
        authors=authors,
        supervisor=_long_person(project.supervisor),
        co_supervisor=_long_person(project.co_supervisor),
        academic_supervisor=_long_person(project.academic_supervisor),
    )


def document_present(doc: DocumentDefinition, project: SyntheticProject) -> bool:
    """Есть ли документ в проекте этой комбинации: вид работы и состав (как `create_project._build_documents`)."""
    return document_in_scope(doc.supported_kinds, doc.supported_staffing, project.kind.value, project.staffing.value)


# ── Ключ кэша ──────────────────────────────────────────────────────────────


def document_digest(files: Mapping[str, str], version: TemplateVersion, def_id: str, extra: Iterable[str] = ()) -> str:
    """Дайджест входа документа: файлы каталога версии без папок других документов (6.3, шаг 4).

    `files` это пути от каталога версии и sha256 содержимого. Правка чужого документа ключ не меняет; правка общих
    файлов (`version.yaml`, `common/`, проверки) меняет ключи всех документов. `extra` это дайджесты того, что вне
    каталога версии, но входит в рендер (манифесты пака и шаблона).
    """
    mine: set[str] = set()
    others: set[str] = set()
    for doc in version.documents:
        dirs = {f"files/{d}/" for d in def_source_dirs(doc)}
        (mine if doc.id == def_id else others).update(dirs)
    others -= mine
    digest = hashlib.sha256()
    for path in sorted(files):
        if any(path.startswith(prefix) for prefix in others) and not any(path.startswith(p) for p in mine):
            continue
        digest.update(f"{path}\0{files[path]}\n".encode())
    for item in extra:
        digest.update(f"+{item}\n".encode())
    return digest.hexdigest()


def preview_cache_key(
    *, doc_digest: str, def_id: str, project: SyntheticProject, engine: str, checks: bool = False
) -> str:
    """Ключ кэша сборки: вход документа, сам документ, синтетический проект (набор и комбинация) и движок.

    Правка другого набора данных или комбинации ключ не меняет: в ключ входит только то, что попало в проект.
    Сборка с проверками (срез T14) это другой ключ: у неё есть находки, у сборки без проверок их нет. Правила
    лежат в каталоге версии (`checks/*.yaml`, `checks_version`), их правка и так меняет вход документа.
    """
    body: dict[str, Any] = {
        "salt": PREVIEW_RENDER_SALT,
        "doc": def_id,
        "inputs": doc_digest,
        "project": project.canonical(),
        "engine": engine,
    }
    if checks:
        body["checks"] = True
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


# ── Сборка ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PreviewError:
    code: str
    detail: str | None = None


@dataclass(frozen=True)
class PreviewCheck:
    """Находка проверки на сборке предпросмотра (срез T14): правило, важность, текст и место в исходнике."""

    rule_id: str
    severity: str
    message: str
    file: str | None = None
    line: int | None = None


@dataclass(frozen=True)
class PreviewBuild:
    """Сборка предпросмотра одного документа в одной комбинации.

    `cached`: ответ взят из кэша по ключу, задачи не было. `version` и прочие части пути это имена папок
    рабочего пространства, как их видит дерево.
    """

    id: UUID
    owner_id: str | None
    workspace_id: UUID
    pack: str
    template: str
    version: str
    document: str
    example: str
    combination: Mapping[str, str]
    key: str
    status: PreviewStatus
    cached: bool
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    pages: int | None = None
    error: PreviewError | None = None
    # Путь исходника в синтетическом проекте (для перехода из журнала к строке); у отказа рендера пусто.
    source_file: str | None = None
    has_anchors: bool = False
    # Сборка с проверками правил версии (срез T14); `checks` находки удачной сборки (None: проверок не было).
    with_checks: bool = False
    checks: tuple[PreviewCheck, ...] | None = None

    @property
    def slot(self) -> tuple[str, ...]:
        """Чья это сборка по смыслу: новая сборка того же слота отменяет прежнюю (6.3, шаг 5)."""
        return (
            str(self.workspace_id),
            self.pack,
            self.template,
            self.version,
            self.document,
            self.example,
            combination_query(self.combination),
            "checks" if self.with_checks else "",
        )


# ── Обмен с рендером в песочнице ───────────────────────────────────────────


class PreviewRenderError(Exception):
    """Синтетический проект не собран: шаблон упал, превысил предел или процесс рендера убит."""


@dataclass(frozen=True)
class RawExample:
    """Файл `examples/<id>.yaml` после разбора YAML в песочнице: данные или текст ошибки."""

    id: str
    data: Any | None
    error: str | None = None


@dataclass(frozen=True)
class VersionDescription:
    """Модель версии и сырые примеры шаблона; id пака и шаблона из манифестов (могут не совпадать с папками)."""

    pack_id: str
    template_id: str
    version: TemplateVersion
    examples: tuple[RawExample, ...] = ()


@dataclass(frozen=True)
class PreviewInputs:
    """Дайджесты входа: файлы каталога версии (путь от каталога версии -> sha256), манифесты пака и шаблона и
    общий дайджест вместе с примерами (по нему кешируется разобранная модель)."""

    files: Mapping[str, str]
    extra: tuple[str, ...]
    tree: str


@dataclass(frozen=True)
class MaterializeRequest:
    pack_id: str
    template_id: str
    version_id: str
    def_id: str
    project: SyntheticProject
    build_id: UUID


@dataclass(frozen=True)
class MaterializedDoc:
    """Что собрать: инстанс документа и его исходник от корня синтетического проекта, как у `TriggerCompileUC`.

    `warnings` это предупреждения рендера (Jinja упала и файл скопирован как есть): они идут в журнал сборки.
    """

    doc_id: str
    def_id: str
    source_file: str
    base_dir: str
    engine: str
    needs_compile: bool
    default_passes: int
    warnings: tuple[str, ...] = ()
