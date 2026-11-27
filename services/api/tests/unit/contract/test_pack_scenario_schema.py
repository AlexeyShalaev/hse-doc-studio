"""Схема сценария `contracts/pack/scenario.schema.json` (срез O8): настоящие сценарии паков её проходят, дефекты формата
нет, а схема и парсер Студии (`core/pack_studio/outcome/scenarios.py`) согласны друг с другом."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from hse_doc_studio.core.pack_studio.outcome.scenarios import ScenarioError, parse_scenario
from hse_doc_studio.infra.pack_studio import pack_schemas

_PACKS = Path(__file__).resolve().parents[5] / "packs"
_FILES = sorted(_PACKS.glob("*/templates/*/scenarios/*.yaml"))

_BASE: dict[str, Any] = {
    "format": 1,
    "name": {"ru": "Имя", "en": "Name"},
    "inputs": {"kind": "project", "meta.nda": "yes"},
    "versions": ["2026.1.*"],
    "assertions": [
        {"kind": "document_state", "doc": "nda", "state": "active"},
        {"kind": "document_count", "state": "active", "count": 3},
        {"kind": "meta_visible", "field": "year", "visible": True},
        {"kind": "participant_present", "persona": "supervisor", "present": False},
        {"kind": "item_active", "point": "final", "doc": "nda", "active": True},
        {"kind": "route_steps", "point": "final", "steps": [["author"], ["supervisor"]]},
        {"kind": "route_pair", "point": "final", "doc": "nda", "slot": "author", "persona": "author", "present": True},
    ],
    "snapshot": {
        "documents": {"nda": "active"},
        "participants": ["author"],
        "meta_visible": ["year"],
        "points": [{"id": "final", "items": ["nda"], "steps": [["author"]], "pairs": 1}],
        "sections": [{"section": "documents", "fingerprint": "ab12cd34ef56", "count": 1}],
    },
}


def _schema_ok(data: Any) -> bool:
    return not pack_schemas.validate("scenario", data)


def _parser_ok(data: Any) -> bool:
    try:
        parse_scenario(yaml.safe_dump(data, allow_unicode=True))
    except ScenarioError:
        return False
    return True


def _mutate(path: list[str | int], value: Any) -> dict[str, Any]:
    data = copy.deepcopy(_BASE)
    node: Any = data
    for part in path[:-1]:
        node = node[part]
    if value is _DELETE:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return data


_DELETE = object()

_BAD: list[tuple[str, dict[str, Any]]] = [
    ("format 2", _mutate(["format"], 2)),
    ("no name", _mutate(["name"], _DELETE)),
    ("empty name", _mutate(["name"], {})),
    ("name language", _mutate(["name"], {"Russian": "x"})),
    ("empty text", _mutate(["name", "ru"], "")),
    ("unknown key", {**_BASE, "extra": 1}),
    ("version as number", _mutate(["versions"], [2026.1])),
    ("version with a space", _mutate(["versions"], ["2026 1"])),
    ("input as list", _mutate(["inputs", "kind"], ["project"])),
    ("empty input", _mutate(["inputs", "kind"], "")),
    ("unknown assertion", _mutate(["assertions", 0, "kind"], "document_is_nice")),
    ("assertion without doc", _mutate(["assertions", 0, "doc"], _DELETE)),
    ("assertion state", _mutate(["assertions", 0, "state"], "gone")),
    ("assertion unknown key", _mutate(["assertions", 0, "why"], "x")),
    ("count as text", _mutate(["assertions", 1, "count"], "3")),
    ("visible as text", _mutate(["assertions", 2, "visible"], "yes")),
    ("steps flat", _mutate(["assertions", 5, "steps"], ["author"])),
    ("fingerprint as number", _mutate(["snapshot", "sections", 0, "fingerprint"], 123456789012)),
    ("section name", _mutate(["snapshot", "sections", 0, "section"], "people")),
    ("snapshot unknown key", _mutate(["snapshot", "extra"], 1)),
    ("point without pairs", _mutate(["snapshot", "points", 0, "pairs"], _DELETE)),
    ("document state", _mutate(["snapshot", "documents", "nda"], "maybe")),
]


@pytest.mark.parametrize("path", _FILES, ids=lambda p: f"{p.parents[3].name}/{p.parents[1].name}/{p.stem}")
def test__real_scenarios__pass_the_schema(path: Path) -> None:
    assert pack_schemas.validate("scenario", yaml.safe_load(path.read_text(encoding="utf-8"))) == []


def test__base_scenario__passes_the_schema_and_the_parser() -> None:
    assert _schema_ok(_BASE)
    assert _parser_ok(_BASE)


@pytest.mark.parametrize(("name", "data"), _BAD, ids=[name for name, _ in _BAD])
def test__defects__fail_the_schema_and_the_parser_alike(name: str, data: dict[str, Any]) -> None:
    assert not _schema_ok(data), name
    assert not _parser_ok(data), name


def test__optional_parts__may_be_absent() -> None:
    for key in ("description", "example", "inputs", "versions", "assertions", "snapshot"):
        data = {k: v for k, v in _BASE.items() if k != key}
        assert _schema_ok(data), key
        assert _parser_ok(data), key


def test__bare_yes_in_inputs__is_accepted_as_the_parser_accepts_it() -> None:
    data = _mutate(["inputs", "meta.nda"], True)

    assert _schema_ok(data)
    assert _parser_ok(data)


def test__schema_for__finds_scenario_files_and_leaves_checks_alone() -> None:
    assert pack_schemas.schema_for(Path("p/templates/t/scenarios/a.yaml")) == "scenario"
    assert pack_schemas.schema_for(Path("p/templates/t/versions/1/checks/a.yaml")) is None


@pytest.mark.parametrize(
    ("extra", "ok"),
    [
        ({"optional": True}, True),
        ({"optional": False}, True),
        ({"optional": "yes"}, False),
        ({"present": False, "optional": True}, False),
    ],
)
def test__route_pair_optional__schema_and_parser_agree(extra: dict[str, Any], ok: bool) -> None:
    data = copy.deepcopy(_BASE)
    pair = next(a for a in data["assertions"] if a["kind"] == "route_pair")
    pair.update(extra)

    assert (_schema_ok(data), _parser_ok(data)) == (ok, ok)
