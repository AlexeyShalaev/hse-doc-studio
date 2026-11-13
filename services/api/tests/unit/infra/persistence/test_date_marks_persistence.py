"""Метки даты и момент подписи в `signatures.json` (docs/design/signing-route.md, 14.3)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from hse_doc_studio.core.enums import DateMarkAlign, DateMarkFormat, SignedAtSource
from hse_doc_studio.core.value_objects import DateMark, SignaturePlacement, SignaturesState, SignedAt
from hse_doc_studio.infra.persistence.serializers import deserialize_signatures_state, serialize_signatures_state
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository

DAY = DateMark(id="d1", page=2, x_mm=120.0, y_mm=250.0, width_mm=8.0, height_mm=5.0, format=DateMarkFormat.day)
MONTH = DateMark(
    id="d2",
    page=2,
    x_mm=132.0,
    y_mm=250.0,
    width_mm=22.0,
    height_mm=5.0,
    format=DateMarkFormat.month_word,
    align=DateMarkAlign.left,
)
APPROVED = SignedAt(at="2026-11-12T23:30:00+00:00", source=SignedAtSource.approval, token="build:abc")


def _state(**placement: object) -> SignaturesState:
    return SignaturesState(
        slots={},
        placements={
            "proposal": {
                "supervisor": SignaturePlacement(enabled=False, page=1, x_mm=10, y_mm=20, width_mm=40, **placement)  # type: ignore[arg-type]
            }
        },
    )


def test__placement__dates_and_signed_at_roundtrip_and_written_even_empty() -> None:
    state = _state(dates=(DAY, MONTH), signed_at=APPROVED)

    data = serialize_signatures_state(state)
    restored = deserialize_signatures_state(data)

    written = data["placements"]["proposal"]["supervisor"]
    assert written["dates"] == [
        {"id": "d1", "page": 2, "x_mm": 120.0, "y_mm": 250.0, "width_mm": 8.0, "height_mm": 5.0, "format": "day",
         "align": "center"},
        {"id": "d2", "page": 2, "x_mm": 132.0, "y_mm": 250.0, "width_mm": 22.0, "height_mm": 5.0,
         "format": "month_word", "align": "left"},
    ]  # fmt: skip
    assert written["signed_at"] == {"at": "2026-11-12T23:30:00+00:00", "source": "approval", "token": "build:abc"}
    assert restored == state
    empty = serialize_signatures_state(_state())["placements"]["proposal"]["supervisor"]
    assert (empty["dates"], empty["signed_at"]) == ([], None)


def test__placement__file_without_dates__no_marks_and_broken_entries_skipped() -> None:
    raw = {
        "slots": {},
        "placements": {
            "old": {"supervisor": {"enabled": True, "page": 1, "x_mm": 1, "y_mm": 2, "width_mm": 3}},
            "proposal": {
                "supervisor": {
                    "enabled": False,
                    "page": 1,
                    "x_mm": 1,
                    "y_mm": 2,
                    "width_mm": 3,
                    "dates": [
                        {"id": "d1", "page": 2, "x_mm": 1, "y_mm": 2, "width_mm": 8, "height_mm": 5, "format": "day"},
                        {"id": "d1", "page": 3, "x_mm": 1, "y_mm": 2, "width_mm": 8, "height_mm": 5, "format": "day"},
                        {"id": "d2", "page": 2, "x_mm": 1, "y_mm": 2, "width_mm": 8, "height_mm": 5, "format": "era"},
                        {"id": "d3", "page": 2, "x_mm": 1, "y_mm": 2, "width_mm": 0, "height_mm": 5, "format": "day"},
                        {"id": "d4", "page": "x", "x_mm": 1, "y_mm": 2, "width_mm": 8, "height_mm": 5},
                        "d5",
                        {"id": "d6", "page": 2, "x_mm": 1, "y_mm": 2, "width_mm": 8, "height_mm": 5,
                         "format": "year", "align": "justify"},
                    ],
                    "signed_at": {"at": "2026-11-13", "source": "telepathy"},
                }
            },
        },
    }  # fmt: skip

    state = deserialize_signatures_state(raw)

    assert state.placements["old"]["supervisor"].dates == ()
    assert state.placements["old"]["supervisor"].signed_at is None
    proposal = state.placements["proposal"]["supervisor"]
    # Повтор id и незнакомый формат (данные более новой Студии) пропускаются, незнакомое выравнивание по центру.
    assert [(m.id, m.page, m.format, m.align) for m in proposal.dates] == [
        ("d1", 2, DateMarkFormat.day, DateMarkAlign.centered),
        ("d6", 2, DateMarkFormat.year, DateMarkAlign.centered),
    ]
    assert proposal.signed_at is None


def test__unknown_fields_of_a_mark_and_of_signed_at__survive_a_rewrite(tmp_path: Path) -> None:
    repository = JsonSignatureRepository()
    repository.save_state(tmp_path, _state(dates=(DAY, MONTH), signed_at=APPROVED))
    path = tmp_path / ".hse-studio" / "signatures.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    placement = raw["placements"]["proposal"]["supervisor"]
    placement["dates"][1]["font"] = "serif"
    placement["signed_at"]["tz"] = "Europe/Moscow"
    path.write_text(json.dumps(raw), encoding="utf-8", newline="\n")

    state = repository.get_state(tmp_path)
    moved = replace(state.placements["proposal"]["supervisor"], dates=(MONTH, replace(DAY, id="d3")))
    repository.save_state(tmp_path, replace(state, placements={"proposal": {"supervisor": moved}}))

    rewritten = json.loads(path.read_text(encoding="utf-8"))["placements"]["proposal"]["supervisor"]
    assert [m["id"] for m in rewritten["dates"]] == ["d2", "d3"]
    assert rewritten["dates"][0]["font"] == "serif"
    assert "font" not in rewritten["dates"][1]
    assert rewritten["signed_at"]["tz"] == "Europe/Moscow"


def test__removed_marks_and_date__not_brought_back_from_the_old_file(tmp_path: Path) -> None:
    repository = JsonSignatureRepository()
    repository.save_state(tmp_path, _state(dates=(DAY,), signed_at=APPROVED))

    repository.save_state(tmp_path, _state())

    placement = repository.get_state(tmp_path).placements["proposal"]["supervisor"]
    assert (placement.dates, placement.signed_at) == ((), None)
