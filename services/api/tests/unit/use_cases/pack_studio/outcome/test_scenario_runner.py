"""Прогон сценариев по версии: утверждения, снимок, статусы и покрытие (`core/pack_studio/outcome/scenario_check.py`,
`use_cases/pack_studio/outcome/scenario_runner.py`).

Синтетическая версия (`synthetic.py`) даёт управляемые различия: вид работы меняет документы и пункты, руководитель из
компании и консультант меняют маршрут и участников. Настоящие версии репозитория: `test_scenarios_real_packs.py`."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import date

import pytest
from hse_doc_studio.api.schemas.pack_studio_outcome import PackScenarioRunResponse
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.model import Digest, Outcome, SectionPrint
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.outcome.scenario_check import (
    check_assertions,
    coverage_of,
    diff_digest,
    judge,
    snapshot_fingerprint,
)
from hse_doc_studio.core.pack_studio.outcome.scenarios import (
    DocumentCountAssertion,
    DocumentStateAssertion,
    ItemActiveAssertion,
    MetaVisibleAssertion,
    ParticipantAssertion,
    RoutePairAssertion,
    RouteStepsAssertion,
    Scenario,
)
from hse_doc_studio.core.pack_studio.preview import AUTO_NORMAL, PreviewExample, auto_examples
from hse_doc_studio.use_cases.pack_studio.outcome.scenario_runner import (
    ScenarioRunError,
    coverage_universe,
    example_of,
    resolve_scenario,
    run_scenarios,
)

from tests.unit.use_cases.pack_studio.outcome.synthetic import load_synthetic

TODAY = date(2026, 11, 16)
COMPANY = {"kind": "research", "supervisor": "company", "co_supervisor": "yes"}
PLAIN = {"kind": "research", "supervisor": "university", "co_supervisor": "no"}


@pytest.fixture(scope="module")
def version(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TemplateVersion]:
    return load_synthetic(tmp_path_factory.mktemp("synthetic"))


@pytest.fixture(scope="module")
def examples(version: TemplateVersion) -> tuple[PreviewExample, ...]:
    return tuple(auto_examples(version))


def _scenario(inputs: dict[str, str], **kw: object) -> Scenario:
    return Scenario(name={"ru": "тест"}, inputs=inputs, **kw)  # type: ignore[arg-type]


def _outcome(version: TemplateVersion, examples: tuple[PreviewExample, ...], inputs: dict[str, str]) -> Outcome:
    return resolve_scenario(version, examples, _scenario(inputs), TODAY)


# ── утверждения ──────────────────────────────────────────────────────────────


def test__assertions__true_statements_about_the_result_all_hold(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    outcome = _outcome(version, examples, COMPANY)
    assertions = (
        DocumentStateAssertion(doc="report", state="active"),
        DocumentStateAssertion(doc="spec", state="absent"),
        DocumentCountAssertion(state="active", count=3),
        MetaVisibleAssertion(field="manuals", visible=False),
        MetaVisibleAssertion(field="topic", visible=True),
        ParticipantAssertion(persona="co_supervisor", present=True),
        ParticipantAssertion(persona="author2", present=False),  # в одиночной работе второго автора нет
        ItemActiveAssertion(point="topic", doc="report", active=True),
        ItemActiveAssertion(point="topic", doc="operator_manual", active=False),
        ItemActiveAssertion(point="topic", doc="not-in-this-point", active=False),
        RouteStepsAssertion(
            point="topic", steps=(("author",), ("co_supervisor", "supervisor"), ("academic_supervisor",))
        ),
        RoutePairAssertion(point="topic", doc="report", slot="co_supervisor", persona="co_supervisor", present=True),
        RoutePairAssertion(point="final", doc="report", slot="co_supervisor", persona="co_supervisor", present=False),
    )

    assert check_assertions(outcome, assertions) == ()


def test__assertions__false_statements__fail_with_expected_actual_and_decisions(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    outcome = _outcome(version, examples, PLAIN)
    assertions = (
        DocumentStateAssertion(doc="report", state="inactive"),  # 0
        DocumentCountAssertion(state="active", count=99),  # 1
        MetaVisibleAssertion(field="manuals", visible=True),  # 2
        ParticipantAssertion(persona="co_supervisor", present=True),  # 3
        ItemActiveAssertion(point="topic", doc="operator_manual", active=True),  # 4
        RouteStepsAssertion(point="topic", steps=(("author",), ("supervisor", "co_supervisor"))),  # 5
        RoutePairAssertion(
            point="topic", doc="report", slot="co_supervisor", persona="co_supervisor", present=True
        ),  # 6
        DocumentStateAssertion(doc="ghost", state="active"),  # 7
        ItemActiveAssertion(point="ghost", doc="report", active=True),  # 8
        RouteStepsAssertion(point="ghost", steps=()),  # 9
        RoutePairAssertion(point="ghost", doc="report", slot="author", persona="author", present=True),  # 10
    )

    failures = {f.index: f for f in check_assertions(outcome, assertions)}

    assert sorted(failures) == list(range(11))
    assert (failures[0].expected, failures[0].actual) == ("inactive", "active")
    assert failures[0].kind == "document_state"
    assert failures[0].why, "документ объясняется решениями трассы"
    assert all(why in {e.id for e in outcome.trace} for f in failures.values() for why in f.why)
    assert (failures[1].expected, failures[1].actual) == ("99", "3")
    assert (failures[2].expected, failures[2].actual) == ("true", "false")
    assert (failures[3].expected, failures[3].actual) == ("true", "false")
    assert (failures[4].expected, failures[4].actual) == ("true", "false")
    assert failures[5].expected == '[["author"], ["supervisor", "co_supervisor"]]'
    assert failures[5].actual == '[["author"], ["supervisor"]]'
    assert (failures[6].expected, failures[6].actual) == ("true", "false")
    assert failures[6].why, "пара пропущена условием слота: причина из трассы"
    assert failures[7].actual == "missing"
    assert (failures[8].actual, failures[9].actual, failures[10].actual) == ("missing point",) * 3


def test__assertions__step_order_inside_a_step_is_not_important(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    outcome = _outcome(version, examples, COMPANY)

    swapped = RouteStepsAssertion(
        point="topic", steps=(("author",), ("co_supervisor", "supervisor"), ("academic_supervisor",))
    )
    wrong_order = RouteStepsAssertion(
        point="topic", steps=(("supervisor", "co_supervisor"), ("author",), ("academic_supervisor",))
    )

    assert check_assertions(outcome, (swapped,)) == ()
    assert len(check_assertions(outcome, (wrong_order,))) == 1


# ── снимок ───────────────────────────────────────────────────────────────────


def test__snapshot__own_result__matches(version: TemplateVersion, examples: tuple[PreviewExample, ...]) -> None:
    outcome = _outcome(version, examples, COMPANY)
    scenario = _scenario(COMPANY, snapshot=outcome.digest)

    verdict = judge(scenario, outcome)

    assert (verdict.status, verdict.failures, verdict.changes) == ("passed", (), ())


def test__snapshot__other_inputs__failed_with_a_readable_list_of_changes(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    recorded = _outcome(version, examples, COMPANY)
    now = _outcome(version, examples, PLAIN)

    verdict = judge(_scenario(COMPANY, snapshot=recorded.digest), now)

    assert verdict.status == "failed"
    by_id = {(c.kind, c.id): c for c in verdict.changes}
    assert by_id[("participant", "co_supervisor")].symbol == "-"
    assert (by_id[("participant", "co_supervisor")].before, by_id[("participant", "co_supervisor")].after) == (
        "co_supervisor",
        None,
    )
    step2 = by_id[("route_step", "topic/step/2")]
    assert (step2.symbol, step2.section, step2.before, step2.after) == (
        "~",
        "route",
        "supervisor, co_supervisor",
        "supervisor",
    )
    assert by_id[("route_step", "topic/step/3")].symbol == "-"
    assert (by_id[("route_pair", "topic/pairs")].before, by_id[("route_pair", "topic/pairs")].after) == ("4", "2")
    (failure,) = verdict.failures
    assert (failure.index, failure.kind) == (None, "snapshot")
    assert (failure.expected, failure.actual) == (snapshot_fingerprint(recorded.digest), now.fingerprint)
    assert failure.why


def test__snapshot__documents_and_items_appear_and_disappear(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    research = _outcome(version, examples, {"kind": "research"})
    project = _outcome(version, examples, {"kind": "project"})

    changes = {(c.kind, c.id): c for c in diff_digest(research.digest, project.digest)}

    assert changes[("document", "spec")].symbol == "+"
    assert (changes[("document", "spec")].before, changes[("document", "spec")].after) == ("absent", "active")
    assert changes[("document", "summary")].symbol == "-"
    assert changes[("item", "topic/spec")].symbol == "+"
    assert changes[("item", "topic/summary")].symbol == "-"
    assert diff_digest(project.digest, project.digest) == ()
    reverse = {(c.kind, c.id): c for c in diff_digest(project.digest, research.digest)}
    assert reverse[("document", "spec")].symbol == "-"


def test__snapshot__inactive_to_absent_is_a_change_but_not_an_appearance() -> None:
    before = Digest({"nda": "inactive"}, (), (), (), ())
    after = Digest({"nda": "absent"}, (), (), (), ())

    (change,) = diff_digest(before, after)

    assert (change.symbol, change.kind, change.before, change.after) == ("~", "document", "inactive", "absent")


def test__snapshot__a_fingerprint_digest_cannot_explain_is_one_line_per_section(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    outcome = _outcome(version, examples, COMPANY)
    sections = tuple(
        replace(p, fingerprint="000000000000") if p.section == "meta" else p for p in outcome.digest.sections
    )

    verdict = judge(_scenario(COMPANY, snapshot=replace(outcome.digest, sections=sections)), outcome)

    assert verdict.status == "failed"
    (change,) = verdict.changes
    assert (change.symbol, change.section, change.kind, change.id) == ("~", "meta", "meta_field", "meta")
    assert change.before == "000000000000"


def test__snapshot__without_sections_is_compared_by_content_only(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    outcome = _outcome(version, examples, COMPANY)
    digest = replace(outcome.digest, sections=())

    assert judge(_scenario(COMPANY, snapshot=digest), outcome).status == "passed"
    assert snapshot_fingerprint(digest) == ""


def test__snapshot__counts_only_difference_is_still_reported() -> None:
    before = Digest({}, (), (), (), (SectionPrint("meta", "aaa", 3),))
    after = Digest({}, (), (), (), (SectionPrint("meta", "aaa", 4),))

    assert [c.section for c in diff_digest(before, after)] == ["meta"]


# ── вердикт ──────────────────────────────────────────────────────────────────


def test__judge__no_expectation__unchecked(version: TemplateVersion, examples: tuple[PreviewExample, ...]) -> None:
    verdict = judge(_scenario({}), _outcome(version, examples, {}))

    assert (verdict.status, verdict.failures, verdict.changes) == ("unchecked", (), ())


def test__judge__assertions_and_snapshot_are_independent(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    other = _outcome(version, examples, COMPANY)
    now = _outcome(version, examples, PLAIN)
    scenario = _scenario(
        PLAIN,
        snapshot=other.digest,
        assertions=(
            ParticipantAssertion(persona="supervisor", present=True),
            ParticipantAssertion(persona="co_supervisor", present=True),
        ),
    )

    verdict = judge(scenario, now)

    assert [f.kind for f in verdict.failures] == ["participant_present", "snapshot"]
    assert [f.index for f in verdict.failures] == [1, None]


# ── прогон ───────────────────────────────────────────────────────────────────


def test__run__statuses_messages_and_counters(version: TemplateVersion, examples: tuple[PreviewExample, ...]) -> None:
    good = _outcome(version, examples, COMPANY)
    scenarios: dict[str, Scenario | str] = {
        "passes": _scenario(
            COMPANY, snapshot=good.digest, assertions=(ParticipantAssertion(persona="co_supervisor", present=True),)
        ),
        "fails": _scenario(PLAIN, assertions=(ParticipantAssertion(persona="co_supervisor", present=True),)),
        "unknown-input": _scenario({"nope": "1"}, assertions=(ParticipantAssertion(persona="author", present=True),)),
        "value-outside": _scenario({"supervisor": "martian"}),
        "bad-example": _scenario({}, example="nope"),
        "broken-file": "assertions[0].kind: unknown kind 'x'",
        "no-expectation": _scenario(COMPANY),
        "other-version": _scenario(COMPANY, versions=("2025.*",)),
        "this-version": _scenario(COMPANY, versions=("1.*",)),
    }

    run = run_scenarios(version, examples, scenarios, TODAY)

    got = {r.scenario: r for r in run.results}
    assert [r.scenario for r in run.results] == list(scenarios), "порядок как у входа"
    assert {k: v.status for k, v in got.items()} == {
        "passes": "passed",
        "fails": "failed",
        "unknown-input": "error",
        "value-outside": "error",
        "bad-example": "error",
        "broken-file": "error",
        "no-expectation": "unchecked",
        "other-version": "unchecked",
        "this-version": "unchecked",
    }
    assert (run.passed, run.failed, run.errors, run.unchecked) == (1, 1, 4, 3)
    assert got["unknown-input"].message == "nope='1': unknown switch"
    assert got["value-outside"].message is not None
    assert got["value-outside"].message.startswith("supervisor='martian'")
    assert got["bad-example"].message == "example 'nope': unknown example"
    assert got["broken-file"].message == "assertions[0].kind: unknown kind 'x'"
    assert got["other-version"].message == "version 1.0.0 is outside versions: 2025.*"
    assert got["other-version"].fingerprint is None
    assert got["passes"].fingerprint == good.fingerprint
    assert got["this-version"].message is None, "версия подходит под шаблон, ожидания нет"
    assert got["no-expectation"].message is None
    assert got["no-expectation"].fingerprint is not None


def test__run__response_is_accepted_by_the_strict_contract_model(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    good = _outcome(version, examples, COMPANY)
    run = run_scenarios(
        version,
        examples,
        {
            "a": _scenario(COMPANY, snapshot=good.digest),
            "b": _scenario(PLAIN, snapshot=good.digest),
            "c": _scenario({"nope": "1"}),
            "d": _scenario({}),
        },
        TODAY,
    )
    body = {
        "workspace_id": "6f1c1c8e-1b7a-4d51-9a43-0a5b2f3c4d10",
        "pack": "p",
        "template": "t",
        "version": "1.0.0",
        "state": "work_tree",
        "revision": "sha256-0",
        **json.loads(json.dumps(to_json(run))),
    }

    parsed = PackScenarioRunResponse.model_validate(body)

    assert [r.status for r in parsed.results] == ["passed", "failed", "error", "unchecked"]
    assert parsed.coverage.rules_total == run.coverage.rules_total


def test__run__is_deterministic_and_does_not_read_files_or_time(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    scenarios: dict[str, Scenario | str] = {"a": _scenario(COMPANY), "b": _scenario(PLAIN)}

    assert run_scenarios(version, examples, scenarios, TODAY) == run_scenarios(version, examples, scenarios, TODAY)


def test__resolve_scenario__example_defaults_to_the_auto_normal_set_and_request_example_wins(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    assert example_of(_scenario({}), examples).id == AUTO_NORMAL
    assert example_of(_scenario({}, example="auto:long"), examples).id == "auto:long"
    assert example_of(_scenario({}, example="auto:long"), examples, "auto:empty").id == "auto:empty"
    assert resolve_scenario(version, examples, _scenario({}, example="auto:long"), TODAY).example == "auto:long"


def test__resolve_scenario__request_inputs_go_over_the_scenario_inputs(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    scenario = _scenario(COMPANY)

    outcome = resolve_scenario(version, examples, scenario, TODAY, inputs={"supervisor": "university"})

    assert outcome.inputs["supervisor"] == "university"
    assert outcome.inputs["co_supervisor"] == "yes"


def test__resolve_scenario__bad_inputs_raise_scenario_run_error(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    with pytest.raises(ScenarioRunError, match="nope='1'"):
        resolve_scenario(version, examples, _scenario({"nope": "1"}), TODAY)
    with pytest.raises(ScenarioRunError, match="unknown example"):
        resolve_scenario(version, examples, _scenario({}), TODAY, wanted_example="file-example")


# ── покрытие ─────────────────────────────────────────────────────────────────


def test__coverage__full_half_and_none(version: TemplateVersion, examples: tuple[PreviewExample, ...]) -> None:
    universe = coverage_universe(version, examples, TODAY)
    company = _outcome(version, examples, COMPANY)
    plain = _outcome(version, examples, PLAIN)

    only_company = coverage_of(universe, {"company": company})
    both = coverage_of(universe, {"company": company, "plain": plain})
    nothing = coverage_of(universe, {})

    assert nothing.rules_total == both.rules_total == only_company.rules_total > 0
    assert nothing.rules_uncovered == nothing.rules_total
    assert nothing.rules_covered == nothing.rules_half == 0
    assert both.rules_covered > only_company.rules_covered
    for cover in (only_company, both, nothing):
        assert cover.rules_covered + cover.rules_half + cover.rules_uncovered == cover.rules_total
        assert len(cover.rules) == cover.rules_half + cover.rules_uncovered
    # Правило слота `when` (роль руководителя) видят оба исхода только при двух разных руководителях.
    slot = next(r for r in only_company.rules if r.kind == "slot_when")
    assert slot.seen in (("held",), ("not_held",))
    assert slot.scenarios == ("company",)
    assert all(r.rule not in {x.rule for x in nothing.rules if x.seen} for r in both.rules)
    assert coverage_of(universe, {"company": company}, total=5).scenarios == 5


def test__coverage__rule_seen_by_scenarios_but_missing_from_the_universe_still_counts(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    company = _outcome(version, examples, COMPANY)

    cover = coverage_of((), {"company": company})

    decided = {e.rule for e in company.trace if e.status != "skipped"}
    # Правило, которое в результате только пропущено (`skipped`), исхода не имеет: в универсум не входит.
    assert cover.rules_total == len(decided)
    assert cover.rules_uncovered == 0
    assert cover.approximate


def test__coverage__universe_is_deterministic_and_has_one_result_per_neighbour(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    first = coverage_universe(version, examples, TODAY)

    assert [o.fingerprint for o in first] == [o.fingerprint for o in coverage_universe(version, examples, TODAY)]
    assert len(first) > 1


def test__coverage__contract_shape(version: TemplateVersion, examples: tuple[PreviewExample, ...]) -> None:
    run = run_scenarios(version, examples, {"a": _scenario(COMPANY, assertions=())}, TODAY)

    shape = to_json(run.coverage)

    assert set(shape) == {
        "scenarios",
        "rules_total",
        "rules_covered",
        "rules_half",
        "rules_uncovered",
        "rules",
        "percent",
        "rows_total",
        "rows_touched",
        "uncovered_rows",
        "rules_omitted",
        "approximate",
    }
    assert set(shape["rules"][0]) == {"rule", "kind", "seen", "possible", "scenarios", "witness"}
    assert set(shape["rules"][0]["rule"]) == {"origin", "file", "pointer", "builtin"}


def test__assertions__route_pair_optional__compared_with_the_signature(
    version: TemplateVersion, examples: tuple[PreviewExample, ...]
) -> None:
    outcome = _outcome(version, examples, COMPANY)
    pair = {"point": "topic", "doc": "report", "slot": "co_supervisor", "persona": "co_supervisor", "present": True}
    actual = next(
        p.optional
        for point in outcome.points
        if point.id == "topic"
        for p in point.route.pairs
        if (p.slot_id, p.persona) == ("co_supervisor", "co_supervisor")
    )

    same = check_assertions(outcome, (RoutePairAssertion(**pair, optional=actual),))
    (other,) = check_assertions(outcome, (RoutePairAssertion(**pair, optional=not actual),))

    assert same == ()
    words = {True: "optional", False: "required"}
    assert (other.kind, other.expected, other.actual) == ("route_pair", words[not actual], words[actual])
