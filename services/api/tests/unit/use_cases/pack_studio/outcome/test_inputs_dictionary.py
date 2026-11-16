"""Словарь вводных версии: из схемы версии, с влиянием на разделы и числом читающих правил."""

from __future__ import annotations

from datetime import date

import pytest
from hse_doc_studio.api.schemas.pack_studio_outcome import OutcomeInput
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.inputs import input_specs
from hse_doc_studio.core.pack_studio.outcome.model import InputInfo
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.preview import PreviewExample, auto_examples
from hse_doc_studio.use_cases.pack_studio.outcome.dictionary import inputs_dictionary

from tests.unit.use_cases.pack_studio.outcome.synthetic import load_synthetic

TODAY = date(2026, 11, 16)


@pytest.fixture(scope="module")
def version(tmp_path_factory: pytest.TempPathFactory) -> TemplateVersion:
    return load_synthetic(tmp_path_factory.mktemp("packs"))


@pytest.fixture(scope="module")
def example(version: TemplateVersion) -> PreviewExample:
    return auto_examples(version)[0]


@pytest.fixture(scope="module")
def inputs(version: TemplateVersion, example: PreviewExample) -> dict[str, InputInfo]:
    return {i.id: i for i in inputs_dictionary(version, example, TODAY, revision="sha256-x").inputs}


def test__dictionary__ids_groups_and_types_come_from_the_version_schema(version: TemplateVersion) -> None:
    specs = input_specs(version)

    assert [(s.id, s.group, s.type) for s in specs] == [
        ("lang", "project", "select"),
        ("kind", "project", "select"),
        ("staffing", "project", "select"),
        ("supervisor", "people", "select"),
        ("co_supervisor", "people", "bool"),
        ("academic_supervisor", "people", "bool"),
        ("nda", "meta", "bool"),
        ("meta.manuals", "meta", "select"),
        ("meta.stage", "meta", "select"),
        ("answer.ai.used_ai", "answers", "select"),
        ("answer.ai.agree", "answers", "bool"),
        ("variant.presentation", "variants", "select"),
    ]


def test__dictionary__values_defaults_and_labels(inputs: dict[str, InputInfo]) -> None:
    assert [v.value for v in inputs["staffing"].values] == ["solo", "team2", "team3"]
    assert [v.value for v in inputs["supervisor"].values] == ["university", "company", "none"]
    assert inputs["supervisor"].default == "university"
    assert inputs["academic_supervisor"].default == "yes"
    assert inputs["meta.stage"].default == "draft"
    assert inputs["meta.manuals"].label == {"ru": "Руководства", "en": "Manuals"}
    assert inputs["lang"].label is None
    used_ai = inputs["answer.ai.used_ai"]
    assert [(v.value, v.label) for v in used_ai.values] == [
        ("no", {"ru": "Нет", "en": "No"}),
        ("yes", {"ru": "Да", "en": "Yes"}),
    ]
    assert [(v.value, v.label) for v in inputs["variant.presentation"].values] == [
        ("pptx", {"ru": "PowerPoint", "en": "PowerPoint"}),
        ("beamer", {"ru": "Beamer", "en": "Beamer"}),
    ]


def test__dictionary__a_variant_input_needs_two_variants_open_in_every_language(inputs: dict[str, InputInfo]) -> None:
    # У спецификации два варианта, но второй только для английского: выбирать автору нечего.
    assert "variant.spec" not in inputs


def test__dictionary__affects_lists_the_sections_the_input_changes(inputs: dict[str, InputInfo]) -> None:
    assert inputs["lang"].affects == ()
    assert inputs["variant.presentation"].affects == ()
    assert inputs["meta.stage"].affects == ()
    assert "documents" in inputs["kind"].affects
    assert "documents" in inputs["staffing"].affects
    assert inputs["supervisor"].affects == ("participants", "route")
    assert inputs["co_supervisor"].affects == ("participants", "route")
    # NDA включает расписку, выключает пункт `skip_if_nda` и вместе с ним его подписи в маршруте.
    assert inputs["nda"].affects == ("documents", "points", "route")
    assert inputs["answer.ai.used_ai"].affects == ("forms",)


def test__dictionary__rules_count_the_manifest_rules_that_read_the_input(inputs: dict[str, InputInfo]) -> None:
    # `supported_langs` у восьми документов; спецификации с вариантом IEEE на умолчаниях (исследовательский вид) нет.
    assert inputs["lang"].rules == 8
    # Зашитое правило руководств это одно правило на два документа.
    assert inputs["meta.manuals"].rules == 1
    assert inputs["nda"].rules == 2  # зашитое правило расписки и `skip_if_nda` пункта
    assert inputs["supervisor"].rules == 1  # `when` слота академрука читает `supervisor` и `supervisor.role`
    assert inputs["co_supervisor"].rules == 1
    assert inputs["meta.stage"].rules == 0


def test__dictionary__defaults_are_the_default_of_every_input_and_values_of_it(
    version: TemplateVersion, example: PreviewExample
) -> None:
    result = inputs_dictionary(version, example, TODAY)

    assert result.defaults == {i.id: i.default for i in result.inputs}
    assert all(i.default in {v.value for v in i.values} for i in result.inputs)


def test__dictionary__without_affects__is_cheaper_and_leaves_them_empty(
    version: TemplateVersion, example: PreviewExample
) -> None:
    result = inputs_dictionary(version, example, TODAY, with_affects=False)

    assert all(i.affects == () for i in result.inputs)
    assert next(i for i in result.inputs if i.id == "kind").rules > 0


def test__dictionary__is_accepted_by_the_strict_contract_model(inputs: dict[str, InputInfo]) -> None:
    for info in inputs.values():
        OutcomeInput.model_validate(to_json(info))


def test__dictionary__example_defaults_move_the_defaults(version: TemplateVersion) -> None:
    from hse_doc_studio.core.pack_studio.preview import ExampleData

    custom = PreviewExample("e", "file", None, ExampleData(defaults={"kind": "project", "staffing": "team2"}))

    result = inputs_dictionary(version, custom, TODAY, with_affects=False)

    assert (result.defaults["kind"], result.defaults["staffing"]) == ("project", "team2")
