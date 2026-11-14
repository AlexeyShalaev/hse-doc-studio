"""Автоочистка по порогу места на сервере: `RunnerControlService.disk_check` (storage-cleanup.md, 14.3)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.jobs.control import RunnerControlError
from hse_doc_studio.core.jobs.disk import (
    DISK_AUTO_TARGETS,
    DiskAutoPolicy,
    DiskCleanupPayload,
    RunnerCommandKind,
    RunnerCommandState,
)
from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.core.jobs.runners import RunnerOwnerKind
from hse_doc_studio.core.jobs.wire import (
    FEATURE_CONTROL,
    FEATURE_DISK,
    FEATURE_DISK_AUTO,
    CommandProgressRequest,
    DiskCheckRequest,
)

from tests.unit.use_cases.jobs.test_runner_control import _PROGRESS, _Env, _Observer

pytestmark = pytest.mark.unit

_AUTO = frozenset({FEATURE_CONTROL, FEATURE_DISK, FEATURE_DISK_AUTO})
_GB = 1024**3
# 5 % свободно: ниже порога по умолчанию (10 %).
_LOW = DiskCheckRequest(free_bytes=5 * _GB, total_bytes=100 * _GB)
_HIGH = DiskCheckRequest(free_bytes=30 * _GB, total_bytes=100 * _GB)


async def test__below_threshold__delivered_auto_command_and_audit_start() -> None:
    env = _Env()
    runner = await env.runner(_AUTO)

    response = await env.service.disk_check(runner, _LOW)

    assert response.command is not None
    assert response.command.kind is RunnerCommandKind.disk_cleanup
    assert response.command.payload == DiskCleanupPayload(targets=DISK_AUTO_TARGETS, auto=True)
    stored = await env.service.get(runner.id, response.command.id)
    assert stored.state is RunnerCommandState.delivered
    assert stored.created_by == ""
    assert stored.delivered_at == env.clock.now
    auto = await env.disks.get_auto(runner.id)
    assert auto is not None
    assert auto.last is not None
    assert auto.last.command_id == stored.id
    assert (auto.last.free_bytes, auto.last.total_bytes, auto.last.finished_at) == (5 * _GB, 100 * _GB, None)
    assert [(c.id, free, total, pct) for c, free, total, pct in env.observer.started] == [
        (stored.id, 5 * _GB, 100 * _GB, 10)
    ]


async def test__above_threshold_or_disabled__nothing() -> None:
    env = _Env()
    runner = await env.runner(_AUTO)
    assert (await env.service.disk_check(runner, _HIGH)).command is None

    await env.disks.set_auto_policy(runner.id, DiskAutoPolicy(enabled=False))
    assert (await env.service.disk_check(runner, _LOW)).command is None

    await env.disks.set_auto_policy(runner.id, DiskAutoPolicy(enabled=True, min_free_percent=40))
    assert (await env.service.disk_check(runner, _HIGH)).command is not None


async def test__empty_volume__nothing() -> None:
    env = _Env()
    runner = await env.runner(_AUTO)

    assert (await env.service.disk_check(runner, DiskCheckRequest(free_bytes=0, total_bytes=0))).command is None


async def test__not_more_often_than_once_an_hour() -> None:
    env = _Env()
    runner = await env.runner(_AUTO)
    first = await env.service.disk_check(runner, _LOW)
    assert first.command is not None
    await env.service.progress(runner, first.command.id, CommandProgressRequest(RunnerCommandState.done, _PROGRESS))

    env.clock.advance(59 * 60)
    assert (await env.service.disk_check(runner, _LOW)).command is None
    env.clock.advance(60)
    assert (await env.service.disk_check(runner, _LOW)).command is not None


async def test__running_cleanup__no_auto_and_interval_kept() -> None:
    env = _Env()
    runner = await env.runner(_AUTO)
    manual = await env.delivered(runner)

    assert (await env.service.disk_check(runner, _LOW)).command is None

    await env.service.progress(runner, manual.id, CommandProgressRequest(RunnerCommandState.done, _PROGRESS))
    # Ручная очистка интервал не тратила: автоочистка идёт сразу после неё.
    assert (await env.service.disk_check(runner, _LOW)).command is not None


async def test__personal_runner__never_auto() -> None:
    env = _Env()
    shared = await env.runner(_AUTO)
    personal = replace(shared, id="personal", token_hash="p", owner_kind=RunnerOwnerKind.user, owner_id="u1")
    await env.runners.add(personal)

    assert (await env.service.disk_check(personal, _LOW)).command is None


async def test__without_the_feature__not_negotiated() -> None:
    env = _Env()
    runner = await env.runner()

    with pytest.raises(RunnerControlError) as exc:
        await env.service.disk_check(runner, _LOW)
    assert exc.value.code is RunnerErrorCode.feature_not_negotiated


async def test__final_result_goes_to_disk_auto_last() -> None:
    env = _Env()
    runner = await env.runner(_AUTO)
    command = (await env.service.disk_check(runner, _LOW)).command
    assert command is not None

    env.clock.advance(90)
    await env.service.progress(runner, command.id, CommandProgressRequest(RunnerCommandState.done, _PROGRESS))

    auto = await env.disks.get_auto(runner.id)
    assert auto is not None
    assert auto.last is not None
    assert auto.last.state is RunnerCommandState.done
    assert auto.last.freed_bytes == _PROGRESS.freed_bytes
    assert auto.last.finished_at == env.clock.now
    assert auto.last.free_bytes == 5 * _GB
    assert [c.id for c in env.observer.closed] == [command.id]


async def test__lost_auto_cleanup__recorded_as_lost() -> None:
    env = _Env()
    runner = await env.runner(_AUTO)
    command = (await env.service.disk_check(runner, _LOW)).command
    assert command is not None

    env.clock.advance(4 * 60)
    await env.service.settle(runner.id)

    auto = await env.disks.get_auto(runner.id)
    assert auto is not None
    assert auto.last is not None
    assert auto.last.state is RunnerCommandState.lost


async def test__observer_failure_does_not_stop_the_command() -> None:
    env = _Env(observers=(_Observer(fail=True),))
    runner = await env.runner(_AUTO)

    assert (await env.service.disk_check(runner, _LOW)).command is not None


async def test__revoked_runner__nothing() -> None:
    env = _Env()
    runner = await env.runner(_AUTO)
    await env.runners.revoke(runner.id, env.clock.now)
    revoked = await env.runners.get(runner.id)
    assert revoked is not None

    assert (await env.service.disk_check(revoked, _LOW)).command is None
