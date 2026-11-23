"""Ожидание в одном вызове тула MCP не дольше MCP_MAX_WAIT_S: больший `wait_s` принимается и урезается.

Клиенты MCP обрывают вызов по своему таймауту (у Claude Code вызов `pack_preview_build` с `wait_s: 120` падал «The
operation timed out»), поэтому сборка предпросмотра, git-синхронизация и скачивание проекта из облака ждут итог не
дольше предела, а дальше ждут повторным вызовом с id начатой операции.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import EditFormat
from hse_doc_studio.core.git_sync.entities import GitOperation, OperationKind, OperationStatus
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.pack_studio.preview import PreviewBuild, PreviewStatus
from hse_doc_studio.use_cases.git_sync.cloud_projects import CloneCloudProjectUC, CloudCloneOutcome
from hse_doc_studio.use_cases.git_sync.operations import GetOperationUC
from hse_doc_studio.use_cases.git_sync.start_sync import StartSyncOutput, StartSyncUC
from hse_doc_studio.use_cases.mcp.tools import git as git_tools
from hse_doc_studio.use_cases.mcp.tools import packs
from hse_doc_studio.use_cases.mcp.tools._base import MCP_MAX_WAIT_S, wait_arg
from hse_doc_studio.use_cases.mcp.tools.cloud import CloneCloudProjectTool
from hse_doc_studio.use_cases.mcp.tools.git import GitSyncTool
from hse_doc_studio.use_cases.mcp.tools.packs import PackPreviewBuildTool
from hse_doc_studio.use_cases.pack_studio.preview import PackPreviewService

ACTOR = Actor.user("u1", source=ActorSource.pat, scopes=frozenset({"mcp", "packs"}))
# Таймаут запроса у клиентов MCP по умолчанию (SDK): вызов должен вернуться раньше.
_CLIENT_TIMEOUT_S = 60


@pytest.fixture(autouse=True)
def _russian() -> None:
    set_interface_language("ru")


class _Deps:
    def __init__(self, by_type: dict[type, object]) -> None:
        self.by_type = by_type

    async def get(self, dependency_type: type[Any], component: str | None = None) -> Any:
        return self.by_type[dependency_type]


def test__cap__is_below_the_client_timeout() -> None:
    assert MCP_MAX_WAIT_S <= 50 < _CLIENT_TIMEOUT_S  # noqa: PLR2004 — предел из задачи


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 45),
        (0, 0),
        (30, 30),
        (MCP_MAX_WAIT_S, MCP_MAX_WAIT_S),
        (120, MCP_MAX_WAIT_S),
        (240, MCP_MAX_WAIT_S),
        ("120", MCP_MAX_WAIT_S),
        (-5, 0),
        (True, 45),
    ],
)
def test__wait_arg__accepts_large_values_and_clamps_them(raw: object, expected: int) -> None:
    args = {} if raw is None else {"wait_s": raw}

    assert wait_arg(args, 45) == expected


def test__wait_arg__default_above_the_cap_is_clamped_too() -> None:
    assert wait_arg({}, 240) == MCP_MAX_WAIT_S


@pytest.mark.parametrize("tool", [PackPreviewBuildTool, GitSyncTool, CloneCloudProjectTool])
def test__spec__says_the_cap_and_how_to_keep_waiting(tool: Any) -> None:
    prop = tool.spec.parameters["properties"]["wait_s"]

    assert prop["default"] <= MCP_MAX_WAIT_S
    assert f"0..{MCP_MAX_WAIT_S}" in prop["description"]
    assert "240" not in prop["description"]
    assert f"не больше {MCP_MAX_WAIT_S}" in tool.spec.description
    assert "повторный вызов" in prop["description"]


def test__preview_spec__tells_to_start_short_and_continue_with_build_id() -> None:
    description = PackPreviewBuildTool.spec.description

    assert "wait_s: 0" in description
    assert "build_id" in description


# ── pack_preview_build ───────────────────────────────────────────────────────


class _Clock:
    """Часы тула: время идёт только во сне опроса, поэтому тест не ждёт по-настоящему."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept = 0.0

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        self.slept += seconds


def _running_build(workspace_id: UUID) -> PreviewBuild:
    return PreviewBuild(
        id=uuid4(),
        owner_id="u1",
        workspace_id=workspace_id,
        pack="demo",
        template="report",
        version="2026.1.1",
        document="report",
        example="auto:normal",
        combination={},
        key="k",
        status=PreviewStatus.running,
        cached=False,
        created_at=datetime.now(UTC),
    )


class _Previews:
    def __init__(self, build: PreviewBuild) -> None:
        self.build = build
        self.polls = 0

    async def get(self, _actor: Actor, _workspace_id: UUID, _build_id: UUID) -> PreviewBuild:
        self.polls += 1
        return self.build


@pytest.mark.parametrize("asked", [120, 240])
async def test__preview_build__long_wait_returns_within_the_cap_with_build_id(
    monkeypatch: pytest.MonkeyPatch, asked: int
) -> None:
    clock = _Clock()
    monkeypatch.setattr(packs, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(packs, "asyncio", SimpleNamespace(sleep=clock.sleep))
    workspace_id = uuid4()
    previews = _Previews(_running_build(workspace_id))
    tool = PackPreviewBuildTool(_Deps({PackPreviewService: previews}))  # type: ignore[arg-type]

    result = await tool.run(
        ACTOR, {"workspace_id": str(workspace_id), "build_id": str(previews.build.id), "wait_s": asked}
    )

    body = json.loads(result.text)
    assert result.is_error is False
    assert MCP_MAX_WAIT_S - 1 <= clock.slept <= MCP_MAX_WAIT_S + 1
    assert body["builds"][0]["status"] == "running"
    assert body["builds"][0]["build_id"] == str(previews.build.id)
    assert "build_id" in body["hint"]


# ── git_sync ─────────────────────────────────────────────────────────────────


class _Start:
    async def execute(self, _inp: Any) -> StartSyncOutput:
        return StartSyncOutput(operation_id="op-new")


class _Operations:
    async def execute(self, operation_id: str) -> GitOperation:
        return GitOperation(
            operation_id, OperationKind.sync, uuid4(), datetime.now(UTC), status=OperationStatus.running
        )


async def test__git_sync__long_wait_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    waited: list[float] = []

    async def fake_wait(operations: Any, operation_id: str, wait_s: float) -> GitOperation:
        waited.append(wait_s)
        return await operations.execute(operation_id)

    monkeypatch.setattr(git_tools, "_wait", fake_wait)
    deps = _Deps({StartSyncUC: _Start(), GetOperationUC: _Operations()})
    ctx = AgentToolContext(project_id=uuid4(), model="mcp-client", edit_format=EditFormat.search_replace)

    result = await GitSyncTool(deps).handle(ctx, {"wait_s": 240})  # type: ignore[arg-type]

    body = json.loads(result.text)
    assert waited == [MCP_MAX_WAIT_S]
    assert body["status"] == "running"
    assert body["operation_id"] == "op-new"


# ── clone_cloud_project ──────────────────────────────────────────────────────


class _Clone:
    def __init__(self) -> None:
        self.waits: list[float] = []

    async def execute(self, address: Any, *, wait_s: float) -> CloudCloneOutcome:
        self.waits.append(wait_s)
        return CloudCloneOutcome(
            project_id=address.project_id, server_url="https://studio.example.org", status="running", operation=None
        )


async def test__clone_cloud_project__long_wait_is_clamped() -> None:
    clone = _Clone()
    ctx = AgentToolContext(project_id=uuid4(), model="mcp-client", edit_format=EditFormat.search_replace)
    args = {"project_id": str(uuid4()), "server": "https://studio.example.org", "wait_s": 120}

    result = await CloneCloudProjectTool(_Deps({CloneCloudProjectUC: clone})).handle(ctx, args)  # type: ignore[arg-type]

    assert clone.waits == [MCP_MAX_WAIT_S]
    assert json.loads(result.text)["status"] == "running"
