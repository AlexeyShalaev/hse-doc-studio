from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.jobs.codec import decode, decode_result, decode_spec, encode, encode_result, encode_spec
from hse_doc_studio.core.jobs.entities import JobResult
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobKind, JobStatus
from hse_doc_studio.core.jobs.errors import JobError

from tests.unit.core.jobs.samples import make_compile_result, make_compile_spec


class _Color(StrEnum):
    red = "red"
    blue = "blue"


@dataclass(frozen=True)
class _Inner:
    n: int
    label: str = "x"


@dataclass(frozen=True)
class _Outer:
    inner: _Inner
    color: _Color
    ident: UUID
    at: datetime
    pair: tuple[str, int]
    many: tuple[_Inner, ...]
    names: frozenset[str]
    maybe: _Inner | None
    ratio: float
    mapping: dict[str, list[int]]
    mode: Literal["a", "b"]
    either: list[str] | Literal["*"]


def _outer() -> _Outer:
    return _Outer(
        inner=_Inner(1),
        color=_Color.blue,
        ident=UUID("33333333-3333-4333-8333-333333333333"),
        at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        pair=("a", 2),
        many=(_Inner(1, "p"), _Inner(2)),
        names=frozenset({"b", "a"}),
        maybe=None,
        ratio=2.0,
        mapping={"k": [1, 2]},
        mode="b",
        either="*",
    )


def test__codec__dataclass_enum_uuid_tuple_optional__round_trips_through_json() -> None:
    value = _outer()

    wire = json.loads(json.dumps(encode(value)))

    assert decode(_Outer, wire) == value


def test__codec__union_with_literal_and_list__decodes_both_variants() -> None:
    wire = json.loads(json.dumps(encode(_Outer(**{**_outer().__dict__, "either": ["x", "y"], "maybe": _Inner(3)}))))
    decoded = decode(_Outer, wire)
    assert decoded.either == ["x", "y"]
    assert decoded.maybe == _Inner(3)


def test__encode__sets_are_sorted_for_a_stable_wire_form() -> None:
    assert encode(frozenset({"b", "c", "a"})) == ["a", "b", "c"]


@pytest.mark.parametrize("value", [Path("/tmp/x"), b"bytes", object(), {1: "a"}, [Path("p")], (b"x",)])
def test__encode__path_bytes_and_live_objects__rejected(value: object) -> None:
    with pytest.raises(TypeError):
        encode(value)


def test__encode__path_field_inside_dataclass__rejected() -> None:
    @dataclass(frozen=True)
    class _WithPath:
        p: Path

    with pytest.raises(TypeError):
        encode(_WithPath(Path("a")))


def test__decode__path_and_bytes_types__rejected() -> None:
    with pytest.raises(TypeError):
        decode(Path, "/tmp/x")
    with pytest.raises(TypeError):
        decode(bytes, "x")


def test__decode__wrong_shapes__raise() -> None:
    wire = encode(_Inner(1))
    with pytest.raises(ValueError, match="no fields"):
        decode(_Inner, {**wire, "extra": 1})  # type: ignore[dict-item]
    with pytest.raises(KeyError):
        decode(_Inner, {"label": "x"})
    with pytest.raises(TypeError):
        decode(_Inner, {"n": True})
    with pytest.raises(TypeError):
        decode(_Inner, {"n": "1"})
    with pytest.raises(ValueError, match="green"):
        decode(_Color, "green")
    with pytest.raises(ValueError, match="expected 2 items"):
        decode(tuple[str, int], ["a"])


def test__spec__local_root_is_dropped_from_the_envelope_and_the_rest_round_trips() -> None:
    spec = make_compile_spec(local_root=Path("/projects/a"))

    wire = json.loads(json.dumps(encode_spec(spec)))
    decoded = decode_spec(wire)

    assert "local_root" not in wire
    assert decoded.local_root is None
    assert decoded == make_compile_spec()
    assert decoded.kind is JobKind.compile
    assert isinstance(decoded.actor, Actor)


def test__spec__unknown_envelope_field__rejected() -> None:
    wire = encode_spec(make_compile_spec())
    with pytest.raises(ValueError, match="unknown job envelope"):
        decode_spec({**wire, "local_root": "/x"})


def test__result__compile_result_round_trips_with_the_registered_class() -> None:
    result = make_compile_result()

    decoded = decode_result(JobKind.compile, json.loads(json.dumps(encode_result(result))))

    assert decoded == result


def test__result__failure_with_error_and_no_data__round_trips() -> None:
    result = JobResult(
        status=JobStatus.failed,
        error=JobError(category=JobErrorCategory.internal, code="handler_crashed", detail="boom"),
    )

    assert decode_result(JobKind.compile, json.loads(json.dumps(encode_result(result)))) == result
