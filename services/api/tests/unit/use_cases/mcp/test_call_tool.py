from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.access.checker import ProjectForbiddenError
from hse_doc_studio.core.access.entities import Actor, ActorSource, Role
from hse_doc_studio.core.agent.entities import ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.errors import NotFoundError, ProjectReadOnlyError
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.mcp.entities import McpCallOutcome, McpCallQuery, McpCallRecord, McpSettings
from hse_doc_studio.core.mcp.errors import McpError, McpErrorCode
from hse_doc_studio.core.quotas.errors import QuotaExceededError
from hse_doc_studio.core.shutdown import ServerRestartingError
from hse_doc_studio.core.signatures.errors import StampImageError
from hse_doc_studio.infra.mcp.local import MemoryMcpCallJournal
from hse_doc_studio.use_cases.mcp.call_tool import map_tool_error, visible_to
from hse_doc_studio.use_cases.mcp.catalog import RULES_BY_NAME, McpToolEntry, with_project_id
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError, jsonable

_ENABLED = McpSettings(enabled=True, disabled_groups=frozenset())


class _Noop:
    async def handle(self, ctx: object, args: dict[str, object]) -> object:
        return None


def _entry(name: str) -> McpToolEntry:
    spec = ToolSpec(name=name, description="", parameters={"type": "object", "properties": {}})
    return McpToolEntry(rule=RULES_BY_NAME[name], definition=ToolDefinition(spec, ToolKind.read, _Noop()))  # type: ignore[arg-type]


def _pat(*scopes: str, admin: bool = False) -> Actor:
    return Actor.user("u1", is_instance_admin=admin, source=ActorSource.pat, scopes=frozenset(scopes))


@pytest.mark.parametrize(
    ("actor", "expected"),
    [
        (_pat("mcp", "mcp:admin", admin=True), True),
        (_pat("mcp", admin=True), False),
        (_pat("mcp", "mcp:admin"), False),
    ],
)
def test__visible_to__admin_tool__needs_admin_and_scope(actor: Actor, expected: bool) -> None:
    assert visible_to(actor, _entry("admin_list_users"), _ENABLED) is expected


def test__visible_to__admin_tool__off_while_group_disabled() -> None:
    actor = _pat("mcp", "mcp:admin", admin=True)

    assert not visible_to(actor, _entry("admin_list_users"), McpSettings(enabled=True))


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (NotFoundError("x"), McpErrorCode.not_found),
        (FileNotFoundError("x"), McpErrorCode.not_found),
        (ProjectForbiddenError("no", Role.editor), McpErrorCode.forbidden),
        (ProjectReadOnlyError(), McpErrorCode.read_only),
        (QuotaExceededError.__new__(QuotaExceededError), McpErrorCode.quota_exceeded),
        (IdentityError(IdentityErrorCode.not_found), McpErrorCode.forbidden),
        (PermissionError("template file"), McpErrorCode.forbidden),
        (ArgumentError("bad"), McpErrorCode.invalid_arguments),
        (ValueError("bad"), McpErrorCode.invalid_arguments),
        (RuntimeError("boom"), McpErrorCode.failed),
    ],
)
def test__map_tool_error__maps_by_type(exc: Exception, code: McpErrorCode) -> None:
    assert map_tool_error(exc).code is code


def test__map_tool_error__server_restarting__keeps_text_and_retry_after() -> None:
    err = map_tool_error(ServerRestartingError("сборка продолжится", retry_after_s=30))

    assert err.code is McpErrorCode.server_restarting
    assert err.retry_after_s == 30
    assert str(err) == "сборка продолжится"


def test__map_tool_error__stamping_failed__failed_with_the_slot_text() -> None:
    err = map_tool_error(StampImageError("картинка слота «author» не читается", slot_id="author"))

    assert err.code is McpErrorCode.failed
    assert "«author»" in str(err)


def test__map_tool_error__role__named_in_message() -> None:
    assert "editor" in str(map_tool_error(ProjectForbiddenError("no", Role.editor)))


def test__map_tool_error__mcp_error__passes_through() -> None:
    err = McpError(McpErrorCode.rate_limited, retry_after_s=3)

    assert map_tool_error(err) is err


def test__with_project_id__prepends_required_project_id() -> None:
    spec = ToolSpec(
        name="t", description="", parameters={"type": "object", "properties": {"path": {}}, "required": ["path"]}
    )

    params = with_project_id(spec).parameters

    assert list(params["properties"]) == ["project_id", "path"]
    assert params["required"] == ["project_id", "path"]


def test__jsonable__entities__become_plain_json() -> None:
    record = McpCallRecord(at=datetime(2026, 1, 1, tzinfo=UTC), tool="t", outcome=McpCallOutcome.ok, duration_ms=1)

    out = jsonable({"r": record, "s": {"b", "a"}})

    assert out == {
        "r": {
            "at": "2026-01-01T00:00:00+00:00",
            "tool": "t",
            "outcome": "ok",
            "duration_ms": 1,
            "actor_id": None,
            "actor_name": None,
            "project_id": None,
            "error_code": None,
            "client": None,
            "arg_keys": [],
        },
        "s": ["a", "b"],
    }


async def test__memory_journal__newest_first_with_filters() -> None:
    journal = MemoryMcpCallJournal(size=3)
    at = datetime(2026, 1, 1, tzinfo=UTC)
    for i, outcome in enumerate([McpCallOutcome.ok, McpCallOutcome.error, McpCallOutcome.ok, McpCallOutcome.ok]):
        await journal.record(McpCallRecord(at=at, tool=f"t{i}", outcome=outcome, duration_ms=i))

    everything = await journal.recent(McpCallQuery())
    errors = await journal.recent(McpCallQuery(outcome=McpCallOutcome.error))

    assert [r.tool for r in everything] == ["t3", "t2", "t1"]
    assert [r.tool for r in errors] == ["t1"]
