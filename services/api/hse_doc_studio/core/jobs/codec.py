"""Проводное кодирование задач: датаклассы и перечисления в JSON-совместимые значения и обратно.

Кодирование идёт по значению, декодирование по аннотациям типов. Всё, что нельзя
передать другому процессу (Path, bytes, произвольные объекты), даёт TypeError, так
что правило «в задаче нет живых объектов» проверяется механически.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Union, cast
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.jobs.entities import JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobKind, JobStatus
from hse_doc_studio.core.jobs.errors import JobError
from hse_doc_studio.core.jobs.registry import job_kind_spec

_SPEC_FIELDS = {"id", "kind", "tags", "project_id", "actor", "locale", "payload"}
_RESULT_FIELDS = {"status", "data", "error"}


_STRINGIFY: tuple[tuple[type, Callable[[Any], str]], ...] = ((UUID, str), (datetime, datetime.isoformat))


def encode(value: object) -> object:
    if value is None or type(value) in (bool, int, float, str):
        return value
    if isinstance(value, Enum):
        return encode(value.value)
    for cls, to_text in _STRINGIFY:
        if isinstance(value, cls):
            return to_text(value)
    if isinstance(value, tuple | list | frozenset | set | dict):
        return _encode_container(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: encode(getattr(value, f.name)) for f in dataclasses.fields(value) if f.init}
    raise TypeError(f"{type(value).__name__} cannot be sent in a job")


def _encode_container(
    value: tuple[object, ...] | list[object] | frozenset[object] | set[object] | dict[str, object],
) -> object:
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("dict keys must be str")
        return {key: encode(item) for key, item in value.items()}
    items = [encode(item) for item in value]
    if isinstance(value, frozenset | set):
        return sorted(items, key=repr)
    return items


def decode[T](tp: type[T], data: object) -> T:
    return cast("T", _decode(tp, data))


def _decode(tp: object, data: object) -> object:
    if tp is Any:
        return data
    if tp is None or tp is type(None):
        if data is not None:
            raise TypeError("expected null")
        return None
    origin = typing.get_origin(tp)
    if origin is None:
        if not isinstance(tp, type):
            raise TypeError(f"unsupported type {tp}")
        return _decode_class(tp, data)
    handler = _GENERICS.get(origin)
    if handler is None:
        raise TypeError(f"unsupported type {tp}")
    return handler(typing.get_args(tp), data)


def _decode_union(args: tuple[object, ...], data: object) -> object:
    if data is None and type(None) in args:
        return None
    for arg in args:
        if arg is type(None):
            continue
        try:
            return _decode(arg, data)
        except (TypeError, ValueError, KeyError):
            continue
    raise TypeError(f"{data!r} matches no variant of {args}")


def _decode_literal(args: tuple[object, ...], data: object) -> object:
    if data not in args:
        raise ValueError(f"{data!r} is not one of {args}")
    return data


def _decode_tuple(args: tuple[object, ...], data: object) -> tuple[object, ...]:
    items = _as_list(data)
    if len(args) == 2 and args[1] is Ellipsis:  # noqa: PLR2004
        return tuple(_decode(args[0], item) for item in items)
    if len(args) != len(items):
        raise ValueError(f"expected {len(args)} items, got {len(items)}")
    return tuple(_decode(arg, item) for arg, item in zip(args, items, strict=True))


def _decode_list(args: tuple[object, ...], data: object) -> list[object]:
    return [_decode(args[0], item) for item in _as_list(data)]


def _decode_frozenset(args: tuple[object, ...], data: object) -> frozenset[object]:
    return frozenset(_decode(args[0], item) for item in _as_list(data))


def _decode_dict(args: tuple[object, ...], data: object) -> dict[object, object]:
    if not isinstance(data, dict):
        raise TypeError("expected object")
    return {_decode(args[0], key): _decode(args[1], item) for key, item in data.items()}


_GENERICS: dict[object, Callable[[tuple[object, ...], object], object]] = {
    Union: _decode_union,
    types.UnionType: _decode_union,
    Literal: _decode_literal,
    tuple: _decode_tuple,
    list: _decode_list,
    frozenset: _decode_frozenset,
    set: _decode_frozenset,
    dict: _decode_dict,
}


def _expect[T](tp: type[T], data: object, label: str) -> T:
    # bool является подклассом int, но в нагрузке числом не считается.
    if not isinstance(data, tp) or (tp is not bool and isinstance(data, bool)):
        raise TypeError(f"expected {label}")
    return data


def _decode_float(data: object) -> float:
    if isinstance(data, bool) or not isinstance(data, int | float):
        raise TypeError("expected number")
    return float(data)


_SCALARS: dict[type, Callable[[object], object]] = {
    bool: lambda data: _expect(bool, data, "bool"),
    int: lambda data: _expect(int, data, "int"),
    float: _decode_float,
    str: lambda data: _expect(str, data, "str"),
    UUID: lambda data: UUID(_expect(str, data, "uuid string")),
    datetime: lambda data: datetime.fromisoformat(_expect(str, data, "datetime string")),
}


def _decode_class(tp: type, data: object) -> object:
    if issubclass(tp, Enum):
        return tp(data)
    scalar = _SCALARS.get(tp)
    if scalar is not None:
        return scalar(data)
    if dataclasses.is_dataclass(tp):
        return _decode_dataclass(tp, data)
    raise TypeError(f"{tp.__name__} cannot be received in a job")


def _decode_dataclass(tp: type, data: object) -> object:
    if not isinstance(data, dict):
        raise TypeError(f"expected object for {tp.__name__}")
    hints = typing.get_type_hints(tp)
    fields = {f.name: f for f in dataclasses.fields(tp) if f.init}
    unknown = set(data) - set(fields)
    if unknown:
        raise ValueError(f"{tp.__name__} has no fields {sorted(unknown)}")
    kwargs: dict[str, object] = {}
    for name, field in fields.items():
        if name in data:
            kwargs[name] = _decode(hints[name], data[name])
        elif field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:
            raise KeyError(f"{tp.__name__}.{name} is missing")
    return tp(**kwargs)


def _as_list(data: object) -> list[object]:
    if not isinstance(data, list):
        raise TypeError("expected array")
    return data


def encode_spec(spec: JobSpec) -> dict[str, object]:
    """Конверт без `local_root`: путь на диске не покидает процесс."""
    return {
        "id": encode(spec.id),
        "kind": encode(spec.kind),
        "tags": encode(spec.tags),
        "project_id": encode(spec.project_id),
        "actor": encode(spec.actor),
        "locale": encode(spec.locale),
        "payload": encode(spec.payload),
    }


def decode_spec(data: dict[str, object]) -> JobSpec:
    unknown = set(data) - _SPEC_FIELDS
    if unknown:
        raise ValueError(f"unknown job envelope fields {sorted(unknown)}")
    kind = decode(JobKind, data["kind"])
    return JobSpec(
        id=decode(UUID, data["id"]),
        kind=kind,
        tags=decode(frozenset[str], data["tags"]),
        project_id=decode(UUID, data["project_id"]),
        actor=decode(Actor, data["actor"]),
        locale=decode(Lang, data["locale"]),
        payload=decode(job_kind_spec(kind).payload_cls, data["payload"]),
    )


def encode_result(result: JobResult) -> dict[str, object]:
    return {"status": encode(result.status), "data": encode(result.data), "error": encode(result.error)}


def decode_result(kind: JobKind, data: dict[str, object]) -> JobResult:
    unknown = set(data) - _RESULT_FIELDS
    if unknown:
        raise ValueError(f"unknown job result fields {sorted(unknown)}")
    spec = job_kind_spec(kind)
    return JobResult(
        status=decode(JobStatus, data["status"]),
        data=None if data["data"] is None else decode(spec.result_cls, data["data"]),
        error=cast("JobError | None", _decode(JobError | None, data["error"])),
    )
