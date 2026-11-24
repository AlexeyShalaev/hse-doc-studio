"""admin_runner_fleet, admin_runner_fleet_upgrade, admin_runner_fleet_cancel: тулы поверх общей службы обновления."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import EditFormat
from hse_doc_studio.core.identity.errors import IdentityError
from hse_doc_studio.use_cases.mcp.catalog import RULES_BY_NAME
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError
from hse_doc_studio.use_cases.mcp.tools.admin import (
    AdminRunnerFleetCancelTool,
    AdminRunnerFleetTool,
    AdminRunnerFleetUpgradeTool,
)
from hse_doc_studio.use_cases.runner_install import RunnerFleetService

from tests.unit.use_cases.runner_install.test_fleet import ADMIN, NEW, World

pytestmark = pytest.mark.unit


class _Deps:
    def __init__(self, service: RunnerFleetService) -> None:
        self._service = service

    async def get(self, dependency_type: Any, component: str | None = None) -> Any:
        assert dependency_type is RunnerFleetService
        return self._service


@pytest.fixture(autouse=True)
def _admin() -> Iterator[None]:
    set_current_actor(ADMIN)
    yield
    set_current_actor(None)


def _ctx() -> AgentToolContext:
    return AgentToolContext(project_id=uuid4(), model="mcp-client", edit_format=EditFormat.search_replace)


async def _call(tool: Any, args: dict[str, object]) -> Any:
    result = await tool.handle(_ctx(), args)
    assert result.is_error is False, result.text
    return json.loads(result.text)


def test__catalog__fleet_tools_are_admin_only_and_the_upgrade_is_dangerous() -> None:
    assert RULES_BY_NAME["admin_runner_fleet"].meta.admin is True
    assert RULES_BY_NAME["admin_runner_fleet"].meta.read_only is True
    assert RULES_BY_NAME["admin_runner_fleet_upgrade"].meta.dangerous is True
    assert RULES_BY_NAME["admin_runner_fleet_upgrade"].meta.read_only is False
    assert RULES_BY_NAME["admin_runner_fleet_cancel"].meta.admin is True


async def test__status__shows_runners_without_install_details() -> None:
    world = World()
    await world.runner("docker-1")
    await world.runner("chart", target=None)

    body = await _call(AdminRunnerFleetTool(_Deps(world.fleet)), {})  # type: ignore[arg-type]

    assert (body["server_version"], body["offer"], body["batch"]) == (NEW, True, None)
    assert [(r["name"], r["kind"], r["manual_reason"]) for r in body["runners"]] == [
        ("chart", "manual", "unknown"),
        ("docker-1", "docker", None),
    ]
    assert "ref" not in json.dumps(body)


async def test__upgrade__all_updates_every_runner_that_can_be_updated_from_here() -> None:
    world = World()
    await world.runner("docker-1")
    await world.runner("kube-1", target=world.kube.target)
    await world.runner("chart", target=None)
    deps = _Deps(world.fleet)

    started = await _call(AdminRunnerFleetUpgradeTool(deps), {"all": True})  # type: ignore[arg-type]
    batch = world.fleet.batch(ADMIN, started["id"])
    assert batch is not None
    await world.done(batch)
    done = await _call(AdminRunnerFleetTool(deps), {"batch_id": started["id"]})  # type: ignore[arg-type]

    assert done["state"] == "finished"
    assert {r["name"]: r["state"] for r in done["runners"]} == {"docker-1": "succeeded", "kube-1": "succeeded"}


async def test__upgrade__without_a_choice_or_with_a_manual_runner_is_an_argument_error() -> None:
    world = World()
    chart = await world.runner("chart", target=None)
    tool = AdminRunnerFleetUpgradeTool(_Deps(world.fleet))  # type: ignore[arg-type]

    with pytest.raises(ArgumentError):
        await tool.handle(_ctx(), {})
    with pytest.raises(ArgumentError):
        await tool.handle(_ctx(), {"all": True})
    with pytest.raises(ArgumentError):
        await tool.handle(_ctx(), {"runner_ids": [chart]})


async def test__cancel__stops_the_run_and_unknown_batch_is_an_error() -> None:
    world = World()
    a = await world.runner("docker-a")
    await world.runner("docker-b")
    world.docker.upgrade_gate = asyncio.Event()
    deps = _Deps(world.fleet)
    batch = await world.fleet.start(ADMIN, [a, world.ids["docker-b"]])
    for _ in range(200):
        if batch.items[0].state.value == "running":
            break
        await asyncio.sleep(0.005)

    cancelled = await _call(AdminRunnerFleetCancelTool(deps), {"batch_id": batch.id})  # type: ignore[arg-type]
    world.docker.upgrade_gate.set()
    await world.done(batch)

    assert cancelled["cancel_requested"] is True
    assert [i.state.value for i in batch.items] == ["succeeded", "skipped"]
    with pytest.raises(ArgumentError):
        await AdminRunnerFleetCancelTool(deps).handle(_ctx(), {"batch_id": "nope"})  # type: ignore[arg-type]


async def test__tools__need_an_instance_admin() -> None:
    from hse_doc_studio.core.access.entities import Actor  # noqa: PLC0415

    world = World()
    set_current_actor(Actor(kind="user", id="u", is_instance_admin=False))

    with pytest.raises(IdentityError):
        await AdminRunnerFleetTool(_Deps(world.fleet)).handle(_ctx(), {})  # type: ignore[arg-type]
