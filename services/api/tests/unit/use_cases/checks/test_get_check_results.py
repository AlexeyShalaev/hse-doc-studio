from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.services import CheckResolutionService
from hse_doc_studio.core.value_objects import (
    CheckLocation,
    CheckResult,
    ChecksOverride,
)
from hse_doc_studio.use_cases.checks.get_check_results import GetCheckResultsUC

from tests.factories import (
    make_check_rule,
    make_document,
    make_document_definition,
    make_project,
    make_template_version,
)


class _StubTemplateRepo:
    def __init__(self, version: TemplateVersion) -> None:
        self._version = version

    def get_version(self, pack_id: str, template_id: str, version: str) -> TemplateVersion:
        return self._version


class _StubFileRepo:
    def __init__(self, files: dict[str, str] | None = None) -> None:
        self._files = files or {}

    def read(self, folder: object, path: str) -> bytes:
        if path not in self._files:
            raise FileNotFoundError(path)
        return self._files[path].encode("utf-8")


def _make_uc(
    version: TemplateVersion,
    file_repo: _StubFileRepo | None = None,
) -> GetCheckResultsUC:
    return GetCheckResultsUC(
        project_repo=None,  # type: ignore[arg-type]
        project_index_repo=None,  # type: ignore[arg-type]
        template_repo=_StubTemplateRepo(version),  # type: ignore[arg-type]
        check_resolution_service=CheckResolutionService(),
        file_repo=file_repo or _StubFileRepo(),  # type: ignore[arg-type]
        compile_repo=None,  # type: ignore[arg-type]
    )


def _version_with_rule(severity: CheckSeverity) -> TemplateVersion:
    return make_template_version(
        documents=(make_document_definition("vkr"),),
        rules=(make_check_rule("r1", applies_to=["vkr"], severity=severity),),
    )


def _finding(severity: CheckSeverity) -> CheckResult:
    return CheckResult(
        rule_id="r1",
        severity=severity,
        message="x",
        location=CheckLocation(file="vkr/main.tex", line=3),
    )


def test__reresolve_severities__doc_override_present__severity_remapped() -> None:
    version = _version_with_rule(CheckSeverity.err)
    doc = replace(
        make_document("vkr"),
        checks_override=ChecksOverride(severity_override={"r1": CheckSeverity.warn}),
    )
    project = make_project(documents=[doc])

    out = _make_uc(version)._reresolve_severities(project, doc, [_finding(CheckSeverity.err)])

    assert out[0].severity == CheckSeverity.warn


def test__reresolve_severities__override_cleared__severity_resets_to_rule_default() -> None:
    # Finding was stored as `warn` (an override was active at compile time);
    # the override is now cleared, so it must re-resolve to the default `err`.
    version = _version_with_rule(CheckSeverity.err)
    doc = make_document("vkr")
    project = make_project(documents=[doc])

    out = _make_uc(version)._reresolve_severities(project, doc, [_finding(CheckSeverity.warn)])

    assert out[0].severity == CheckSeverity.err


def test__reresolve_severities__rule_disabled__keeps_stored_severity() -> None:
    version = _version_with_rule(CheckSeverity.err)
    doc = replace(make_document("vkr"), checks_override=ChecksOverride(disabled=("r1",)))
    project = make_project(documents=[doc])
    stored = _finding(CheckSeverity.err)

    out = _make_uc(version)._reresolve_severities(project, doc, [stored])

    assert out[0] is stored


def test__filter_suppressed__line_has_matching_noqa__finding_dropped() -> None:
    version = _version_with_rule(CheckSeverity.err)
    project = make_project(documents=[make_document("vkr")])
    file_repo = _StubFileRepo({"vkr/main.tex": "line1\nline2\n\\foo % hse-noqa: r1"})

    out = _make_uc(version, file_repo)._filter_suppressed(project, [_finding(CheckSeverity.err)])

    assert out == []


def test__filter_suppressed__noqa_targets_other_rule__finding_kept() -> None:
    version = _version_with_rule(CheckSeverity.err)
    project = make_project(documents=[make_document("vkr")])
    file_repo = _StubFileRepo({"vkr/main.tex": "line1\nline2\n\\foo % hse-noqa: other"})
    finding = _finding(CheckSeverity.err)

    out = _make_uc(version, file_repo)._filter_suppressed(project, [finding])

    assert out == [finding]


def test__filter_suppressed__source_file_unreadable__finding_kept() -> None:
    version = _version_with_rule(CheckSeverity.err)
    project = make_project(documents=[make_document("vkr")])
    finding = _finding(CheckSeverity.err)

    # Empty stub repo -> read raises -> best-effort keeps the finding.
    out = _make_uc(version)._filter_suppressed(project, [finding])

    assert out == [finding]


def _scoped(file: str | None) -> CheckResult:
    loc = CheckLocation(file=file, line=1) if file is not None else None
    return CheckResult(rule_id="r1", severity=CheckSeverity.err, message=file or "doc-level", location=loc)


def test__filter_by_document_scope__own_and_imported_files__kept_others_dropped(tmp_path: Path) -> None:
    # Real files on disk: vkr/main.tex \inputs sections/intro; tp/tp.tex is a
    # different document and must be filtered out.
    (tmp_path / "vkr" / "sections").mkdir(parents=True)
    (tmp_path / "vkr" / "main.tex").write_text(
        "\\documentclass{article}\n\\input{sections/intro}\n\\begin{document}\nhi\n\\end{document}\n",
        encoding="utf-8",
    )
    (tmp_path / "vkr" / "sections" / "intro.tex").write_text("intro body\n", encoding="utf-8")
    (tmp_path / "tp").mkdir()
    (tmp_path / "tp" / "tp.tex").write_text("other document\n", encoding="utf-8")

    version = _version_with_rule(CheckSeverity.err)
    doc = make_document("vkr")
    project = make_project(documents=[doc], folder=tmp_path)

    own = _scoped("vkr/main.tex")
    imported = _scoped("vkr/sections/intro.tex")
    other = _scoped("tp/tp.tex")
    fileless = _scoped(None)

    out = _make_uc(version)._filter_by_document_scope(project, doc, [own, imported, other, fileless])

    assert out == [own, imported, fileless]


def test__filter_by_document_scope__non_tex_project_artifact__kept(tmp_path: Path) -> None:
    # file_exists findings point at project-level artifacts (.hse-studio/…)
    # that are never in the document's \input set — they must survive the
    # document scope, otherwise the tab shows nothing while the doc status
    # still says «с замечаниями».
    (tmp_path / "vkr").mkdir(parents=True)
    (tmp_path / "vkr" / "main.tex").write_text("\\begin{document}hi\\end{document}\n", encoding="utf-8")

    version = _version_with_rule(CheckSeverity.err)
    doc = make_document("vkr")
    project = make_project(documents=[doc], folder=tmp_path)

    artifact = _scoped(".hse-studio/forms/ai_declaration.json")
    other_tex = _scoped("tp/tp.tex")

    out = _make_uc(version)._filter_by_document_scope(project, doc, [artifact, other_tex])

    assert out == [artifact]


def test__filter_by_document_scope__doc_missing_from_template__fails_open_keeps_finding(tmp_path: Path) -> None:
    # Doc id absent from the template version -> can't resolve a source file ->
    # pass results through rather than hiding everything.
    version = _version_with_rule(CheckSeverity.err)
    doc = make_document("unknown")
    project = make_project(documents=[doc], folder=tmp_path)
    finding = _scoped("tp/tp.tex")

    out = _make_uc(version)._filter_by_document_scope(project, doc, [finding])

    assert out == [finding]
