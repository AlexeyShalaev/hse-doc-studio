"""Линтер результата (срез O8): по каждому правилу синтетическая версия с заведомым дефектом, на которой оно
срабатывает, и версия, на которой нет; реальные паки; находка со всеми полями контракта.

Синтетическая версия `synthetic.py` исправна (линтер на ней молчит об ошибках), дефект вносится заменой строки в её
манифесте: так видно, что именно сломано и какое правило это ловит."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from hse_doc_studio.api.schemas.pack_studio_outcome import OutcomeFinding
from hse_doc_studio.core.pack_studio.outcome.atlas import AtlasTooLarge
from hse_doc_studio.core.pack_studio.outcome.lint import RULE_IDS, RULES, LintFinding, LintSources, limit_per_rule
from hse_doc_studio.core.pack_studio.outcome.lint_atlas import AtlasObserver, _RuleStat, _when_finding
from hse_doc_studio.core.pack_studio.outcome.lint_static import static_findings
from hse_doc_studio.core.pack_studio.outcome.model import RuleRef
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.preview import auto_examples
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio.outcome.lint import OutcomeLint, lint_outcome, scan_atlas

from tests.unit.use_cases.pack_studio.outcome.synthetic import VERSION_YAML, load_synthetic

TODAY = date(2026, 11, 16)
_PACKS = Path(__file__).resolve().parents[7] / "packs"

Edit = Callable[[str], str]


def _replace(old: str, new: str) -> Edit:
    def edit(text: str) -> str:
        assert old in text, old
        return text.replace(old, new, 1)

    return edit


def _lint(tmp_path: Path, *edits: Edit, limit: int = 2000) -> OutcomeLint:
    text = VERSION_YAML
    for edit in edits:
        text = edit(text)
    version = load_synthetic(tmp_path, version_yaml=text)
    example = auto_examples(version)[0]
    return lint_outcome(version, {"version.yaml": text}, example, TODAY, limit=limit)


def _found(result: OutcomeLint, rule: str) -> list[LintFinding]:
    return [f for f in result.findings if f.rule_id == rule]


def _ids(result: OutcomeLint) -> set[str]:
    return {f.rule_id for f in result.findings}


# ── базовая версия ───────────────────────────────────────────────────────────


def test__synthetic_version__has_no_errors_and_only_the_expected_warnings(tmp_path: Path) -> None:
    result = _lint(tmp_path)

    assert result.errors == 0
    assert _ids(result) <= {"slot-never-routed", "route-step-without-person", "dimension-no-effect", "point-empty"}
    assert not result.atlas_skipped
    assert result.universe is not None
    assert len(result.universe.rows) > 0


def test__finding__carries_every_field_the_contract_needs(tmp_path: Path) -> None:
    result = _lint(tmp_path, _replace('equals: "yes" }', 'equals: "maybe" }'))

    item = _found(result, "visible-if-value-not-in-options")[0]
    body = to_json(item)

    assert OutcomeFinding.model_validate(body).rule_id == "visible-if-value-not-in-options"
    assert item.severity == "error"
    assert item.message
    assert item.hint
    assert item.file == "version.yaml"
    assert item.pointer
    assert item.pointer.endswith("/visible_if/equals")
    assert item.line is not None
    assert item.line > 1
    assert [(e.section, e.id) for e in item.elements] == [("forms", "ai/tools")]


def test__rule_table__every_rule_has_a_code_a_severity_and_a_source() -> None:
    assert len(RULE_IDS) == len(RULES)
    assert {severity for _, severity, _ in RULES} == {"error", "warning", "info"}
    assert {source for _, _, source in RULES} == {"static", "atlas", "files", "static+atlas"}


# ── visible_if ───────────────────────────────────────────────────────────────


def test__visible_if_unknown_field__fires_and_holds_back_on_a_known_one(tmp_path: Path) -> None:
    broken = _lint(tmp_path / "a", _replace("visible_if: { field: used_ai,", "visible_if: { field: nope,"))
    clean = _lint(tmp_path / "b")

    (item,) = _found(broken, "visible-if-unknown-field")
    assert "nope" in item.message
    assert item.pointer is not None
    assert item.pointer.endswith("/visible_if/field")
    assert "visible-if-unknown-field" not in _ids(clean)


@pytest.mark.parametrize(
    ("edit", "mention"),
    [
        (_replace('equals: "yes" }', 'equals: "maybe" }'), "no, yes"),
        # `equals: yes` без кавычек YAML читает как true: у select-поля ответ строка, условие не выполнится.
        (_replace('equals: "yes" }', "equals: yes }"), "не логическое"),
        (_replace("equals: true }", 'equals: "yes" }'), "true или false"),
    ],
)
def test__visible_if_value_not_in_options__fires_on_values_the_answer_can_never_have(
    tmp_path: Path, edit: Edit, mention: str
) -> None:
    result = _lint(tmp_path, edit)

    (item,) = _found(result, "visible-if-value-not-in-options")
    assert item.severity == "error"
    assert mention in item.message


def test__visible_if_value_not_in_options__a_real_option_is_fine(tmp_path: Path) -> None:
    assert "visible-if-value-not-in-options" not in _ids(_lint(tmp_path, _replace('equals: "yes" }', 'equals: "no" }')))


# ── обязательные и скрытые поля ──────────────────────────────────────────────


def test__required_hidden__atlas_catches_a_required_field_that_is_never_visible(tmp_path: Path) -> None:
    broken = _lint(tmp_path / "a", _replace('equals: "yes" }', 'equals: "maybe" }'))
    clean = _lint(tmp_path / "b")

    (item,) = _found(broken, "required-hidden")
    assert item.severity == "error"
    assert item.pointer is not None
    assert "/fields/1" in item.pointer
    assert "required-hidden" not in _ids(clean)


def test__field_never_visible__is_a_warning_for_an_optional_field(tmp_path: Path) -> None:
    result = _lint(
        tmp_path,
        _replace("equals: true }", "equals: false }"),
    )

    # `agree` бывает true и false, поэтому `note` видна при false: правило молчит.
    assert "field-never-visible" not in _ids(result)

    hidden = _lint(tmp_path / "b", _replace("equals: true }", 'equals: "maybe" }'))
    (item,) = _found(hidden, "field-never-visible")
    assert item.severity == "warning"
    assert "note" in item.message


def test__required_hidden__static_form_with_no_known_kind_is_named_once_at_the_form(tmp_path: Path) -> None:
    text = VERSION_YAML
    version = load_synthetic(tmp_path, version_yaml=text)
    forms = tuple(replace(f, supported_kinds=("reserch",)) if f.id == "repo" else f for f in version.forms)
    broken = replace(version, forms=forms)

    items = [f for f in static_findings(LintSources(broken, {"version.yaml": text})) if f.rule_id == "required-hidden"]

    assert [i.pointer for i in items] == ["/forms/1"]
    assert items[0].severity == "error"


# ── языки ────────────────────────────────────────────────────────────────────


def test__variant_lang_outside_langs__fires_for_a_variant_and_for_a_document(tmp_path: Path) -> None:
    variant = _lint(tmp_path / "a", _replace("supported_langs: [en] }", "supported_langs: [de] }"))
    document = _lint(
        tmp_path / "b", _replace("supported_langs: [ru, en]\n    variants:", "supported_langs: [ru, de]\n    variants:")
    )
    clean = _lint(tmp_path / "c")

    (v,) = _found(variant, "variant-lang-outside-langs")
    (d,) = _found(document, "variant-lang-outside-langs")
    assert v.pointer is not None
    assert v.pointer.endswith("/variants/1/supported_langs")
    assert d.pointer is not None
    assert d.pointer.endswith("/supported_langs")
    assert "/variants" not in d.pointer
    assert v.severity == d.severity == "error"
    # Документы описаны прямо в version.yaml: находка ведёт в запись `documents`, а не в несуществующий doc.yaml.
    assert v.file == d.file == "version.yaml"
    assert "variant-lang-outside-langs" not in _ids(clean)


# ── NDA и зашитые правила ────────────────────────────────────────────────────


def _without_nda(text: str) -> str:
    text = text.replace("nda: { source_dir: nda }\n", "")
    text = text.replace('  nda: { type: bool, label: { ru: "NDA", en: "NDA" } }\n', "")
    start = text.index("  - { id: nda, ")
    end = text.index("\n", text.index("supported_langs: [ru], scope: personal, required: false }", start))
    return text[:start] + text[end + 1 :]


def test__skip_if_nda_without_nda__fires_only_when_the_version_has_no_nda(tmp_path: Path) -> None:
    broken = _lint(tmp_path / "a", _without_nda)
    clean = _lint(tmp_path / "b")

    (item,) = _found(broken, "skip-if-nda-without-nda")
    assert item.severity == "warning"
    assert "spec" in item.message
    assert item.pointer is not None
    assert item.pointer.endswith("/skip_if_nda")
    assert "skip-if-nda-without-nda" not in _ids(clean)
    assert not _found(broken, "builtin-gate-mismatch")


def test__builtin_gate_mismatch__manuals_that_cannot_switch_a_manual_off(tmp_path: Path) -> None:
    options = _replace(
        'options: ["Программиста и оператора", "Только программиста", "Только оператора"]',
        'options: ["Все", "Часть"]',
    )

    broken = _lint(tmp_path / "a", options)
    clean = _lint(tmp_path / "b")

    items = _found(broken, "builtin-gate-mismatch")
    assert [{e.id for e in i.elements} for i in items] == [{"programmer_manual", "operator_manual"}]
    assert all(i.severity == "warning" and i.pointer == "/meta_fields/manuals/options" for i in items)
    assert "builtin-gate-mismatch" not in _ids(clean)


def test__builtin_gate_mismatch__nda_document_without_a_switch_and_a_switch_without_a_document(tmp_path: Path) -> None:
    no_switch = _lint(
        tmp_path / "a",
        _replace("nda: { source_dir: nda }\n", ""),
        _replace('  nda: { type: bool, label: { ru: "NDA", en: "NDA" } }\n', ""),
    )
    no_document = _lint(
        tmp_path / "b", _replace("nda: { source_dir: nda }\n", ""), _replace("  - { id: nda, ", "  - { id: nda2, ")
    )

    assert any("nda_gate" in f.message for f in _found(no_switch, "builtin-gate-mismatch"))
    assert any("включённое NDA" in f.message for f in _found(no_document, "builtin-gate-mismatch"))


# ── условия слотов ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("edit", "mention"),
    [
        (_replace("when: { person: co_supervisor } }", "when: { person: boss } }"), "boss"),
        (_replace("{ doc_id: report, slot_id: co_supervisor,", "{ doc_id: report, slot_id: ghost,"), "ghost"),
        (_replace("{ doc_id: report, slot_id: co_supervisor,", "{ doc_id: nodoc, slot_id: co_supervisor,"), "nodoc"),
    ],
)
def test__when_unknown_person__fires_for_a_bad_person_slot_or_document(
    tmp_path: Path, edit: Edit, mention: str
) -> None:
    result = _lint(tmp_path, edit)

    items = _found(result, "when-unknown-person")
    assert any(mention in i.message for i in items)
    assert all(i.severity == "error" for i in items)


def test__when_unknown_person__a_valid_entry_is_not_flagged(tmp_path: Path) -> None:
    assert "when-unknown-person" not in _ids(_lint(tmp_path))


def test__when_never_held__a_condition_no_combination_can_meet(tmp_path: Path) -> None:
    # Соруководитель в синтетических проектах всегда из университета: условие роли `company` не выполнится никогда.
    broken = _lint(
        tmp_path / "a",
        _replace("when: { person: co_supervisor } }", "when: { person: co_supervisor, role: company } }"),
    )
    clean = _lint(tmp_path / "b")

    (item,) = _found(broken, "when-never-held")
    assert item.severity == "warning"
    assert item.pointer is not None
    assert item.pointer.endswith("/signing_slots/0/when")
    assert item.witnesses
    assert len(item.witnesses) <= 3
    assert "when-never-held" not in _ids(clean)


def test__when_always_held__is_info_and_only_when_the_condition_never_fails() -> None:
    always = _RuleStat("slot_when")
    always.add("held", {"kind": "project"}, ())
    mixed = _RuleStat("slot_when")
    mixed.add("held", {"kind": "project"}, ())
    mixed.add("not_held", {"kind": "research"}, ())
    never = _RuleStat("slot_when")
    never.add("not_held", {"kind": "research"}, ())

    def codes(stat: _RuleStat | None) -> list[str]:
        return [f.rule_id for f in _when_finding("topic", "report", "co", "/p", stat)]

    assert codes(always) == ["when-always-held"]
    assert codes(mixed) == []
    assert codes(never) == ["when-never-held"]
    assert codes(None) == ["when-never-held"]
    assert next(iter(_when_finding("t", "d", "s", "/p", always))).severity == "info"


def test__slot_when_overlap__two_entries_for_one_slot_with_different_conditions_held_together(tmp_path: Path) -> None:
    second = _replace(
        "      deadline_hint:",
        "      deadline_hint:",
    )
    duplicate = _replace(
        "        - { doc_id: report, slot_id: co_supervisor, when: { person: co_supervisor } }\n",
        "        - { doc_id: report, slot_id: co_supervisor, when: { person: co_supervisor } }\n"
        "        - { doc_id: report, slot_id: co_supervisor, when: { person: academic_supervisor } }\n",
    )

    broken = _lint(tmp_path / "a", duplicate, second)
    clean = _lint(tmp_path / "b")

    (item,) = _found(broken, "slot-when-overlap")
    assert item.severity == "warning"
    assert item.pointer is not None
    assert item.pointer.endswith("/signing_slots/1")
    assert item.witnesses
    assert "slot-when-overlap" not in _ids(clean)


# ── слоты и маршрут ──────────────────────────────────────────────────────────


def test__slot_never_routed__static_for_an_unnamed_slot_and_atlas_for_one_the_conditions_never_let_in(
    tmp_path: Path,
) -> None:
    extra_slot = _replace(
        "pack_submission:\n",
        "",
    )
    unnamed = _lint(
        tmp_path / "a",
        _replace(
            "    - { id: academic_supervisor, label:",
            "    - { id: ghost, label: { ru: Призрак, en: Ghost }, applies_to: [report],\n"
            "        default_placement: { page: 1, x_mm: 10, y_mm: 20, width_mm: 30 } }\n"
            "    - { id: academic_supervisor, label:",
        ),
        extra_slot,
    )
    named = _lint(
        tmp_path / "b",
        _replace(
            "    - { id: academic_supervisor, label:",
            "    - { id: ghost, label: { ru: Призрак, en: Ghost }, applies_to: [report],\n"
            "        default_placement: { page: 1, x_mm: 10, y_mm: 20, width_mm: 30 } }\n"
            "    - { id: academic_supervisor, label:",
        ),
        _replace(
            "signing_route: [[author], [supervisor, co_supervisor], [academic_supervisor]]",
            "signing_route: [[author], [supervisor, co_supervisor], [academic_supervisor], [ghost]]",
        ),
    )

    (a,) = (f for f in _found(unnamed, "slot-never-routed") if "ghost" in f.message)
    (b,) = (f for f in _found(named, "slot-never-routed") if "ghost" in f.message)
    assert "не назван" in a.message
    assert "не назван" not in b.message
    assert a.pointer == b.pointer
    assert a.pointer is not None
    assert a.pointer.startswith("/signatures/slots/")
    assert not [f for f in _found(_lint(tmp_path / "c"), "slot-never-routed") if "ghost" in f.message]


def test__static_findings__name_an_unnamed_slot_without_any_calculation(tmp_path: Path) -> None:
    text = VERSION_YAML.replace(
        "    - { id: academic_supervisor, label:",
        "    - { id: ghost, label: { ru: Призрак, en: Ghost }, applies_to: [report],\n"
        "        default_placement: { page: 1, x_mm: 10, y_mm: 20, width_mm: 30 } }\n"
        "    - { id: academic_supervisor, label:",
    )
    version = load_synthetic(tmp_path, version_yaml=text)

    found = static_findings(LintSources(version, {"version.yaml": text}))

    assert [f.rule_id for f in found] == ["slot-never-routed"]
    assert found[0].line is not None


def test__route_step_without_person__fires_when_a_step_waits_for_a_missing_person(tmp_path: Path) -> None:
    result = _lint(tmp_path)

    items = _found(result, "route-step-without-person")
    topic = next(i for i in items if i.elements[0].id == "topic")
    assert "supervisor" in topic.message
    assert topic.severity == "warning"
    assert topic.witnesses
    assert topic.witnesses[0]["co_supervisor"] == "no"
    assert topic.pointer is not None
    assert topic.pointer.endswith("/signing_route")


def test__route_step_without_person__names_only_the_persons_the_route_really_waits_for(tmp_path: Path) -> None:
    author_only = _lint(
        tmp_path,
        _replace("signatures: [author, supervisor] }", "signatures: [author] }"),
        _replace("signatures: [supervisor], skip_if_nda: true }", "signatures: [author], skip_if_nda: true }"),
        _replace(
            "signing_route: [[author], [supervisor, co_supervisor], [academic_supervisor]]", "signing_route: [[author]]"
        ),
    )

    topic = next(f for f in _found(author_only, "route-step-without-person") if f.elements[0].id == "topic")
    waited = topic.message.split("персон, которых нет в проекте: ")[1].split(" (")[0]
    assert waited == "academic_supervisor"


def test__route_gap__a_point_that_needs_signatures_nobody_present_can_give(tmp_path: Path) -> None:
    gap = _lint(
        tmp_path / "a",
        _replace(
            "- { doc_id: report, signatures: [author, supervisor] }", "- { doc_id: report, signatures: [supervisor] }"
        ),
        _replace(
            "signing_route: [[author], [supervisor, co_supervisor], [academic_supervisor]]",
            "signing_route: [[supervisor]]",
        ),
    )
    clean = _lint(tmp_path / "b")

    items = _found(gap, "route-gap")
    assert [i.elements[0].id for i in items] == ["topic"]
    assert items[0].witnesses
    assert items[0].witnesses[0]["supervisor"] == "none"
    assert "route-gap" not in _ids(clean)


# ── документы, пункты, точки ─────────────────────────────────────────────────


def test__document_never_active__a_team_document_in_a_solo_only_version(tmp_path: Path) -> None:
    broken = _lint(
        tmp_path / "a", _replace("supported_staffing: [solo, team]\nnda:", "supported_staffing: [solo]\nnda:")
    )
    clean = _lint(tmp_path / "b")

    (item,) = _found(broken, "document-never-active")
    assert item.severity == "warning"
    assert item.elements[0].id == "shared_spec"
    assert "document-never-active" not in _ids(clean)


def test__item_never_active__an_item_the_document_never_lets_through(tmp_path: Path) -> None:
    broken = _lint(
        tmp_path / "a",
        _replace(
            "- { doc_id: operator_manual, signatures: [] }",
            "- { doc_id: operator_manual, signatures: [], supported_kinds: [research] }",
        ),
    )
    clean = _lint(tmp_path / "b")

    (item,) = _found(broken, "item-never-active")
    assert item.elements[0].id == "topic/operator_manual"
    assert "item-never-active" not in _ids(clean)


def test__point_empty__a_point_with_no_active_item_in_some_combinations(tmp_path: Path) -> None:
    broken = _lint(
        tmp_path / "a",
        _replace(
            "        - { doc_id: report, signatures: [author] }\n        - { doc_id: presentation, signatures: [] }",
            "        - { doc_id: report, signatures: [author], supported_kinds: [research] }\n"
            "        - { doc_id: presentation, signatures: [], supported_kinds: [research] }",
        ),
    )

    (item,) = [f for f in _found(broken, "point-empty") if f.elements[0].id == "final"]
    assert item.severity == "info"
    assert item.witnesses
    assert not [f for f in _found(_lint(tmp_path / "b"), "point-empty") if f.elements[0].id == "final"]


# ── переводы ─────────────────────────────────────────────────────────────────


def test__translation_missing__fires_for_a_text_with_only_one_language(tmp_path: Path) -> None:
    help_ru = _replace(
        'year: { type: string, label: { ru: "Год", en: "Year" }, auto: academic_year }',
        'year: { type: string, label: { ru: "Год", en: "Year" }, help: { ru: "Год защиты" }, auto: academic_year }',
    )
    label_ru = _replace(
        'topic: { type: string, label: { ru: "Тема", en: "Topic" },', 'topic: { type: string, label: { ru: "Тема" },'
    )

    broken = _lint(tmp_path / "a", help_ru, label_ru)
    clean = _lint(tmp_path / "b")

    found = {f.pointer: f for f in _found(broken, "translation-missing")}
    assert set(found) == {"/meta_fields/year/help", "/meta_fields/topic/label"}
    assert all(f.severity == "warning" for f in found.values())
    assert "en" in found["/meta_fields/year/help"].message
    assert "translation-missing" not in _ids(clean)


def test__translation_missing__an_absent_hint_is_not_a_gap(tmp_path: Path) -> None:
    assert "translation-missing" not in _ids(_lint(tmp_path))


# ── вводные без влияния и пределы ────────────────────────────────────────────


def test__dimension_no_effect__is_info_for_a_select_nothing_reads(tmp_path: Path) -> None:
    result = _lint(tmp_path)

    (item,) = [f for f in _found(result, "dimension-no-effect") if f.pointer == "/meta_fields/stage"]
    assert item.severity == "info"


def test__atlas_skipped__a_table_over_the_limit_leaves_only_the_static_rules(tmp_path: Path) -> None:
    result = _lint(tmp_path, _replace('equals: "yes" }', 'equals: "maybe" }'), limit=2)

    assert result.atlas_skipped
    assert result.universe is None
    assert "atlas-skipped" in _ids(result)
    assert "visible-if-value-not-in-options" in _ids(result)
    assert not {"route-step-without-person", "document-never-active"} & _ids(result)
    (skipped,) = _found(result, "atlas-skipped")
    assert skipped.severity == "info"


def test__scan_atlas__too_large_raises_before_any_row_is_calculated(tmp_path: Path) -> None:
    version = load_synthetic(tmp_path)

    with pytest.raises(AtlasTooLarge):
        scan_atlas(version, auto_examples(version)[0], TODAY, limit=1)


# ── общие приёмы ─────────────────────────────────────────────────────────────


def test__limit_per_rule__glues_repeats_and_cuts_the_tail() -> None:
    def make(pointer: str) -> LintFinding:
        return LintFinding("translation-missing", "warning", "m", "h", "version.yaml", pointer)

    items = [make("/a"), make("/a"), *(make(f"/p{i}") for i in range(10))]

    kept = limit_per_rule(items, limit=4)

    assert [f.pointer for f in kept] == ["/a", "/p0", "/p1", "/p2"]


def test__findings__are_ordered_errors_first(tmp_path: Path) -> None:
    result = _lint(tmp_path, _replace('equals: "yes" }', 'equals: "maybe" }'))

    severities = [f.severity for f in result.findings]
    assert severities == sorted(severities, key=["error", "warning", "info"].index)
    assert severities[0] == "error"


# ── реальные паки ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def repo() -> YamlTemplateRepository:
    return YamlTemplateRepository(_PACKS)


def _real(repo: YamlTemplateRepository, ref: tuple[str, str, str]) -> OutcomeLint:
    version = repo.get_version(*ref)
    assert version is not None
    folder = _PACKS / ref[0] / "templates" / ref[1] / "versions" / ref[2]
    texts = {"version.yaml": (folder / "version.yaml").read_text(encoding="utf-8")}
    texts.update(
        {f"files/{d.parent.name}/doc.yaml": d.read_text(encoding="utf-8") for d in folder.glob("files/*/doc.yaml")}
    )
    return lint_outcome(version, texts, auto_examples(version)[0], TODAY)


def _count(result: OutcomeLint) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in result.findings:
        counts[item.rule_id] = counts.get(item.rule_id, 0) + 1
    return counts


def test__real_vkr__known_findings_and_no_errors(repo: YamlTemplateRepository) -> None:
    result = _real(repo, ("hse-cs-se", "vkr", "2026.1.2"))

    assert result.errors == 0
    assert _count(result) == {"slot-never-routed": 1, "route-step-without-person": 5, "translation-missing": 6}
    assert result.universe is not None
    assert len(result.universe.rows) == 864
    gap = _found(result, "slot-never-routed")[0]
    assert "co_supervisor" in gap.message
    assert gap.pointer == "/signatures/slots/2"
    final = next(f for f in _found(result, "route-step-without-person") if f.elements[0].id == "final")
    assert final.witnesses[0]["supervisor"] == "none"


def test__real_hse_cs_se_coursework__seven_warnings_like_the_design_says(repo: YamlTemplateRepository) -> None:
    result = _real(repo, ("hse-cs-se", "coursework", "2026.1.2"))

    assert result.errors == 0
    counts = _count(result)
    assert counts["slot-never-routed"] == 2
    assert counts["translation-missing"] == 5
    assert result.warnings == 7


def test__real_sse_coursework__latest_version_has_only_the_step_warning(repo: YamlTemplateRepository) -> None:
    result = _real(repo, ("hse-cs-sse", "coursework", "2026.1.6"))

    assert result.errors == 0
    assert _count(result) == {"route-step-without-person": 1, "dimension-no-effect": 2}


def test__real_pp__is_clean(repo: YamlTemplateRepository) -> None:
    result = _real(repo, ("hse-cs-se", "pp", "2026.1.1"))

    assert result.findings == ()


def _all_rule_ids(findings: Iterable[LintFinding]) -> set[str]:
    return {f.rule_id for f in findings}


def test__every_finding_rule_is_in_the_rule_table(repo: YamlTemplateRepository) -> None:
    result = _real(repo, ("hse-cs-se", "vkr", "2026.1.2"))

    assert _all_rule_ids(result.findings) <= RULE_IDS


def test__observer__rows_and_rules_of_a_real_atlas_are_consistent(repo: YamlTemplateRepository) -> None:
    version = repo.get_version("hse-cs-sse", "coursework", "2026.1.6")
    assert version is not None
    scan = scan_atlas(version, auto_examples(version)[0], TODAY)

    universe = scan.universe
    assert len(universe.rows) == scan.atlas.rows_total == len(universe.row_cells)
    assert universe.dimensions == tuple(d.input for d in scan.atlas.dimensions)
    assert all(rule.possible for rule in universe.rules)
    assert isinstance(scan.observation.findings, tuple)
    assert RuleRef("manifest", "version.yaml", "/pack_submission/profiles/0/signing_slots/1/when") in {
        r.rule for r in universe.rules
    }
    assert AtlasObserver  # класс публичен для служб
