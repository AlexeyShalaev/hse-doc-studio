from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import EditFormat, RequirementFormatKind, ToolKind
from hse_doc_studio.core.value_objects import RequirementsFormat
from hse_doc_studio.use_cases.chat.tools.preview_requirements_format import PreviewRequirementsFormatTool
from hse_doc_studio.use_cases.chat.tools.set_requirements_format import SetRequirementsFormatTool
from hse_doc_studio.use_cases.requirements.get_requirements import GetRequirementsInput, GetRequirementsOutput
from hse_doc_studio.use_cases.requirements.update_requirements_format import (
    UpdateRequirementsFormatInput,
    UpdateRequirementsFormatOutput,
)
from tests.unit.use_cases.chat.tools.conftest import _matrix


def _ctx() -> AgentToolContext:
    return AgentToolContext(project_id=uuid4(), model="m", edit_format=EditFormat.search_replace)


class _FakeGetUC:
    def __init__(self, out: GetRequirementsOutput) -> None:
        self.out = out
        self.calls: list[GetRequirementsInput] = []

    async def execute(self, inp: GetRequirementsInput) -> GetRequirementsOutput:
        self.calls.append(inp)
        return self.out


class _FakeUpdateUC:
    def __init__(self) -> None:
        self.calls: list[UpdateRequirementsFormatInput] = []

    async def execute(self, inp: UpdateRequirementsFormatInput) -> UpdateRequirementsFormatOutput:
        self.calls.append(inp)
        return UpdateRequirementsFormatOutput(requirements_format=inp.requirements_format)


def test__definition__preview_is_read_kind_set_is_write_kind() -> None:
    assert PreviewRequirementsFormatTool(cast(Any, None)).definition().kind == ToolKind.read
    assert SetRequirementsFormatTool(cast(Any, None), cast(Any, None)).definition().kind == ToolKind.write


def test__definition__both_tools_require_a_project() -> None:
    assert PreviewRequirementsFormatTool(cast(Any, None)).definition().requires_project is True
    assert SetRequirementsFormatTool(cast(Any, None), cast(Any, None)).definition().requires_project is True


def test__definition__set_hidden_from_weak_models__preview_stays_exposed() -> None:
    # A mistyped regex from a small model would silently break the scan, so only
    # the read-only dry run is offered to weak/local models.
    assert PreviewRequirementsFormatTool(cast(Any, None)).definition().weak_model_safe is True
    assert SetRequirementsFormatTool(cast(Any, None), cast(Any, None)).definition().weak_model_safe is False


async def test__preview_handle__format_override__dry_runs_without_persisting() -> None:
    fmt = RequirementsFormat(kind=RequirementFormatKind.id, id_pattern=r"R-\d+", definition_docs=("tz",))
    fake_get = _FakeGetUC(_matrix(fmt))
    tool = PreviewRequirementsFormatTool(cast(Any, fake_get))

    result = await tool.handle(_ctx(), {"kind": "id", "id_pattern": r"R-\d+", "definition_docs": ["tz"]})

    assert result.is_error is False
    assert "Пробный прогон" in result.text
    # The candidate format reached the read use case as a dry-run override.
    assert len(fake_get.calls) == 1
    override = fake_get.calls[0].format_override
    assert override is not None
    assert override.kind is RequirementFormatKind.id
    assert override.id_pattern == r"R-\d+"


async def test__preview_handle__bad_kind__returns_error_without_calling_get_uc() -> None:
    fake_get = _FakeGetUC(_matrix(RequirementsFormat()))
    tool = PreviewRequirementsFormatTool(cast(Any, fake_get))

    result = await tool.handle(_ctx(), {"kind": "nope"})

    assert result.is_error is True
    assert not fake_get.calls  # never reached the use case


async def test__set_handle__valid_format__persists_then_reads_fresh_matrix() -> None:
    fmt = RequirementsFormat(kind=RequirementFormatKind.id, id_pattern=r"ТЗ-Ф-\d+", definition_docs=("tz",))
    fake_update = _FakeUpdateUC()
    fake_get = _FakeGetUC(_matrix(fmt, overridden=True))
    tool = SetRequirementsFormatTool(cast(Any, fake_update), cast(Any, fake_get))

    result = await tool.handle(_ctx(), {"kind": "id", "id_pattern": r"ТЗ-Ф-\d+", "definition_docs": ["tz"]})

    assert result.is_error is False
    assert "сохранён" in result.text
    # Update was called with the parsed format; the post-read uses no override.
    assert len(fake_update.calls) == 1
    saved = fake_update.calls[0].requirements_format
    assert saved is not None
    assert saved.kind is RequirementFormatKind.id
    assert saved.id_pattern == r"ТЗ-Ф-\d+"
    assert fake_get.calls[0].format_override is None
