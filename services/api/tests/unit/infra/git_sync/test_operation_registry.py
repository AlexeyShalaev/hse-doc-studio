from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.git_sync.entities import (
    CloneResult,
    GitOperationError,
    OperationKind,
    OperationPhase,
    OperationStatus,
    SchemaAccess,
    SyncOutcome,
    SyncResult,
)
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.infra.git_sync.operation_registry import InMemoryGitOperationRegistry

pytestmark = pytest.mark.unit


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def registry(clock: _Clock) -> InMemoryGitOperationRegistry:
    return InMemoryGitOperationRegistry(clock=clock)


def test__begin__new_operation_is_running_and_cancellable(
    registry: InMemoryGitOperationRegistry, tmp_path: Path
) -> None:
    project_id = uuid4()

    op = registry.begin(OperationKind.sync, project_id=project_id, folder=tmp_path)

    assert op.id.startswith("op_")
    assert (op.status, op.phase, op.percent, op.cancellable) == (
        OperationStatus.running,
        OperationPhase.queued,
        None,
        True,
    )
    assert registry.get(op.id) == op
    assert registry.current_for(project_id) == op
    assert registry.is_busy(tmp_path) is True


def test__begin__second_operation_on_same_folder__sync_busy_with_id_of_the_first(
    registry: InMemoryGitOperationRegistry, tmp_path: Path
) -> None:
    first = registry.begin(OperationKind.sync, project_id=uuid4(), folder=tmp_path)

    with pytest.raises(GitSyncError) as raised:
        registry.begin(OperationKind.connect, project_id=uuid4(), folder=tmp_path)

    assert raised.value.code is GitErrorCode.sync_busy
    assert raised.value.ctx == {"operation_id": first.id}


def test__begin__same_folder_through_a_different_spelling__is_still_busy(
    registry: InMemoryGitOperationRegistry, tmp_path: Path
) -> None:
    (tmp_path / "a").mkdir()
    registry.begin(OperationKind.sync, project_id=uuid4(), folder=tmp_path / "a")

    with pytest.raises(GitSyncError):
        registry.begin(OperationKind.sync, project_id=uuid4(), folder=tmp_path / "a" / ".." / "a")


def test__begin__other_folders_and_folderless_operations__do_not_collide(
    registry: InMemoryGitOperationRegistry, tmp_path: Path
) -> None:
    registry.begin(OperationKind.sync, project_id=uuid4(), folder=tmp_path / "a")
    registry.begin(OperationKind.sync, project_id=uuid4(), folder=tmp_path / "b")
    registry.begin(OperationKind.clone, project_id=None, folder=None)
    registry.begin(OperationKind.clone, project_id=None, folder=None)

    assert registry.is_busy(tmp_path / "a")
    assert registry.is_busy(tmp_path / "b")
    assert registry.is_busy(tmp_path / "c") is False


def test__finish__frees_the_folder_and_keeps_the_outcome(
    registry: InMemoryGitOperationRegistry, tmp_path: Path
) -> None:
    project_id = uuid4()
    op = registry.begin(OperationKind.sync, project_id=project_id, folder=tmp_path)
    result = SyncResult(outcome=SyncOutcome.pushed, pushed_commits=2)

    registry.finish(op.id, result=result)

    done = registry.get(op.id)
    assert done is not None
    assert (done.status, done.result, done.cancellable, done.finished_at) == (
        OperationStatus.succeeded,
        result,
        False,
        done.finished_at,
    )
    assert done.finished_at is not None
    assert registry.is_busy(tmp_path) is False
    assert registry.current_for(project_id) is None
    registry.begin(OperationKind.sync, project_id=project_id, folder=tmp_path)


def test__finish__failure_carries_the_error_and_cannot_be_overwritten(
    registry: InMemoryGitOperationRegistry, tmp_path: Path
) -> None:
    op = registry.begin(OperationKind.sync, project_id=uuid4(), folder=tmp_path)
    error = GitOperationError(GitErrorCode.auth_failed, "no")

    registry.finish(op.id, status=OperationStatus.failed, error=error)
    registry.finish(op.id, status=OperationStatus.succeeded)

    done = registry.get(op.id)
    assert done is not None
    assert (done.status, done.error) == (OperationStatus.failed, error)


def test__update__phase_change_resets_percent_and_values_are_clamped(
    registry: InMemoryGitOperationRegistry, tmp_path: Path
) -> None:
    op = registry.begin(OperationKind.sync, project_id=uuid4(), folder=tmp_path)

    registry.update(op.id, phase=OperationPhase.fetch, percent=140.0, message="Получение")
    clamped = registry.get(op.id)
    registry.update(op.id, phase=OperationPhase.merge)
    next_phase = registry.get(op.id)
    registry.update(op.id, percent=-5)
    floor = registry.get(op.id)

    assert clamped is not None
    assert (clamped.phase, clamped.percent, clamped.message) == (
        OperationPhase.fetch,
        100.0,
        "Получение",
    )
    assert next_phase is not None
    assert (next_phase.phase, next_phase.percent) == (OperationPhase.merge, None)
    assert floor is not None
    assert floor.percent == 0.0


def test__update__finished_or_unknown_operation__is_ignored(
    registry: InMemoryGitOperationRegistry, tmp_path: Path
) -> None:
    op = registry.begin(OperationKind.sync, project_id=uuid4(), folder=tmp_path)
    registry.finish(op.id)

    registry.update(op.id, phase=OperationPhase.push)
    registry.update("op_missing", phase=OperationPhase.push)

    done = registry.get(op.id)
    assert done is not None
    assert done.phase is OperationPhase.queued


def test__get__returns_a_snapshot_not_the_live_object(registry: InMemoryGitOperationRegistry, tmp_path: Path) -> None:
    op = registry.begin(OperationKind.sync, project_id=uuid4(), folder=tmp_path)
    snapshot = registry.get(op.id)
    assert snapshot is not None

    registry.update(op.id, phase=OperationPhase.push, percent=50)

    assert snapshot.phase is OperationPhase.queued
    assert snapshot.percent is None


def test__get__finished_operation_is_forgotten_after_fifteen_minutes(
    registry: InMemoryGitOperationRegistry, clock: _Clock, tmp_path: Path
) -> None:
    op = registry.begin(OperationKind.sync, project_id=uuid4(), folder=tmp_path)
    registry.finish(op.id)

    clock.now += timedelta(minutes=14, seconds=59)
    assert registry.get(op.id) is not None
    clock.now += timedelta(seconds=2)
    assert registry.get(op.id) is None


def test__get__running_operation_is_never_forgotten(
    registry: InMemoryGitOperationRegistry, clock: _Clock, tmp_path: Path
) -> None:
    op = registry.begin(OperationKind.sync, project_id=uuid4(), folder=tmp_path)

    clock.now += timedelta(days=2)

    assert registry.get(op.id) is not None
    assert registry.is_busy(tmp_path)


async def test__cancel__cancels_the_attached_task(registry: InMemoryGitOperationRegistry, tmp_path: Path) -> None:
    op = registry.begin(OperationKind.sync, project_id=uuid4(), folder=tmp_path)
    task = asyncio.create_task(asyncio.sleep(30))
    registry.attach_task(op.id, task)

    cancelled = registry.cancel(op.id)
    with pytest.raises(asyncio.CancelledError):
        await task

    assert cancelled is not None
    assert cancelled.id == op.id
    assert task.cancelled()


def test__cancel__without_task_or_when_not_cancellable_or_finished__raises(
    registry: InMemoryGitOperationRegistry, tmp_path: Path
) -> None:
    bare = registry.begin(OperationKind.sync, project_id=uuid4(), folder=tmp_path / "a")
    final = registry.begin(OperationKind.sync, project_id=uuid4(), folder=tmp_path / "b")
    registry.update(final.id, cancellable=False)

    for op_id in (bare.id, final.id):
        with pytest.raises(GitSyncError) as raised:
            registry.cancel(op_id)
        assert raised.value.code is GitErrorCode.operation_not_cancellable


def test__cancel__unknown_operation__returns_none(registry: InMemoryGitOperationRegistry) -> None:
    assert registry.cancel("op_missing") is None


def test__finish__clone_result__operation_learns_the_project_id(
    registry: InMemoryGitOperationRegistry, tmp_path: Path
) -> None:
    op = registry.begin(OperationKind.clone, project_id=None, folder=tmp_path)
    project_id = uuid4()

    registry.finish(op.id, result=CloneResult(project_id, str(tmp_path), SchemaAccess.full))

    finished = registry.get(op.id)
    assert finished is not None
    assert finished.project_id == project_id
    assert registry.is_busy(tmp_path) is False
