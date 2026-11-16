"""`pack check`: файлы сценариев, линтер результата и прогон сценариев (срез O8, `infra/pack_studio/outcome_check.py`).

Решение владельца: нарушение формата файла сценария это ошибка (Студия его не прочитает), упавший сценарий и
вводные, не подходящие версии, это предупреждения; ошибки линтера в выпущенной версии тоже предупреждения."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hse_doc_studio.cli import main
from hse_doc_studio.infra.pack_studio.layout import discover
from hse_doc_studio.infra.pack_studio.outcome_check import OutcomeCheck, check_outcome
from hse_doc_studio.infra.template.releases import ReleaseEntry

from tests.unit.use_cases.pack_studio.outcome.synthetic import VERSION_YAML, load_synthetic

_OK = """\
format: 1
name: { ru: Сценарий, en: Scenario }
versions: ["1.*"]
inputs:
  kind: project
assertions:
  - { kind: participant_present, persona: author, present: true }
"""


def _template(tmp_path: Path, version_yaml: str = VERSION_YAML) -> Path:
    load_synthetic(tmp_path, version_yaml=version_yaml)
    template = tmp_path / "p" / "templates" / "t"
    (template / "scenarios").mkdir()
    return template


def _scenario(template: Path, name: str, text: str) -> None:
    (template / "scenarios" / f"{name}.yaml").write_text(text, encoding="utf-8")


def _check(tmp_path: Path, released: dict[str, ReleaseEntry] | None = None) -> OutcomeCheck:
    return check_outcome(discover([tmp_path]), lambda _t: released or {}, jinja=False)


def _by(result: OutcomeCheck, check: str, severity: str) -> list[str]:
    return [m for s, c, _p, m in result.findings if (c, s) == (check, severity)]


def test__valid_scenario__passes_and_is_summarised_with_coverage(tmp_path: Path) -> None:
    template = _template(tmp_path)
    _scenario(template, "ok", _OK)

    result = _check(tmp_path)

    assert _by(result, "scenario", "error") == []
    assert _by(result, "scenario", "warning") == []
    (summary,) = result.summaries
    assert (summary.template, summary.version) == ("p/t", "1.0.0")
    assert (summary.scenarios, summary.passed, summary.failed) == (1, 1, 0)
    assert summary.rules_total > 0
    assert 0 < summary.percent <= 100
    assert summary.rows_total > 0
    assert summary.rows_touched == 1
    assert summary.to_dict()["coverage"]["percent"] == summary.percent


@pytest.mark.parametrize(
    ("name", "text", "mention"),
    [
        ("ok", _OK.replace("format: 1", "format: 2"), "format"),
        ("ok", _OK.replace("kind: participant_present", "kind: made_up"), "kind"),
        ("ok", _OK + "extra: 1\n", "extra"),
        ("ok", "format: 1\nname: [\n", "YAML"),
        ("Bad_Name", _OK, "имя файла"),
    ],
)
def test__format_violations__are_errors(tmp_path: Path, name: str, text: str, mention: str) -> None:
    template = _template(tmp_path)
    _scenario(template, name, text)

    result = _check(tmp_path)

    errors = _by(result, "scenario", "error")
    assert errors
    assert any(mention in e for e in errors), errors


def test__failing_assertion__is_a_warning_not_an_error(tmp_path: Path) -> None:
    template = _template(tmp_path)
    _scenario(template, "wrong", _OK.replace("present: true", "present: false"))

    result = _check(tmp_path)

    assert _by(result, "scenario", "error") == []
    (warning,) = _by(result, "scenario", "warning")
    assert "сценарий wrong на 1.0.0" in warning
    assert "participant_present" in warning
    assert result.summaries[0].failed == 1


def test__snapshot_mismatch__is_a_warning_with_the_changes(tmp_path: Path) -> None:
    template = _template(tmp_path)
    _scenario(
        template,
        "snap",
        _OK + "snapshot:\n  documents: { report: absent }\n  participants: [author]\n  meta_visible: []\n  points: []\n"
        "  sections: []\n",
    )

    result = _check(tmp_path)

    (warning,) = _by(result, "scenario", "warning")
    assert "snapshot" in warning
    assert "документ report" in warning


def test__inputs_that_do_not_fit_the_version__are_a_warning(tmp_path: Path) -> None:
    template = _template(tmp_path)
    _scenario(template, "typo", _OK.replace("kind: project", "kind: reserch"))

    result = _check(tmp_path)

    assert _by(result, "scenario", "error") == []
    (warning,) = _by(result, "scenario", "warning")
    assert "вводные не подходят" in warning
    assert "reserch" in warning
    assert result.summaries[0].errors == 1


def test__versions_matching_nothing__is_a_warning(tmp_path: Path) -> None:
    template = _template(tmp_path)
    _scenario(template, "old", _OK.replace('["1.*"]', '["2030.*"]'))

    result = _check(tmp_path)

    (warning,) = _by(result, "scenario", "warning")
    assert "ни одна версия" in warning
    assert result.summaries == []


def test__outcome_errors__in_a_draft_stay_errors_and_in_a_released_version_become_warnings(tmp_path: Path) -> None:
    broken = VERSION_YAML.replace('equals: "yes" }', 'equals: "maybe" }')
    _template(tmp_path, broken)

    draft = _check(tmp_path)
    frozen = _check(tmp_path, {"1.0.0": ReleaseEntry("1.0.0", "sha256:" + "0" * 64, None)})

    assert any("[visible-if-value-not-in-options]" in m for m in _by(draft, "outcome", "error"))
    assert not _by(frozen, "outcome", "error")
    assert any("выпущенная версия неизменна" in m for m in _by(frozen, "outcome", "warning"))


def test__info_findings__are_not_printed(tmp_path: Path) -> None:
    _template(tmp_path)

    result = _check(tmp_path)

    assert not any("[dimension-no-effect]" in m for *_x, m in result.findings)


def test__cli__format_error_fails_the_run_and_a_failing_scenario_only_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    template = _template(tmp_path)
    _scenario(template, "wrong", _OK.replace("present: true", "present: false"))

    code = main(["pack", "check", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    report, _ = json.JSONDecoder().raw_decode(out[out.index("{") :])
    scenario = [f for f in report["findings"] if f["check"] == "scenario"]

    assert [f["severity"] for f in scenario] == ["warning"]
    assert report["scenarios"][0]["failed"] == 1
    assert main(["pack", "check", str(tmp_path), "--strict", "--json"]) == 1
    capsys.readouterr()
    _scenario(template, "broken", _OK.replace("format: 1", "format: 9"))
    assert main(["pack", "check", str(tmp_path), "--json"]) == 1
    assert code in {0, 1}


def test__repository_packs__scenarios_pass_and_the_outcome_check_has_no_errors() -> None:
    root = Path(__file__).resolve().parents[6] / "packs"

    result = check_outcome(discover([root]), lambda _t: {}, jinja=False)

    assert not [m for s, _c, _p, m in result.findings if s == "error"]
    assert not [m for s, c, _p, m in result.findings if c == "scenario"], "упавший сценарий в паках репозитория"
    assert {s.template for s in result.summaries} == {
        "hse-cs-se/vkr",
        "hse-cs-se/coursework",
        "hse-cs-se/pp",
        "hse-cs-sse/coursework",
    }
    assert all(s.failed == s.errors == 0 and s.passed == s.scenarios for s in result.summaries)
