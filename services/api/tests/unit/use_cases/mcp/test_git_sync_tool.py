"""git_sync: присоединение к идущей синхронизации, итог, отказ до запуска и ожидание без ошибки."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import EditFormat
from hse_doc_studio.core.git_sync.entities import (
    GitOperation,
    GitOperationError,
    OperationKind,
    OperationStatus,
    SyncOutcome,
    SyncResult,
)
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.use_cases.git_sync.get_conflicts import GetConflictsUC
from hse_doc_studio.use_cases.git_sync.operations import GetOperationUC
from hse_doc_studio.use_cases.git_sync.start_sync import StartSyncOutput, StartSyncUC
from hse_doc_studio.use_cases.mcp.tools.git import SYNC_WAIT_S, GitSyncTool

_SECRET = "ghp_SECRET_TOKEN"


class _Start:
    def __init__(self, *, busy: str | None = None, refuse: Exception | None = None) -> None:
        self.busy = busy
        self.refuse = refuse
        self.calls = 0

    async def execute(self, _inp: Any) -> StartSyncOutput:
        self.calls += 1
        if self.refuse is not None:
            raise self.refuse
        if self.busy is not None:
            raise git_error(GitErrorCode.sync_busy, operation_id=self.busy)
        return StartSyncOutput(operation_id="op-new")


class _Operations:
    def __init__(self, *states: GitOperation) -> None:
        self.states = list(states)
        self.asked: list[str] = []

    async def execute(self, operation_id: str) -> GitOperation:
        self.asked.append(operation_id)
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]


class _Deps:
    def __init__(self, start: _Start, operations: _Operations) -> None:
        self.by_type: dict[type, object] = {StartSyncUC: start, GetOperationUC: operations, GetConflictsUC: None}

    async def get(self, dependency_type: type[Any], component: str | None = None) -> Any:
        return self.by_type[dependency_type]


def _op(op_id: str, status: OperationStatus, **changes: Any) -> GitOperation:
    return GitOperation(op_id, OperationKind.sync, uuid4(), datetime.now(UTC), status=status, **changes)


def _ctx() -> AgentToolContext:
    return AgentToolContext(project_id=uuid4(), model="mcp-client", edit_format=EditFormat.search_replace)


@pytest.fixture(autouse=True)
def _russian() -> None:
    set_interface_language("ru")


def test__spec__wait_below_client_timeout_and_example() -> None:
    assert GitSyncTool.spec.parameters["properties"]["wait_s"]["default"] == SYNC_WAIT_S < 60
    assert "Пример" in GitSyncTool.spec.description


async def test__finished__reports_outcome_and_counts() -> None:
    done = _op("op-new", OperationStatus.succeeded, result=SyncResult(SyncOutcome.merged, 2, 1, files_changed=3))
    start, operations = _Start(), _Operations(done)

    result = await GitSyncTool(_Deps(start, operations)).handle(_ctx(), {})

    report = json.loads(result.text)
    assert result.is_error is False
    assert (report["outcome"], report["pulled_commits"], report["pushed_commits"]) == ("merged", 2, 1)
    assert operations.asked == ["op-new"]


async def test__already_running__joins_that_sync_like_the_web() -> None:
    done = _op("op-old", OperationStatus.succeeded, result=SyncResult(SyncOutcome.up_to_date))
    start, operations = _Start(busy="op-old"), _Operations(done)

    result = await GitSyncTool(_Deps(start, operations)).handle(_ctx(), {})

    report = json.loads(result.text)
    assert report["joined"] is True
    assert report["operation_id"] == "op-old"
    assert start.calls == 1


async def test__not_finished_within_wait__running_with_hint_not_error() -> None:
    start, operations = _Start(), _Operations(_op("op-new", OperationStatus.running))

    result = await GitSyncTool(_Deps(start, operations)).handle(_ctx(), {"wait_s": 0})

    report = json.loads(result.text)
    assert result.is_error is False
    assert report["status"] == "running"
    assert "вызовите git_sync снова" in report["hint"]


async def test__failed__error_code_and_detail_without_secrets() -> None:
    error = GitOperationError(GitErrorCode.auth_failed, "Нет доступа к репозиторию")
    start, operations = _Start(), _Operations(_op("op-new", OperationStatus.failed, error=error))

    result = await GitSyncTool(_Deps(start, operations)).handle(_ctx(), {})

    assert result.is_error is True
    report = json.loads(result.text)
    assert report["error"] == {"code": "auth_failed", "detail": "Нет доступа к репозиторию"}
    assert _SECRET not in result.text


async def test__refused_before_start__localized_reason_and_code() -> None:
    start = _Start(refuse=git_error(GitErrorCode.profile_required))
    operations = _Operations(_op("x", OperationStatus.running))

    result = await GitSyncTool(_Deps(start, operations)).handle(_ctx(), {})

    assert result.is_error is True
    assert result.text.endswith("(profile_required)")
    assert operations.asked == []
