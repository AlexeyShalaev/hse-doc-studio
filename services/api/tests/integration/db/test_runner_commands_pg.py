"""Postgres: команды раннерам и замер диска. Частичный индекс очистки, предел 20, выдача под гонкой, просрочка и
потеря, долгий опрос на двух экземплярах сервиса с общей базой."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.jobs.codec import decode
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
    disk_cleanable_bytes,
)
from hse_doc_studio.core.jobs.runners import Runner
from hse_doc_studio.core.jobs.wire import FEATURE_CONTROL, FEATURE_DISK, ControlPollRequest
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.jobs import RunnerRow
from hse_doc_studio.infra.db.repositories.runner_commands import SqlRunnerCommandRepository, SqlRunnerDiskStore
from hse_doc_studio.infra.db.repositories.runners import SqlRunnerRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.use_cases.jobs.runner_control import RunnerCommandWakeup, RunnerControlService
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
_S = RunnerCommandState
_FIXTURES = Path(__file__).resolve().parents[5] / "contracts" / "runner" / "fixtures"
_CLEANUP = DiskCleanupPayload(targets=(DiskTarget.old_versions,), include_rollback=True)
_PROGRESS = CommandProgress(
    steps=(CommandStep(CommandStepKind.image, "studio:0.20.0", CommandStepStatus.done, 10, None),),
    freed_bytes=10,
    error=None,
)


class _Repos:
    def __init__(self, engine: AsyncEngine) -> None:
        sessions = SessionProvider(create_sessionmaker(engine))
        self.runners = SqlRunnerRepository(sessions)
        self.commands = SqlRunnerCommandRepository(sessions)
        self.disks = SqlRunnerDiskStore(sessions)

    async def runner(self, runner_id: str | None = None) -> Runner:
        runner = Runner(
            id=runner_id or uuid4().hex,
            name="r",
            token_hash=uuid4().hex,
            tags=frozenset({"compile"}),
            concurrency=1,
            resource_class="standard",
            version="0.22.0",
            created_at=NOW,
            features=frozenset({FEATURE_CONTROL, FEATURE_DISK}),
        )
        await self.runners.add(runner)
        return runner


def _command(
    runner_id: str,
    *,
    kind: RunnerCommandKind = RunnerCommandKind.disk_cleanup,
    state: RunnerCommandState = _S.queued,
    at: datetime = NOW,
) -> RunnerCommand:
    payload = _CLEANUP if kind is RunnerCommandKind.disk_cleanup else DiskMeasurePayload()
    return RunnerCommand(
        id=uuid4(),
        runner_id=runner_id,
        kind=kind,
        payload=payload,
        state=state,
        created_by="admin",
        created_at=at,
        updated_at=at,
    )


def _report(name: str = "docker") -> RunnerDiskReport:
    raw = json.loads((_FIXTURES / "RunnerDiskReportBody" / f"{name}.json").read_text(encoding="utf-8"))
    return decode(RunnerDiskReport, raw)


async def test__add__roundtrip_and_one_open_cleanup_per_runner(pg_migrated_engine: AsyncEngine) -> None:
    repos = _Repos(pg_migrated_engine)
    runner = await repos.runner()
    other = await repos.runner()
    first = _command(runner.id)

    assert await repos.commands.add(first) is True
    assert await repos.commands.add(_command(runner.id)) is False
    assert await repos.commands.add(_command(runner.id, kind=RunnerCommandKind.disk_measure)) is True
    assert await repos.commands.add(_command(other.id)) is True
    assert await repos.commands.get(first.id) == first
    assert await repos.commands.find_open(runner.id, RunnerCommandKind.disk_cleanup) == first

    await repos.commands.transition(first.id, expected=_S.queued, to=_S.cancelled, now=NOW)
    assert await repos.commands.add(_command(runner.id)) is True


async def test__add__keeps_twenty_latest_finished_and_every_open(pg_migrated_engine: AsyncEngine) -> None:
    repos = _Repos(pg_migrated_engine)
    runner = await repos.runner()
    other = await repos.runner()
    foreign = _command(other.id, state=_S.done)
    await repos.commands.add(foreign)
    for i in range(24):
        await repos.commands.add(_command(runner.id, state=_S.done, at=NOW + timedelta(seconds=i)))
    still_open = _command(runner.id, at=NOW - timedelta(days=1))
    await repos.commands.add(still_open)

    kept = await repos.commands.list_for_runner(runner.id, limit=100)

    assert len(kept) == 21
    assert kept[0].created_at == NOW + timedelta(seconds=23)
    assert still_open.id in {c.id for c in kept}
    assert await repos.commands.get(foreign.id) is not None


async def test__claim__concurrent_claimers_get_a_command_once(pg_migrated_engine: AsyncEngine) -> None:
    repos = _Repos(pg_migrated_engine)
    runner = await repos.runner()
    command = _command(runner.id, kind=RunnerCommandKind.disk_measure)
    await repos.commands.add(command)
    kinds = frozenset(RunnerCommandKind)

    claimed = await asyncio.gather(
        *(repos.commands.claim(runner.id, kinds, now=NOW, not_before=NOW - timedelta(minutes=10)) for _ in range(8))
    )

    winners = [c for c in claimed if c is not None]
    assert [c.id for c in winners] == [command.id]
    assert winners[0].state is _S.delivered
    assert winners[0].delivered_at == NOW


async def test__claim__skips_old_and_other_kinds(pg_migrated_engine: AsyncEngine) -> None:
    repos = _Repos(pg_migrated_engine)
    runner = await repos.runner()
    await repos.commands.add(_command(runner.id, at=NOW - timedelta(minutes=11)))
    await repos.commands.add(_command(runner.id, kind=RunnerCommandKind.disk_measure))

    nothing = await repos.commands.claim(
        runner.id, [RunnerCommandKind.disk_cleanup], now=NOW, not_before=NOW - timedelta(minutes=10)
    )

    assert nothing is None


async def test__transition__conditional_and_keeps_progress(pg_migrated_engine: AsyncEngine) -> None:
    repos = _Repos(pg_migrated_engine)
    runner = await repos.runner()
    command = _command(runner.id, state=_S.delivered)
    await repos.commands.add(command)
    later = NOW + timedelta(seconds=30)

    running = await repos.commands.transition(
        command.id, expected=_S.delivered, to=_S.running, now=later, progress=_PROGRESS
    )
    stale = await repos.commands.transition(command.id, expected=_S.delivered, to=_S.done, now=later)
    cancelling = await repos.commands.transition(command.id, expected=_S.running, to=_S.cancelling, now=later)
    done = await repos.commands.transition(command.id, expected=_S.cancelling, to=_S.done, now=later)

    assert running is not None
    assert running.progress == _PROGRESS
    assert stale is None
    assert cancelling is not None
    assert cancelling.progress == _PROGRESS
    assert done is not None
    assert (done.state, done.finished_at, done.updated_at) == (_S.done, later, later)


async def test__expire_and_lose__by_age_revocation_and_offline(pg_migrated_engine: AsyncEngine) -> None:
    repos = _Repos(pg_migrated_engine)
    quiet, revoked, offline, fine = [await repos.runner() for _ in range(4)]
    old_queued = _command(quiet.id, kind=RunnerCommandKind.disk_measure, at=NOW - timedelta(minutes=11))
    fresh_queued = _command(fine.id, kind=RunnerCommandKind.disk_measure)
    silent = _command(quiet.id, state=_S.running, at=NOW - timedelta(minutes=4))
    on_revoked = _command(revoked.id, state=_S.delivered)
    on_offline = _command(offline.id, state=_S.cancelling, at=NOW - timedelta(seconds=30))
    alive = _command(fine.id, state=_S.running, at=NOW - timedelta(minutes=1))
    for command in (old_queued, fresh_queued, silent, on_revoked, on_offline, alive):
        await repos.commands.add(command)
    await repos.runners.revoke(revoked.id, NOW)
    await repos.runners.mark_offline(offline.id, NOW - timedelta(seconds=10))
    later = NOW + timedelta(seconds=1)

    expired = await repos.commands.expire_queued(before=NOW - timedelta(minutes=10), now=later)
    lost_one = await repos.commands.lose(silent_before=NOW - timedelta(minutes=3), now=later, runner_id=revoked.id)
    lost = await repos.commands.lose(silent_before=NOW - timedelta(minutes=3), now=later)

    assert [(c.id, c.state) for c in expired] == [(old_queued.id, _S.expired)]
    assert [c.id for c in lost_one] == [on_revoked.id]
    assert {c.id for c in lost} == {silent.id, on_offline.id}
    assert all(c.state is _S.lost and c.finished_at == later for c in lost)
    assert (await repos.commands.get(alive.id)).state is _S.running  # type: ignore[union-attr]
    assert (await repos.commands.get(fresh_queued.id)).state is _S.queued  # type: ignore[union-attr]


async def test__disk__roundtrip_list_revoked_and_garbage(pg_migrated_engine: AsyncEngine) -> None:
    repos = _Repos(pg_migrated_engine)
    runner = await repos.runner()
    revoked = await repos.runner()
    await repos.runners.revoke(revoked.id, NOW)

    assert await repos.disks.get_disk(runner.id) is None
    assert await repos.disks.set_disk(runner.id, _report(), NOW) is True
    assert await repos.disks.set_disk(revoked.id, _report(), NOW) is False
    assert await repos.disks.set_disk("missing", _report(), NOW) is False

    stored = await repos.disks.get_disk(runner.id)
    assert stored is not None
    assert (stored.report, stored.received_at) == (_report(), NOW)
    assert set(await repos.disks.list_disks()) == {runner.id}
    # Строка раннера читается без замера (отложенная колонка), и всё остальное в ней цело.
    assert (await repos.runners.get(runner.id)).features == runner.features  # type: ignore[union-attr]
    assert len(await repos.runners.list()) == 2

    async with pg_migrated_engine.begin() as conn:
        await conn.execute(update(RunnerRow).where(RunnerRow.id == runner.id).values(disk={"docker": "podman"}))
    assert await repos.disks.get_disk(runner.id) is None
    assert await repos.disks.list_disks() == {}


async def test__disk_briefs__projection_matches_the_cleanable_rule(pg_migrated_engine: AsyncEngine) -> None:
    repos = _Repos(pg_migrated_engine)
    names = ("docker", "docker_unavailable", "kubernetes", "desktop")
    runners = {name: await repos.runner() for name in names}
    for name, runner in runners.items():
        await repos.disks.set_disk(runner.id, _report(name), NOW)
    silent = await repos.runner()

    briefs = await repos.disks.list_disk_briefs()

    assert set(briefs) == {r.id for r in runners.values()}
    for name, runner in runners.items():
        brief = briefs[runner.id]
        report = _report(name)
        assert (brief.cleanable_bytes, brief.measured_at, brief.received_at) == (
            disk_cleanable_bytes(report),
            report.measured_at,
            NOW,
        ), name
    picked = await repos.disks.list_disk_briefs([runners["docker"].id, silent.id])
    assert set(picked) == {runners["docker"].id}
    assert await repos.disks.list_disk_briefs([]) == {}
    # Гигабайты не упираются в int4: размеры в отчёте и сумма считаются в bigint.
    big = await repos.runner()
    report = _report()
    assert report.docker is not None
    huge = replace(report, docker=replace(report.docker, cleanable_bytes=5 * 2**40))
    await repos.disks.set_disk(big.id, huge, NOW)
    assert (await repos.disks.list_disk_briefs([big.id]))[big.id].cleanable_bytes == disk_cleanable_bytes(huge)


async def test__long_poll__two_service_instances_share_the_database(pg_migrated_engine: AsyncEngine) -> None:
    """Команда, поставленная на одной реплике, доходит до опроса на другой не позже интервала перепроверки."""
    repos_a, repos_b = _Repos(pg_migrated_engine), _Repos(pg_migrated_engine)
    runner = await repos_a.runner()

    def service(repos: _Repos) -> RunnerControlService:
        return RunnerControlService(
            repos.commands, repos.disks, repos.runners, RunnerCommandWakeup(), poll_interval_s=0.1
        )

    poller, admin = service(repos_b), service(repos_a)
    waiting = asyncio.create_task(poller.poll(runner, ControlPollRequest(wait_s=10)))
    await asyncio.sleep(0.2)

    command = await admin.enqueue(runner, RunnerCommandKind.disk_cleanup, _CLEANUP, created_by="admin")
    polled = await asyncio.wait_for(waiting, 3)

    assert polled.command is not None
    assert polled.command.id == command.id
    assert polled.command.payload == _CLEANUP
    assert (await admin.get(runner.id, command.id)).state is _S.delivered
