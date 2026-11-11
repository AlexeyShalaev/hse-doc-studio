"""In-memory команды раннерам и замеры диска с теми же правилами, что у Postgres-репозиториев."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.jobs.control import COMMANDS_KEPT_PER_RUNNER, StoredDiskReport
from hse_doc_studio.core.jobs.disk import (
    COMMAND_OPEN_STATES,
    CommandProgress,
    RunnerCommand,
    RunnerCommandKind,
    RunnerCommandState,
    RunnerDiskReport,
)

from tests.fakes.runners import InMemoryRunnerRepository

_IN_FLIGHT = frozenset({RunnerCommandState.delivered, RunnerCommandState.running, RunnerCommandState.cancelling})


class InMemoryRunnerCommandRepository:
    def __init__(self, runners: InMemoryRunnerRepository) -> None:
        self._runners = runners
        self._items: dict[UUID, RunnerCommand] = {}

    def _newest_first(self, runner_id: str) -> list[RunnerCommand]:
        mine = [c for c in self._items.values() if c.runner_id == runner_id]
        return sorted(mine, key=lambda c: (c.created_at, c.id.hex), reverse=True)

    async def add(self, command: RunnerCommand, *, keep: int = COMMANDS_KEPT_PER_RUNNER) -> bool:
        if command.kind is RunnerCommandKind.disk_cleanup and command.state in COMMAND_OPEN_STATES:
            for other in self._items.values():
                if (
                    other.runner_id == command.runner_id
                    and other.kind is RunnerCommandKind.disk_cleanup
                    and other.state in COMMAND_OPEN_STATES
                ):
                    return False
        self._items[command.id] = command
        recent = {c.id for c in self._newest_first(command.runner_id)[:keep]}
        for other in self._newest_first(command.runner_id):
            if other.id not in recent and other.state.finished:
                del self._items[other.id]
        return True

    async def get(self, command_id: UUID) -> RunnerCommand | None:
        return self._items.get(command_id)

    async def list_for_runner(self, runner_id: str, *, limit: int) -> list[RunnerCommand]:
        return self._newest_first(runner_id)[:limit]

    async def find_open(self, runner_id: str, kind: RunnerCommandKind) -> RunnerCommand | None:
        return next(
            (c for c in self._newest_first(runner_id) if c.kind is kind and c.state in COMMAND_OPEN_STATES), None
        )

    async def claim(
        self, runner_id: str, kinds: Collection[RunnerCommandKind], *, now: datetime, not_before: datetime
    ) -> RunnerCommand | None:
        queued = [
            c
            for c in reversed(self._newest_first(runner_id))
            if c.state is RunnerCommandState.queued and c.kind in kinds and c.created_at >= not_before
        ]
        if not queued:
            return None
        return await self.transition(
            queued[0].id, expected=RunnerCommandState.queued, to=RunnerCommandState.delivered, now=now
        )

    async def transition(
        self,
        command_id: UUID,
        *,
        expected: RunnerCommandState,
        to: RunnerCommandState,
        now: datetime,
        progress: CommandProgress | None = None,
    ) -> RunnerCommand | None:
        command = self._items.get(command_id)
        if command is None or command.state is not expected:
            return None
        moved = replace(
            command,
            state=to,
            updated_at=now,
            progress=progress if progress is not None else command.progress,
            delivered_at=now if to is RunnerCommandState.delivered else command.delivered_at,
            finished_at=now if to.finished else command.finished_at,
        )
        self._items[command_id] = moved
        return moved

    def _close(self, command: RunnerCommand, state: RunnerCommandState, now: datetime) -> RunnerCommand:
        closed = replace(command, state=state, updated_at=now, finished_at=now)
        self._items[command.id] = closed
        return closed

    async def expire_queued(
        self, *, before: datetime, now: datetime, runner_id: str | None = None
    ) -> list[RunnerCommand]:
        return [
            self._close(c, RunnerCommandState.expired, now)
            for c in list(self._items.values())
            if (runner_id is None or c.runner_id == runner_id)
            and c.state is RunnerCommandState.queued
            and c.created_at < before
        ]

    async def lose(self, *, silent_before: datetime, now: datetime, runner_id: str | None = None) -> list[RunnerCommand]:
        closed: list[RunnerCommand] = []
        for command in list(self._items.values()):
            if (runner_id is not None and command.runner_id != runner_id) or command.state not in _IN_FLIGHT:
                continue
            runner = await self._runners.get(command.runner_id)
            gone = runner is not None and (
                runner.revoked_at is not None
                or (runner.offline_at is not None and runner.offline_at >= command.updated_at)
            )
            if command.updated_at < silent_before or gone:
                closed.append(self._close(command, RunnerCommandState.lost, now))
        return closed


class InMemoryRunnerDiskStore:
    def __init__(self, runners: InMemoryRunnerRepository) -> None:
        self._runners = runners
        self._items: dict[str, StoredDiskReport] = {}

    async def set_disk(self, runner_id: str, report: RunnerDiskReport, now: datetime) -> bool:
        runner = await self._runners.get(runner_id)
        if runner is None or runner.revoked_at is not None:
            return False
        self._items[runner_id] = StoredDiskReport(report=report, received_at=now)
        return True

    async def get_disk(self, runner_id: str) -> StoredDiskReport | None:
        return self._items.get(runner_id)

    async def list_disks(self) -> dict[str, StoredDiskReport]:
        return dict(self._items)
