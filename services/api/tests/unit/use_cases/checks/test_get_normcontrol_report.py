from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.value_objects import CheckLocation, CheckResult
from hse_doc_studio.use_cases.checks.get_normcontrol_report import (
    GetNormcontrolReportInput,
    GetNormcontrolReportUC,
)

from tests.factories import make_check_rule

_CID = uuid4()


def _result(rule_id: str, severity: CheckSeverity) -> CheckResult:
    return CheckResult(rule_id=rule_id, severity=severity, message="m", location=CheckLocation("vkr/vkr.tex", 1))


def _make_uc(vkr_results: list[CheckResult]) -> GetNormcontrolReportUC:
    uc = GetNormcontrolReportUC(
        project_repo=MagicMock(),
        project_index_repo=MagicMock(),
        template_repo=MagicMock(),
        compile_repo=MagicMock(),
    )
    vkr = SimpleNamespace(id="vkr", def_id="vkr", last_compile_id=_CID, status="warn")
    tz = SimpleNamespace(id="tz", def_id="tz", last_compile_id=None, status="ok")
    project = SimpleNamespace(
        documents=[vkr, tz],
        lock=SimpleNamespace(pack_id="p", template_id="t", version="1"),
        folder=Path("."),
    )
    uc._get_project_uc = AsyncMock()
    uc._get_project_uc.execute.return_value = SimpleNamespace(project=project)
    uc._template_repo.get_version.return_value = SimpleNamespace(
        rules=[
            make_check_rule(rule_id="gost-7.32-2017/page-margins", params={}),
            make_check_rule(rule_id="typography-ru/quotes", params={}),
        ]
    )

    def _get_record(folder: Path, compile_id: UUID) -> object:
        if compile_id == _CID:
            return SimpleNamespace(check_results=vkr_results)
        return None

    uc._compile_repo.get_for_project.side_effect = _get_record
    return uc


async def test__report__aggregates_totals_and_readiness() -> None:
    uc = _make_uc(
        [_result("gost-7.32-2017/page-margins", CheckSeverity.err), _result("typography-ru/quotes", CheckSeverity.warn)]
    )
    report = await uc.execute(GetNormcontrolReportInput(project_id=uuid4()))

    assert report.totals.errors == 1
    assert report.totals.warnings == 1
    assert report.docs_total == 2
    # vkr has an error → not clean; tz has no compile → clean. 1/2 = 50%.
    assert report.docs_clean == 1
    assert report.readiness_pct == 50


async def test__report__groups_by_source() -> None:
    uc = _make_uc(
        [_result("gost-7.32-2017/page-margins", CheckSeverity.err), _result("typography-ru/quotes", CheckSeverity.warn)]
    )
    report = await uc.execute(GetNormcontrolReportInput(project_id=uuid4()))

    by_source = {g.key: g.counts for g in report.by_source}
    assert by_source["gost-7.32-2017"].errors == 1
    assert by_source["typography-ru"].warnings == 1


async def test__report__all_clean__full_readiness() -> None:
    uc = _make_uc([])
    report = await uc.execute(GetNormcontrolReportInput(project_id=uuid4()))
    assert report.readiness_pct == 100
    assert report.totals.total == 0
