"""Слияние JSON по полям: трёхстороннее, с правилами для известных мест документа.

Файлы состояния Студии (`project.json`, `signatures.json`, формы, `template.json`) нельзя сливать
как текст: две сборки на двух машинах правят одни и те же строки (`last_compile_id`, `updated_at`),
хотя по смыслу не спорят. Движок идёт по документу рекурсивно и решает каждое поле отдельно:

    поле не менялось с одной стороны       берём правку другой стороны
    обе стороны поменяли одинаково         берём общее значение
    обе поменяли по-разному                правило места (максимум, множество, «только у меня»)
                                           или конфликт поля, который решает человек

Что делает конфликтом, а что нет, описывают правила (`JsonRules`): списки с ключом (документы по
id, авторы по slug), множества, максимум и минимум, неделимые записи, поля «только у меня», группы
полей. Без правила словарь сливается по ключам, а список и скаляр целиком: по-разному правили
оба — конфликт поля.

Порядок результата не зависит от того, какая сторона «моя»: ключи словаря идут в порядке базы,
затем остальные по алфавиту; так же устроены списки с ключом. Две машины, сливающие одну пару
коммитов, получают один и тот же файл. Исключение одно, и оно намеренное: поле «только у меня»
остаётся моим, а не общим.

Пока конфликт не решён, в итоге его место занимает «моя» сторона: документ остаётся корректным.
Решения человека — словарь `JSON-указатель → mine | theirs | union`: слияние запускается заново с
ними, поэтому порядок и правила не расходятся с первым прогоном.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from itertools import chain
from typing import Any, Literal

from hse_doc_studio.core.git_sync.entities import SyncWarning
from hse_doc_studio.core.git_sync.merge.choices import FieldChoice


class _Sentinel:
    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:
        return self._name

    def __bool__(self) -> bool:
        return False


# Значения JSON не бывают «отсутствующими», а у слияния ключа такая сторона есть: ключа нет вовсе.
ABSENT: Any = _Sentinel("ABSENT")
# Ответ правила «сам не решаю»: поле станет конфликтом.
UNRESOLVED: Any = _Sentinel("UNRESOLVED")

Pattern = tuple[str, ...]


class FieldType(StrEnum):
    scalar = "scalar"
    list = "list"
    record = "record"
    presence = "presence"


class ConflictKind(StrEnum):
    field = "field"
    signature_group = "signature_group"


class InvalidFieldChoiceError(ValueError):
    """Решение по полю не подходит: неизвестный указатель или выбор, которого поле не допускает."""

    def __init__(self, pointers: Sequence[str]) -> None:
        super().__init__(", ".join(pointers))
        self.pointers = tuple(pointers)


def canon(value: Any) -> str:
    """Каноничная запись значения для сравнения: порядок ключей не важен, `1` и `true` разные."""
    if value is ABSENT:
        return "\0absent"
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def same(first: Any, second: Any) -> bool:
    return canon(first) == canon(second)


def canonical_dumps(value: Any) -> str:
    """Как пишут репозитории состояния (`ensure_ascii=False, indent=2`): без перевода строки в конце."""
    return json.dumps(value, ensure_ascii=False, indent=2)


def pointer_of(path: Sequence[str]) -> str:
    """JSON-указатель (RFC 6901); элемент списка с ключом записан как `@<ключ>`."""
    return "".join("/" + segment.replace("~", "~0").replace("/", "~1") for segment in path)


# --- правила -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Keyed:
    """Список объектов с ключом: элементы сливаются попарно, порядок — база, затем новые по ключу."""

    pattern: Pattern
    key: Callable[[Any], Hashable | None]
    # Если задан, итог сортируется по нему (история обновлений читается с конца).
    order: Callable[[Any], Any] | None = None


@dataclass(frozen=True)
class SetOf:
    """Список скаляров как множество: удаления и добавления обеих сторон складываются."""

    pattern: Pattern
    sort: bool = False


@dataclass(frozen=True)
class Extremum:
    """Скаляр, у которого побеждает больший или меньший: номер схемы, версия, время."""

    pattern: Pattern
    pick: Literal["max", "min"]
    # Сравнимый ключ значения или None, если значение не разобрать (тогда конфликт).
    key: Callable[[Any], Any | None]


@dataclass(frozen=True)
class Atomic:
    """Запись целиком: если правили обе стороны, это один конфликт, а не слияние по полям."""

    pattern: Pattern


@dataclass(frozen=True)
class LocalOnly:
    """Поле машины: остаётся моим, чужое не приходит. У добавленной чужой записи берётся `default`."""

    pattern: Pattern
    default: Any = ABSENT


@dataclass(frozen=True)
class MustEqual:
    """Поле, которое не может отличаться: любое расхождение сторон — конфликт, даже если правили одну."""

    pattern: Pattern


@dataclass(frozen=True)
class Custom:
    """Своё правило для обеих изменённых сторон: значение или UNRESOLVED."""

    pattern: Pattern
    resolve: Callable[[Any, Any, Any], Any]


Rule = Keyed | SetOf | Extremum | Atomic | LocalOnly | MustEqual | Custom


@dataclass(frozen=True)
class FieldGroup:
    """Поля одного словаря, которые берутся все с одной стороны: побеждает новее (`newest_theirs`)."""

    pattern: Pattern
    fields: tuple[str, ...]


@dataclass(frozen=True)
class DocGroups:
    """Одноимённые записи нескольких словарей как неделимая группа: берутся целиком с одной стороны.

    Правили обе стороны — конфликт группы. Подписанный PDF и подписи к нему покрывают одни и те же
    байты, смешивать их по полям нельзя.
    """

    pattern: Pattern
    members: tuple[str, ...]
    # Из чего строится указатель конфликта: `/<label>/<id>`.
    label: str


@dataclass(frozen=True)
class PostResult:
    value: Any
    warnings: tuple[SyncWarning, ...] = ()


# Проверка итога: (итог, мой документ, чужой документ) → итог, возможно исправленный, и предупреждения.
PostFn = Callable[[Any, Any, Any], PostResult]


def _matches(pattern: Pattern, path: Sequence[str]) -> bool:
    return len(pattern) == len(path) and all(
        part in ("*", segment) for part, segment in zip(pattern, path, strict=True)
    )


def _prefix_matches(pattern: Pattern, path: Sequence[str]) -> bool:
    return len(pattern) > len(path) and all(
        part in ("*", segment) for part, segment in zip(pattern, path, strict=False)
    )


@dataclass(frozen=True)
class JsonRules:
    """Правила файла: на каждый путь действует первое подошедшее. Звёздочка в шаблоне — любой один сегмент."""

    name: str = "state"
    rules: tuple[Rule, ...] = ()
    field_groups: tuple[FieldGroup, ...] = ()
    doc_groups: tuple[DocGroups, ...] = ()
    post: tuple[PostFn, ...] = ()

    def lookup(self, path: Sequence[str]) -> Rule | None:
        return next((rule for rule in self.rules if _matches(rule.pattern, path)), None)

    def has_inner_rules(self, path: Sequence[str]) -> bool:
        """Под этим путём есть поле «только у меня» или обязанное совпадать: чужую правку нельзя брать целиком."""
        return any(isinstance(r, LocalOnly | MustEqual) and _prefix_matches(r.pattern, path) for r in self.rules)


# --- результат ---------------------------------------------------------------------------------


def _json(value: Any) -> Any:
    return None if value is ABSENT else value


@dataclass(frozen=True)
class FieldConflict:
    """Поле, по которому обе стороны ушли от базы в разные стороны. Отсутствующая сторона — None."""

    pointer: str
    type: FieldType
    base: Any
    ours: Any
    theirs: Any
    allowed: tuple[FieldChoice, ...]
    kind: ConflictKind = ConflictKind.field


@dataclass(frozen=True)
class AutoField:
    """Поле, которое правило решило без человека; `allowed` — чем человек может его заменить."""

    pointer: str
    type: FieldType
    base: Any
    ours: Any
    theirs: Any
    allowed: tuple[FieldChoice, ...] = (FieldChoice.mine, FieldChoice.theirs)


@dataclass(frozen=True)
class JsonMerge:
    value: Any
    conflicts: tuple[FieldConflict, ...] = ()
    auto: tuple[AutoField, ...] = ()
    warnings: tuple[SyncWarning, ...] = ()

    @property
    def is_clean(self) -> bool:
        return not self.conflicts


# --- слияние -----------------------------------------------------------------------------------


def _type_of(ours: Any, theirs: Any) -> FieldType:
    values = [value for value in (ours, theirs) if value is not ABSENT]
    if len(values) < 2:
        return FieldType.presence
    if any(isinstance(value, dict) for value in values):
        return FieldType.record
    if any(isinstance(value, list) for value in values):
        return FieldType.list
    return FieldType.scalar


def _scalar_list(value: Any) -> bool:
    return isinstance(value, list) and not any(isinstance(item, dict | list) for item in value)


def _union(ours: Any, theirs: Any) -> list[Any]:
    seen = {canon(item) for item in ours}
    return [*ours, *(item for item in theirs if canon(item) not in seen)]


def _ordered_keys(base: Mapping[Any, Any], *others: Mapping[Any, Any]) -> list[Any]:
    """Ключи в порядке базы, затем остальные по алфавиту: от того, кто «я», порядок не зависит."""
    rest = set(chain.from_iterable(others)) - set(base)
    return [*base, *sorted(rest, key=str)]


def _as_dict(value: Any) -> dict[str, Any]:
    return {} if value is ABSENT else value


def _group_canon(group: Sequence[Any]) -> str:
    return canon([None if item is ABSENT else {"v": item} for item in group])


def _json_map(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _json(value) for key, value in values.items()}


def _agreed_group(base: tuple[Any, ...], ours: tuple[Any, ...], theirs: tuple[Any, ...]) -> tuple[Any, ...] | None:
    """Группа, по которой спора нет (правила те же, что у отдельного поля); None — правили обе стороны."""
    mine, other, before = _group_canon(ours), _group_canon(theirs), _group_canon(base)
    if other in (mine, before):
        return ours
    return theirs if before == mine else None


def _keyed_items(rule: Keyed, value: Any) -> dict[Hashable, Any] | None:
    """Элементы списка по ключу; None, если список для слияния по ключу не годится."""
    if value is ABSENT:
        return {}
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        return None
    keys = [rule.key(item) for item in value]
    if any(key is None for key in keys) or len(set(keys)) != len(keys):
        return None
    return dict(zip(keys, value, strict=True))


@dataclass
class _Merger:
    rules: JsonRules
    choices: Mapping[str, FieldChoice]
    newest_theirs: Callable[[Any, Any], bool] | None
    conflicts: list[FieldConflict] = field(default_factory=list)
    auto: list[AutoField] = field(default_factory=list)
    used: set[str] = field(default_factory=set)

    def merge(self, path: tuple[str, ...], base: Any, ours: Any, theirs: Any) -> Any:
        rule = self.rules.lookup(path)
        if isinstance(rule, LocalOnly):
            return self._local(path, rule, base, ours, theirs)
        if isinstance(rule, MustEqual) and ABSENT not in (ours, theirs) and not same(ours, theirs):
            return self._conflict(path, base, ours, theirs)
        if same(ours, theirs) or same(base, theirs):
            return ours
        if same(base, ours):
            return self._theirs_only(path, rule, base, ours, theirs)
        return self._diverged(path, rule, base, ours, theirs)

    def _theirs_only(self, path: tuple[str, ...], rule: Rule | None, base: Any, ours: Any, theirs: Any) -> Any:
        """Правила только чужая сторона: берём её, но поля «только у меня» остаются моими."""
        if theirs is ABSENT or not self.rules.has_inner_rules(path):
            return theirs
        merged = self._container(path, rule, base, ours, theirs)
        return theirs if merged is UNRESOLVED else merged

    def _diverged(self, path: tuple[str, ...], rule: Rule | None, base: Any, ours: Any, theirs: Any) -> Any:
        if ours is ABSENT or theirs is ABSENT:
            return self._presence(path, base, ours, theirs)
        resolved = self._by_rule(path, rule, base, ours, theirs)
        if resolved is UNRESOLVED:
            resolved = self._container(path, rule, base, ours, theirs)
        if resolved is UNRESOLVED:
            return self._conflict(path, base, ours, theirs)
        return resolved

    # --- поля «только у меня» ---

    def _local(self, path: tuple[str, ...], rule: LocalOnly, base: Any, ours: Any, theirs: Any) -> Any:
        if same(ours, theirs):
            return ours
        value = ours
        if ours is ABSENT and theirs is not ABSENT:
            value = rule.default
        return self._auto(path, base, ours, theirs, value)

    def _strip_local(self, path: tuple[str, ...], value: Any) -> Any:
        """Значение без полей «только у меня»: правка только в них не считается правкой записи."""
        rule = self.rules.lookup(path)
        if isinstance(rule, LocalOnly):
            return UNRESOLVED
        if isinstance(value, dict):
            stripped = {key: self._strip_local((*path, key), item) for key, item in value.items()}
            return {key: item for key, item in stripped.items() if item is not UNRESOLVED}
        items = _keyed_items(rule, value) if isinstance(rule, Keyed) else None
        if items is None:
            return value
        return [self._strip_local((*path, f"@{key}"), item) for key, item in items.items()]

    def _presence(self, path: tuple[str, ...], base: Any, ours: Any, theirs: Any) -> Any:
        """Одна сторона удалила запись, другая её правила: конфликт, если правка не только в локальных полях."""
        edited = theirs if ours is ABSENT else ours
        if same(self._strip_local(path, edited), self._strip_local(path, base)):
            return ABSENT
        return self._conflict(path, base, ours, theirs)

    # --- правила места ---

    def _by_rule(self, path: tuple[str, ...], rule: Rule | None, base: Any, ours: Any, theirs: Any) -> Any:
        if isinstance(rule, Custom):
            value = rule.resolve(base, ours, theirs)
        elif isinstance(rule, Extremum):
            value = self._extremum(rule, ours, theirs)
        elif isinstance(rule, SetOf):
            value = self._set(rule, base, ours, theirs)
        else:
            return UNRESOLVED
        if value is UNRESOLVED:
            return value
        return self._auto(path, base, ours, theirs, value)

    @staticmethod
    def _extremum(rule: Extremum, ours: Any, theirs: Any) -> Any:
        if rule.key(ours) is None or rule.key(theirs) is None:
            return UNRESOLVED
        ranked = sorted((ours, theirs), key=lambda value: (rule.key(value), canon(value)))
        return ranked[-1] if rule.pick == "max" else ranked[0]

    @staticmethod
    def _set(rule: SetOf, base: Any, ours: Any, theirs: Any) -> Any:
        if not (_scalar_list(ours) and _scalar_list(theirs)):
            return UNRESOLVED
        sides = [{canon(item): item for item in side} for side in (base if _scalar_list(base) else [], ours, theirs)]
        before, mine, other = sides
        removed = (before.keys() - mine.keys()) | (before.keys() - other.keys())
        added = (mine.keys() | other.keys()) - before.keys()
        result = [item for key, item in before.items() if key not in removed]
        result += [({**mine, **other})[key] for key in sorted(added)]
        return sorted(result, key=canon) if rule.sort else result

    def _auto(self, path: tuple[str, ...], base: Any, ours: Any, theirs: Any, value: Any) -> Any:
        """Итог, выбранный правилом; человек может заменить его моим или чужим значением."""
        pointer = pointer_of(path)
        choice = self.choices.get(pointer)
        if choice is not None:
            self.used.add(pointer)
            value = self._pick(pointer, choice, (FieldChoice.mine, FieldChoice.theirs), ours, theirs)
        if not same(ours, theirs):
            kind = _type_of(ours, theirs)
            self.auto.append(AutoField(pointer, kind, _json(base), _json(ours), _json(theirs)))
        return value

    # --- составные значения ---

    def _container(self, path: tuple[str, ...], rule: Rule | None, base: Any, ours: Any, theirs: Any) -> Any:
        if isinstance(rule, Atomic | Custom):
            return UNRESOLVED
        sides = [side for side in (base, ours, theirs) if side is not ABSENT]
        if isinstance(rule, Keyed) and all(_keyed_items(rule, side) is not None for side in sides):
            return self._keyed(path, rule, base, ours, theirs)
        if all(isinstance(side, dict) for side in sides):
            return self._dict(path, base, ours, theirs)
        return UNRESOLVED

    def _dict(self, path: tuple[str, ...], base: Any, ours: Any, theirs: Any) -> dict[str, Any]:
        before, mine, other = _as_dict(base), _as_dict(ours), _as_dict(theirs)
        grouped = {
            **self._field_groups(path, before, mine, other),
            **self._doc_groups(path, before, mine, other),
        }
        merged: dict[str, Any] = {}
        for key in _ordered_keys(before, mine, other):
            if key in grouped:
                value = grouped[key]
            else:
                value = self.merge((*path, key), before.get(key, ABSENT), mine.get(key, ABSENT), other.get(key, ABSENT))
            if value is not ABSENT:
                merged[key] = value
        return merged

    def _keyed(self, path: tuple[str, ...], rule: Keyed, base: Any, ours: Any, theirs: Any) -> list[Any]:
        before, mine, other = (_keyed_items(rule, side) or {} for side in (base, ours, theirs))
        merged = []
        for key in _ordered_keys(before, mine, other):
            item = self.merge(
                (*path, f"@{key}"), before.get(key, ABSENT), mine.get(key, ABSENT), other.get(key, ABSENT)
            )
            if item is not ABSENT:
                merged.append(item)
        return sorted(merged, key=rule.order) if rule.order is not None else merged

    # --- группы ---

    def _field_groups(
        self, path: tuple[str, ...], base: dict[str, Any], ours: dict[str, Any], theirs: dict[str, Any]
    ) -> dict[str, Any]:
        grouped: dict[str, Any] = {}
        for group in self.rules.field_groups:
            if _matches(group.pattern, path):
                sides = [tuple(side.get(name, ABSENT) for name in group.fields) for side in (base, ours, theirs)]
                grouped.update(zip(group.fields, self._chosen_fields(path, group, *sides), strict=True))
        return grouped

    def _chosen_fields(
        self,
        path: tuple[str, ...],
        group: FieldGroup,
        base: tuple[Any, ...],
        ours: tuple[Any, ...],
        theirs: tuple[Any, ...],
    ) -> tuple[Any, ...]:
        agreed = _agreed_group(base, ours, theirs)
        if agreed is not None:
            return agreed
        # Правили обе стороны: поля берутся вместе с той, чья правка новее.
        mine, other = _group_canon(ours), _group_canon(theirs)
        wins = self.newest_theirs(mine.encode(), other.encode()) if self.newest_theirs else other > mine
        names = group.fields
        shown = [_json_map(dict(zip(names, side, strict=True))) for side in (ours, theirs)]
        pointer = pointer_of((*path, names[0]))
        self.auto.append(AutoField(pointer, FieldType.record, None, shown[0], shown[1], allowed=()))
        return theirs if wins else ours

    def _doc_groups(
        self, path: tuple[str, ...], base: dict[str, Any], ours: dict[str, Any], theirs: dict[str, Any]
    ) -> dict[str, Any]:
        grouped: dict[str, Any] = {}
        for group in self.rules.doc_groups:
            if _matches(group.pattern, path):
                grouped.update(self._doc_group(group, base, ours, theirs))
        return grouped

    def _doc_group(
        self, group: DocGroups, base: dict[str, Any], ours: dict[str, Any], theirs: dict[str, Any]
    ) -> dict[str, Any]:
        sides = [[side.get(member, ABSENT) for member in group.members] for side in (base, ours, theirs)]
        if any(item is not ABSENT and not isinstance(item, dict) for side in sides for item in side):
            return {}
        maps = [[_as_dict(item) for item in side] for side in sides]
        doc_ids = _ordered_keys(*({doc: None for item in side for doc in item} for side in maps))
        merged: dict[str, dict[str, Any]] = {member: {} for member in group.members}
        for doc_id in doc_ids:
            triple = [tuple(item.get(doc_id, ABSENT) for item in side) for side in maps]
            for member, value in zip(group.members, self._chosen_group(group, doc_id, *triple), strict=True):
                if value is not ABSENT:
                    merged[member][doc_id] = value
        return {
            member: merged[member]
            for index, member in enumerate(group.members)
            if any(side[index] is not ABSENT for side in sides)
        }

    def _chosen_group(
        self,
        group: DocGroups,
        doc_id: str,
        base: tuple[Any, ...],
        ours: tuple[Any, ...],
        theirs: tuple[Any, ...],
    ) -> tuple[Any, ...]:
        agreed = _agreed_group(base, ours, theirs)
        if agreed is not None:
            return agreed
        pointer = pointer_of((group.label, doc_id))
        choice = self.choices.get(pointer)
        if choice is None:
            before, mine, other = (
                _json_map(dict(zip(group.members, side, strict=True))) for side in (base, ours, theirs)
            )
            allowed = (FieldChoice.mine, FieldChoice.theirs)
            conflict = FieldConflict(
                pointer, FieldType.record, before, mine, other, allowed, ConflictKind.signature_group
            )
            self.conflicts.append(conflict)
            return ours
        self.used.add(pointer)
        if choice not in (FieldChoice.mine, FieldChoice.theirs):
            raise InvalidFieldChoiceError([pointer])
        return ours if choice is FieldChoice.mine else theirs

    # --- конфликты ---

    def _conflict(self, path: tuple[str, ...], base: Any, ours: Any, theirs: Any) -> Any:
        pointer = pointer_of(path)
        kind = _type_of(ours, theirs)
        allowed = [FieldChoice.mine, FieldChoice.theirs]
        if kind is FieldType.list and _scalar_list(ours) and _scalar_list(theirs):
            allowed.append(FieldChoice.union)
        choice = self.choices.get(pointer)
        if choice is not None:
            self.used.add(pointer)
            return self._pick(pointer, choice, allowed, ours, theirs)
        self.conflicts.append(FieldConflict(pointer, kind, _json(base), _json(ours), _json(theirs), tuple(allowed)))
        # Пока человек не решил, в итоге моя сторона.
        return ours

    @staticmethod
    def _pick(pointer: str, choice: FieldChoice, allowed: Sequence[FieldChoice], ours: Any, theirs: Any) -> Any:
        if choice not in allowed:
            raise InvalidFieldChoiceError([pointer])
        if choice is FieldChoice.union:
            return _union(ours, theirs)
        return ours if choice is FieldChoice.mine else theirs


def merge_json(
    base: Any,
    ours: Any,
    theirs: Any,
    rules: JsonRules,
    *,
    choices: Mapping[str, FieldChoice] | None = None,
    newest_theirs: Callable[[Any, Any], bool] | None = None,
) -> JsonMerge:
    """Трёхстороннее слияние документов. Отсутствующая сторона — ABSENT (у файла без общей базы база — ABSENT).

    `choices` — решения человека по указателям конфликтов и автоматических полей. Указатель, которого в
    слиянии нет, и выбор, которого поле не допускает, — InvalidFieldChoiceError.
    `newest_theirs(мои_байты, чужие_байты)` решает, чья версия группы полей новее (подписи слотов
    следуют за картинкой, которая побеждает по времени); без него побеждает большее значение.
    """
    merger = _Merger(rules, choices or {}, newest_theirs)
    value = merger.merge((), base, ours, theirs)
    unknown = sorted(set(choices or {}) - merger.used)
    if unknown:
        raise InvalidFieldChoiceError(unknown)
    warnings: tuple[SyncWarning, ...] = ()
    if not merger.conflicts:
        value, warnings = _post(rules, value, ours, theirs)
    return JsonMerge(value, tuple(merger.conflicts), tuple(merger.auto), warnings)


def _post(rules: JsonRules, value: Any, ours: Any, theirs: Any) -> tuple[Any, tuple[SyncWarning, ...]]:
    warnings: list[SyncWarning] = []
    for check in rules.post:
        result = check(value, ours, theirs)
        value = result.value
        warnings.extend(result.warnings)
    return value, tuple(warnings)
