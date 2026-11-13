"""Пометка «место из шаблона» в `signatures.json` (docs/design/signing-route.md, 15.4)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from hse_doc_studio.core.value_objects import FromPack, SignaturePlacement, SignaturesState
from hse_doc_studio.infra.persistence.serializers import deserialize_signatures_state, serialize_signatures_state
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository

MARK = FromPack(version="2026.1.4", digest="0123456789abcdef")


def _state(from_pack: FromPack | None = None) -> SignaturesState:
    placement = SignaturePlacement(enabled=True, page=1, x_mm=80, y_mm=139, width_mm=40, from_pack=from_pack)
    return SignaturesState(slots={}, placements={"project_proposal": {"supervisor": placement}})


def test__from_pack__roundtrips_and_is_written_as_null_without_a_mark() -> None:
    data = serialize_signatures_state(_state(MARK))

    assert data["placements"]["project_proposal"]["supervisor"]["from_pack"] == {
        "version": "2026.1.4",
        "digest": "0123456789abcdef",
    }
    assert deserialize_signatures_state(data) == _state(MARK)
    assert serialize_signatures_state(_state())["placements"]["project_proposal"]["supervisor"]["from_pack"] is None


@pytest.mark.parametrize("raw", [None, "2026.1.4", {"version": "2026.1.4"}, {"version": 1, "digest": "x"}, {}])
def test__from_pack__absent_or_broken__read_as_no_mark(raw: object) -> None:
    data = serialize_signatures_state(_state())
    data["placements"]["project_proposal"]["supervisor"]["from_pack"] = raw

    assert deserialize_signatures_state(data).placements["project_proposal"]["supervisor"].from_pack is None


def test__cleared_mark__not_brought_back_and_unknown_fields_inside_survive(tmp_path: Path) -> None:
    repository = JsonSignatureRepository()
    repository.save_state(tmp_path, _state(MARK))
    path = tmp_path / ".hse-studio" / "signatures.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["placements"]["project_proposal"]["supervisor"]["from_pack"]["profile"] = "topic-approval"
    path.write_text(json.dumps(raw), encoding="utf-8", newline="\n")

    restamped = replace(MARK, digest="fedcba9876543210")
    repository.save_state(tmp_path, _state(restamped))
    rewritten = json.loads(path.read_text(encoding="utf-8"))["placements"]["project_proposal"]["supervisor"]
    assert rewritten["from_pack"] == {"version": "2026.1.4", "digest": "fedcba9876543210", "profile": "topic-approval"}

    repository.save_state(tmp_path, _state())
    assert repository.get_state(tmp_path).placements["project_proposal"]["supervisor"].from_pack is None


def test__from_pack__anchor_and_build_roundtrip_only_on_anchored_places() -> None:
    anchored = replace(MARK, anchor="supervisor", build="0123456789abcdef")
    unknown = replace(MARK, anchor="supervisor")  # запасное место: якоря были неизвестны

    data = serialize_signatures_state(_state(anchored))

    assert data["placements"]["project_proposal"]["supervisor"]["from_pack"] == {
        "version": "2026.1.4",
        "digest": "0123456789abcdef",
        "anchor": "supervisor",
        "build": "0123456789abcdef",
    }
    assert deserialize_signatures_state(data) == _state(anchored)
    assert deserialize_signatures_state(serialize_signatures_state(_state(unknown))) == _state(unknown)


@pytest.mark.parametrize(
    ("anchor", "build", "expected"),
    [
        ("Supervisor", "0123456789abcdef", MARK),  # битый якорь: место в мм
        ("supervisor", "xyz", replace(MARK, anchor="supervisor")),  # битая сборка: неизвестна
        (7, None, MARK),
    ],
)
def test__from_pack__broken_anchor_or_build__read_tolerantly(anchor: object, build: object, expected: FromPack) -> None:
    data = serialize_signatures_state(_state(MARK))
    data["placements"]["project_proposal"]["supervisor"]["from_pack"].update(anchor=anchor, build=build)

    assert deserialize_signatures_state(data).placements["project_proposal"]["supervisor"].from_pack == expected
