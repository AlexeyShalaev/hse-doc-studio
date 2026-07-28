from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException

from hse_doc_studio.api.schemas.checks import (
    ApplyFixRequest,
    CheckResultsResponse,
    CheckRuleResponse,
    DocReportItemResponse,
    GroupReportItemResponse,
    NormcontrolReportResponse,
    SeverityCountsResponse,
)
from hse_doc_studio.api.schemas.checks import map_check_result as _map_check_result
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.checks.apply_check_fix import ApplyCheckFixInput, ApplyCheckFixUC
from hse_doc_studio.use_cases.checks.get_normcontrol_report import (
    GetNormcontrolReportInput,
    GetNormcontrolReportUC,
    NormcontrolReport,
    SeverityCounts,
)
from hse_doc_studio.use_cases.checks.list_document_check_rules import (
    CheckRuleListItem,
    ListDocumentCheckRulesInput,
    ListDocumentCheckRulesUC,
)
from hse_doc_studio.use_cases.checks.list_project_check_rules import (
    ListProjectCheckRulesInput,
    ListProjectCheckRulesUC,
)
from hse_doc_studio.use_cases.checks.run_checks import RunChecksInput, RunChecksUC

router = APIRouter(route_class=DishkaRoute)


def _map_counts(c: SeverityCounts) -> SeverityCountsResponse:
    return SeverityCountsResponse(errors=c.errors, warnings=c.warnings, infos=c.infos, total=c.total)


def _map_report(report: NormcontrolReport) -> NormcontrolReportResponse:
    return NormcontrolReportResponse(
        documents=[
            DocReportItemResponse(doc_id=d.doc_id, status=d.status, counts=_map_counts(d.counts))
            for d in report.documents
        ],
        by_category=[GroupReportItemResponse(key=g.key, counts=_map_counts(g.counts)) for g in report.by_category],
        by_source=[GroupReportItemResponse(key=g.key, counts=_map_counts(g.counts)) for g in report.by_source],
        totals=_map_counts(report.totals),
        docs_total=report.docs_total,
        docs_clean=report.docs_clean,
        readiness_pct=report.readiness_pct,
    )


def _map_rule(item: CheckRuleListItem) -> CheckRuleResponse:
    return CheckRuleResponse(
        rule_id=item.rule_id,
        title=item.title,
        description=item.description,
        category=item.category,
        effective_severity=str(item.effective_severity),
        enabled=item.enabled,
        source=item.source,
        source_label=item.source_label,
    )


@router.get(
    "/projects/{project_id}/documents/{doc_id}/checks/rules",
    response_model=list[CheckRuleResponse],
)
async def list_document_check_rules(
    project_id: UUID,
    doc_id: str,
    uc: FromDishka[ListDocumentCheckRulesUC],
) -> list[CheckRuleResponse]:
    try:
        result = await uc.execute(ListDocumentCheckRulesInput(project_id=project_id, doc_id=doc_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_map_rule(r) for r in result.rules]


@router.get(
    "/projects/{project_id}/checks/rules",
    response_model=list[CheckRuleResponse],
)
async def list_project_check_rules(
    project_id: UUID,
    uc: FromDishka[ListProjectCheckRulesUC],
) -> list[CheckRuleResponse]:
    try:
        result = await uc.execute(ListProjectCheckRulesInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_map_rule(r) for r in result.rules]


@router.post(
    "/projects/{project_id}/documents/{doc_id}/checks/run",
    response_model=CheckResultsResponse,
)
async def run_checks(
    project_id: UUID,
    doc_id: str,
    uc: FromDishka[RunChecksUC],
    include_external: bool = True,
) -> CheckResultsResponse:
    """Run source-based checks now, without compiling — powers live normative
    checks while editing. `include_external=false` skips LanguageTool for a
    faster pass (e.g. on a keystroke debounce)."""
    try:
        result = await uc.execute(
            RunChecksInput(project_id=project_id, doc_id=doc_id, include_external=include_external)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CheckResultsResponse(
        doc_id=doc_id,
        compile_id=None,
        results=[_map_check_result(r) for r in result.results],
    )


@router.post(
    "/projects/{project_id}/checks/apply-fix",
    status_code=204,
    response_model=None,
)
async def apply_check_fix(
    project_id: UUID,
    body: ApplyFixRequest,
    uc: FromDishka[ApplyCheckFixUC],
) -> None:
    """Apply a single deterministic quick-fix (search→replace at file:line).
    Returns 409 if the text no longer matches (stale fix)."""
    try:
        await uc.execute(
            ApplyCheckFixInput(
                project_id=project_id,
                path=body.path,
                search=body.search,
                replace=body.replace,
                line=body.line,
            )
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/projects/{project_id}/normcontrol-report",
    response_model=NormcontrolReportResponse,
)
async def get_normcontrol_report(
    project_id: UUID,
    uc: FromDishka[GetNormcontrolReportUC],
) -> NormcontrolReportResponse:
    """Aggregated «Нормоконтроль» report across all documents (from each one's
    last build): per-document / per-category / per-source counts + readiness %."""
    try:
        report = await uc.execute(GetNormcontrolReportInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_report(report)
