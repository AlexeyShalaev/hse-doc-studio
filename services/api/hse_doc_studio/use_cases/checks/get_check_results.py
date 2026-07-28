from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.check_suppression import line_suppresses_rule
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import CompileStatus
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IFileRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import CheckResolutionService, ProjectTemplateService
from hse_doc_studio.core.value_objects import CheckResult, ChecksOverride
from hse_doc_studio.infra.checks.utils import expand_inputs
from hse_doc_studio.infra.persistence.compile import JsonCompileRepository
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class GetCheckResultsInput:
    project_id: UUID
    doc_id: str
    # When True, keep only findings located in the document's own source file or
    # a file it transitively imports (\input/\include/\subfile). Used by the
    # «Проверки» tab so a document shows only its own issues, not every finding
    # in the project. Off by default so other consumers (e.g. the editor's
    # cross-file diagnostics) keep seeing the full set.
    scope_to_document: bool = False


@dataclass
class GetCheckResultsOutput:
    compile_id: UUID | None
    results: list[CheckResult]


class GetCheckResultsUC:
    """Return the check results from the document's most recent compile.

    Uses `doc.last_compile_id` as the source of truth — TriggerCompileUC keeps
    that field pointed at the latest compile (success or failure). When no
    compile has run yet, returns empty.

    Severities are *re-resolved* against the current override chain on read, so
    changing a rule's severity (or resetting it) is reflected on the stored
    findings immediately, without waiting for the next compile. Findings whose
    rule is now disabled keep their stored severity (the UI greys them).
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        check_resolution_service: CheckResolutionService,
        file_repo: IFileRepository,
        compile_repo: JsonCompileRepository,
    ) -> None:
        self._get_project_uc = GetProjectUC(project_repo, project_index_repo)
        self._template_repo = template_repo
        self._check_resolution_service = check_resolution_service
        self._template_service = ProjectTemplateService()
        self._file_repo = file_repo
        self._compile_repo = compile_repo

    async def execute(self, inp: GetCheckResultsInput) -> GetCheckResultsOutput:
        project_result = await self._get_project_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = project_result.project

        doc = next((d for d in project.documents if d.id == inp.doc_id), None)
        if doc is None:
            raise NotFoundError(
                localized_error(
                    f"Документ {inp.doc_id!r} не найден в проекте {inp.project_id}",
                    f"Document {inp.doc_id!r} not found in project {inp.project_id}",
                )
            )

        if doc.last_compile_id is None:
            return GetCheckResultsOutput(compile_id=None, results=[])

        record = self._compile_repo.get_for_project(project.folder, doc.last_compile_id)
        if record is None:
            logger.warning(
                "GetCheckResultsUC: last_compile_id points to a missing record",
                project_id=str(inp.project_id),
                doc_id=inp.doc_id,
                compile_id=str(doc.last_compile_id),
            )
            return GetCheckResultsOutput(compile_id=None, results=[])

        # While a build runs, `last_compile_id` already points at the in-flight
        # record, which has no check results yet. Serve the most recent
        # finished record instead, so the «Проверки» tab keeps the last known
        # findings during the build rather than flashing empty/0%.
        if record.status in (CompileStatus.pending, CompileStatus.running):
            finished = [
                r
                for r in self._compile_repo.list_for_document(project.folder, inp.doc_id)
                if r.status in (CompileStatus.success, CompileStatus.failure)
            ]
            if finished:
                record = finished[-1]

        results = self._reresolve_severities(project, doc, list(record.check_results))
        results = self._filter_suppressed(project, results)
        if inp.scope_to_document:
            results = self._filter_by_document_scope(project, doc, results)

        return GetCheckResultsOutput(compile_id=record.id, results=results)

    def _filter_by_document_scope(
        self,
        project: Project,
        doc: Document,
        results: list[CheckResult],
    ) -> list[CheckResult]:
        """Keep only findings located in the document's own file or a file it
        imports (its transitive \\input/\\include/\\subfile set). File-level
        findings (no location) are always kept.

        Fails open: if the document's source file or its import set can't be
        determined, results pass through unchanged so nothing is hidden by
        accident (a too-broad list is recoverable; a silently-empty tab is not).
        """
        version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        if version is None:
            return results
        try:
            source_file, _output = self._template_service.resolve_instance_source(project, doc, version)
        except (ValueError, NotFoundError):
            return results

        allowed = self._document_file_set(project.folder, source_file)
        if not allowed:
            return results

        # Scoping constrains only findings located in .tex sources. Findings
        # pointing at non-.tex artifacts (`.hse-studio/…` from file_exists,
        # project.json, .bib) are project-level results of THIS document's own
        # rule run — dropping them would empty the «Проверки» tab while the
        # document status still says «с замечаниями».
        return [
            r
            for r in results
            if r.location is None or not r.location.file.endswith(".tex") or r.location.file in allowed
        ]

    def _document_file_set(self, project_folder: Path, source_file: str) -> set[str]:
        """Project-relative POSIX paths of the document's own file plus every
        file reachable from it via \\input/\\include/\\subfile.

        Built from the source (not the compile's .fls), so it works even before
        a successful compile and matches what the student actually edits.
        `expand_inputs` only emits origins for content lines, so the entry file
        is added explicitly in case it is a thin include-only wrapper.

        The entry file is first canonicalised through ``resolve()`` so its case
        matches what the check engines emit (their `location.file` comes from
        `glob()`, i.e. on-disk casing). On a case-insensitive filesystem the
        template may declare e.g. `Tz/tz.tex` while disk is `tz/tz.tex`;
        without this, the main file's findings wouldn't match the allowed set.
        Resolved-include children already use on-disk casing.
        """
        entry = self._canonical_rel(project_folder, source_file)
        files = {line.file for line in expand_inputs(project_folder, entry)}
        files.add(Path(entry).as_posix())
        return files

    @staticmethod
    def _canonical_rel(project_folder: Path, source_file: str) -> str:
        """`source_file` with on-disk casing (best-effort, original on failure)."""
        try:
            return (project_folder / source_file).resolve().relative_to(project_folder.resolve()).as_posix()
        except (OSError, ValueError):
            return Path(source_file).as_posix()

    def _filter_suppressed(self, project: Project, results: list[CheckResult]) -> list[CheckResult]:
        """Drop findings whose source line carries a covering `% hse-noqa` marker.

        Read against the *current* source files (cached per file) so a marker
        added in the editor takes effect immediately, before the next compile.
        Best-effort: unreadable files leave their findings untouched.
        """
        source_lines: dict[str, list[str] | None] = {}

        def lines_for(file: str) -> list[str] | None:
            if file not in source_lines:
                try:
                    content = self._file_repo.read(project.folder, file).decode("utf-8", errors="replace")
                    source_lines[file] = content.splitlines()
                except OSError:
                    source_lines[file] = None
            return source_lines[file]

        kept: list[CheckResult] = []
        for result in results:
            loc = result.location
            if loc is not None and loc.line is not None:
                lines = lines_for(loc.file)
                if (
                    lines is not None
                    and 1 <= loc.line <= len(lines)
                    and line_suppresses_rule(lines[loc.line - 1], result.rule_id)
                ):
                    continue
            kept.append(result)
        return kept

    def _reresolve_severities(
        self,
        project: Project,
        doc: Document,
        results: list[CheckResult],
    ) -> list[CheckResult]:
        """Remap each finding's severity to the current effective severity.

        Best-effort: if the template version can't be loaded the stored results
        are returned unchanged rather than failing the read.
        """
        version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        if version is None:
            return results

        doc_def = self._template_service.find_definition(version, doc)
        if doc_def is None:
            return results

        # `applies_to` в паке — id определений; в team doc.id несёт суффикс
        # владельца, поэтому резолвим по def_id.
        rules_with_severity = self._check_resolution_service.resolve(
            rules=list(version.rules),
            doc_id=doc.def_id,
            version_cfg=version.checks_config,
            doc_definition_checks=doc_def.checks,
            project_override=project.checks_override,
            doc_override=doc.checks_override,
            user_override=ChecksOverride(),
        )
        effective_severity = {rule.id: severity for rule, severity in rules_with_severity}

        return [
            result
            if result.rule_id not in effective_severity or effective_severity[result.rule_id] == result.severity
            else replace(result, severity=effective_severity[result.rule_id])
            for result in results
        ]
