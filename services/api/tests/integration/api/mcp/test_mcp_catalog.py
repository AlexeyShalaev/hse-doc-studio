"""Каталог MCP против настоящего реестра агента: таблица правил и обработчики не расходятся."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from dishka import AsyncContainer
from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.mcp.entities import McpToolGroup
from hse_doc_studio.use_cases.chat._registry import ToolRegistry
from hse_doc_studio.use_cases.chat.tool_access import TOOL_ACCESS
from hse_doc_studio.use_cases.mcp.catalog import MCP_TOOL_CLASSES, MCP_TOOL_RULES, RULES_BY_NAME, McpCatalog

from tests.fixtures.app import create_test_container

# Тулы агента, которые MCP не выставляет: интерфейсные действия (docs/design/mcp.md, раздел 5).
_NOT_EXPOSED = {"ask_user", "set_theme", "set_engine"}


@pytest_asyncio.fixture
async def request_container(tmp_path: Path) -> AsyncIterator[AsyncContainer]:
    root = create_test_container(tmp_path / "data")
    async with root() as container:
        yield container
    await root.close()


async def test__catalog__server_mode__has_every_rule_but_local_only(request_container: AsyncContainer) -> None:
    registry = await request_container.get(ToolRegistry)

    catalog = McpCatalog(registry, request_container, server_mode=True)

    assert [e.meta.name for e in catalog.all()] == [r.name for r in MCP_TOOL_RULES if not r.meta.local_only]
    assert catalog.get("clone_cloud_project") is None


async def test__catalog__local_mode__drops_server_only(request_container: AsyncContainer) -> None:
    catalog = McpCatalog(await request_container.get(ToolRegistry), request_container, server_mode=False)

    groups = {e.meta.group for e in catalog.all()}

    assert McpToolGroup.review not in groups
    assert McpToolGroup.admin not in groups
    assert catalog.get("clone_cloud_project") is not None


async def test__catalog__local_mode__create_project_requires_folder(request_container: AsyncContainer) -> None:
    catalog = McpCatalog(await request_container.get(ToolRegistry), request_container, server_mode=False)

    entry = catalog.get("create_project")

    assert entry is not None
    assert "folder" in entry.spec.parameters["required"]
    assert "ask_user" not in entry.spec.description


async def test__catalog__set_project_people__needs_project_settings(request_container: AsyncContainer) -> None:
    catalog = McpCatalog(await request_container.get(ToolRegistry), request_container, server_mode=True)

    entry = catalog.get("set_project_people")

    assert entry is not None
    assert entry.rule.action is Action.PROJECT_SETTINGS
    assert entry.rule.guards_write
    assert entry.spec.parameters["required"] == ["project_id"]


@pytest.mark.parametrize("server_mode", [True, False])
async def test__catalog__set_document_variant__files_write_in_the_document_author_scope(
    request_container: AsyncContainer, server_mode: bool
) -> None:
    catalog = McpCatalog(await request_container.get(ToolRegistry), request_container, server_mode=server_mode)

    entry = catalog.get("set_document_variant")

    assert entry is not None
    assert entry.rule.action is Action.FILES_WRITE
    assert entry.rule.instance_args == ("doc_id",)
    assert entry.rule.guards_write
    assert entry.spec.parameters["required"] == ["project_id", "doc_id"]


async def test__catalog__kinds_match_handlers(request_container: AsyncContainer) -> None:
    catalog = McpCatalog(await request_container.get(ToolRegistry), request_container, server_mode=True)

    mismatched = [e.meta.name for e in catalog.all() if e.meta.kind is not e.definition.kind]

    assert not mismatched


async def test__catalog__every_agent_tool_is_ruled_or_excluded(request_container: AsyncContainer) -> None:
    registry = await request_container.get(ToolRegistry)

    missing = {d.spec.name for d in registry.all()} - set(RULES_BY_NAME) - _NOT_EXPOSED

    assert not missing


def test__rules__agent_tools__use_the_same_action_as_the_agent() -> None:
    differing = {
        name: (rule.action, TOOL_ACCESS[name].action)
        for name, rule in RULES_BY_NAME.items()
        if name in TOOL_ACCESS and rule.action is not TOOL_ACCESS[name].action
    }

    assert not differing


def test__rules__names_are_unique_and_every_class_is_ruled() -> None:
    names = [r.name for r in MCP_TOOL_RULES]

    assert len(names) == len(set(names))
    assert {cls.spec.name for cls in MCP_TOOL_CLASSES} <= set(names)


def test__rules__admin_tools__are_server_only() -> None:
    assert all(r.meta.server_only for r in MCP_TOOL_RULES if r.meta.group is McpToolGroup.admin)


def test__rules__no_tool_is_both_server_and_local_only() -> None:
    assert not [r.name for r in MCP_TOOL_RULES if r.meta.server_only and r.meta.local_only]
