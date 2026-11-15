"""Профили сдачи и порядок маршрута в `version.yaml` (docs/design/template-studio.md, 5.5, 5.6, 5.8, срез T13).

Порт `IPackSubmission`. Модель читается из текста манифеста теми же функциями, что у лоадера (`parse_signing_route`,
`parse_signing_slot`, `parse_deadline_hint`, `_parse_submission_profile`), с индексами записей в списках YAML.
Запись идёт точечными правками (`yaml_edits`, D11):

- запись списка пишется в порядке ключей справки, поля со значением лоадера по умолчанию не пишутся
  (`skip_if_nda: false`, пустые `methods`, `supported_kinds` из обоих видов, `optional: false`);
- правка записи меняет только известные форме ключи: незнакомые (пак от более новой Студии) остаются как были;
- новый список профиля пишется блоком строк; рядом с записями одной строкой (`- { doc_id: ..., slot_id: ... }`)
  новая запись встаёт так же;
- `signing_route` встаёт за `extra_items` (или `items`), `deadline_hint` в конец профиля, как в паках.

Каждая правка проверяет себя: после неё у профилей и порядка версии не должно появиться новых проблем строгого
разбора лоадера и схемы `version.schema.json`. Проблемы, которые были до правки, правку не запрещают: форма
не запирает пак, который автор чинит по частям. Связи (документ в ростере, слот в каталоге, `when` только у
слота сверх точки) проверяет линтер пака после записи, его находки видны в «Проблемах» и у профиля.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

import yaml

from hse_doc_studio.core.checkpoint_deadlines import parse_deadline_hint
from hse_doc_studio.core.pack_studio.submission import (
    KINDS,
    SIGN_METHODS,
    WHEN_PERSONS,
    WHEN_ROLES,
    ExtraEntry,
    FormInfo,
    Indexed,
    ItemEntry,
    ProfileHead,
    ProfileView,
    SlotEntry,
    SlotInfo,
    SubmissionEditError,
    SubmissionList,
    SubmissionOp,
    SubmissionOpKind,
    VersionSubmission,
    WhenCondition,
)
from hse_doc_studio.core.signatures.route_order import BUILTIN_ROUTE
from hse_doc_studio.infra.pack_studio.pack_schemas import validation_errors
from hse_doc_studio.infra.pack_studio.yaml_edits import YamlEditError, delete, insert_item, move_item, set_value
from hse_doc_studio.infra.template.yaml_template_repository import (
    _parse_submission_profile,
    parse_signature_slot,
    parse_signing_route,
    parse_signing_slot,
)

_LOADER: Any = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
_PROFILES = ("pack_submission", "profiles")
_ROUTE = ("signatures", "route")
_PARSE_ERRORS = (TypeError, ValueError, KeyError, AttributeError)
_MISSING = object()
_FORMS_DIR = ".hse-studio/forms"

# Ключи записей, которые знает форма; прочие ключи записи она не трогает.
_ITEM_KEYS = ("doc_id", "signatures", "methods", "skip_if_nda", "supported_kinds")
_EXTRA_KEYS = ("source", "output_name", "format", "supported_kinds")
_SLOT_KEYS = ("doc_id", "slot_id", "when", "optional")
_HEAD_KEYS = ("id", "name", "description")

Path = tuple[str | int, ...]


# ── чтение ──────────────────────────────────────────────────────────────────


def _load(text: str) -> dict[str, Any]:
    try:
        data = yaml.load(text, Loader=_LOADER)  # noqa: S506 — безопасный загрузчик (CSafeLoader или SafeLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"version.yaml is not valid YAML: {exc}") from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TypeError("version.yaml is not a mapping")
    return data


def _mapping(raw: Any) -> dict[str, Any]:
    return raw if isinstance(raw, dict) else {}


def _list(raw: Any) -> list[Any]:
    return raw if isinstance(raw, list) else []


def _raw_profiles(data: dict[str, Any]) -> list[Any]:
    return _list(_mapping(data.get("pack_submission")).get("profiles"))


def _localized(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if v is not None}
    if isinstance(raw, str):
        return {"ru": raw}
    return {}


def _kinds(raw: Any) -> tuple[str, ...]:
    """Виды работы записи как написаны (только известные); пусто: ключа нет, запись в обоих видах."""
    if not isinstance(raw, list):
        return ()
    return tuple(dict.fromkeys(str(k) for k in raw if str(k) in KINDS))


def _documents(data: dict[str, Any]) -> tuple[str, ...]:
    ids = (item.get("id") if isinstance(item, dict) else item for item in _list(data.get("documents")))
    return tuple(doc for doc in ids if isinstance(doc, str))


def _error(exc: BaseException) -> str:
    text = str(exc).strip("'\"") if isinstance(exc, KeyError) else str(exc)
    return (f"missing key {text!r}" if isinstance(exc, KeyError) else text)[:300]


def _methods(raw: Any) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise TypeError("methods must be a mapping {slot: [image, detached, pades]}")
    result: list[tuple[str, tuple[str, ...]]] = []
    for slot_id, values in raw.items():
        listed = values if isinstance(values, list) else [values]
        unknown = [v for v in listed if v not in SIGN_METHODS]
        if unknown:
            raise ValueError(f"methods.{slot_id}: unknown {unknown}, expected {list(SIGN_METHODS)}")
        result.append((str(slot_id), tuple(str(v) for v in listed)))
    return tuple(result)


def _item(raw: Any) -> ItemEntry:
    if not isinstance(raw, dict):
        raise TypeError("an item must be a mapping with doc_id")
    doc_id = raw["doc_id"]
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise ValueError("doc_id must be a non-empty string")
    signatures = raw.get("signatures", [])
    if not isinstance(signatures, list):
        raise TypeError("signatures must be a list of slot ids")
    return ItemEntry(
        doc_id=doc_id,
        signatures=tuple(str(s) for s in signatures),
        methods=_methods(raw.get("methods")),
        skip_if_nda=bool(raw.get("skip_if_nda", False)),
        supported_kinds=_kinds(raw.get("supported_kinds")),
    )


def _extra(raw: Any) -> ExtraEntry:
    if not isinstance(raw, dict):
        raise TypeError("an extra item must be a mapping with source")
    source = raw["source"]
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source must be a non-empty string")
    fmt = raw.get("format")
    return ExtraEntry(
        source=source,
        output_name=str(raw.get("output_name") or ""),
        format=str(fmt) if fmt is not None else None,
        supported_kinds=_kinds(raw.get("supported_kinds")),
    )


def _slot_entry(raw: Any, index: int) -> SlotEntry:
    parsed = parse_signing_slot(raw, f"signing_slots[{index}]")
    when = (
        WhenCondition(parsed.when.person, parsed.when.role.value if parsed.when.role is not None else None)
        if parsed.when is not None
        else None
    )
    return SlotEntry(doc_id=parsed.doc_id, slot_id=parsed.slot_id, when=when, optional=parsed.optional)


def _indexed[T](items: list[Any], parse: Callable[[Any, int], T]) -> tuple[Indexed[T], ...]:
    result: list[Indexed[T]] = []
    for i, raw in enumerate(items):
        try:
            result.append(Indexed(i, parse(raw, i)))
        except _PARSE_ERRORS as exc:
            result.append(Indexed(i, None, _error(exc)))
    return tuple(result)


def _route(raw: Any) -> tuple[tuple[str, ...], ...] | None:
    return None if raw is None else parse_signing_route(raw)


def _hint(raw: Any) -> dict[str, str] | None:
    """Подсказка срока как написана (битая тоже: форма её показывает, чтобы автор поправил)."""
    if raw is None:
        return None
    return {lang: str(raw.get(lang) or "") for lang in ("ru", "en")} if isinstance(raw, dict) else {"ru": str(raw)}


def _profile_problems(raw: dict[str, Any]) -> Iterator[str]:
    """Чего не понимает лоадер в профиле (строгий разбор: лоадер такое молча отбрасывает)."""
    slots = raw.get("signing_slots")
    if slots is not None and not isinstance(slots, list):
        yield "signing_slots must be a list"
    checks: list[tuple[Callable[[Any, int], object], Any, int]] = [
        (lambda value, _i: _parse_submission_profile(value), raw, 0),
        (lambda value, _i: _route(value), raw.get("signing_route"), 0),
        (lambda value, _i: parse_deadline_hint(value), raw.get("deadline_hint"), 0),
        *((lambda value, _i: _item(value), item, i) for i, item in enumerate(_list(raw.get("items")))),
        *((lambda value, _i: _extra(value), item, i) for i, item in enumerate(_list(raw.get("extra_items")))),
        *((_slot_entry, item, i) for i, item in enumerate(_list(slots))),
    ]
    for check, value, index in checks:
        try:
            check(value, index)
        except _PARSE_ERRORS as exc:
            yield _error(exc)


def _profile_view(index: int, raw: Any) -> ProfileView:
    if not isinstance(raw, dict):
        return ProfileView(index, None, {}, {}, None, (), (), None, (), error="the profile is not a mapping")
    problems = list(_profile_problems(raw))
    try:
        route = _route(raw.get("signing_route"))
    except _PARSE_ERRORS:
        route = None
    raw_id = raw.get("id")
    return ProfileView(
        index=index,
        id=str(raw_id) if isinstance(raw_id, str | int) else None,
        name=_localized(raw.get("name")),
        description=_localized(raw.get("description")),
        deadline_hint=_hint(raw.get("deadline_hint")),
        items=_indexed(_list(raw.get("items")), lambda item, _i: _item(item)),
        extra_items=_indexed(_list(raw.get("extra_items")), lambda item, _i: _extra(item)),
        signing_route=route,
        signing_slots=_indexed(_list(raw.get("signing_slots")), _slot_entry),
        error=problems[0] if problems else None,
    )


def _slots(data: dict[str, Any]) -> tuple[SlotInfo, ...]:
    result: list[SlotInfo] = []
    for raw in _list(_mapping(data.get("signatures")).get("slots")):
        if not isinstance(raw, dict) or "id" not in raw:
            continue
        try:
            slot = parse_signature_slot(raw)
        except _PARSE_ERRORS:
            continue
        result.append(SlotInfo(slot.id, slot.label, slot.applies_to, slot.required, slot.per_author))
    return tuple(result)


def _forms(data: dict[str, Any]) -> tuple[FormInfo, ...]:
    result: list[FormInfo] = []
    for raw in _list(data.get("forms")):
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            continue
        output = _mapping(raw.get("output"))
        fmt = output.get("format")
        result.append(
            FormInfo(
                id=raw["id"],
                title=_localized(raw.get("title")),
                source=f"{_FORMS_DIR}/{raw['id']}.json",
                output_name=str(output.get("output_name") or ""),
                format=str(fmt) if fmt is not None else None,
                required_for_pack=bool(raw.get("required_for_pack", False)),
            )
        )
    return tuple(result)


# ── проверка правки ─────────────────────────────────────────────────────────


def _problems(data: dict[str, Any]) -> Counter[str]:
    """Проблемы профилей и порядка версии: строгий разбор и схема; без путей, чтобы перестановка их не меняла."""
    found: Counter[str] = Counter()
    for raw in _raw_profiles(data):
        owner = f"profile {raw.get('id', '?')}" if isinstance(raw, dict) else "profile"
        problems = _profile_problems(raw) if isinstance(raw, dict) else iter(["the profile is not a mapping"])
        found.update(f"{owner}: {problem}" for problem in problems)
    try:
        _route(_mapping(data.get("signatures")).get("route"))
    except _PARSE_ERRORS as exc:
        found[f"signatures.route: {_error(exc)}"] += 1
    for path, message in validation_errors("version", data):
        if path[:2] == _PROFILES or path[:2] == _ROUTE:
            profile = _profile_at(data, path)
            found[f"{profile}{_schema_where(path)}: {message}"] += 1
    return found


def _profile_at(data: dict[str, Any], path: tuple[str | int, ...]) -> str:
    if path[:2] != _PROFILES or len(path) < 3 or not isinstance(path[2], int):
        return ""
    profiles = _raw_profiles(data)
    raw = profiles[path[2]] if path[2] < len(profiles) else None
    return f"profile {raw.get('id', '?')}: " if isinstance(raw, dict) else "profile: "


def _schema_where(path: tuple[str | int, ...]) -> str:
    """Ключ схемы без индексов списков: `items.methods`, `signing_slots.when`."""
    keys = [str(part) for part in path[3 if path[:2] == _PROFILES else 0 :] if not isinstance(part, int)]
    return ".".join(keys) or "profile"


def _checked(before: str, after: str) -> str:
    old = _problems(_load(before))
    new = _problems(_load(after))
    added = new - old
    if added:
        raise SubmissionEditError(next(iter(added)))
    return after


# ── запись ──────────────────────────────────────────────────────────────────


def _node(text: str, path: Path) -> Any:
    node: Any = _load(text)
    for key in path:
        if isinstance(node, dict):
            node = node.get(key, _MISSING)
        elif isinstance(node, list) and isinstance(key, int) and 0 <= key < len(node):
            node = node[key]
        else:
            return _MISSING
        if node is _MISSING:
            return _MISSING
    return node


def _put(text: str, path: Path, value: Any, *, after: str | None = None, block: bool = False) -> str:
    """Значение по пути; недостающие словари-родители (`pack_submission`, `signatures`) создаются с ним."""
    for depth in range(1, len(path)):
        node = _node(text, path[:depth])
        if node is _MISSING or node == {} or node is None:
            nested: Any = value
            for key in reversed(path[depth:]):
                nested = {key: nested}
            return set_value(text, path[:depth], nested, block=True)
    return set_value(text, path, value, after=after, block=block)


def _need[T](value: T | None, name: str) -> T:
    if value is None:
        raise SubmissionEditError(f"the operation needs {name}")
    return value


def _profile_path(text: str, op: SubmissionOp) -> Path:
    index = _need(op.profile, "a profile index")
    profiles = _node(text, _PROFILES)
    if not isinstance(profiles, list) or not 0 <= index < len(profiles):
        raise SubmissionEditError(f"there is no profile {index}")
    if not isinstance(profiles[index], dict):
        raise SubmissionEditError(f"profile {index} is not a mapping: fix it in the source")
    return (*_PROFILES, index)


def _localized_value(value: Mapping[str, str]) -> dict[str, str]:
    return {lang: text.strip() for lang, text in value.items() if text.strip()}


def _id(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise SubmissionEditError("the profile id is empty")
    return cleaned


def _head_value(head: ProfileHead) -> dict[str, Any]:
    value: dict[str, Any] = {"id": _id(head.id), "name": _localized_value(head.name)}
    description = _localized_value(head.description)
    if description:
        value["description"] = description
    return value


def _set_keys(
    text: str, path: Path, value: Mapping[str, Any], known: Sequence[str], seen: Mapping[str, Any] | None = None
) -> str:
    """Известные ключи записи по `value` (нет в `value`: ключ уходит), незнакомые остаются как были.

    `seen` запись так, как её видит форма: ключ, который для формы не изменился, остаётся байт в байт, даже если
    записан иначе (выпущенные паки бывают с текстом через запятую без кавычек).
    """
    current = _node(text, path)
    if not isinstance(current, dict):
        return set_value(text, path, dict(value))
    kept = {k for k in value if k in current and (seen or {}).get(k) == value[k]}
    merged = {
        k: (v if k in kept or k not in known else value[k]) for k, v in current.items() if k in value or k not in known
    }
    merged.update({k: v for k, v in value.items() if k not in merged})
    return set_value(text, path, merged)


def _add_profile(text: str, op: SubmissionOp) -> str:
    value = {**_head_value(_need(op.head, "a profile head")), "items": []}
    profiles = _node(text, _PROFILES)
    if isinstance(profiles, list) and profiles:
        if any(isinstance(p, dict) and p.get("id") == value["id"] for p in profiles):
            raise SubmissionEditError(f"profile {value['id']!r} already exists")
        text = insert_item(text, _PROFILES, len(profiles), {"id": value["id"]}, block=True)
        return set_value(text, (*_PROFILES, len(profiles)), value)
    # Первый профиль: список блоком строк, поля профиля по одному (названия одной строкой, как в паках).
    text = _put(text, _PROFILES, [{"id": value["id"]}], block=True)
    return set_value(text, (*_PROFILES, 0), value)


def _set_profile(text: str, op: SubmissionOp) -> str:
    path = _profile_path(text, op)
    head = _need(op.head, "a profile head")
    value = _head_value(head)
    others = [p for i, p in enumerate(_node(text, _PROFILES)) if i != path[-1] and isinstance(p, dict)]
    if any(p.get("id") == value["id"] for p in others):
        raise SubmissionEditError(f"profile {value['id']!r} already exists")
    for key in _HEAD_KEYS:
        text = _write_head_key(text, (*path, key), key, value.get(key))
    hint = _localized_value(head.deadline_hint) if head.deadline_hint is not None else None
    return _write_hint(text, (*path, "deadline_hint"), hint or None)


def _write_head_key(text: str, path: Path, key: str, value: Any) -> str:
    """Поле шапки; без изменений для формы запись остаётся как есть, None убирает ключ."""
    current = _node(text, path)
    if value is None:
        return delete(text, path) if current is not _MISSING else text
    if current is not _MISSING and _seen_head(key, current) == value:
        return text
    return set_value(text, path, value, after={"name": "id", "description": "name"}.get(key))


def _write_hint(text: str, path: Path, hint: dict[str, str] | None) -> str:
    current = _node(text, path)
    if hint is None:
        return delete(text, path) if current is not _MISSING else text
    if current is not _MISSING and _localized_value(_hint(current) or {}) == hint:
        return text
    return set_value(text, path, hint)


def _seen_head(key: str, raw: Any) -> Any:
    """Поле шапки так, как его видит форма."""
    return str(raw).strip() if key == "id" else _localized_value(_localized(raw))


def _seen_entry(kind: SubmissionList, raw: Any, index: int) -> dict[str, Any]:
    """Запись списка так, как её пишет форма; битая запись пуста."""
    try:
        if kind is SubmissionList.items:
            item = _item(raw)
            return _item_value(
                {
                    "doc_id": item.doc_id,
                    "signatures": list(item.signatures),
                    "methods": {slot: list(methods) for slot, methods in item.methods},
                    "skip_if_nda": item.skip_if_nda,
                    "supported_kinds": list(item.supported_kinds),
                }
            )
        if kind is SubmissionList.extra_items:
            extra = _extra(raw)
            return _extra_value(
                {
                    "source": extra.source,
                    "output_name": extra.output_name,
                    "format": extra.format,
                    "supported_kinds": list(extra.supported_kinds),
                }
            )
        slot = _slot_entry(raw, index)
        when = {"person": slot.when.person, "role": slot.when.role} if slot.when is not None else None
        return _slot_value({"doc_id": slot.doc_id, "slot_id": slot.slot_id, "when": when, "optional": slot.optional})
    except (*_PARSE_ERRORS, SubmissionEditError):
        return {}


def _remove_profile(text: str, op: SubmissionOp) -> str:
    return delete(text, _profile_path(text, op))


def _move_profile(text: str, op: SubmissionOp) -> str:
    path = _profile_path(text, op)
    return move_item(text, _PROFILES, int(path[-1]), _need(op.to, "a target index"))


def _steps_value(steps: Sequence[Sequence[str]]) -> list[list[str]]:
    result = [[slot.strip() for slot in step if slot.strip()] for step in steps]
    return [step for step in result if step]


def _set_route_at(text: str, path: Path, steps: Sequence[Sequence[str]] | None, after: str | None) -> str:
    value = _steps_value(steps) if steps is not None else None
    if not value:
        return delete(text, path) if _node(text, path) is not _MISSING else text
    return _put(text, path, value, after=after)


def _set_profile_route(text: str, op: SubmissionOp) -> str:
    path = _profile_path(text, op)
    profile = _node(text, path)
    after = "extra_items" if "extra_items" in profile else "items"
    return _set_route_at(text, (*path, "signing_route"), op.steps, after)


def _set_route(text: str, op: SubmissionOp) -> str:
    return _set_route_at(text, _ROUTE, op.steps, "slots")


def _list_key(op: SubmissionOp) -> SubmissionList:
    return _need(op.entries, "a list")


def _kinds_value(raw: Any) -> list[str] | None:
    kinds = [k for k in KINDS if k in (raw or ())]
    return kinds if kinds and set(kinds) != set(KINDS) else None


def _item_value(raw: Mapping[str, Any]) -> dict[str, Any]:
    doc_id = str(raw.get("doc_id") or "").strip()
    if not doc_id:
        raise SubmissionEditError("the item needs a document")
    signatures = [str(s) for s in dict.fromkeys(raw.get("signatures") or ())]
    value: dict[str, Any] = {"doc_id": doc_id, "signatures": signatures}
    methods_raw = raw.get("methods") or {}
    if not isinstance(methods_raw, Mapping):
        raise SubmissionEditError("methods must be a mapping {slot: [methods]}")
    methods = {
        str(slot): [m for m in SIGN_METHODS if m in (listed or ())]
        for slot, listed in methods_raw.items()
        if slot in signatures and listed
    }
    unknown = [m for listed in methods_raw.values() for m in (listed or ()) if m not in SIGN_METHODS]
    if unknown:
        raise SubmissionEditError(f"unknown signing methods {unknown}, expected {list(SIGN_METHODS)}")
    methods = {slot: listed for slot, listed in methods.items() if listed}
    if methods:
        value["methods"] = methods
    if raw.get("skip_if_nda"):
        value["skip_if_nda"] = True
    kinds = _kinds_value(raw.get("supported_kinds"))
    if kinds:
        value["supported_kinds"] = kinds
    return value


def _extra_value(raw: Mapping[str, Any]) -> dict[str, Any]:
    source = str(raw.get("source") or "").strip()
    if not source:
        raise SubmissionEditError("the extra item needs a source file")
    value: dict[str, Any] = {"source": source}
    output_name = str(raw.get("output_name") or "").strip()
    if output_name:
        value["output_name"] = output_name
    fmt = str(raw.get("format") or "").strip()
    if fmt:
        value["format"] = fmt
    kinds = _kinds_value(raw.get("supported_kinds"))
    if kinds:
        value["supported_kinds"] = kinds
    return value


def _slot_value(raw: Mapping[str, Any]) -> dict[str, Any]:
    doc_id = str(raw.get("doc_id") or "").strip()
    slot_id = str(raw.get("slot_id") or "").strip()
    if not doc_id or not slot_id:
        raise SubmissionEditError("the entry needs a document and a slot")
    value: dict[str, Any] = {"doc_id": doc_id, "slot_id": slot_id}
    when = raw.get("when")
    if when:
        if not isinstance(when, Mapping) or when.get("person") not in WHEN_PERSONS:
            raise SubmissionEditError(f"when.person must be one of {list(WHEN_PERSONS)}")
        role = when.get("role")
        if role is not None and role not in WHEN_ROLES:
            raise SubmissionEditError(f"when.role must be one of {list(WHEN_ROLES)}")
        value["when"] = {"person": when["person"], **({"role": role} if role else {})}
    if raw.get("optional"):
        value["optional"] = True
    return value


_VALUES: dict[SubmissionList, tuple[Callable[[Mapping[str, Any]], dict[str, Any]], tuple[str, ...]]] = {
    SubmissionList.items: (_item_value, _ITEM_KEYS),
    SubmissionList.extra_items: (_extra_value, _EXTRA_KEYS),
    SubmissionList.signing_slots: (_slot_value, _SLOT_KEYS),
}
# Куда встаёт новый список профиля: за соседом, как в паках.
_AFTER: dict[SubmissionList, str] = {
    SubmissionList.items: "description",
    SubmissionList.extra_items: "items",
    SubmissionList.signing_slots: "signing_route",
}


def _entry_value(op: SubmissionOp) -> tuple[dict[str, Any], tuple[str, ...]]:
    build, known = _VALUES[_list_key(op)]
    return build(_need(op.value, "a value")), known


def _entries(text: str, op: SubmissionOp) -> tuple[Path, list[Any]]:
    path = (*_profile_path(text, op), _list_key(op).value)
    current = _node(text, path)
    if current is not _MISSING and not isinstance(current, list):
        raise SubmissionEditError(f"{_list_key(op).value} is not a list: fix it in the source")
    return path, current if isinstance(current, list) else []


def _entry_index(entries: list[Any], op: SubmissionOp) -> int:
    index = _need(op.index, "an entry index")
    if not 0 <= index < len(entries):
        raise SubmissionEditError(f"there is no entry {index} in {_list_key(op).value}")
    return index


def _add_entry(text: str, op: SubmissionOp) -> str:
    value, _known = _entry_value(op)
    path, entries = _entries(text, op)
    first = next(iter(value))
    if entries:
        # Запись блоком, если соседи блоком, и одной строкой рядом с записями одной строкой; поля по одному.
        text = insert_item(text, path, len(entries), {first: value[first]}, block=True)
        return set_value(text, (*path, len(entries)), value)
    after = _AFTER[_list_key(op)]
    profile = _node(text, path[:-1])
    if after not in profile:
        after = "items" if "items" in profile else "name"
    # Новый список блоком строк, а поля записи по одному: короткие списки и словари внутри одной строкой.
    text = set_value(text, path, [{first: value[first]}], after=after, block=True)
    return set_value(text, (*path, 0), value)


def _set_entry(text: str, op: SubmissionOp) -> str:
    value, known = _entry_value(op)
    path, entries = _entries(text, op)
    index = _entry_index(entries, op)
    return _set_keys(text, (*path, index), value, known, _seen_entry(_list_key(op), entries[index], index))


def _remove_entry(text: str, op: SubmissionOp) -> str:
    path, entries = _entries(text, op)
    index = _entry_index(entries, op)
    if len(entries) == 1 and _list_key(op) is not SubmissionList.items:
        # Опустевший `extra_items` или `signing_slots` уходит целиком, с комментарием над ним.
        return delete(text, path)
    return delete(text, (*path, index))


def _move_entry(text: str, op: SubmissionOp) -> str:
    path, entries = _entries(text, op)
    index = _entry_index(entries, op)
    to = _need(op.to, "a target index")
    if not 0 <= to < len(entries):
        raise SubmissionEditError(f"cannot move entry {index} to {to}")
    return move_item(text, path, index, to)


_HANDLERS: dict[SubmissionOpKind, Callable[[str, SubmissionOp], str]] = {
    SubmissionOpKind.add_profile: _add_profile,
    SubmissionOpKind.set_profile: _set_profile,
    SubmissionOpKind.remove_profile: _remove_profile,
    SubmissionOpKind.move_profile: _move_profile,
    SubmissionOpKind.set_profile_route: _set_profile_route,
    SubmissionOpKind.add_entry: _add_entry,
    SubmissionOpKind.set_entry: _set_entry,
    SubmissionOpKind.remove_entry: _remove_entry,
    SubmissionOpKind.move_entry: _move_entry,
    SubmissionOpKind.set_route: _set_route,
}


class PackSubmissionEditor:
    """Реализация порта `IPackSubmission` (core/pack_studio/protocols.py)."""

    def describe(self, text: str) -> VersionSubmission:
        data = _load(text)
        signatures = _mapping(data.get("signatures"))
        try:
            route = _route(signatures.get("route"))
        except _PARSE_ERRORS:
            route = None
        kinds = _kinds(data.get("supported_kinds")) or KINDS
        return VersionSubmission(
            documents=_documents(data),
            supported_kinds=kinds,
            has_nda=data.get("nda") is not None,
            slots=_slots(data),
            forms=_forms(data),
            route=route,
            builtin_route=BUILTIN_ROUTE,
            profiles=tuple(_profile_view(i, raw) for i, raw in enumerate(_raw_profiles(data))),
        )

    def apply(self, text: str, ops: Sequence[SubmissionOp]) -> str:
        before = text
        for op in ops:
            try:
                text = _HANDLERS[op.op](text, op)
            except YamlEditError as exc:
                raise SubmissionEditError(str(exc)) from None
        return _checked(before, text) if text != before else text
