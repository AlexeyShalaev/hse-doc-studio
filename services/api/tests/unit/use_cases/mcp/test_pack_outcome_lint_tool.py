"""Тул `pack_outcome_lint` (template-studio-outcome.md, 4.7, срез O8) без HTTP и без диска: служба линтера подменена,
проверяется, что тул передаёт ей, как показывает находки и покрытие и как переводит отказы."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import EditFormat
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.mcp.entities import MCP_PACKS_SCOPE, McpToolGroup
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.rate_limit import PACK_OUTCOME_LINT
from hse_doc_studio.use_cases.mcp.catalog import RULES_BY_NAME
from hse_doc_studio.use_cases.mcp.tools import pack_outcome as tools
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError
from hse_doc_studio.use_cases.pack_studio.access import PackStudioAccess
from hse_doc_studio.use_cases.pack_studio.outcome_lint import PackOutcomeLintService
from hse_doc_studio.use_cases.pack_studio.outcome_service import OutcomeReply

WS = uuid4()
ACTOR = Actor.user("u1", source=ActorSource.pat, scopes=frozenset({"mcp", "packs"}))
_ARGS = {"wording": "tech", "workspace_id": str(WS), "version": "hse-cs-se/vkr/2026.1.2"}

_BODY: dict[str, Any] = {
    "workspace_id": str(WS),
    "pack": "hse-cs-se",
    "template": "vkr",
    "version": "2026.1.2",
    "state": "work_tree",
    "revision": "sha256-x",
    "errors": 1,
    "warnings": 1,
    "infos": 1,
    "jinja": "not_run",
    "atlas_skipped": False,
    "findings": [
        {
            "rule_id": "required-hidden",
            "severity": "error",
            "message": "Поле скрыто",
            "hint": "Снимите условие",
            "file": "version.yaml",
            "pointer": "/forms/0",
            "line": 12,
            "elements": [],
            "witnesses": [{"kind": "project", "staffing": "solo"}],
        },
        {
            "rule_id": "translation-missing",
            "severity": "warning",
            "message": "Нет перевода",
            "hint": None,
            "file": "version.yaml",
            "pointer": None,
            "line": None,
            "elements": [],
            "witnesses": [],
        },
        {
            "rule_id": "dimension-no-effect",
            "severity": "info",
            "message": "Ни на что не влияет",
            "hint": "Нормально",
            "file": None,
            "pointer": None,
            "line": None,
            "elements": [],
            "witnesses": [],
        },
    ],
    "coverage": {
        "scenarios": 2,
        "rules_total": 10,
        "rules_covered": 4,
        "rules_half": 3,
        "rules_uncovered": 3,
        "rules": [],
        "percent": 55.5,
        "rows_total": 864,
        "rows_touched": 2,
        "uncovered_rows": [{"inputs": {"kind": "research", "staffing": "team2"}, "gain": 7}],
        "rules_omitted": 0,
        "approximate": False,
    },
}


@pytest.fixture(autouse=True)
def _actor() -> Iterator[None]:
    set_current_actor(ACTOR)
    set_interface_language("ru")
    yield
    set_current_actor(None)
    set_interface_language(None)


class _Service:
    def __init__(self, body: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._body = body
        self._error = error

    async def lint(
        self, actor: Actor, ws: UUID, pack: str, template: str, version: str, state: str, **kw: Any
    ) -> OutcomeReply:
        self.calls.append({"actor": actor, "ws": ws, "ref": (pack, template, version), "state": state, **kw})
        if self._error is not None:
            raise self._error
        return OutcomeReply("etag", self._body)


class _Access:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def require(self, actor: Actor) -> None:
        if self.error is not None:
            raise self.error


class _Deps:
    def __init__(self, service: _Service, access: _Access) -> None:
        self._by_type: dict[object, object] = {PackOutcomeLintService: service, PackStudioAccess: access}

    async def get(self, dependency_type: Any, component: str | None = None) -> Any:
        return self._by_type[dependency_type]


def _ctx() -> AgentToolContext:
    return AgentToolContext(project_id=UUID(int=0), model="mcp-client", edit_format=EditFormat.search_replace)


def _tool(service: _Service, access: _Access | None = None) -> Any:
    return tools.PackOutcomeLintTool(_Deps(service, access or _Access()))


def test__catalog__read_only_packs_tool_with_scope_and_its_own_rate() -> None:
    rule = RULES_BY_NAME["pack_outcome_lint"]

    assert rule.meta.group is McpToolGroup.packs
    assert rule.meta.read_only
    assert not rule.meta.dangerous
    assert rule.scope == MCP_PACKS_SCOPE
    assert rule.rate is PACK_OUTCOME_LINT
    assert (PACK_OUTCOME_LINT.limit, PACK_OUTCOME_LINT.window_s) == (6, 60)


async def test__tool__passes_state_and_jinja_to_the_service() -> None:
    service = _Service(_BODY)

    result = await _tool(service).handle(_ctx(), {**_ARGS, "state": "head", "jinja": True})

    assert result.is_error is False, result.text
    (call,) = service.calls
    assert (call["actor"], call["ws"], call["ref"], call["state"], call["jinja"]) == (
        ACTOR,
        WS,
        ("hse-cs-se", "vkr", "2026.1.2"),
        "head",
        True,
    )


async def test__text__shows_findings_with_place_hint_and_a_combination_then_the_coverage() -> None:
    result = await _tool(_Service(_BODY)).handle(_ctx(), _ARGS)

    text = result.text
    assert text.splitlines()[0] == (
        "Линтер результата hse-cs-se/vkr/2026.1.2 (work_tree): ошибок 1, предупреждений 1, информации 1."
    )
    assert "- [error] required-hidden version.yaml:12 (/forms/0): Поле скрыто" in text
    assert "    как исправить: Снимите условие" in text
    assert "    комбинация: kind=project, staffing=solo" in text
    assert "- [warning] translation-missing version.yaml: Нет перевода" in text
    assert "dimension-no-effect" not in text
    assert "Покрытие правил сценариями: 55.5% исходов" in text
    assert "затронуто 2 из 864" in text
    assert "+7 исходов: kind=research, staffing=team2" in text


async def test__severity_and_limit_shape_the_text() -> None:
    everything = await _tool(_Service(_BODY)).handle(_ctx(), {**_ARGS, "severity": "info"})
    only_errors = await _tool(_Service(_BODY)).handle(_ctx(), {**_ARGS, "severity": "error"})
    limited = await _tool(_Service(_BODY)).handle(_ctx(), {**_ARGS, "limit": 1})

    assert "dimension-no-effect" in everything.text
    assert "translation-missing" not in only_errors.text
    assert "required-hidden" in only_errors.text
    assert "translation-missing" not in limited.text
    assert limited.truncated


async def test__text__no_findings_and_the_skipped_atlas_are_said_plainly() -> None:
    body = {
        **_BODY,
        "findings": [],
        "errors": 0,
        "warnings": 0,
        "infos": 0,
        "atlas_skipped": True,
        "jinja": "unavailable",
    }
    body["coverage"] = {**_BODY["coverage"], "approximate": True, "uncovered_rows": []}

    text = (await _tool(_Service(body)).handle(_ctx(), {**_ARGS, "state": "head", "jinja": True})).text

    assert "Находок нет." in text
    assert "только статические правила" in text
    assert "Правила Jinja только на рабочем дереве" in text
    assert "приближённые" in text


async def test__formats() -> None:
    tool = _tool(_Service(_BODY))

    text = await tool.handle(_ctx(), _ARGS)
    structured = await tool.handle(_ctx(), {**_ARGS, "format": "json"})
    both = await tool.handle(_ctx(), {**_ARGS, "format": "both"})

    assert json.loads(structured.text)["coverage"]["percent"] == 55.5
    assert json.loads(both.text)["text"] == text.text


@pytest.mark.parametrize("args", [{"severity": "fatal"}, {"format": "xml"}, {"state": "tail"}])
async def test__bad_arguments__are_refused_before_the_service(args: dict[str, Any]) -> None:
    service = _Service(_BODY)

    with pytest.raises(ArgumentError):
        await _tool(service).handle(_ctx(), {**_ARGS, **args})

    assert service.calls == []


async def test__refusals_of_the_service_become_messages_with_a_hint() -> None:
    error = PackStudioError(PackStudioErrorCode.outcome_busy, reason="timeout", retry_after_s=5)

    result = await _tool(_Service(error=error)).handle(_ctx(), _ARGS)

    assert result.is_error
    assert "через 5 с" in result.text


async def test__guard__a_closed_section_stops_the_call_before_the_service() -> None:
    service = _Service(_BODY)
    access = _Access(PackStudioError(PackStudioErrorCode.pack_studio_disabled))

    result = await _tool(service, access).handle(_ctx(), _ARGS)

    assert result.is_error
    assert service.calls == []
