"""«Освободить место»: предпросмотр с потолком, прогон по всем источникам, остановка, прерывание, аудит."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.identity.entities import AuditEntry
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.lifecycle.policies import POLICIES
from hse_doc_studio.core.lifecycle.sweeps import (
    PREVIEW_CAP,
    ExcludedReason,
    LifecycleSweep,
    StepStatus,
    SweepStatus,
    SweepStep,
)
from hse_doc_studio.use_cases.lifecycle.engine import LifecycleEngine
from hse_doc_studio.use_cases.lifecycle.sweep import LifecycleSweepService

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.data_lifecycle import FakeRuns, FakeSource, InMemoryLifecycleSweeps
from tests.fakes.identity import InMemoryInstanceSettingsRepository

NOW = datetime(2026, 11, 16, 12, tzinfo=UTC)
ADMIN = Actor(kind=ActorKind.user, id="boss", is_instance_admin=True)
STUDENT = Actor(kind=ActorKind.user, id="anna")
MANUAL = [
    "ai_usage",
    "jobs",
    "notifications",
    "mail_log",
    "collab_requests",
    "share_links",
    "guest_sessions",
    "collab_state",
]


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


class Env:
    def __init__(self, **sources: FakeSource) -> None:
        keys = [p.key for p in POLICIES]
        self.sources = {k: sources.get(k, FakeSource(k)) for k in keys}
        self.settings = InMemoryInstanceSettingsRepository()
        self.audit = InMemoryAuditLog()
        self.clock = Clock()
        self.engine = LifecycleEngine(
            self.sources,
            self.settings,
            FakeRuns(),
            self.audit,
            env_days={"audit_log": 365},
            batch_size=100,
            budget_s=10,
            clock=self.clock,
        )
        self.sweeps = InMemoryLifecycleSweeps()
        ids = iter(f"sw-{n}" for n in range(100))
        self.service = LifecycleSweepService(
            self.engine, self.sweeps, self.settings, self.audit, clock=self.clock, new_id=lambda: next(ids)
        )

    async def entries(self) -> list[AuditEntry]:
        return list(reversed(await self.audit.list()))  # журнал отдаёт новые первыми

    async def actions(self) -> list[str]:
        return [e.action for e in await self.entries()]


async def test__preview__manual_sources_in_registry_order_with_days_cutoff_and_cap() -> None:
    env = Env(
        ai_usage=FakeSource("ai_usage", expired=PREVIEW_CAP + 50),
        jobs=FakeSource("jobs", expired=None),
        notifications=FakeSource("notifications", expired=0),
    )
    await env.settings.set("retention.notifications_days", 30, source="admin")

    preview = await env.service.preview(ADMIN)

    by_key = {s.key: s for s in preview.sources}
    assert [s.key for s in preview.sources] == MANUAL
    assert (by_key["ai_usage"].count, by_key["ai_usage"].capped) == (PREVIEW_CAP, True)
    assert (by_key["jobs"].count, by_key["jobs"].capped) == (None, False)
    assert (by_key["notifications"].days, by_key["notifications"].cutoff) == (30, NOW - timedelta(days=30))
    assert by_key["guest_sessions"].days is None
    assert by_key["collab_state"].bytes == 1024
    assert env.sources["ai_usage"].counted == [(NOW - timedelta(days=90), PREVIEW_CAP)]
    assert not preview.nothing
    excluded = dict(preview.excluded)
    assert excluded["audit_log"] is ExcludedReason.protected
    assert excluded["blobs"] is ExcludedReason.own_task
    assert excluded["lifecycle_sweeps"] is ExcludedReason.on_write
    assert excluded["container_logs"] is ExcludedReason.infra
    assert set(excluded) | set(by_key) == {p.key for p in POLICIES}
    assert await env.actions() == []


async def test__preview__nothing_when_every_count_is_zero() -> None:
    env = Env(**{k: FakeSource(k, expired=0) for k in MANUAL})

    assert (await env.service.preview(ADMIN)).nothing


async def test__start__runs_every_manual_source_and_audits_start_and_outcome() -> None:
    env = Env(collab_state=FakeSource("collab_state", sizes=(5000, 1000)))

    started = await env.service.start(ADMIN)
    await env.service.drain()

    sweep = await env.sweeps.get(started.id)
    assert started.status is SweepStatus.running
    assert [s.key for s in started.steps] == MANUAL
    assert sweep is not None
    assert sweep.status is SweepStatus.done
    assert [s.status for s in sweep.steps] == [StepStatus.done] * len(MANUAL)
    assert sweep.removed_total == 3 * len(MANUAL)
    assert sweep.freed_bytes == 4000
    assert sweep.finished_at == NOW
    assert await env.actions() == ["lifecycle.sweep", "lifecycle.swept"]
    entries = await env.entries()
    assert entries[0].details == {"sweep_id": "sw-0", "sources": MANUAL}
    assert entries[0].target == "all"
    assert entries[1].actor_id == "boss"
    assert entries[1].details == {
        "sweep_id": "sw-0",
        "status": "done",
        "removed": 3 * len(MANUAL),
        "freed_bytes": 4000,
        "errors": 0,
    }
    assert env.service.finished == {"done": 1}


async def test__start__one_source_fails__others_still_run_and_sweep_is_error() -> None:
    env = Env(jobs=FakeSource("jobs", fail=True))

    started = await env.service.start(ADMIN)
    await env.service.drain()

    sweep = await env.sweeps.get(started.id)
    assert sweep is not None
    assert sweep.status is SweepStatus.error
    statuses = {s.key: s.status for s in sweep.steps}
    assert statuses["jobs"] is StepStatus.error
    assert [k for k, st in statuses.items() if st is StepStatus.done] == [k for k in MANUAL if k != "jobs"]
    assert {s.key: s.error for s in sweep.steps}["jobs"] == "RuntimeError: boom"
    assert (await env.entries())[-1].details["errors"] == 1


async def test__start__second_while_running__busy() -> None:
    gate = asyncio.Event()
    env = Env()
    env.sources["ai_usage"].gate = gate

    await env.service.start(ADMIN)
    await asyncio.sleep(0)
    with pytest.raises(IdentityError) as busy:
        await env.service.start(ADMIN)
    gate.set()
    await env.service.drain()

    assert busy.value.code is IdentityErrorCode.lifecycle_sweep_busy
    assert (await env.service.start(ADMIN)).id == "sw-2"
    await env.service.drain()


async def test__cancel__stops_after_current_source_rest_skipped() -> None:
    gate = asyncio.Event()
    env = Env()
    env.sources["jobs"].gate = gate

    started = await env.service.start(ADMIN)
    while not env.sources["jobs"].seen:
        await asyncio.sleep(0)
    cancelling = await env.service.cancel(ADMIN, started.id)
    gate.set()
    await env.service.drain()

    sweep = await env.sweeps.get(started.id)
    assert cancelling.status is SweepStatus.cancelling
    assert sweep is not None
    assert sweep.status is SweepStatus.cancelled
    assert [s.status for s in sweep.steps] == [StepStatus.done, StepStatus.done] + [StepStatus.skipped] * (
        len(MANUAL) - 2
    )
    assert env.sources["notifications"].seen == []
    assert await env.actions() == ["lifecycle.sweep", "lifecycle.sweep_cancel", "lifecycle.swept"]
    assert (await env.entries())[-1].details["status"] == "cancelled"


async def test__cancel__finished_or_unknown() -> None:
    env = Env()
    started = await env.service.start(ADMIN)
    await env.service.drain()

    with pytest.raises(IdentityError) as finished:
        await env.service.cancel(ADMIN, started.id)
    with pytest.raises(IdentityError) as unknown:
        await env.service.cancel(ADMIN, "nope")

    assert finished.value.code is IdentityErrorCode.command_finished
    assert unknown.value.code is IdentityErrorCode.not_found


async def test__current__stale_running_becomes_interrupted_and_audited() -> None:
    env = Env()
    orphan = LifecycleSweep(
        id="orphan",
        status=SweepStatus.running,
        started_by="boss",
        started_at=NOW - timedelta(minutes=20),
        updated_at=NOW - timedelta(minutes=6),
        finished_at=None,
        steps=(
            SweepStep("ai_usage", StepStatus.done, removed=10),
            SweepStep("jobs", StepStatus.running),
            SweepStep("notifications"),
        ),
    )
    env.sweeps.rows[orphan.id] = orphan

    sweep = await env.service.current(ADMIN)

    assert sweep is not None
    assert sweep.status is SweepStatus.interrupted
    assert [s.status for s in sweep.steps] == [StepStatus.done, StepStatus.error, StepStatus.skipped]
    assert sweep.finished_at == NOW
    assert await env.actions() == ["lifecycle.swept"]
    entry = (await env.entries())[0]
    assert (entry.actor_id, entry.details["status"], entry.details["removed"]) == ("boss", "interrupted", 10)


async def test__current__fresh_running_is_left_alone_and_new_start_after_stale_is_allowed() -> None:
    env = Env()
    env.sweeps.rows["live"] = LifecycleSweep(
        "live", SweepStatus.running, "boss", NOW, NOW - timedelta(minutes=4), None, (SweepStep("jobs"),)
    )

    sweep = await env.service.current(ADMIN)
    env.clock.now = NOW + timedelta(minutes=2)
    started = await env.service.start(ADMIN)
    await env.service.drain()

    assert sweep is not None
    assert sweep.status is SweepStatus.running
    assert env.sweeps.rows["live"].status is SweepStatus.interrupted
    assert started.status is SweepStatus.running


async def test__aclose__running_sweep_closed_as_interrupted() -> None:
    gate = asyncio.Event()
    env = Env()
    env.sources["ai_usage"].gate = gate

    started = await env.service.start(ADMIN)
    while not env.sources["ai_usage"].seen:
        await asyncio.sleep(0)
    await env.service.aclose()

    sweep = await env.sweeps.get(started.id)
    assert sweep is not None
    assert sweep.status is SweepStatus.interrupted
    assert sweep.steps[0].status is StepStatus.error
    assert all(s.status is StepStatus.skipped for s in sweep.steps[1:])
    assert env.service.finished == {"interrupted": 1}


async def test__retention_keeps_last_20_sweeps() -> None:
    env = Env()
    for n in range(23):
        env.clock.now = NOW + timedelta(minutes=n)
        await env.service.start(ADMIN)
        await env.service.drain()

    assert len(env.sweeps.rows) == 20
    latest = await env.service.current(ADMIN)
    assert latest is not None
    assert latest.id == "sw-22"


@pytest.mark.parametrize("call", ["preview", "current", "start"])
async def test__not_admin__not_found(call: str) -> None:
    env = Env()

    with pytest.raises(IdentityError) as denied:
        await getattr(env.service, call)(STUDENT)

    assert denied.value.code is IdentityErrorCode.not_found
    assert env.sweeps.rows == {}
