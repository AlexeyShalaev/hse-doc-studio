from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.team import is_doc_active
from hse_doc_studio.core.value_objects import CheckResult
from hse_doc_studio.infra.persistence.compile import JsonCompileRepository
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()

_PERCENT = 100


@dataclass
class SeverityCounts:
    errors: int = 0
    warnings: int = 0
    infos: int = 0

    def add(self, severity: CheckSeverity) -> None:
        if severity == CheckSeverity.err:
            self.errors += 1
        elif severity == CheckSeverity.warn:
            self.warnings += 1
        elif severity != CheckSeverity.skipped:
            self.infos += 1

    @property
    def total(self) -> int:
        return self.errors + self.warnings + self.infos


@dataclass
class DocReportItem:
    doc_id: str
    status: str
    counts: SeverityCounts


@dataclass
class GroupReportItem:
    key: str
    counts: SeverityCounts


@dataclass
class NormcontrolReport:
    documents: list[DocReportItem] = field(default_factory=list)
    by_category: list[GroupReportItem] = field(default_factory=list)
    by_source: list[GroupReportItem] = field(default_factory=list)
    totals: SeverityCounts = field(default_factory=SeverityCounts)
    docs_total: int = 0
    docs_clean: int = 0  # documents with zero error-level findings
    readiness_pct: int = 0


@dataclass
class GetNormcontrolReportInput:
    project_id: UUID


class GetNormcontrolReportUC:
    """Aggregate the latest check findings across all project documents into a
    single «Нормоконтроль» report: per-document, per-category and per-source
    (GOST file) breakdowns, plus a readiness percentage (share of documents
    with no error-level findings). Reads each document's last compile results —
    so it reflects the most recent build, no recompilation."""

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        compile_repo: JsonCompileRepository,
    ) -> None:
        self._get_project_uc = GetProjectUC(project_repo, project_index_repo)
        self._template_repo = template_repo
        self._compile_repo = compile_repo

    async def execute(self, inp: GetNormcontrolReportInput) -> NormcontrolReport:
        project = (await self._get_project_uc.execute(GetProjectInput(project_id=inp.project_id))).project

        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        category_by_rule: dict[str, str] = {}
        if version is not None:
            category_by_rule = {r.id: (r.category or "other") for r in version.rules}

        report = NormcontrolReport()
        category_counts: dict[str, SeverityCounts] = {}
        source_counts: dict[str, SeverityCounts] = {}

        for doc in project.documents:
            # Невыбранные руководства (РП/РО) не учитываются в нормоконтроле.
            if not is_doc_active(project, doc):
                continue
            results = self._results_for(project.folder, doc.last_compile_id)
            doc_counts = SeverityCounts()
            for r in results:
                doc_counts.add(r.severity)
                report.totals.add(r.severity)
                category_counts.setdefault(category_by_rule.get(r.rule_id, "other"), SeverityCounts()).add(r.severity)
                source_counts.setdefault(_source_of(r.rule_id), SeverityCounts()).add(r.severity)
            report.documents.append(DocReportItem(doc_id=doc.id, status=str(doc.status), counts=doc_counts))
            report.docs_total += 1
            if doc_counts.errors == 0:
                report.docs_clean += 1

        report.by_category = [GroupReportItem(key=k, counts=v) for k, v in sorted(category_counts.items())]
        report.by_source = [GroupReportItem(key=k, counts=v) for k, v in sorted(source_counts.items())]
        report.readiness_pct = (
            round(report.docs_clean / report.docs_total * _PERCENT) if report.docs_total else _PERCENT
        )
        return report

    def _results_for(self, folder: Path, compile_id: UUID | None) -> list[CheckResult]:
        if compile_id is None:
            return []
        record = self._compile_repo.get_for_project(folder, compile_id)
        return list(record.check_results) if record is not None else []


def _source_of(rule_id: str) -> str:
    return rule_id.split("/", 1)[0] if "/" in rule_id else "misc"
