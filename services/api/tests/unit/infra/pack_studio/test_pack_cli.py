"""`hse-doc-studio pack` (template-studio.md, 11, срез T2): lint, check, classify, new-version, freeze.

Команды гоняются через `cli.main`, как их зовёт CI: код выхода и `--json` это интерфейс для T18.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
import yaml
from hse_doc_studio.cli import main
from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.infra.pack_studio.versions import create_version, next_number, release_version
from hse_doc_studio.infra.template import pack_lint
from hse_doc_studio.infra.template.releases import freeze, load_releases

REPO_ROOT = Path(__file__).resolve().parents[6]
PACKS_ROOT = REPO_ROOT / "packs"

_VERSION = """\
# Манифест версии: комментарий шапки остаётся как есть
id: "2026.1"
released_at: 2026-09-01
status: stable
release:
  kind: major
summary:
  ru: Отчёт
  en: Report
breaking_changes:
  ru: []
  en: []

# ── заметки к версии ──
changes:
  ru:
    - "Первая версия."
  en:
    - "First version."

langs: [ru]

meta_fields:
  year:        { type: string, required_at: create }   # выровнено
"""

_TEMPLATE = """\
# Шаблон отчёта
id: report
name: { ru: Отчёт, en: Report }
default_version: "2026.1"
"""


def _template(root: Path, *, frozen: bool = True) -> Path:
    template = root / "demo" / "templates" / "report"
    version = template / "versions" / "2026.1"
    (version / "files").mkdir(parents=True)
    (version / "files" / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8", newline="\n")
    (version / "version.yaml").write_text(_VERSION, encoding="utf-8", newline="\n")
    (template / "template.yaml").write_text(_TEMPLATE, encoding="utf-8", newline="\n")
    (root / "demo" / "pack.yaml").write_text("id: demo\n", encoding="utf-8", newline="\n")
    if frozen:
        freeze(template, "2026.1", TemplateUpdateClass.major)
    return template


def _run(capsys: pytest.CaptureFixture[str], *argv: str | Path) -> tuple[int, str]:
    code = main(["pack", *map(str, argv)])
    return code, capsys.readouterr().out


def _json(capsys: pytest.CaptureFixture[str], *argv: str | Path) -> tuple[int, dict]:
    code, out = _run(capsys, *argv, "--json")
    return code, json.loads(out)


def _fill_notes(version_dir: Path) -> None:
    path = version_dir / "version.yaml"
    text = path.read_text(encoding="utf-8")
    text = text.replace("\nchanges:\n  ru: []\n  en: []\n", '\nchanges:\n  ru:\n    - "Правка."\n  en:\n    - "Fix."\n')
    path.write_text(text, encoding="utf-8", newline="\n")


# ── номер ──


@pytest.mark.parametrize(
    ("latest", "cls", "expected"),
    [
        ("2026.1.3", TemplateUpdateClass.patch, "2026.1.4"),
        ("2026.1", TemplateUpdateClass.patch, "2026.1.1"),
        ("2026.1.3", TemplateUpdateClass.minor, "2026.2.0"),
        ("2026.1.3", TemplateUpdateClass.major, "2027.1"),
    ],
)
def test_next_number_follows_the_class(latest: str, cls: TemplateUpdateClass, expected: str) -> None:
    assert next_number(latest, cls) == expected


# ── check и lint ──


def test_check_on_the_repository_packs_passes() -> None:
    """Паки репозитория проходят `pack check`: на этом стоит джоб CI (T18)."""
    assert main(["pack", "check", str(PACKS_ROOT)]) == 0


def test_check_json_reports_tree_and_class_of_drafts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    template = _template(tmp_path)
    create_version(template)
    _fill_notes(template / "versions" / "2026.1.1")

    code, report = _json(capsys, "check", tmp_path)

    assert code == 0, report
    assert report["ok"] is True
    assert report["summary"] == {"packs": 1, "templates": 1, "versions": 2, "errors": 0, "warnings": 0}
    (cls,) = report["classes"]
    assert (cls["template"], cls["version"], cls["base"]) == ("report", "2026.1.1", "2026.1")
    assert cls["minimum"] == "patch"
    assert cls["by_number"] == "patch"


def test_check_schema_error_is_an_error_in_a_draft_and_a_warning_in_a_released_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    template = _template(tmp_path, frozen=False)
    manifest = template / "versions" / "2026.1" / "version.yaml"
    manifest.write_text(_VERSION + "unknown_key: 1\n", encoding="utf-8", newline="\n")

    code, report = _json(capsys, "check", template)
    assert code == 1
    (finding,) = [f for f in report["findings"] if f["check"] == "schema"]
    assert finding["severity"] == "error"
    assert finding["path"].endswith("version.yaml")

    freeze(template, "2026.1", TemplateUpdateClass.major)
    code, report = _json(capsys, "check", template)
    assert code == 0
    (finding,) = [f for f in report["findings"] if f["check"] == "schema"]
    assert finding["severity"] == "warning"
    assert "выпущенная версия неизменна" in finding["message"]
    assert main(["pack", "check", str(template), "--strict"]) == 1


def test_check_reports_an_edited_released_version(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    template = _template(tmp_path)
    (template / "versions" / "2026.1" / "files" / "main.tex").write_text("changed\n", encoding="utf-8")

    code, out = _run(capsys, "check", tmp_path)

    assert code == 1
    assert "[releases]" in out
    assert "каталог выпущенной версии изменён" in out


def test_lint_prints_every_version_and_old_entry_delegates(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    template = _template(tmp_path)
    version_dir = template / "versions" / "2026.1"

    code, out = _run(capsys, "lint", tmp_path)
    assert code == 0
    assert f"== {version_dir}\n  ok\n" in out

    assert pack_lint.main([str(version_dir)]) == 0
    assert "  ok" in capsys.readouterr().out
    assert pack_lint.main([]) == 2


def test_missing_directory_is_a_usage_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, report = _json(capsys, "lint", tmp_path / "nope")

    assert code == 2
    assert report["ok"] is False
    assert report["error"]["code"] == "usage"


# ── classify ──


def test_classify_names_the_reasons_and_fails_on_a_too_soft_number(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    template = _template(tmp_path)
    create_version(template)
    manifest = template / "versions" / "2026.1.1" / "version.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "  udc:         { type: string, required_at: create }\n",
        encoding="utf-8",
        newline="\n",
    )

    code, report = _json(capsys, "classify", template, "2026.1", "2026.1.1")
    assert code == 1
    assert report["number_ok"] is False
    assert report["minimum"] == "minor"
    assert [r["path"] for r in report["reasons"] if r["code"] == "field_added"] == ["meta_fields.udc"]

    code, out = _run(capsys, "classify", template, "2026.1.1", "--lang", "en")
    assert code == 1
    assert "New field meta_fields.udc" in out


# ── new-version ──


def test_new_version_copies_the_latest_and_edits_only_the_draft_keys(tmp_path: Path) -> None:
    template = _template(tmp_path)

    created = create_version(template, today=date(2026, 11, 14))

    assert (created.base, created.version, created.update_class) == ("2026.1", "2026.1.1", TemplateUpdateClass.patch)
    draft = template / "versions" / "2026.1.1"
    assert (draft / "files" / "main.tex").read_bytes() == (
        template / "versions" / "2026.1" / "files" / "main.tex"
    ).read_bytes()
    expected = (
        # Кавычки у "2026.1" вынужденные (иначе число), у нового номера они не нужны: правило yaml_edits.
        _VERSION.replace('id: "2026.1"', "id: 2026.1.1")
        .replace("released_at: 2026-09-01", "released_at: 2026-11-14")
        .replace("status: stable\nrelease:\n  kind: major\n", "status: beta\n")
        .replace('\n  ru:\n    - "Первая версия."\n  en:\n    - "First version."\n', "\n  ru: []\n  en: []\n")
    )
    assert (draft / "version.yaml").read_text(encoding="utf-8") == expected
    assert load_releases(template).keys() == {"2026.1"}
    assert not [p for p in (template / "versions").iterdir() if p.name.startswith(".")]


@pytest.mark.parametrize(
    ("argv", "expected", "cls"),
    [
        (["--class", "minor"], "2026.2.0", "minor"),
        (["--class", "major"], "2027.1", "major"),
        (["--to", "2026.3.0"], "2026.3.0", "minor"),
    ],
)
def test_new_version_number_by_class_or_explicit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str], expected: str, cls: str
) -> None:
    template = _template(tmp_path)

    code, report = _json(capsys, "new-version", template, *argv)

    assert code == 0, report
    assert (report["version"], report["class"]) == (expected, cls)
    assert (template / "versions" / expected / "version.yaml").is_file()


@pytest.mark.parametrize("to", ["2026.1", "2025.9", "next"])
def test_new_version_refuses_a_taken_lower_or_bad_number(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], to: str
) -> None:
    template = _template(tmp_path)

    code, report = _json(capsys, "new-version", template, "--to", to)

    assert code == 1
    assert report["error"]["code"] == "refused"
    assert sorted(p.name for p in (template / "versions").iterdir()) == ["2026.1"]


def test_new_version_from_an_older_base_and_notes_unreleased(tmp_path: Path) -> None:
    template = _template(tmp_path)
    create_version(template)

    created = create_version(template, base="2026.1", update_class=TemplateUpdateClass.minor)

    assert (created.base, created.version) == ("2026.1", "2026.2.0")
    assert created.notes == ("уже есть невыпущенные версии: 2026.1.1",)


# ── freeze ──


def test_freeze_release_marks_the_version_and_sets_the_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    template = _template(tmp_path)
    create_version(template, today=date(2026, 11, 1))
    draft = template / "versions" / "2026.1.1"
    _fill_notes(draft)

    released = release_version(template, "2026.1.1", mark_released=True, set_default=True, today=date(2026, 11, 14))

    assert released.entry.kind is TemplateUpdateClass.patch
    assert released.previous == "2026.1"
    text = (draft / "version.yaml").read_text(encoding="utf-8")
    assert "id: 2026.1.1\nreleased_at: 2026-11-14\nstatus: stable\nrelease: { kind: patch }\nsummary:" in text
    assert yaml.safe_load(text)["release"] == {"kind": "patch"}
    assert "default_version: 2026.1.1" in (template / "template.yaml").read_text(encoding="utf-8")
    assert load_releases(template)["2026.1.1"].kind is TemplateUpdateClass.patch
    assert main(["pack", "check", str(tmp_path)]) == 0
    capsys.readouterr()


def test_freeze_without_release_refuses_a_beta_and_leaves_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    template = _template(tmp_path)
    create_version(template)
    _fill_notes(template / "versions" / "2026.1.1")
    before = (template / "releases.yaml").read_bytes()

    code = main(["pack", "freeze", str(template), "2026.1.1", "--default"])

    assert code == 1
    assert (template / "releases.yaml").read_bytes() == before
    assert 'default_version: "2026.1"' in (template / "template.yaml").read_text(encoding="utf-8")
    assert "--release" in capsys.readouterr().err


def test_freeze_rolls_back_on_lint_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    template = _template(tmp_path)
    create_version(template)  # changes пусты: линтер называет это ошибкой
    manifest = template / "versions" / "2026.1.1" / "version.yaml"
    before = manifest.read_bytes()

    code, report = _json(capsys, "freeze", template, "2026.1.1", "--release", "--default")

    assert code == 1
    assert report["error"]["code"] == "lint_failed"
    assert any("changes.ru" in e for e in report["error"]["errors"])
    assert manifest.read_bytes() == before
    assert 'default_version: "2026.1"' in (template / "template.yaml").read_text(encoding="utf-8")
    assert load_releases(template).keys() == {"2026.1"}


def test_freeze_refuses_a_kind_softer_than_the_number(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    template = _template(tmp_path)
    create_version(template, update_class=TemplateUpdateClass.minor)
    _fill_notes(template / "versions" / "2026.2.0")

    code, report = _json(capsys, "freeze", template, "2026.2.0", "--release", "--kind", "patch")

    assert code == 1
    assert "мягче номера" in report["error"]["message"]


def test_freeze_replace_only_the_newest_entry(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    template = _template(tmp_path)
    create_version(template)
    draft = template / "versions" / "2026.1.1"
    _fill_notes(draft)
    release_version(template, "2026.1.1", mark_released=True)

    code, _ = _run(capsys, "freeze", template, "2026.1.1")
    assert code == 1
    (draft / "files" / "main.tex").write_text("\\documentclass{report}\n", encoding="utf-8")
    code, report = _json(capsys, "freeze", template, "2026.1.1", "--replace")
    assert code == 0, report
    assert report["replaced"] is True
    assert main(["pack", "check", str(template)]) == 0
    capsys.readouterr()

    code, report = _json(capsys, "freeze", template, "2026.1", "--replace")
    assert code == 1
    assert "только последнюю" in report["error"]["message"]


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="нужен git")
def test_base_ref_guards_released_entries(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    template = _template(tmp_path)
    create_version(template)
    _fill_notes(template / "versions" / "2026.1.1")
    release_version(template, "2026.1.1", mark_released=True)
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")

    code, report = _json(capsys, "freeze", template, "2026.1.1", "--replace", "--base", "main")
    assert code == 1
    assert "выпущена в main" in report["error"]["message"]

    # Ветка переиздаёт выпущенную версию: каталог и запись согласованы, но база помнит другой дайджест.
    (template / "versions" / "2026.1.1" / "files" / "main.tex").write_text("x\n", encoding="utf-8")
    release_version(template, "2026.1.1", replace=True)
    assert main(["pack", "check", str(tmp_path)]) == 0
    capsys.readouterr()
    code, report = _json(capsys, "check", tmp_path, "--base", "main")
    assert code == 1
    (finding,) = [f for f in report["findings"] if f["check"] == "base"]
    assert "изменена относительно базы" in finding["message"]

    code, report = _json(capsys, "check", tmp_path, "--base", "no-such-ref")
    assert code == 2
