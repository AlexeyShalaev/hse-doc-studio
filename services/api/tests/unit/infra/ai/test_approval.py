from __future__ import annotations

from typing import Any

from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.infra.ai.agent.approval import ConfigApprovalGate


class _FakeSettingsRepo:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def get(self) -> dict[str, Any]:
        return self._data

    def save(self, settings: dict[str, Any]) -> None:
        self._data = settings


def test__requires_approval__auto_approve_disabled__gates_writes_and_exec_not_reads() -> None:
    gate = ConfigApprovalGate(auto_approve_writes=False)

    assert gate.requires_approval(ToolKind.read) is False
    assert gate.requires_approval(ToolKind.write) is True
    assert gate.requires_approval(ToolKind.exec_) is True


def test__requires_approval__auto_approve_enabled__writes_no_longer_gated() -> None:
    gate = ConfigApprovalGate(auto_approve_writes=True)

    assert gate.requires_approval(ToolKind.write) is False


def test__requires_approval__settings_repo_provided__reflects_live_runtime_setting() -> None:
    repo = _FakeSettingsRepo({"agent_auto_approve_writes": False})
    gate = ConfigApprovalGate(False, settings_repo=repo)  # type: ignore[arg-type]

    assert gate.requires_approval(ToolKind.write) is True

    # Flip the runtime setting → the gate reflects it without reconstruction.
    repo.save({"agent_auto_approve_writes": True})

    assert gate.requires_approval(ToolKind.write) is False
