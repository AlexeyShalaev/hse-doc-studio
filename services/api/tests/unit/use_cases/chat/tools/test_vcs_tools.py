from __future__ import annotations

from typing import Any, cast

from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.use_cases.chat.tools.vcs_diff import VcsDiffTool
from hse_doc_studio.use_cases.chat.tools.vcs_list_history import VcsListHistoryTool
from hse_doc_studio.use_cases.chat.tools.vcs_restore import VcsRestoreTool
from hse_doc_studio.use_cases.chat.tools.vcs_save_snapshot import VcsSaveSnapshotTool
from hse_doc_studio.use_cases.chat.tools.vcs_status import VcsStatusTool


def test__definition__status_history_diff__are_read_kind() -> None:
    assert VcsStatusTool(cast(Any, None)).definition().kind == ToolKind.read
    assert VcsListHistoryTool(cast(Any, None)).definition().kind == ToolKind.read
    assert VcsDiffTool(cast(Any, None)).definition().kind == ToolKind.read


def test__definition__save_snapshot__is_write_kind() -> None:
    assert VcsSaveSnapshotTool(cast(Any, None)).definition().kind == ToolKind.write


def test__definition__restore__is_exec_kind() -> None:
    assert VcsRestoreTool(cast(Any, None)).definition().kind == ToolKind.exec_


def test__definition__restore_tool__exposes_no_mode_param() -> None:
    # The agent must never be able to trigger a destructive hard reset: the tool
    # schema has commit_id only, no `mode`.
    spec = VcsRestoreTool(cast(Any, None)).definition().spec
    props = spec.parameters["properties"]
    assert "mode" not in props
    assert spec.parameters["required"] == ["commit_id"]


def test__definition__all_vcs_tools__require_a_project() -> None:
    for tool in (
        VcsStatusTool(cast(Any, None)),
        VcsListHistoryTool(cast(Any, None)),
        VcsDiffTool(cast(Any, None)),
        VcsSaveSnapshotTool(cast(Any, None)),
        VcsRestoreTool(cast(Any, None)),
    ):
        assert tool.definition().requires_project is True
