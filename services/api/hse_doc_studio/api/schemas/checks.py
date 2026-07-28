from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from hse_doc_studio.core.value_objects import CheckResult

CheckSeverityName = Literal["info", "warn", "err"]


class CheckFixResponse(BaseModel):
    file: str
    search: str
    replace: str
    line: int | None
    title: str | None


class ApplyFixRequest(BaseModel):
    path: str
    search: str
    replace: str
    line: int | None = None


class CheckResultResponse(BaseModel):
    rule_id: str
    severity: str
    message: str
    location: dict[str, Any] | None
    fix: CheckFixResponse | None = None


class CheckResultsResponse(BaseModel):
    doc_id: str
    compile_id: str | None
    results: list[CheckResultResponse]


class CheckRuleResponse(BaseModel):
    rule_id: str
    title: dict[str, str]
    description: dict[str, str]
    category: str | None
    effective_severity: CheckSeverityName
    enabled: bool
    source: str
    # Подпись группы, объявленная паком. Пусто -> UI покажет `source` как есть.
    source_label: dict[str, str] = {}  # noqa: RUF012 — pydantic копирует дефолт на каждый экземпляр


class SeverityCountsResponse(BaseModel):
    errors: int
    warnings: int
    infos: int
    total: int


class DocReportItemResponse(BaseModel):
    doc_id: str
    status: str
    counts: SeverityCountsResponse


class GroupReportItemResponse(BaseModel):
    key: str
    counts: SeverityCountsResponse


class NormcontrolReportResponse(BaseModel):
    documents: list[DocReportItemResponse]
    by_category: list[GroupReportItemResponse]
    by_source: list[GroupReportItemResponse]
    totals: SeverityCountsResponse
    docs_total: int
    docs_clean: int
    readiness_pct: int


def map_check_result(r: CheckResult) -> CheckResultResponse:
    """Map a domain CheckResult to its API response, including any quick-fix.

    Shared by the compile and checks routers so both surface fixes identically.
    """
    location: dict[str, Any] | None = None
    if r.location is not None:
        location = {"file": r.location.file, "line": r.location.line}
    fix: CheckFixResponse | None = None
    if r.fix is not None:
        fix = CheckFixResponse(
            file=r.fix.file,
            search=r.fix.search,
            replace=r.fix.replace,
            line=r.fix.line,
            title=r.fix.title,
        )
    return CheckResultResponse(
        rule_id=r.rule_id,
        severity=str(r.severity),
        message=r.message,
        location=location,
        fix=fix,
    )
