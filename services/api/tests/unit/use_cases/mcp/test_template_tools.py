"""Тулы обновления шаблона: разбор решений по конфликтам, отказ сценария и запись в аудит."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import ConflictResolution, EditFormat
from hse_doc_studio.core.mcp.protocols import IMcpChangeAudit
from hse_doc_studio.core.template_update.entities import TemplateUpdateRecord
from hse_doc_studio.core.template_update.errors import TemplateUpdatePlanOutdatedError
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError
from hse_doc_studio.use_cases.mcp.tools.template import TEMPLATE_UPDATE_AUDIT_ACTION, ApplyTemplateUpdateTool
from hse_doc_studio.use_cases.template_update.apply_template_update import (
    ApplyTemplateUpdateInput,
    ApplyTemplateUpdateOutput,
    ApplyTemplateUpdateUC,
)

_RECORD = TemplateUpdateRecord(
    id="upd1", from_version="2026.1.1", to_version="2026.1.2", at="2026-11-08T00:00:00Z", pre_commit="abc"
)


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, str | None, Mapping[str, object]]] = []

    async def record(self, action: str, *, target: str | None, details: Mapping[str, object]) -> None:
        self.events.append((action, target, details))


class _Apply:
    def __init__(self, error: Exception | None = None) -> None:
        self.inputs: list[ApplyTemplateUpdateInput] = []
        self._error = error

    async def execute(self, inp: ApplyTemplateUpdateInput) -> ApplyTemplateUpdateOutput:
        self.inputs.append(inp)
        if self._error is not None:
            raise self._error
        return ApplyTemplateUpdateOutput(
            record=_RECORD, written=["report/report.tex"], deleted=["report/old.tex"], markers=[]
        )


class _Deps:
    def __init__(self, apply: _Apply, audit: _Audit) -> None:
        self._by_type: dict[object, object] = {ApplyTemplateUpdateUC: apply, IMcpChangeAudit: audit}

    async def get(self, dependency_type: Any, component: str | None = None) -> Any:
        return self._by_type[dependency_type]


def _setup(error: Exception | None = None) -> tuple[ApplyTemplateUpdateTool, _Apply, _Audit, UUID]:
    apply, audit = _Apply(error), _Audit()
    return ApplyTemplateUpdateTool(_Deps(apply, audit)), apply, audit, uuid4()  # type: ignore[arg-type]


def _ctx(project_id: UUID) -> AgentToolContext:
    return AgentToolContext(project_id=project_id, model="mcp-client", edit_format=EditFormat.search_replace)


async def test__apply__passes_the_plan_and_resolutions_and_audits() -> None:
    tool, apply, audit, project_id = _setup()

    result = await tool.handle(
        _ctx(project_id),
        {"to_version": "2026.1.2", "fingerprint": "fp", "resolutions": {"report/report.tex": "theirs"}},
    )

    assert result.is_error is False, result.text
    assert apply.inputs == [
        ApplyTemplateUpdateInput(
            project_id=project_id,
            to_version="2026.1.2",
            fingerprint="fp",
            resolutions={"report/report.tex": ConflictResolution.theirs},
        )
    ]
    ((action, target, details),) = audit.events
    assert (action, target) == (TEMPLATE_UPDATE_AUDIT_ACTION, str(project_id))
    assert details["from_version"] == "2026.1.1"
    assert details["to_version"] == "2026.1.2"
    assert details["via"] == "mcp"


async def test__apply__outdated_plan__error_and_no_audit() -> None:
    tool, _, audit, project_id = _setup(TemplateUpdatePlanOutdatedError("Проект изменился после предпросмотра"))

    result = await tool.handle(_ctx(project_id), {"to_version": "2026.1.2", "fingerprint": "old"})

    assert result.is_error is True
    assert "изменился" in result.text
    assert audit.events == []


@pytest.mark.parametrize(
    "args",
    [
        {"to_version": "2026.1.2"},
        {"fingerprint": "fp"},
        {"to_version": "2026.1.2", "fingerprint": "fp", "resolutions": {"a.tex": "both"}},
        {"to_version": "2026.1.2", "fingerprint": "fp", "resolutions": ["a.tex"]},
    ],
)
async def test__apply__bad_arguments__argument_error_and_no_call(args: dict[str, object]) -> None:
    tool, apply, audit, project_id = _setup()

    with pytest.raises(ArgumentError):
        await tool.handle(_ctx(project_id), args)

    assert apply.inputs == []
    assert audit.events == []
