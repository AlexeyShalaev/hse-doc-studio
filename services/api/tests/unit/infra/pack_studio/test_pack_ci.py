"""Срез T18 (template-studio.md, 4.4): разбор лоадером в `pack check` и `pack ci init` для репозитория паков."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from hse_doc_studio import __version__
from hse_doc_studio.cli import main
from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.infra.pack_studio.ci_init import (
    PackCiError,
    PackCiProvider,
    detect_branch,
    normalize_packs_path,
    render_pack_ci,
)
from hse_doc_studio.infra.template.releases import freeze

_VERSION = """\
id: "2026.1"
status: stable
langs: [ru]
"""


def _pack(root: Path, *, pack_id: str = "demo", template_id: str = "report", frozen: bool = False) -> Path:
    template = root / "demo" / "templates" / "report"
    version = template / "versions" / "2026.1"
    (version / "files").mkdir(parents=True)
    (version / "files" / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8", newline="\n")
    (version / "version.yaml").write_text(_VERSION, encoding="utf-8", newline="\n")
    (template / "template.yaml").write_text(f"id: {template_id}\nname: {{ ru: Отчёт, en: Report }}\n", encoding="utf-8")
    (root / "demo" / "pack.yaml").write_text(f"id: {pack_id}\n", encoding="utf-8", newline="\n")
    if frozen:
        freeze(template, "2026.1", TemplateUpdateClass.major)
    return template


def _check(capsys: pytest.CaptureFixture[str], *argv: str | Path) -> tuple[int, dict]:
    code = main(["pack", "check", *map(str, argv), "--json"])
    return code, json.loads(capsys.readouterr().out)


def _load_findings(report: dict) -> list[dict]:
    return [f for f in report["findings"] if f["check"] == "load"]


# ── pack check: лоадер ──


def test_check_loads_a_clean_pack_without_findings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _pack(tmp_path)

    code, report = _check(capsys, tmp_path)

    assert code == 0, report
    assert _load_findings(report) == []


def test_check_reports_a_version_the_loader_drops(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    template = _pack(tmp_path)
    manifest = template / "versions" / "2026.1" / "version.yaml"
    manifest.write_text(_VERSION + "manifest_format: 99\n", encoding="utf-8", newline="\n")

    code, report = _check(capsys, tmp_path)

    assert code == 1
    found = _load_findings(report)
    assert [f["severity"] for f in found] == ["warning", "error"]
    assert "manifest format is newer" in found[0]["message"]
    assert "версии не будет в каталоге" in found[1]["message"]
    assert found[1]["path"].endswith("2026.1")


def test_check_reports_ids_that_differ_from_folder_names(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _pack(tmp_path, pack_id="other", template_id="paper")

    code, report = _check(capsys, tmp_path)

    assert code == 1
    messages = [f["message"] for f in _load_findings(report) if f["severity"] == "error"]
    assert any("id пака 'other'" in m for m in messages)
    assert any("id шаблона 'paper'" in m for m in messages)


def test_check_reports_a_pack_manifest_the_loader_cannot_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _pack(tmp_path)
    (tmp_path / "demo" / "pack.yaml").write_text("name: no id\n", encoding="utf-8")

    code, report = _check(capsys, tmp_path / "demo")

    assert code == 1
    assert any("пака не будет в каталоге" in f["message"] for f in _load_findings(report))


def test_lint_does_not_run_the_loader(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _pack(tmp_path, pack_id="other")

    code = main(["pack", "lint", str(tmp_path), "--json"])
    report = json.loads(capsys.readouterr().out)

    assert code == 0
    assert _load_findings(report) == []


# ── pack ci init ──


def test_github_workflow_checks_packs_in_the_studio_image(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "packs").mkdir()

    code = main(["pack", "ci", "init", str(tmp_path), "--branch", "trunk"])

    assert code == 0
    target = tmp_path / ".github" / "workflows" / "hse-packs.yml"
    workflow = yaml.safe_load(target.read_text(encoding="utf-8"))
    triggers = workflow[True]  # PyYAML читает ключ `on` как True
    assert set(triggers) == {"pull_request", "push", "workflow_dispatch"}
    assert triggers["push"]["branches"] == ["trunk"]
    assert workflow["permissions"] == {"contents": "read"}
    steps = workflow["jobs"]["check"]["steps"]
    run = steps[-1]["run"]
    assert f"ghcr.io/alexeyshalaev/hse-doc-studio:{__version__}" in run
    assert "hse-doc-studio pack check packs" in run
    assert '--base "origin/${GITHUB_BASE_REF}"' in run
    assert "GITHUB_BASE_REF" in steps[1]["run"]
    assert "warning" not in capsys.readouterr().out


def test_gitlab_job_compares_with_the_target_branch(tmp_path: Path) -> None:
    code = main(["pack", "ci", "init", str(tmp_path), "--provider", "gitlab", "--packs-path", "./my/packs/"])

    assert code == 0
    config = yaml.safe_load((tmp_path / ".gitlab-ci.yml").read_text(encoding="utf-8"))
    job = config["hse-packs"]
    assert job["image"]["name"].startswith("ghcr.io/alexeyshalaev/hse-doc-studio:")
    assert job["image"]["entrypoint"] == [""]
    script = "\n".join(job["script"])
    assert "hse-doc-studio pack check my/packs --base FETCH_HEAD" in script
    assert "CI_MERGE_REQUEST_TARGET_BRANCH_NAME" in script


def test_existing_file_needs_force_and_stdout_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ci = tmp_path / ".gitlab-ci.yml"
    ci.write_text("my-job:\n  script: [true]\n", encoding="utf-8")

    assert main(["pack", "ci", "init", str(tmp_path), "--provider", "gitlab"]) == 1
    assert "--force" in capsys.readouterr().err
    assert ci.read_text(encoding="utf-8").startswith("my-job")

    assert main(["pack", "ci", "init", str(tmp_path), "--provider", "gitlab", "--stdout", "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["path"] == ".gitlab-ci.yml"
    assert "hse-packs:" in printed["content"]
    assert ci.read_text(encoding="utf-8").startswith("my-job")

    assert (
        main(["pack", "ci", "init", str(tmp_path), "--provider", "gitlab", "--force", "--image", "reg.example/s:1"])
        == 0
    )
    assert "reg.example/s:1" in ci.read_text(encoding="utf-8")


@pytest.mark.parametrize("raw", ["../packs", "/abs", "pa cks", "-x", "a/../../b", "p'q"])
def test_unsafe_packs_path_is_a_usage_error(raw: str) -> None:
    with pytest.raises(PackCiError) as exc:
        normalize_packs_path(raw)
    assert exc.value.code == "usage"


@pytest.mark.parametrize(("raw", "expected"), [("packs", "packs"), ("./packs/", "packs"), ("", "."), ("a\\b", "a/b")])
def test_packs_path_is_normalized(raw: str, expected: str) -> None:
    assert normalize_packs_path(raw) == expected


@pytest.mark.parametrize(("image", "branch"), [("Bad Image", "main"), ("ghcr.io/x:1", "a b"), ("ghcr.io/x:1", "-f")])
def test_unsafe_image_or_branch_is_refused(image: str, branch: str) -> None:
    with pytest.raises(PackCiError):
        render_pack_ci(PackCiProvider.github, image=image, packs_path="packs", branch=branch)


def test_usage_errors_exit_with_code_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["pack", "ci", "init", str(tmp_path / "missing")]) == 2
    assert main(["pack", "ci", "init", str(tmp_path), "--packs-path", "../x", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "usage"


def test_branch_is_taken_from_the_repository(tmp_path: Path) -> None:
    assert detect_branch(tmp_path) == "main"  # не репозиторий git
    subprocess.run(["git", "init", "-q", "-b", "trunk", str(tmp_path)], check=True)
    assert detect_branch(tmp_path) == "trunk"


def test_frozen_pack_passes_check_with_the_generated_command(tmp_path: Path) -> None:
    """Ровно та команда, что в файле CI, проходит на чистом паке."""
    _pack(tmp_path / "packs", frozen=True)
    ci_file = render_pack_ci(PackCiProvider.github, image="ghcr.io/x:1", packs_path="packs", branch="main")
    assert "pack check packs" in ci_file.content
    assert main(["pack", "check", str(tmp_path / "packs")]) == 0
