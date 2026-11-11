"""Канал команд раннеру на сервере: постановка, долгий опрос, ход и итог, просрочка и потеря (storage-cleanup.md, 5.3)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.jobs.codec import decode
from hse_doc_studio.core.jobs.control import (
    RunnerCommandBusyError,
    RunnerCommandUnsupportedError,
    RunnerControlError,
)
from hse_doc_studio.core.jobs.disk import (
    CommandProgress,
    CommandStep,
    CommandStepKind,
    CommandStepStatus,
    DiskCleanupPayload,
    DiskMeasurePayload,
    DiskTarget,
    RunnerCommand,
    RunnerCommandKind,
    RunnerCommandState,
    RunnerDiskReport,
)
from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.core.jobs.errors import RunnerAuthError
from hse_doc_studio.core.jobs.runners import Runner, RunnerOwnerKind
from hse_doc_studio.core.jobs.wire import (
    FEATURE_ANNOUNCE,
    FEATURE_CONTROL,
    FEATURE_DISK,
    CommandProgressRequest,
    ControlPollRequest,
)
from hse_doc_studio.use_cases.jobs.runner_control import RunnerCommandWakeup, RunnerControlService

from tests.fakes.runner_commands import InMemoryRunnerCommandRepository, InMemoryRunnerDiskStore
from tests.fakes.runners import InMemoryRunnerRepository

pytestmark = pytest.mark.unit

_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "runner" / "fixtures"
_S = RunnerCommandState
_CLEANUP = DiskCleanupPayload(targets=(DiskTarget.build_cache, DiskTarget.runner_cache))
_STEP = CommandStep(CommandStepKind.build_cache, None, CommandStepStatus.done, 1024, None)
_PROGRESS = CommandProgress(steps=(_STEP,), freed_bytes=1024, error=None)
_EMPTY = CommandProgress(steps=(), freed_bytes=0, error=None)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class _Observer:
    def __init__(self, *, fail: bool = False) -> None:
        self.closed: list[RunnerCommand] = []
        self._fail = fail

    async def command_finished(self, command: RunnerCommand) -> None:
        self.closed.append(command)
        if self._fail:
            raise RuntimeError("boom")


class _Env:
    def __init__(self, *, observers: tuple[_Observer, ...] = ()) -> None:
        self.clock = _Clock()
        self.runners = InMemoryRunnerRepository()
        self.commands = InMemoryRunnerCommandRepository(self.runners)
        self.disks = InMemoryRunnerDiskStore(self.runners)
        self.wakeup = RunnerCommandWakeup()
        self.observer = _Observer()
        self.service = RunnerControlService(
            self.commands,
            self.disks,
            self.runners,
            self.wakeup,
            clock=self.clock,
            poll_interval_s=0.05,
            observers=(self.observer, *observers),
        )

    async def runner(self, features: frozenset[str] = frozenset({FEATURE_CONTROL, FEATURE_DISK})) -> Runner:
        runner = Runner(
            id=uuid4().hex,
            name="r",
            token_hash=uuid4().hex,
            tags=frozenset({"compile"}),
            concurrency=1,
            resource_class="standard",
            version="0.22.0",
            created_at=self.clock.now,
            features=frozenset({FEATURE_ANNOUNCE}) | features,
        )
        await self.runners.add(runner)
        return runner

    async def cleanup(self, runner: Runner) -> RunnerCommand:
        return await self.service.enqueue(runner, RunnerCommandKind.disk_cleanup, _CLEANUP, created_by="admin")

    async def delivered(self, runner: Runner) -> RunnerCommand:
        await self.cleanup(runner)
        polled = await self.service.poll(runner, ControlPollRequest(wait_s=0))
        assert polled.command is not None
        return await self.service.get(runner.id, polled.command.id)

    async def report(self, runner: Runner, command: RunnerCommand, state: RunnerCommandState) -> bool:
        progress = _PROGRESS if state is not _S.running else _EMPTY
        response = await self.service.progress(runner, command.id, CommandProgressRequest(state, progress))
        return response.cancel


def _report(name: str = "docker") -> RunnerDiskReport:
    raw = json.loads((_FIXTURES / "RunnerDiskReportBody" / f"{name}.json").read_text(encoding="utf-8"))
    return decode(RunnerDiskReport, raw)


def _code(exc: pytest.ExceptionInfo[RunnerControlError]) -> RunnerErrorCode:
    return exc.value.code


# --- постановка и остановка ---


async def test__enqueue__runner_without_control_or_disk__unsupported() -> None:
    env = _Env()
    for features in (frozenset(), frozenset({FEATURE_CONTROL}), frozenset({FEATURE_DISK})):
        runner = await env.runner(features)
        with pytest.raises(RunnerCommandUnsupportedError):
            await env.cleanup(runner)


async def test__enqueue__second_cleanup__busy_and_measure_during_cleanup__busy() -> None:
    env = _Env()
    runner = await env.runner()
    first = await env.cleanup(runner)

    with pytest.raises(RunnerCommandBusyError) as busy:
        await env.cleanup(runner)
    with pytest.raises(RunnerCommandBusyError):
        await env.service.enqueue(runner, RunnerCommandKind.disk_measure, DiskMeasurePayload(), created_by="admin")

    assert busy.value.command is not None
    assert busy.value.command.id == first.id


async def test__enqueue__measure_twice__returns_the_queued_one() -> None:
    env = _Env()
    runner = await env.runner()

    first = await env.service.enqueue(runner, RunnerCommandKind.disk_measure, DiskMeasurePayload(), created_by="a")
    again = await env.service.enqueue(runner, RunnerCommandKind.disk_measure, DiskMeasurePayload(), created_by="b")

    assert again.id == first.id
    assert first.state is _S.queued


async def test__enqueue__keeps_last_twenty_finished_per_runner() -> None:
    env = _Env()
    runner = await env.runner()
    other = await env.runner()
    foreign = await env.cleanup(other)
    for _ in range(25):
        command = await env.cleanup(runner)
        await env.service.cancel(runner.id, command.id)
        env.clock.advance(1)

    kept = await env.service.recent(runner.id, limit=100)

    assert len(kept) == 20
    assert await env.commands.get(foreign.id) is not None


async def test__cancel__queued_closes_at_once_and_tells_observers() -> None:
    env = _Env()
    runner = await env.runner()
    command = await env.cleanup(runner)

    cancelled = await env.service.cancel(runner.id, command.id)

    assert cancelled.state is _S.cancelled
    assert cancelled.finished_at == env.clock.now
    assert [c.id for c in env.observer.closed] == [command.id]
    # Новая очистка ставится сразу: остановленная больше не держит раннер.
    await env.cleanup(runner)


async def test__cancel__delivered__cancelling_until_the_runner_reports() -> None:
    env = _Env()
    runner = await env.runner()
    command = await env.delivered(runner)

    cancelling = await env.service.cancel(runner.id, command.id)
    again = await env.service.cancel(runner.id, command.id)

    assert cancelling.state is again.state is _S.cancelling
    assert env.observer.closed == []


async def test__cancel__finished_or_foreign__command_finished_and_not_found() -> None:
    env = _Env()
    runner = await env.runner()
    other = await env.runner()
    command = await env.cleanup(runner)
    await env.service.cancel(runner.id, command.id)

    with pytest.raises(RunnerControlError) as finished:
        await env.service.cancel(runner.id, command.id)
    with pytest.raises(RunnerControlError) as foreign:
        await env.service.cancel(other.id, command.id)

    assert _code(finished) is RunnerErrorCode.command_finished
    assert _code(foreign) is RunnerErrorCode.command_not_found


# --- долгий опрос ---


async def test__poll__without_control__feature_not_negotiated() -> None:
    env = _Env()
    runner = await env.runner(frozenset({FEATURE_DISK}))

    with pytest.raises(RunnerControlError) as exc:
        await env.service.poll(runner, ControlPollRequest(wait_s=0))

    assert _code(exc) is RunnerErrorCode.feature_not_negotiated


async def test__poll__hands_out_the_oldest_command_once() -> None:
    env = _Env()
    runner = await env.runner()
    measure = await env.service.enqueue(runner, RunnerCommandKind.disk_measure, DiskMeasurePayload(), created_by="a")
    env.clock.advance(1)
    cleanup = await env.cleanup(runner)

    first = await env.service.poll(runner, ControlPollRequest(wait_s=0))
    second = await env.service.poll(runner, ControlPollRequest(wait_s=0))
    third = await env.service.poll(runner, ControlPollRequest(wait_s=0))

    assert first.command is not None
    assert second.command is not None
    assert (first.command.id, first.command.kind) == (measure.id, RunnerCommandKind.disk_measure)
    assert (second.command.id, second.command.payload) == (cleanup.id, _CLEANUP)
    assert second.command.issued_at == cleanup.created_at
    assert third.command is None
    delivered = await env.service.get(runner.id, cleanup.id)
    assert delivered.state is _S.delivered
    assert delivered.delivered_at == env.clock.now


async def test__poll__waiting_runner_wakes_on_enqueue() -> None:
    env = _Env()
    env.service._interval = 30.0  # noqa: SLF001 — пробуждение, а не перепроверка по интервалу
    runner = await env.runner()
    waiting = asyncio.create_task(env.service.poll(runner, ControlPollRequest(wait_s=10)))
    await asyncio.sleep(0.05)

    command = await env.cleanup(runner)
    polled = await asyncio.wait_for(waiting, 2)

    assert polled.command is not None
    assert polled.command.id == command.id


async def test__poll__other_runner_or_lost_disk_feature__gets_nothing() -> None:
    env = _Env()
    runner = await env.runner()
    other = await env.runner()
    await env.cleanup(runner)
    # Раннер откатился на версию без `disk`: команда ему не выдаётся и истечёт.
    await env.runners.add(replace(runner, features=frozenset({FEATURE_CONTROL})))

    assert (await env.service.poll(other, ControlPollRequest(wait_s=0))).command is None
    assert (await env.service.poll(runner, ControlPollRequest(wait_s=0))).command is None


async def test__poll__queued_too_long__not_handed_out_and_expires() -> None:
    env = _Env()
    runner = await env.runner()
    command = await env.cleanup(runner)
    env.clock.advance(601)

    polled = await env.service.poll(runner, ControlPollRequest(wait_s=0))
    expired = await env.service.get(runner.id, command.id)

    assert polled.command is None
    assert expired.state is _S.expired
    assert [c.state for c in env.observer.closed] == [_S.expired]


async def test__poll__revoked_or_offline_after_start__ends_empty() -> None:
    env = _Env()
    runner = await env.runner()
    waiting = asyncio.create_task(env.service.poll(runner, ControlPollRequest(wait_s=10)))
    await asyncio.sleep(0.05)
    await env.runners.mark_offline(runner.id, env.clock.now)

    polled = await asyncio.wait_for(waiting, 2)

    assert polled.command is None


async def test__poll__client_gone__ends_empty() -> None:
    env = _Env()
    runner = await env.runner()

    async def gone() -> bool:
        return True

    polled = await asyncio.wait_for(env.service.poll(runner, ControlPollRequest(wait_s=10), gone=gone), 1)

    assert polled.command is None


# --- ход и итог ---


@pytest.mark.parametrize(
    ("start", "reported", "after", "cancel"),
    [
        (_S.delivered, _S.running, _S.running, False),
        (_S.delivered, _S.done, _S.done, False),
        (_S.delivered, _S.cancelled, _S.cancelled, False),
        (_S.delivered, _S.error, _S.error, False),
        (_S.running, _S.running, _S.running, False),
        (_S.running, _S.done, _S.done, False),
        (_S.cancelling, _S.running, _S.cancelling, True),
        (_S.cancelling, _S.cancelled, _S.cancelled, False),
        (_S.cancelling, _S.done, _S.done, False),
        (_S.cancelling, _S.error, _S.error, False),
    ],
)
async def test__progress__transitions(
    start: RunnerCommandState, reported: RunnerCommandState, after: RunnerCommandState, cancel: bool
) -> None:
    env = _Env()
    runner = await env.runner()
    command = await env.delivered(runner)
    if start is _S.running:
        await env.report(runner, command, _S.running)
    if start is _S.cancelling:
        await env.service.cancel(runner.id, command.id)
    env.clock.advance(5)

    answered = await env.report(runner, command, reported)
    stored = await env.service.get(runner.id, command.id)

    assert answered is cancel
    assert stored.state is after
    assert stored.updated_at == env.clock.now
    assert stored.progress == (_EMPTY if reported is _S.running else _PROGRESS)
    assert (stored.finished_at == env.clock.now) is after.finished
    assert [c.state for c in env.observer.closed] == ([after] if after.finished else [])


async def test__progress__repeated_final__harmless_and_observed_once() -> None:
    env = _Env()
    runner = await env.runner()
    command = await env.delivered(runner)

    assert await env.report(runner, command, _S.done) is False
    assert await env.report(runner, command, _S.done) is False

    assert len(env.observer.closed) == 1


@pytest.mark.parametrize("reported", [_S.running, _S.error])
async def test__progress__after_another_final_or_loss__command_finished(reported: RunnerCommandState) -> None:
    env = _Env()
    runner = await env.runner()
    done = await env.delivered(runner)
    await env.report(runner, done, _S.done)
    lost = await env.delivered(runner)
    env.clock.advance(181)
    await env.service.settle()

    for command in (done, lost):
        with pytest.raises(RunnerControlError) as exc:
            await env.report(runner, command, reported)
        assert _code(exc) is RunnerErrorCode.command_finished


async def test__progress__foreign_unknown_or_not_yet_delivered__not_found() -> None:
    env = _Env()
    runner = await env.runner()
    other = await env.runner()
    queued = await env.cleanup(runner)
    delivered = await env.delivered(other)

    for who, command_id in ((runner, queued.id), (runner, delivered.id), (runner, uuid4())):
        with pytest.raises(RunnerControlError) as exc:
            await env.service.progress(who, command_id, CommandProgressRequest(_S.running, _EMPTY))
        assert _code(exc) is RunnerErrorCode.command_not_found


async def test__progress__without_control__feature_not_negotiated() -> None:
    env = _Env()
    runner = await env.runner(frozenset({FEATURE_DISK}))

    with pytest.raises(RunnerControlError) as exc:
        await env.service.progress(runner, uuid4(), CommandProgressRequest(_S.running, _EMPTY))

    assert _code(exc) is RunnerErrorCode.feature_not_negotiated


async def test__measure__closes_from_delivered_straight_to_done() -> None:
    env = _Env()
    runner = await env.runner()
    command = await env.service.enqueue(runner, RunnerCommandKind.disk_measure, DiskMeasurePayload(), created_by="a")
    await env.service.poll(runner, ControlPollRequest(wait_s=0))

    await env.service.report_disk(runner, _report())
    await env.service.progress(runner, command.id, CommandProgressRequest(_S.done, _EMPTY))

    stored = await env.service.get(runner.id, command.id)
    assert stored.state is _S.done
    assert stored.progress == _EMPTY


# --- просрочка и потеря ---


async def test__settle__silence_loses_in_flight_commands_only_after_three_minutes() -> None:
    env = _Env()
    runner = await env.runner()
    command = await env.delivered(runner)
    env.clock.advance(170)
    await env.report(runner, command, _S.running)
    env.clock.advance(170)

    assert await env.service.settle() == 0
    env.clock.advance(11)
    assert await env.service.settle() == 1
    assert (await env.service.get(runner.id, command.id)).state is _S.lost
    assert [c.state for c in env.observer.closed] == [_S.lost]


@pytest.mark.parametrize("how", ["revoked", "offline"])
async def test__settle__revoked_or_offline_runner_loses_its_command(how: str) -> None:
    env = _Env()
    runner = await env.runner()
    command = await env.delivered(runner)
    queued_other = await env.cleanup(await env.runner())
    env.clock.advance(1)
    if how == "revoked":
        await env.runners.revoke(runner.id, env.clock.now)
    else:
        await env.runners.mark_offline(runner.id, env.clock.now)

    lost = await env.service.get(runner.id, command.id)

    assert lost.state is _S.lost
    assert (await env.commands.get(queued_other.id)).state is _S.queued  # type: ignore[union-attr]


async def test__settle__offline_before_delivery__does_not_lose_the_new_command() -> None:
    env = _Env()
    runner = await env.runner()
    await env.runners.mark_offline(runner.id, env.clock.now)
    env.clock.advance(1)
    command = await env.delivered(runner)

    assert (await env.service.get(runner.id, command.id)).state is _S.delivered


async def test__observer_failure__does_not_undo_the_transition() -> None:
    failing = _Observer(fail=True)
    env = _Env(observers=(failing,))
    runner = await env.runner()
    command = await env.cleanup(runner)

    cancelled = await env.service.cancel(runner.id, command.id)

    assert cancelled.state is _S.cancelled
    assert len(failing.closed) == len(env.observer.closed) == 1


# --- замер диска ---


async def test__report_disk__stored_for_shared_and_personal_runners() -> None:
    env = _Env()
    shared = await env.runner()
    personal = replace(await env.runner(), owner_kind=RunnerOwnerKind.user, owner_id="u1")
    await env.runners.add(personal)

    await env.service.report_disk(shared, _report("docker"))
    await env.service.report_disk(personal, _report("desktop"))

    stored = await env.service.disk(shared.id)
    assert stored is not None
    assert stored.report == _report("docker")
    assert stored.received_at == env.clock.now
    assert set(await env.service.disks()) == {shared.id, personal.id}


async def test__report_disk__without_disk_feature_or_revoked__refused() -> None:
    env = _Env()
    old = await env.runner(frozenset({FEATURE_CONTROL}))
    revoked = await env.runner()
    await env.runners.revoke(revoked.id, env.clock.now)

    with pytest.raises(RunnerControlError) as exc:
        await env.service.report_disk(old, _report())
    with pytest.raises(RunnerAuthError):
        await env.service.report_disk(revoked, _report())

    assert _code(exc) is RunnerErrorCode.feature_not_negotiated
    assert await env.service.disk(old.id) is None
