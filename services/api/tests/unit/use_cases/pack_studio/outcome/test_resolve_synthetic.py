"""Вычислители разделов результата на синтетической версии (`synthetic.py`): по правилу закрытого языка ровно там,
где его нужно проверить. Реальные паки проверяет `test_resolve_real_packs.py`."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

import pytest
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.model import DocumentOutcome, Outcome, PointOutcome
from hse_doc_studio.core.pack_studio.outcome.people import steps_without_person
from hse_doc_studio.core.pack_studio.preview import PreviewExample, auto_examples
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import OutcomeInputError, resolve

from tests.unit.use_cases.pack_studio.outcome.invariants import assert_contract
from tests.unit.use_cases.pack_studio.outcome.synthetic import load_synthetic

TODAY = date(2026, 11, 16)
PROJECT = {"kind": "project"}


@pytest.fixture(scope="module")
def version(tmp_path_factory: pytest.TempPathFactory) -> TemplateVersion:
    return load_synthetic(tmp_path_factory.mktemp("packs"))


@pytest.fixture(scope="module")
def example(version: TemplateVersion) -> PreviewExample:
    return auto_examples(version)[0]


@pytest.fixture
def run(version: TemplateVersion, example: PreviewExample) -> Any:
    def _run(inputs: Mapping[str, str] | None = None, **kwargs: Any) -> Outcome:
        return resolve(version, inputs or {}, example, TODAY, **kwargs)

    return _run


def _doc(outcome: Outcome, doc_id: str) -> DocumentOutcome:
    return next(d for d in outcome.documents if d.id == doc_id)


def _point(outcome: Outcome, point_id: str) -> PointOutcome:
    return next(p for p in outcome.points if p.id == point_id)


def _states(outcome: Outcome) -> dict[str, str]:
    return {d.id: d.state for d in outcome.documents}


def _trace(outcome: Outcome, decision_id: str) -> Any:
    return next(t for t in outcome.trace if t.id == decision_id)


# ── Вводные ──────────────────────────────────────────────────────────────────


def test__inputs__defaults_come_from_the_version(run: Any) -> None:
    outcome = run()

    assert outcome.inputs == {
        "lang": "ru",
        "kind": "research",
        "staffing": "solo",
        "supervisor": "university",
        "co_supervisor": "no",
        "academic_supervisor": "yes",
        "nda": "no",
        "meta.manuals": "Программиста и оператора",
        "meta.stage": "draft",
        "answer.ai.used_ai": "no",
        "answer.ai.agree": "no",
        "variant.presentation": "pptx",
    }
    assert outcome.example == "auto:normal"
    assert outcome.out_of_scope == ("python_checks", "signature_anchors", "tex_content", "jinja_content")


@pytest.mark.parametrize(
    ("inputs", "field", "reason"),
    [
        ({"bogus": "x"}, "bogus", "unknown switch"),
        ({"lang": "de"}, "lang", "value not allowed"),
        ({"variant.spec": "ieee"}, "variant.spec", "unknown switch"),
    ],
)
def test__inputs__unknown_input_or_value__is_an_input_error(
    run: Any, inputs: dict[str, str], field: str, reason: str
) -> None:
    with pytest.raises(OutcomeInputError) as caught:
        run(inputs)

    assert (caught.value.field, caught.value.reason) == (field, reason)


def test__inputs__example_defaults_sit_between_the_version_and_the_request(version: TemplateVersion) -> None:
    from hse_doc_studio.core.pack_studio.preview import ExampleData

    custom = PreviewExample("example", "file", None, ExampleData(defaults={"kind": "project", "lang": "en"}))

    plain = resolve(version, {}, custom, TODAY)
    overridden = resolve(version, {"lang": "ru"}, custom, TODAY)

    assert (plain.inputs["kind"], plain.inputs["lang"]) == ("project", "en")
    assert overridden.inputs["lang"] == "ru"


# ── Документы ────────────────────────────────────────────────────────────────


def test__documents__project_kind_solo__gates_and_builtin_rules(run: Any) -> None:
    outcome = run(PROJECT)

    assert _states(outcome) == {
        "report": "active",
        "spec": "active",
        "shared_spec": "absent",
        "summary": "absent",
        "programmer_manual": "active",
        "operator_manual": "active",
        "nda": "inactive",
        "presentation": "active",
    }


def test__documents__research_kind__project_only_documents_are_absent(run: Any) -> None:
    states = _states(run({"kind": "research"}))

    assert states["summary"] == "active"
    assert {states[d] for d in ("spec", "programmer_manual", "operator_manual")} == {"absent"}


def test__documents__manuals_selection__switches_a_manual_to_inactive(run: Any) -> None:
    outcome = run({**PROJECT, "meta.manuals": "Только программиста"})

    assert _doc(outcome, "programmer_manual").state == "active"
    assert _doc(outcome, "operator_manual").state == "inactive"
    # Выключенный документ остаётся в проекте: у него есть экземпляр и исходник.
    assert _doc(outcome, "operator_manual").instances
    assert _doc(outcome, "operator_manual").source_file == "om/om.tex"


def test__documents__nda__turns_the_undertaking_on(run: Any) -> None:
    assert _doc(run(PROJECT), "nda").state == "inactive"
    assert _doc(run({**PROJECT, "nda": "yes"}), "nda").state == "active"


def test__documents__team_staffing__personal_documents_per_author_and_shared_ones(run: Any) -> None:
    outcome = run({**PROJECT, "staffing": "team2"})

    report = _doc(outcome, "report")
    assert [(i.id, i.owner, i.owner_name) for i in report.instances] == [
        ("report--author1", "author1", "Иванов Иван Иванович"),
        ("report--author2", "author2", "Петрова Мария Сергеевна"),
    ]
    assert [i.file_name for i in report.instances] == ["Отчёт — Иванов.pdf", "Отчёт — Петрова.pdf"]
    shared = _doc(outcome, "shared_spec")
    assert shared.state == "active"
    assert shared.scope == "shared"
    assert [(i.id, i.owner) for i in shared.instances] == [("shared_spec", None)]
    assert _doc(run(PROJECT), "report").instances[0].owner is None


def test__documents__language__changes_file_names_and_language_state_only(run: Any) -> None:
    ru, en = run(PROJECT), run({**PROJECT, "lang": "en"})

    assert _doc(ru, "report").instances[0].file_name == "Отчёт.pdf"
    assert _doc(en, "report").instances[0].file_name == "Report.pdf"
    # NDA написана только по-русски: при английском проекте берётся русская редакция.
    assert (_doc(ru, "nda").lang_state, _doc(en, "nda").lang_state) == ("native", "fallback")
    assert _doc(en, "nda").languages == ("ru",)
    assert _states(ru) == _states(en)
    assert ru.fingerprint == en.fingerprint


def test__documents__variants__language_gates_availability_and_the_input_picks_one(run: Any) -> None:
    ru, en = _doc(run(PROJECT), "spec"), _doc(run({**PROJECT, "lang": "en"}), "spec")

    assert [(v.id, v.available, v.chosen) for v in ru.variants] == [("espd", True, True), ("ieee", False, False)]
    assert [(v.id, v.available, v.chosen) for v in en.variants] == [("espd", True, True), ("ieee", True, False)]
    assert ru.variants[1].langs == ("en",)
    assert ru.variants[1].why
    assert ru.source_file == "spec/spec.tex"

    beamer = _doc(run({**PROJECT, "variant.presentation": "beamer"}), "presentation")
    assert [v.id for v in beamer.variants if v.chosen] == ["beamer"]
    assert beamer.source_file == "pres/pres.tex"
    assert beamer.instances[0].file_name == "Презентация.pdf"
    assert _doc(run(PROJECT), "presentation").instances[0].file_name == "Презентация.pptx"


def test__documents__absent_document__has_no_instances_variants_or_source(run: Any) -> None:
    summary = _doc(run(PROJECT), "summary")

    assert (summary.instances, summary.variants, summary.source_file) == ((), (), None)
    assert summary.manifest == "files/summary/doc.yaml"


def test__documents__trace__skips_staffing_when_the_kind_already_excluded_the_document(run: Any) -> None:
    outcome = run(PROJECT)

    summary = _doc(outcome, "summary")
    statuses = {_trace(outcome, i).kind: _trace(outcome, i).status for i in summary.why}
    assert statuses == {"supported_kinds": "not_held", "supported_staffing": "skipped", "supported_langs": "held"}
    kinds = _trace(outcome, summary.why[0])
    assert (kinds.rule.file, kinds.rule.pointer) == ("files/summary/doc.yaml", "/supported_kinds")
    assert kinds.terms[0].expected == ("research",)
    assert kinds.actual == {"kind": "project"}


def test__documents__builtin_rules__are_traced_as_builtin_gates(run: Any) -> None:
    outcome = run({**PROJECT, "meta.manuals": "Только программиста", "nda": "yes"})

    manual = _trace(outcome, _doc(outcome, "operator_manual").why[2])
    assert (manual.rule.origin, manual.rule.builtin, manual.kind, manual.status) == (
        "builtin",
        "manuals_gate",
        "builtin_gate",
        "not_held",
    )
    assert (manual.terms[0].op, manual.terms[0].expected, manual.actual) == (
        "contains_any",
        ("оператора",),
        {"meta.manuals": "Только программиста"},
    )
    nda = _trace(outcome, _doc(outcome, "nda").why[2])
    assert (nda.rule.builtin, nda.terms[0].op, nda.terms[0].subject, nda.actual, nda.status) == (
        "nda_gate",
        "truthy",
        "nda",
        {"nda": "yes"},
        "held",
    )


# ── Метаданные и анкеты ──────────────────────────────────────────────────────


def test__meta__fields_keep_visibility_required_at_and_example_values(run: Any) -> None:
    project, research = {m.id: m for m in run(PROJECT).meta}, {m.id: m for m in run({"kind": "research"}).meta}

    assert project["manuals"].visible
    assert not research["manuals"].visible
    assert project["manuals"].why
    assert research["manuals"].why
    assert (project["topic"].required_at, project["topic"].value) == ("create", "Тема работы")
    assert (project["code"].required_at, project["code"].value) == ("finalize", "09.04.04")
    assert project["supervisor"].type == "person"
    assert project["supervisor"].value is None
    assert project["stage"].options == ("draft", "final")
    assert (project["nda"].type, project["nda"].value) == ("bool", "no")


def test__meta__kind_restricted_field__traces_the_manifest_rule(run: Any) -> None:
    outcome = run({"kind": "research"})
    manuals = next(m for m in outcome.meta if m.id == "manuals")

    decision = _trace(outcome, manuals.why[0])

    assert (decision.rule.file, decision.rule.pointer) == ("version.yaml", "/meta_fields/manuals/supported_kinds")
    assert (decision.kind, decision.effect, decision.status) == ("field_kinds", "display", "not_held")
    assert [s.id for s in decision.subjects] == ["manuals"]
    # Поле без ограничения по виду работы в трассу не попадает.
    assert next(m for m in outcome.meta if m.id == "topic").why == ()


def test__forms__visible_if_follows_the_answers(run: Any) -> None:
    no = next(f for f in run(PROJECT).forms if f.id == "ai")
    yes = next(f for f in run({**PROJECT, "answer.ai.used_ai": "yes", "answer.ai.agree": "yes"}).forms if f.id == "ai")

    by_no, by_yes = {f.id: f for f in no.fields}, {f.id: f for f in yes.fields}
    assert (by_no["tools"].visible, by_yes["tools"].visible) == (False, True)
    assert (by_no["note"].visible, by_yes["note"].visible) == (False, True)
    # Обязательность считается в этой комбинации: скрытое поле и поясняющий текст ответа не требуют.
    assert (by_no["tools"].required, by_yes["tools"].required) == (False, True)
    assert by_no["used_ai"].required
    assert by_no["agree"].required
    assert not by_yes["clauses"].required
    assert by_no["tools"].why
    assert not by_no["used_ai"].why


def test__forms__visible_if_trace__reads_the_answer_input(run: Any) -> None:
    outcome = run(PROJECT)
    tools = next(f for f in next(f for f in outcome.forms if f.id == "ai").fields if f.id == "tools")

    decision = _trace(outcome, tools.why[0])

    assert (decision.rule.pointer, decision.kind, decision.status) == (
        "/forms/0/sections/0/fields/1/visible_if",
        "visible_if",
        "not_held",
    )
    assert (decision.terms[0].op, decision.terms[0].subject, decision.terms[0].expected) == (
        "equals",
        "answer.ai.used_ai",
        ("yes",),
    )
    assert decision.actual == {"answer.ai.used_ai": "no"}
    # Условие на bool-поле сравнивается с булевым ответом, в трассе это `yes`.
    note = next(f for f in next(f for f in outcome.forms if f.id == "ai").fields if f.id == "note")
    assert _trace(outcome, note.why[0]).terms[0].expected == ("yes",)


def test__forms__kind_restricted_form__does_not_apply_and_its_fields_are_hidden(run: Any) -> None:
    project, research = run(PROJECT), run({"kind": "research"})

    repo_project = next(f for f in project.forms if f.id == "repo")
    repo_research = next(f for f in research.forms if f.id == "repo")
    assert (repo_project.applies, repo_research.applies) == (False, True)
    assert not repo_project.fields[0].visible
    assert repo_research.fields[0].visible
    assert repo_research.fields[0].required
    assert _trace(project, repo_project.why[0]).status == "not_held"


# ── Участники ────────────────────────────────────────────────────────────────


def test__participants__solo__one_author_and_three_supervisor_slots(run: Any) -> None:
    people = {p.persona: p for p in run({"co_supervisor": "no"}).participants}

    assert list(people) == ["author", "supervisor", "co_supervisor", "academic_supervisor"]
    assert people["author"].present
    assert people["author"].org is None
    assert (people["supervisor"].present, people["supervisor"].org, people["supervisor"].name) == (
        True,
        "university",
        "Петров Пётр Петрович",
    )
    assert (people["co_supervisor"].present, people["co_supervisor"].name, people["co_supervisor"].org) == (
        False,
        "",
        None,
    )


def test__participants__team_authors_are_numbered_and_company_supervisor_has_an_org(run: Any) -> None:
    people = run({"staffing": "team3", "supervisor": "company", "academic_supervisor": "no"}).participants

    assert [p.persona for p in people[:3]] == ["author1", "author2", "author3"]
    assert next(p for p in people if p.persona == "supervisor").org == "company"
    assert not next(p for p in people if p.persona == "academic_supervisor").present


# ── Точки сдачи ──────────────────────────────────────────────────────────────


def _items(point: PointOutcome) -> dict[str, tuple[bool, str | None]]:
    return {i.doc_id: (i.active, i.off_reason) for i in point.items}


def test__points__items_carry_the_reason_they_are_off(run: Any) -> None:
    project = _point(run(PROJECT), "topic")
    nda = _point(run({**PROJECT, "nda": "yes"}), "topic")
    research = _point(run({"kind": "research"}), "topic")
    programmer_only = _point(run({**PROJECT, "meta.manuals": "Только программиста"}), "topic")

    assert _items(project) == {
        "report": (True, None),
        "spec": (True, None),
        "summary": (False, "kind"),
        "operator_manual": (True, None),
    }
    assert _items(nda)["spec"] == (False, "nda")
    assert _items(research)["spec"] == (False, "absent")
    assert _items(research)["summary"] == (True, None)
    assert _items(programmer_only)["operator_manual"] == (False, "inactive")


def test__points__item_trace__rules_and_document_reasons(run: Any) -> None:
    outcome = run({**PROJECT, "nda": "yes", "meta.manuals": "Только программиста"})
    topic = _point(outcome, "topic")
    items = {i.doc_id: i for i in topic.items}

    skip = _trace(outcome, items["spec"].why[0])
    assert (skip.kind, skip.effect, skip.status, skip.actual) == ("skip_if_nda", "exclude", "held", {"nda": "yes"})
    assert skip.rule.pointer == "/pack_submission/profiles/0/items/1/skip_if_nda"
    kinds = _trace(outcome, items["summary"].why[0])
    assert (kinds.kind, kinds.status, kinds.rule.pointer) == (
        "item_kinds",
        "not_held",
        "/pack_submission/profiles/0/items/2/supported_kinds",
    )
    # Пункт выключенного документа ссылается на решения самого документа до первого невыполненного.
    chain = [_trace(outcome, i) for i in items["operator_manual"].why]
    assert [t.status for t in chain] == ["held", "held", "not_held"]
    assert chain[-1].rule.builtin == "manuals_gate"
    assert items["report"].why == ()


def test__points__extra_items_follow_the_kind(run: Any) -> None:
    project, research = _point(run(PROJECT), "topic"), _point(run({"kind": "research"}), "topic")

    assert [(e.source, e.active, e.off_reason) for e in project.extra_items] == [
        (".hse-studio/forms/repo.json", False, "kind")
    ]
    assert research.extra_items[0].active
    assert research.extra_items[0].off_reason is None
    assert (project.deadline_hint, research.name) == (
        {"ru": "В ноябре", "en": "In November"},
        {"ru": "Тема", "en": "Topic"},
    )
    assert _point(run(PROJECT), "final").deadline_hint is None


# ── Маршрут ──────────────────────────────────────────────────────────────────


def _steps(point: PointOutcome) -> list[list[str]]:
    return [[p.persona for p in step] for step in point.route.steps]


def test__route__company_supervisor_with_a_co_supervisor__preset_adds_both_slots(run: Any) -> None:
    topic = _point(run({**PROJECT, "supervisor": "company", "co_supervisor": "yes"}), "topic")

    assert _steps(topic) == [["author"], ["supervisor", "co_supervisor"], ["academic_supervisor"]]
    assert [(p.doc_id, p.slot_id, p.persona, p.source, p.optional) for p in topic.route.pairs] == [
        ("report", "author", "author", "point", False),
        ("report", "supervisor", "supervisor", "point", False),
        ("spec", "supervisor", "supervisor", "point", False),
        ("report", "co_supervisor", "co_supervisor", "preset", False),
        ("report", "academic_supervisor", "academic_supervisor", "preset", True),
    ]
    assert (topic.route.order_source, topic.route.preset, topic.route.skipped) == ("profile", True, ())
    academic = topic.route.pairs[-1]
    assert (academic.when.person, academic.when.role) == ("supervisor", "company")  # type: ignore[union-attr]


def test__route__university_supervisor_without_a_co_supervisor__slots_are_skipped_by_the_condition(run: Any) -> None:
    outcome = run(PROJECT)
    topic = _point(outcome, "topic")

    assert _steps(topic) == [["author"], ["supervisor"]]
    assert [(s.doc_id, s.slot_id) for s in topic.route.skipped] == [
        ("report", "co_supervisor"),
        ("report", "academic_supervisor"),
    ]
    skipped = _trace(outcome, topic.route.skipped[1].why[0])
    assert (skipped.kind, skipped.effect, skipped.status) == ("slot_when", "add", "not_held")
    assert [(t.op, t.subject, t.expected) for t in skipped.terms] == [
        ("present", "supervisor", ()),
        ("equals", "supervisor.role", ("company",)),
    ]
    assert skipped.actual == {"supervisor": "yes", "supervisor.role": "university"}
    assert skipped.rule.pointer == "/pack_submission/profiles/0/signing_slots/1/when"


def test__route__slot_condition_and_optional_mark_are_traced_on_the_pair(run: Any) -> None:
    outcome = run({**PROJECT, "supervisor": "company", "co_supervisor": "yes"})
    pairs = {p.slot_id: p for p in _point(outcome, "topic").route.pairs if p.source == "preset"}

    co = _trace(outcome, pairs["co_supervisor"].why[0])
    assert (co.status, co.actual, co.terms[0].op) == ("held", {"co_supervisor": "yes"}, "present")
    academic = [_trace(outcome, i) for i in pairs["academic_supervisor"].why]
    assert [t.kind for t in academic] == ["slot_when", "slot_optional"]
    assert academic[1].rule.pointer == "/pack_submission/profiles/0/signing_slots/1/optional"
    assert academic[1].effect == "require"


def test__route__order_comes_from_the_profile_or_falls_back_to_the_builtin_order(run: Any) -> None:
    outcome = run(PROJECT)
    topic, final = _point(outcome, "topic"), _point(outcome, "final")

    order = _trace(outcome, topic.route.why[0])
    assert (order.kind, order.effect, order.rule.pointer, order.terms) == (
        "route_order",
        "order",
        "/pack_submission/profiles/0/signing_route",
        (),
    )
    assert (final.route.order_source, final.route.preset) == ("builtin", False)
    builtin = _trace(outcome, final.route.why[0])
    assert (builtin.rule.origin, builtin.rule.builtin) == ("builtin", "builtin_route")
    assert _steps(final) == [["author"]]
    assert [(d.doc_id, d.slot_id) for d in final.route.may_add] == [
        ("report", "supervisor"),
        ("report", "co_supervisor"),
        ("report", "academic_supervisor"),
    ]


def test__route__team__author_personas_are_numbered_in_steps_and_pairs(run: Any) -> None:
    final = _point(run({**PROJECT, "staffing": "team2"}), "final")

    assert _steps(final) == [["author1", "author2"]]
    assert {p.persona for p in final.route.pairs} == {"author1", "author2"}
    assert {p.slot_id for p in final.route.pairs} == {"author"}


def test__route__no_supervisor__step_stays_with_an_empty_name_and_the_helper_reports_it(run: Any) -> None:
    outcome = run({**PROJECT, "supervisor": "none"})
    topic = _point(outcome, "topic")

    assert _steps(topic) == [["author"], ["supervisor"]]
    assert topic.route.steps[1][0].name == ""
    assert steps_without_person(topic.route.steps, outcome.participants) == ((2, "supervisor"),)
    assert steps_without_person(_point(run(PROJECT), "topic").route.steps, run(PROJECT).participants) == ()


# ── Проверки ─────────────────────────────────────────────────────────────────


def test__checks__are_only_computed_on_request(run: Any) -> None:
    assert run(PROJECT).checks is None
    assert run(PROJECT, include={"checks"}).checks is not None


def test__checks__applicability_and_reasons_for_being_off(run: Any) -> None:
    outcome = run(PROJECT, include={"checks"})
    rules = {c.id: c for c in outcome.checks or ()}

    assert (rules["fmt/margins"].enabled, rules["fmt/margins"].applies_to, rules["fmt/margins"].off_reason) == (
        True,
        ("report",),
        None,
    )
    assert (rules["fmt/off"].enabled, rules["fmt/off"].off_reason) == (False, "disabled")
    assert (rules["sty/tone"].enabled, rules["sty/tone"].off_reason) == (False, "category_disabled")
    assert rules["sty/tone"].applies_to == tuple(d.id for d in outcome.documents if d.state == "active")
    assert rules["spec/sections"].enabled
    assert (rules["sum/short"].enabled, rules["sum/short"].off_reason, rules["sum/short"].applies_to) == (
        False,
        "no_active_document",
        (),
    )
    assert (rules["fmt/margins"].severity, rules["fmt/margins"].engine) == ("warn", "structural")
    off = _trace(outcome, rules["fmt/off"].why[0])
    assert (off.kind, off.rule.pointer) == ("check_disabled", "/checks_version/disabled")
    assert _trace(outcome, rules["sty/tone"].why[0]).rule.pointer == "/checks_version/disabled_categories"


def test__checks__do_not_change_the_fingerprint_or_the_digest(run: Any) -> None:
    plain, with_checks = run(PROJECT), run(PROJECT, include={"checks"})

    assert plain.fingerprint == with_checks.fingerprint
    assert plain.digest == with_checks.digest


# ── Отпечаток, трасса и детерминизм ──────────────────────────────────────────


def test__fingerprint__structure_changes_it_cosmetics_do_not(run: Any) -> None:
    base = run(PROJECT)

    assert run({**PROJECT, "lang": "en"}).fingerprint == base.fingerprint
    assert run({**PROJECT, "variant.presentation": "beamer"}).fingerprint == base.fingerprint
    assert run({**PROJECT, "supervisor": "company"}).fingerprint != base.fingerprint
    assert run({**PROJECT, "nda": "yes"}).fingerprint != base.fingerprint
    assert run({"kind": "research"}).fingerprint != base.fingerprint


def test__resolve__today_is_an_input__auto_fields_follow_it(version: TemplateVersion, example: PreviewExample) -> None:
    def year(day: date) -> str | None:
        outcome = resolve(version, {}, example, day, trace=False)
        return next(m.value for m in outcome.meta if m.id == "year")

    # Академический год: с сентября по декабрь это следующий календарный год.
    assert year(date(2026, 11, 16)) == "2027"
    assert year(date(2027, 2, 1)) == "2027"
    assert year(date(2027, 11, 16)) == "2028"


def test__resolve__is_deterministic_for_the_same_call(run: Any) -> None:
    assert run(PROJECT, include={"checks", "branches"}) == run(PROJECT, include={"checks", "branches"})


def test__resolve__without_trace__same_structure_empty_explanations(run: Any) -> None:
    traced, plain = run(PROJECT), run(PROJECT, trace=False)

    assert plain.trace == ()
    assert plain.fingerprint == traced.fingerprint
    assert plain.digest == traced.digest
    assert all(d.why == () for d in plain.documents)
    assert [d.state for d in plain.documents] == [d.state for d in traced.documents]


def test__resolve__result_is_accepted_by_the_strict_contract_models(run: Any) -> None:
    for inputs in (
        {},
        PROJECT,
        {**PROJECT, "staffing": "team3", "supervisor": "company", "co_supervisor": "yes", "nda": "yes"},
        {"kind": "research", "lang": "en", "answer.ai.used_ai": "yes"},
    ):
        assert_contract(run(inputs, include={"checks", "branches"}))


# ── Ветки ────────────────────────────────────────────────────────────────────


def test__branches__list_only_inputs_that_change_the_result_with_deltas_against_the_current_value(run: Any) -> None:
    outcome = run({**PROJECT, "supervisor": "company", "co_supervisor": "yes"}, include={"branches"})
    branches = {b.input: b for b in outcome.branches or ()}

    # Язык и вариант презентации результат не меняют (косметика): веток нет.
    assert "lang" not in branches
    assert "variant.presentation" not in branches
    supervisor = branches["supervisor"]
    assert supervisor.chosen == "company"
    assert set(supervisor.affects) <= {"participants", "route"}
    current = next(a for a in supervisor.alternatives if a.value == "company")
    assert (current.delta, current.fingerprint) == ((), outcome.fingerprint)
    university = next(a for a in supervisor.alternatives if a.value == "university")
    assert university.delta
    assert university.fingerprint != outcome.fingerprint
    assert [a.value for a in supervisor.alternatives] == ["university", "company", "none"]
    # Варианты ответа анкеты подписаны текстом пака.
    answer = branches["answer.ai.used_ai"]
    assert answer.affects == ("forms",)
    assert next(a for a in answer.alternatives if a.value == "yes").label == {"ru": "Да", "en": "Yes"}


def test__branches__kind_branch_counts_added_changed_and_removed_elements(run: Any) -> None:
    outcome = run(PROJECT, include={"branches"})
    kind = next(b for b in outcome.branches or () if b.input == "kind")
    research = next(a for a in kind.alternatives if a.value == "research")

    sections = {d.section: d for d in research.delta}
    assert set(kind.affects) >= {"documents", "points"}
    assert sections["documents"].changed >= 1
    assert sections["meta"].changed >= 1


def test__branches__are_not_computed_unless_asked(run: Any) -> None:
    assert run(PROJECT).branches is None
