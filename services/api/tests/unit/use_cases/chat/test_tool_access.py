from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import ProjectForbiddenError
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor, Grant, ProjectAcl, Role
from hse_doc_studio.core.agent.entities import (
    AgentToolContext,
    NormalizedTurn,
    TokenUsage,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import AgentRunStatus, StopReason, ToolKind
from hse_doc_studio.infra.identity.project_access import ServerProjectAccessChecker
from hse_doc_studio.infra.persistence.chat import JsonChatRepository
from hse_doc_studio.use_cases.chat._registry import ToolRegistry
from hse_doc_studio.use_cases.chat.tool_access import TOOL_ACCESS, require_tool_access
from tests.unit.use_cases.chat.test_agent_loop import _FakeProvider, _make_loop, _seed_session

PROJECT_ID = uuid4()
EDITOR = Actor.user("u-alice", "Alice", "alice@example.com")
OWNER = Actor.user("u-owner", "Owner", "owner@example.com")
_TOOLS_DIR = Path(__file__).parents[4] / "hse_doc_studio" / "use_cases" / "chat" / "tools"


class _AclRepo:
    def __init__(self, acl: ProjectAcl) -> None:
        self._acl = acl

    async def load_for(self, actor: Actor, project_id: UUID) -> ProjectAcl | None:
        grant = self._acl.grants.get(actor.key or "")
        return ProjectAcl(
            project_id=self._acl.project_id,
            owner_id=self._acl.owner_id,
            team=self._acl.team,
            grants={actor.key or "": grant} if grant else {},
        )


@pytest.fixture
def checker() -> Iterator[ServerProjectAccessChecker]:
    acl = ProjectAcl(
        project_id=str(PROJECT_ID),
        owner_id=OWNER.key,
        team=True,
        grants={
            EDITOR.key or "": Grant(Role.editor, persona_slug="alice"),
            OWNER.key or "": Grant(Role.owner),
        },
    )
    yield ServerProjectAccessChecker(_AclRepo(acl))
    set_current_actor(None)


async def test__edit_tex__team_editor_foreign_author_path__forbidden(checker: ServerProjectAccessChecker) -> None:
    set_current_actor(EDITOR)

    with pytest.raises(ProjectForbiddenError):
        await require_tool_access(checker, PROJECT_ID, "edit_tex", {"path": "bob/main.tex"})
    await require_tool_access(checker, PROJECT_ID, "edit_tex", {"path": "alice/main.tex"})
    await require_tool_access(checker, PROJECT_ID, "edit_tex", {"path": "shared/notes.tex"})


@pytest.mark.parametrize("tool", ["set_project_meta", "set_language", "set_requirements_format"])
async def test__settings_tools__editor__forbidden_owner_allowed(checker: ServerProjectAccessChecker, tool: str) -> None:
    set_current_actor(EDITOR)
    with pytest.raises(ProjectForbiddenError):
        await require_tool_access(checker, PROJECT_ID, tool, {})

    set_current_actor(OWNER)
    await require_tool_access(checker, PROJECT_ID, tool, {})


async def test__vcs_restore__team_editor__forbidden_but_snapshot_allowed(checker: ServerProjectAccessChecker) -> None:
    set_current_actor(EDITOR)

    with pytest.raises(ProjectForbiddenError):
        await require_tool_access(checker, PROJECT_ID, "vcs_restore", {})
    await require_tool_access(checker, PROJECT_ID, "vcs_save_snapshot", {})


def test__tool_access__every_project_tool_has_an_entry() -> None:
    names: set[str] = set()
    for source in _TOOLS_DIR.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        if "requires_project=False" in text:
            continue
        names.update(re.findall(r'^\s+name="([a-z_]+)",$', text, flags=re.MULTILINE))

    assert names
    assert names <= set(TOOL_ACCESS)
    assert all(isinstance(rule.action, Action) for rule in TOOL_ACCESS.values())


class _WriteTool:
    def __init__(self) -> None:
        self.calls = 0

    def definition(self) -> ToolDefinition:
        spec = ToolSpec(name="edit_tex", description="edit", parameters={"type": "object"})
        return ToolDefinition(spec=spec, kind=ToolKind.write, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        self.calls += 1
        return ToolResult.ok("written")


async def test__agent_loop__team_editor_edits_foreign_file__tool_not_run(
    tmp_path: Path, checker: ServerProjectAccessChecker
) -> None:
    set_current_actor(EDITOR)
    repo = JsonChatRepository()
    session = await _seed_session(repo, tmp_path, "перепиши файл Боба")
    tool = _WriteTool()
    provider = _FakeProvider(
        [
            NormalizedTurn(
                text="",
                tool_calls=(ToolCall(id="c1", name="edit_tex", arguments={"path": "bob/main.tex"}),),
                stop_reason=StopReason.tool_calls,
                usage=TokenUsage(),
            ),
            NormalizedTurn(text="ок", tool_calls=(), stop_reason=StopReason.end_turn, usage=TokenUsage()),
        ]
    )
    loop = _make_loop(repo, provider, ToolRegistry([tool.definition()]), auto_approve_writes=True, access=checker)

    result = await loop.run(
        project_id=PROJECT_ID,
        project_folder=tmp_path,
        session_id=session.id,
        run_id=uuid4(),
        system="s",
        cancel=asyncio.Event(),
    )

    assert result.status == AgentRunStatus.succeeded
    assert tool.calls == 0
    tool_msg = (await repo.list_messages(tmp_path, session.id))[2]
    assert tool_msg.blocks[0].is_error is True
