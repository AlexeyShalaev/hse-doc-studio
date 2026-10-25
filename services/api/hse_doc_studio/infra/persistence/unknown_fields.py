"""Сохранение неизвестных полей при перезаписи json-состояния проекта.

Сериализаторы пишут только известные им ключи. Без этого модуля Студия, которую
откатили на старую версию, при первой же записи `project.json` молча стирала бы
поля, добавленные более новой Студией. Поэтому перед записью новый словарь
сливается со старым содержимым файла по ФОРМЕ документа:

* `Struct` — объект с фиксированным набором ключей: ключ, которого писатель не
  знает (его нет в новом словаре), переносится из старого как есть;
* `MapOf` — словарь с произвольными ключами (мета-поля, размещения подписей):
  набор ключей берётся из нового словаря, иначе удалённый пользователем ключ
  воскресал бы; значения при желании сливаются по своей форме;
* `ListOf` — список объектов: элементы сопоставляются по ключу (id документа,
  слаг автора) и сливаются попарно.

Форма описывает только то, что сериализатор пишет ВСЕГДА (в том числе `null`).
Ключ, который сериализатор пишет условно, сюда не годится: его отсутствие
означало бы «удалить», а слияние вернуло бы старое значение.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Struct:
    fields: Mapping[str, Shape] = field(default_factory=dict)


@dataclass(frozen=True)
class MapOf:
    value: Shape | None = None


@dataclass(frozen=True)
class ListOf:
    item: Shape
    key: Callable[[dict[str, Any]], Hashable | None]


Shape = Struct | MapOf | ListOf


def preserve_unknown(new: Any, old: Any, shape: Shape | None) -> Any:
    """`new`, дополненный неизвестными писателю полями из `old`."""
    if shape is None or old is None:
        return new
    if isinstance(shape, Struct):
        return _merge_struct(new, old, shape)
    if isinstance(shape, MapOf):
        return _merge_map(new, old, shape)
    return _merge_list(new, old, shape)


def _merge_struct(new: Any, old: Any, shape: Struct) -> Any:
    if not isinstance(new, dict) or not isinstance(old, dict):
        return new
    merged = dict(new)
    for key, old_value in old.items():
        if key not in new:
            merged[key] = old_value
        elif key in shape.fields:
            merged[key] = preserve_unknown(new[key], old_value, shape.fields[key])
    return merged


def _merge_map(new: Any, old: Any, shape: MapOf) -> Any:
    if shape.value is None or not isinstance(new, dict) or not isinstance(old, dict):
        return new
    return {key: preserve_unknown(value, old.get(key), shape.value) for key, value in new.items()}


def _merge_list(new: Any, old: Any, shape: ListOf) -> Any:
    if not isinstance(new, list) or not isinstance(old, list):
        return new
    index: dict[Hashable, dict[str, Any]] = {}
    for item in old:
        if isinstance(item, dict):
            key = shape.key(item)
            if key is not None:
                index.setdefault(key, item)
    return [
        preserve_unknown(item, index.get(shape.key(item)), shape.item) if isinstance(item, dict) else item
        for item in new
    ]


def _author_key(author: dict[str, Any]) -> Hashable | None:
    return author.get("slug") or author.get("name") or None


def _doc_key(doc: dict[str, Any]) -> Hashable | None:
    return doc.get("id")


_CHECKS_OVERRIDE = Struct({"severity_override": MapOf()})

PROJECT_SHAPE = Struct(
    {
        "lock": Struct(),
        "schema": Struct(),
        "authors": ListOf(Struct({"meta": MapOf()}), key=_author_key),
        "meta": MapOf(),
        "supervisor": Struct(),
        "co_supervisor": Struct(),
        "academic_supervisor": Struct(),
        "documents": ListOf(
            Struct({"checks_override": _CHECKS_OVERRIDE, "custom_file": Struct()}),
            key=_doc_key,
        ),
        "checks_override": _CHECKS_OVERRIDE,
        "requirements": Struct(),
    }
)

SIGNATURES_SHAPE = Struct(
    {
        "slots": MapOf(Struct({"signer": Struct()})),
        "placements": MapOf(MapOf(Struct())),
        "frozen": MapOf(Struct()),
        "detached": MapOf(MapOf(Struct())),
    }
)

FORM_STATE_SHAPE = Struct({"answers": MapOf()})
