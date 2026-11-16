"""Формат сценария (`core/pack_studio/outcome/scenarios.py`): разбор, ошибки, канонический YAML, шаблоны версий и
соответствие строгой модели контракта на эталонах."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.schemas.pack_studio_outcome import PackScenario
from hse_doc_studio.core.pack_studio.outcome.model import Digest, DigestPoint, SectionPrint
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.outcome.scenarios import (
    DocumentCountAssertion,
    DocumentStateAssertion,
    ItemActiveAssertion,
    MetaVisibleAssertion,
    ParticipantAssertion,
    RoutePairAssertion,
    RouteStepsAssertion,
    Scenario,
    ScenarioError,
    check_scenario_id,
    is_scenario_id,
    parse_scenario,
    scenario_file_name,
    scenario_from_data,
    scenario_id_of,
    scenario_text,
    version_matches,
)

_FIXTURES = Path(__file__).resolve().parents[7] / "contracts" / "pack-studio" / "fixtures"
_SCENARIO_FIXTURES = sorted((_FIXTURES / "PackScenario").glob("*.json"))

# Файл в том виде, в каком его пишет автор: логические значения без кавычек, лишние пробелы и комментарии.
HAND_WRITTEN = """\
# Научрук из компании
format: 1
name:
  ru: Научрук из компании
  en: Company supervisor
example: auto:normal
versions: ["2026.1.*"]
inputs:
  supervisor: company
  co_supervisor: yes        # голое yes парсер понимает
assertions:
  - { kind: route_steps, point: topic-approval, steps: [[author], [supervisor, co_supervisor]] }
  - { kind: participant_present, persona: co_supervisor, present: true }
"""


def _digest() -> Digest:
    return Digest(
        documents={"report": "active", "nda": "inactive", "annex": "absent"},
        participants=("author", "supervisor"),
        meta_visible=("year", "name_ru"),
        points=(
            DigestPoint("final", ("report",), (("author",), ("supervisor", "co_supervisor")), 3),
            DigestPoint("empty", (), (), 0),
        ),
        sections=(SectionPrint("documents", "94a80e445490", 1), SectionPrint("meta", "123456789012", 2)),
    )


ALL_KINDS = (
    DocumentStateAssertion(doc="report", state="active"),
    DocumentCountAssertion(state="active", count=4),
    MetaVisibleAssertion(field="manuals", visible=False),
    ParticipantAssertion(persona="co_supervisor", present=True),
    ItemActiveAssertion(point="final", doc="nda", active=False),
    RouteStepsAssertion(point="final", steps=(("author",), ("supervisor", "co_supervisor"))),
    RoutePairAssertion(point="final", doc="report", slot="supervisor", persona="supervisor", present=True),
)


# ── разбор ───────────────────────────────────────────────────────────────────


def test__parse__hand_written_file__bare_yes_becomes_the_string_yes() -> None:
    scenario = parse_scenario(HAND_WRITTEN)

    assert scenario.inputs == {"supervisor": "company", "co_supervisor": "yes"}
    assert scenario.name == {"ru": "Научрук из компании", "en": "Company supervisor"}
    assert scenario.example == "auto:normal"
    assert scenario.versions == ("2026.1.*",)
    assert scenario.snapshot is None
    assert [a.kind for a in scenario.assertions] == ["route_steps", "participant_present"]
    assert scenario.has_expectation


def test__parse__minimal_file__every_optional_part_is_empty() -> None:
    scenario = parse_scenario("format: 1\nname: { ru: Минимум }\n")

    assert (scenario.inputs, scenario.versions, scenario.assertions, scenario.snapshot) == ({}, (), (), None)
    assert (scenario.description, scenario.example) == ({}, None)
    assert not scenario.has_expectation


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "the file must be a mapping"),
        ("- a\n- b\n", "the file must be a mapping"),
        ("name: [unclosed\n", "yaml: not a valid YAML document"),
        ("name: { ru: A }\n", "format: only 1 is supported"),
        ("format: 2\nname: { ru: A }\n", "format: only 1 is supported"),
        ("format: true\nname: { ru: A }\n", "format: only 1 is supported"),
        ("format: 1\n", "name: a mapping of language to text is required"),
        ("format: 1\nname: {}\n", "name: a mapping of language to text is required"),
        ("format: 1\nname: { RU: A }\n", "name: language key"),
        ("format: 1\nname: { ru: '' }\n", "name.ru: a non-empty string is expected"),
        ("format: 1\nname: { ru: A }\nextra: 1\n", "extra: unknown key"),
        ("format: 1\nname: { ru: A }\ninputs: [a]\n", "inputs: a mapping of input to value is expected"),
        ("format: 1\nname: { ru: A }\ninputs: { a: 1 }\n", "inputs.a: a non-empty string is expected"),
        ("format: 1\nname: { ru: A }\nversions: [2026.1]\n", "versions[0]: a quoted pattern"),
        ("format: 1\nname: { ru: A }\nversions: ['a b']\n", "versions[0]: a quoted pattern"),
        ("format: 1\nname: { ru: A }\nassertions: [1]\n", "assertions[0]: a mapping with kind is expected"),
        (
            "format: 1\nname: { ru: A }\nassertions: [{ kind: nope }]\n",
            "assertions[0].kind: unknown kind 'nope'",
        ),
        (
            "format: 1\nname: { ru: A }\nassertions: [{ kind: document_state, doc: report }]\n",
            "assertions[0].state: required for document_state",
        ),
        (
            "format: 1\nname: { ru: A }\nassertions: [{ kind: document_state, doc: report, state: on }]\n",
            "assertions[0].state: one of active, inactive, absent",
        ),
        (
            "format: 1\nname: { ru: A }\nassertions: [{ kind: participant_present, persona: a, present: 'yes' }]\n",
            "assertions[0].present: true or false is expected",
        ),
        (
            "format: 1\nname: { ru: A }\nassertions: [{ kind: document_count, state: active, count: -1 }]\n",
            "assertions[0].count: an integer from 0 to 1000",
        ),
        (
            "format: 1\nname: { ru: A }\nassertions: [{ kind: meta_visible, field: a, visible: true, why: 1 }]\n",
            "assertions[0].why: unknown key",
        ),
        (
            "format: 1\nname: { ru: A }\nsnapshot: { documents: { a: maybe } }\n",
            "snapshot.documents.a: one of active, inactive, absent",
        ),
        (
            "format: 1\nname: { ru: A }\nsnapshot: { sections: [{ section: nope, fingerprint: a, count: 1 }] }\n",
            "snapshot.sections[0].section: one of",
        ),
        (
            "format: 1\nname: { ru: A }\nsnapshot: { sections: [{ section: meta, fingerprint: 123456, count: 1 }] }\n",
            "quote the fingerprint",
        ),
        ("format: 1\nname: { ru: A }\nsnapshot: { points: [{ id: a }] }\n", "snapshot.points[0].items: required"),
    ],
)
def test__parse__bad_file__scenario_error_names_the_place(text: str, reason: str) -> None:
    with pytest.raises(ScenarioError) as raised:
        parse_scenario(text)

    assert reason in raised.value.reason


def test__parse__limits__too_many_inputs_assertions_and_versions_are_refused() -> None:
    many_inputs = {"inputs": {f"i{n}": "x" for n in range(65)}}
    many_assertions = {"assertions": [{"kind": "participant_present", "persona": "a", "present": True}] * 65}
    many_versions = {"versions": [f"{n}.*" for n in range(17)]}
    base: dict[str, Any] = {"format": 1, "name": {"ru": "A"}}

    for extra, reason in (
        (many_inputs, "inputs: more than 64 inputs"),
        (many_assertions, "assertions: a list of up to 64"),
        (many_versions, "versions: a list of up to 16"),
    ):
        with pytest.raises(ScenarioError) as raised:
            scenario_from_data({**base, **extra})
        assert reason in raised.value.reason


def test__parse__request_body_with_nulls__is_the_same_as_missing_keys() -> None:
    body = {
        "format": 1,
        "name": {"ru": "A"},
        "description": None,
        "example": None,
        "inputs": {},
        "versions": None,
        "snapshot": None,
        "assertions": None,
    }

    assert scenario_from_data(body) == scenario_from_data({"format": 1, "name": {"ru": "A"}})


# ── канонический YAML ────────────────────────────────────────────────────────


def test__text__hand_written_file__round_trips_through_the_canonical_form_byte_for_byte() -> None:
    first = scenario_text(parse_scenario(HAND_WRITTEN))
    second = scenario_text(parse_scenario(first))

    assert first == second
    assert parse_scenario(first) == parse_scenario(HAND_WRITTEN)
    # Лишнее убрано, порядок ключей и вид записей фиксирован.
    assert first.splitlines()[0] == "format: 1"
    assert "# " not in first
    assert '  co_supervisor: "yes"' in first
    assert "  supervisor: company" in first


def test__text__every_assertion_kind_and_a_snapshot__round_trip() -> None:
    scenario = Scenario(
        name={"ru": "Все виды", "en": "All kinds"},
        description={"ru": "Описание: с двоеточием и запятыми, (скобками)"},
        example="auto:long",
        inputs={"meta.nda": "yes", "meta.manuals": "Только программиста", "lang": "en", "staffing": "team3"},
        versions=("2026.1.*", "2027.*"),
        snapshot=_digest(),
        assertions=ALL_KINDS,
    )

    text = scenario_text(scenario)

    assert parse_scenario(text) == scenario
    assert scenario_text(parse_scenario(text)) == text
    # Хэш из одних цифр читался бы числом: он пишется в кавычках.
    assert 'fingerprint: "123456789012"' in text
    assert "fingerprint: 94a80e445490" in text


def test__text__tricky_strings__are_quoted_when_plain_would_change_the_meaning() -> None:
    scenario = Scenario(
        name={"ru": "yes", "en": "a: b #c"},
        inputs={"x": "true", "y": "null", "z": "1.5", "w": "  lead", "v": "с # решёткой", "u": "a, b]"},
    )

    assert parse_scenario(scenario_text(scenario)) == scenario


def test__text__empty_inputs_are_written_as_an_empty_mapping() -> None:
    text = scenario_text(Scenario(name={"ru": "A"}))

    assert text == "format: 1\nname:\n  ru: A\ninputs: {}\n"
    assert parse_scenario(text) == Scenario(name={"ru": "A"})


@pytest.mark.parametrize("path", _SCENARIO_FIXTURES, ids=lambda p: p.stem)
def test__contract_fixtures__model_dataclass_and_yaml_agree(path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    model = PackScenario.model_validate(raw)

    scenario = scenario_from_data(model.model_dump(mode="json"))

    # Строгая модель контракта и ядро видят один и тот же сценарий, в обе стороны и через YAML.
    assert PackScenario.model_validate(to_json(scenario)) == model
    assert parse_scenario(scenario_text(scenario)) == scenario
    assert scenario_from_data(raw) == scenario


# ── идентификатор, файл и версии ─────────────────────────────────────────────


@pytest.mark.parametrize("value", ["a", "company-supervisor", "nda-2", "0", "a-b-c", "x" * 64])
def test__id__valid(value: str) -> None:
    assert is_scenario_id(value)
    assert check_scenario_id(value) == value
    assert scenario_file_name(value) == f"{value}.yaml"


@pytest.mark.parametrize(
    "value", ["", "A", "a_b", "a b", "-a", "a-", "a--b", "a.b", "a/b", "..", "я", "x" * 65, "a\nb"]
)
def test__id__invalid(value: str) -> None:
    assert not is_scenario_id(value)
    with pytest.raises(ScenarioError, match="^id: "):
        check_scenario_id(value)


def test__id_of__file_name() -> None:
    assert scenario_id_of("company-supervisor.yaml") == "company-supervisor"
    assert scenario_id_of("Company.yaml") is None
    assert scenario_id_of("company.yml") is None
    assert scenario_id_of("README.md") is None


@pytest.mark.parametrize(
    ("patterns", "version", "expected"),
    [
        ((), "2026.1.6", True),
        (("2026.1.*",), "2026.1.6", True),
        (("2026.1.*",), "2026.1", False),
        (("2026.1.*",), "2026.10.1", False),
        (("2026.*",), "2026.1", True),
        (("2025.*", "2026.1.6"), "2026.1.6", True),
        (("2026.1.6",), "2026.1.60", False),
        (("2026.1.?",), "2026.1.6", False),  # `?` буквальный знак: шаблон знает только `*`
        (("*",), "anything", True),
    ],
)
def test__version_matches(patterns: tuple[str, ...], version: str, expected: bool) -> None:
    assert version_matches(patterns, version) is expected
