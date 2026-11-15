"""Проверки и правила формой (template-studio.md, 5.7, срез T14): модель файлов правил и точечные правки."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from hse_doc_studio.core.pack_studio.checks_form import (
    ChecksConfig,
    ChecksEditError,
    ChecksHeader,
    ChecksOp,
    ChecksOpKind,
    RuleEntry,
)
from hse_doc_studio.infra.pack_studio.checks_form import PackChecksFormEditor

_REPO = Path(__file__).resolve().parents[6]
_EDITOR = PackChecksFormEditor()
_FILES = sorted((_REPO / "packs").glob("*/templates/*/versions/*/checks/*.yaml"))

_TEXT = """\
# Правила для тестов.
label:
  ru: Демо
  en: Demo
ref:
  ru: Демо-стандарт §1
  en: Demo standard §1
source:
  ru: Демо-стандарт
  url: https://example.org/demo

rules:
  # ── Поля ──
  - id: demo/page-margins
    title:       { ru: Поля, en: Margins }
    category:    formatting
    applies_to:  [report]
    default_severity: warn
    engine: structural
    params:
      check: page_geometry
      expected: { left_mm: 30, right_mm: 15, top_mm: 20, bottom_mm: 20 }
      tolerance_mm: 1
      message: { ru: "Поля не те", en: "Wrong margins" }
    review: keep   # ключ от более новой Студии

  - id: demo/intro
    title:       { ru: Введение, en: Introduction }
    applies_to:  "*"
    default_severity: err
    engine: regex
    params:
      file_glob: "report/report.tex"
      pattern: '(?i)\\\\section\\{Введение'
"""


def _rules(text: str) -> list[dict[str, object]]:
    return yaml.safe_load(text)["rules"]


@pytest.mark.parametrize("path", _FILES, ids=lambda p: "/".join(p.parts[-7:]))
def test__describe__every_checks_file_of_the_repository_reads(path: Path) -> None:
    view = _EDITOR.describe_file(path.read_text(encoding="utf-8"), path.stem)

    assert view.error is None
    assert all(rule.entry is not None for rule in view.rules)


@pytest.mark.parametrize("path", _FILES, ids=lambda p: "/".join(p.parts[-7:]))
def test__set_rule__same_values_change_nothing_byte_for_byte(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    view = _EDITOR.describe_file(text, path.stem)

    ops = [ChecksOp(ChecksOpKind.set_rule, index=r.index, rule=r.entry) for r in view.rules if r.entry]
    ops.append(ChecksOp(ChecksOpKind.set_header, header=view.header))

    assert _EDITOR.apply_file(text, ops) == text


def test__describe__header_rules_and_all_documents() -> None:
    view = _EDITOR.describe_file(_TEXT, "demo")

    assert view.header.label == {"ru": "Демо", "en": "Demo"}
    assert view.header.source == {"ru": "Демо-стандарт"}
    assert view.header.url == "https://example.org/demo"
    margins, intro = (r.entry for r in view.rules)
    assert margins is not None
    assert intro is not None
    assert margins.applies_to == ("report",)
    assert intro.applies_to is None
    assert margins.params["expected"] == {"left_mm": 30, "right_mm": 15, "top_mm": 20, "bottom_mm": 20}


def test__set_rule__param_change_keeps_comments_message_and_unknown_key() -> None:
    rule = _EDITOR.describe_file(_TEXT, "demo").rules[0].entry
    assert rule is not None
    changed = replace(rule, params={**rule.params, "tolerance_mm": 2}, default_severity="err")

    text = _EDITOR.apply_file(_TEXT, [ChecksOp(ChecksOpKind.set_rule, index=0, rule=changed)])

    assert text == _TEXT.replace("tolerance_mm: 1", "tolerance_mm: 2").replace(
        "default_severity: warn", "default_severity: err"
    )


def test__add_rule__new_rule_at_the_end_in_pack_key_order() -> None:
    rule = RuleEntry(
        id="demo/conclusion",
        title={"ru": "Заключение", "en": "Conclusion"},
        description={},
        category="structure",
        applies_to=("report",),
        default_severity="warn",
        engine="regex",
        params={"file_glob": "report/report.tex", "pattern": "Заключение"},
    )

    text = _EDITOR.apply_file(_TEXT, [ChecksOp(ChecksOpKind.add_rule, rule=rule)])

    added = _rules(text)[2]
    assert list(added) == ["id", "title", "category", "applies_to", "default_severity", "engine", "params"]
    assert "  - id: demo/conclusion\n    title: { ru: Заключение, en: Conclusion }\n" in text
    assert text.startswith(_TEXT.rstrip("\n"))


def test__move_and_remove_rule_keep_comment_with_its_rule() -> None:
    text = _EDITOR.apply_file(_TEXT, [ChecksOp(ChecksOpKind.move_rule, index=0, to=1)])

    assert [r["id"] for r in _rules(text)] == ["demo/intro", "demo/page-margins"]
    assert "  # ── Поля ──\n  - id: demo/page-margins\n" in text
    removed = _EDITOR.apply_file(text, [ChecksOp(ChecksOpKind.remove_rule, index=1)])
    assert [r["id"] for r in _rules(removed)] == ["demo/intro"]
    assert "── Поля ──" not in removed


def test__set_header__label_and_source_in_place() -> None:
    header = ChecksHeader({"ru": "Демо 2", "en": "Demo 2"}, {"ru": "§2", "en": "§2"}, {"ru": "Новый"}, None)

    text = _EDITOR.apply_file(_TEXT, [ChecksOp(ChecksOpKind.set_header, header=header)])

    data = yaml.safe_load(text)
    assert data["label"] == {"ru": "Демо 2", "en": "Demo 2"}
    assert data["source"] == {"ru": "Новый"}
    assert "# Правила для тестов.\n" in text


def test__apply__header_without_translation_is_refused() -> None:
    header = ChecksHeader({"ru": "Демо"}, {"ru": "§1", "en": "§1"}, {}, None)

    with pytest.raises(ChecksEditError, match="label"):
        _EDITOR.apply_file(_TEXT, [ChecksOp(ChecksOpKind.set_header, header=header)])


def test__apply__repeated_id_is_refused() -> None:
    rule = _EDITOR.describe_file(_TEXT, "demo").rules[0].entry
    assert rule is not None

    with pytest.raises(ChecksEditError, match="repeated"):
        _EDITOR.apply_file(_TEXT, [ChecksOp(ChecksOpKind.add_rule, rule=rule)])


def test__apply__unknown_engine_or_severity_is_refused() -> None:
    rule = _EDITOR.describe_file(_TEXT, "demo").rules[1].entry
    assert rule is not None

    with pytest.raises(ChecksEditError, match="engine"):
        _EDITOR.apply_file(_TEXT, [ChecksOp(ChecksOpKind.set_rule, index=1, rule=replace(rule, engine="magic"))])
    with pytest.raises(ChecksEditError, match="severity"):
        _EDITOR.apply_file(
            _TEXT, [ChecksOp(ChecksOpKind.set_rule, index=1, rule=replace(rule, default_severity="fatal"))]
        )


def test__first_rule_of_an_empty_file() -> None:
    rule = RuleEntry("new/one", {"ru": "Одно", "en": "One"}, {}, None, None, "info", "file_exists", {"path": "a.tex"})
    empty = 'label: { ru: "Новое", en: "New" }\nref: { ru: "§1", en: "§1" }\n'

    text = _EDITOR.apply_file(empty, [ChecksOp(ChecksOpKind.add_rule, rule=rule)])

    assert _rules(text) == [
        {
            "id": "new/one",
            "title": {"ru": "Одно", "en": "One"},
            "applies_to": "*",
            "default_severity": "info",
            "engine": "file_exists",
            "params": {"path": "a.tex"},
        }
    ]


def test__config__written_in_place_and_created_when_missing() -> None:
    manifest = 'id: "1"\nchecks_version:\n  disabled_categories: []\n  disabled: []\n  severity_override: {}\n'
    config = ChecksConfig(("typography",), ("demo/intro",), {"demo/page-margins": "err"})

    text = _EDITOR.apply_config(manifest, config)

    assert text == (
        'id: "1"\nchecks_version:\n  disabled_categories: [typography]\n  disabled: [demo/intro]\n'
        "  severity_override: { demo/page-margins: err }\n"
    )
    assert _EDITOR.describe_config(text) == config
    created = _EDITOR.apply_config('id: "1"\n', ChecksConfig((), ("a/b",), {}))
    assert yaml.safe_load(created)["checks_version"] == {
        "disabled_categories": [],
        "disabled": ["a/b"],
        "severity_override": {},
    }
    with pytest.raises(ChecksEditError):
        _EDITOR.apply_config(manifest, ChecksConfig((), (), {"demo/intro": "fatal"}))
