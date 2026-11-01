"""Восстановление из админки: предпросмотр, подтверждения, режим обслуживания, откат и повтор."""

from __future__ import annotations

from collections.abc import Mapping
from typing import BinaryIO

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorKind, ActorSource
from hse_doc_studio.core.backup.entities import RunTrigger
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.backup.protocols import TargetState
from hse_doc_studio.core.backup.restore_job import RestoreJob, RestorePhase
from hse_doc_studio.core.identity.errors import IdentityError
from hse_doc_studio.infra.backup.parts import PartFetcher
from hse_doc_studio.use_cases.backup.restore_admin import RestoreCoordinator

from tests.unit.use_cases.backup.test_backup_service import Env, admin, env  # noqa: F401


class FakeTarget:
    def __init__(self, state: TargetState, *, fail_db: bool = False, others: int = 0) -> None:
        self.state = state
        self.fail_db = fail_db
        self.others = others
        self.calls: list[str] = []
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def api_is_running(self) -> bool:
        self.others -= 1 if self.others > 0 else 0
        return self.others > 0

    async def describe(self) -> TargetState:
        return self.state

    async def current_revision_known(self, revision: str | None) -> bool:
        return True

    async def restore_database(self, source: BinaryIO) -> None:
        self.calls.append("db")
        while source.read(1 << 20):
            pass
        if self.fail_db:
            raise BackupError(BackupErrorCode.integrity, "pg_restore exited with 1")

    async def restore_files(self, source: BinaryIO, *, move_existing: bool, stamp: str) -> int:
        self.calls.append(f"files move={move_existing}")
        while source.read(1 << 20):
            pass
        return 1

    async def restore_objects(self, source: BinaryIO) -> int:
        self.calls.append("objects")
        return 0


class FakeTargets:
    def __init__(self, target: FakeTarget) -> None:
        self.target = target

    async def open(self) -> FakeTarget:
        return self.target


class FakeMaintenance:
    def __init__(self) -> None:
        self._active = False
        self.events: list[str] = []
        self.status: Mapping[str, object] = {}
        self.restart = True

    @property
    def active(self) -> bool:
        return self._active

    async def enter(self, *, reason: str) -> None:
        self._active = True
        self.events.append("enter")

    async def leave(self) -> None:
        self._active = False
        self.events.append("leave")

    def publish(self, status: Mapping[str, object]) -> None:
        self.status = status

    def request_restart(self, *, delay_s: float) -> bool:
        self.events.append("restart")
        return self.restart


class Stack:
    def __init__(self, env: Env, target: FakeTarget, *, apply_allowed: bool = True) -> None:
        self.env = env
        self.target = target
        self.maintenance = FakeMaintenance()
        self.coordinator = RestoreCoordinator(
            env.destinations,
            env.runs,
            env.service,
            env.keys,
            FakeTargets(target),  # type: ignore[arg-type]
            PartFetcher(env.root / "fetch"),
            self.maintenance,
            env.audit,
            others_wait_s=0.0,
            others_poll_s=0.0,
            apply_allowed=apply_allowed,
        )

    async def backup(self) -> tuple[str, str]:
        dest_id = await self.env.add_local()
        run = await self.env.service.run_and_wait(trigger=RunTrigger.manual, destination_id=dest_id, actor_id=None)
        assert run.backup_id
        return dest_id, run.backup_id

    async def previewed(self) -> RestoreJob:
        dest_id, backup_id = await self.backup()
        job = await self.coordinator.preview(admin(), dest_id, backup_id)
        await self.coordinator.drain()
        return job


EMPTY = TargetState(0, 0, 0)
BUSY = TargetState(3, 2, 10)


async def test__preview__verifies_and_writes_nothing(env: Env) -> None:  # noqa: F811
    stack = Stack(env, FakeTarget(BUSY))
    job = await stack.previewed()
    assert job.phase is RestorePhase.verified
    assert job.manifest is not None and job.manifest.app_version == "9.9.9"
    assert job.requires_overwrite
    assert stack.target.calls == []
    assert stack.target.closed
    assert stack.maintenance.events == []
    assert any("sha256" in line for line in job.log)


async def test__preview__corrupted_part_fails_with_integrity(env: Env) -> None:  # noqa: F811
    stack = Stack(env, FakeTarget(EMPTY))
    dest_id, backup_id = await stack.backup()
    folder = env.root / "dest" / "main" / backup_id
    blob = bytearray((folder / "db.pgdump.enc").read_bytes())
    blob[40] ^= 0xFF
    (folder / "db.pgdump.enc").write_bytes(bytes(blob))
    job = await stack.coordinator.preview(admin(), dest_id, backup_id)
    await stack.coordinator.drain()
    assert job.phase is RestorePhase.failed
    assert job.error_code == BackupErrorCode.integrity.value


async def test__apply__requires_admin_and_preview(env: Env) -> None:  # noqa: F811
    stack = Stack(env, FakeTarget(EMPTY))
    nobody = Actor(id="u", kind=ActorKind.user, source=ActorSource.session, is_instance_admin=False)
    dest_id, backup_id = await stack.backup()
    with pytest.raises(IdentityError):
        await stack.coordinator.preview(nobody, dest_id, backup_id)
    with pytest.raises(BackupError) as caught:
        await stack.coordinator.apply(admin(), "nope", overwrite=False, confirm=backup_id)
    assert caught.value.code is BackupErrorCode.not_found


async def test__apply__wrong_confirmation_is_rejected(env: Env) -> None:  # noqa: F811
    stack = Stack(env, FakeTarget(EMPTY))
    job = await stack.previewed()
    with pytest.raises(BackupError) as caught:
        await stack.coordinator.apply(admin(), job.id, overwrite=False, confirm="other")
    assert caught.value.code is BackupErrorCode.restore_unconfirmed
    assert stack.maintenance.events == []


async def test__apply__non_empty_target_needs_overwrite(env: Env) -> None:  # noqa: F811
    stack = Stack(env, FakeTarget(BUSY))
    job = await stack.previewed()
    with pytest.raises(BackupError) as caught:
        await stack.coordinator.apply(admin(), job.id, overwrite=False, confirm=job.backup_id)
    assert caught.value.code is BackupErrorCode.unsafe_target
    assert stack.target.calls == []


async def test__apply__disabled_by_config(env: Env) -> None:  # noqa: F811
    stack = Stack(env, FakeTarget(EMPTY), apply_allowed=False)
    job = await stack.previewed()
    with pytest.raises(BackupError) as caught:
        await stack.coordinator.apply(admin(), job.id, overwrite=False, confirm=job.backup_id)
    assert caught.value.code is BackupErrorCode.unsupported


async def test__apply__empty_target__writes_in_maintenance_and_restarts(env: Env) -> None:  # noqa: F811
    stack = Stack(env, FakeTarget(EMPTY))
    job = await stack.previewed()
    await stack.coordinator.apply(admin(), job.id, overwrite=False, confirm=job.backup_id)
    await stack.coordinator.drain()
    assert job.phase is RestorePhase.done
    assert job.wrote and job.restarting
    assert stack.maintenance.events == ["enter", "restart"]
    assert stack.target.calls == ["db", "files move=False"]
    assert stack.maintenance.status["phase"] == "done"
    actions = [e.action for e in env.audit._entries if e.action.startswith("backup.restore")]  # noqa: SLF001
    assert actions == ["backup.restore_preview", "backup.restore_start", "backup.restore_finish"]


async def test__apply__overwrite__moves_existing_folders(env: Env) -> None:  # noqa: F811
    stack = Stack(env, FakeTarget(BUSY))
    job = await stack.previewed()
    await stack.coordinator.apply(admin(), job.id, overwrite=True, confirm=job.backup_id)
    await stack.coordinator.drain()
    assert job.phase is RestorePhase.done
    assert stack.target.calls[-1] == "files move=True"


async def test__apply__connections_remain__fails_before_writing_and_leaves_maintenance(env: Env) -> None:  # noqa: F811
    stack = Stack(env, FakeTarget(EMPTY, others=10**6))
    job = await stack.previewed()
    await stack.coordinator.apply(admin(), job.id, overwrite=False, confirm=job.backup_id)
    await stack.coordinator.drain()
    assert job.phase is RestorePhase.failed
    assert job.error_code == BackupErrorCode.unsafe_target.value
    assert not job.wrote
    assert stack.maintenance.events == ["enter", "leave"]
    assert stack.target.calls == []


async def test__apply__db_failure__stays_in_maintenance_and_can_be_retried(env: Env) -> None:  # noqa: F811
    stack = Stack(env, FakeTarget(EMPTY, fail_db=True))
    job = await stack.previewed()
    await stack.coordinator.apply(admin(), job.id, overwrite=False, confirm=job.backup_id)
    await stack.coordinator.drain()
    assert job.phase is RestorePhase.failed and job.wrote
    assert stack.maintenance.active
    stack.target.fail_db = False
    await stack.coordinator.apply(admin(), job.id, overwrite=False, confirm=job.backup_id)
    await stack.coordinator.drain()
    assert job.phase is RestorePhase.done


async def test__cancel__leaves_maintenance_and_forgets_job(env: Env) -> None:  # noqa: F811
    stack = Stack(env, FakeTarget(EMPTY, fail_db=True))
    job = await stack.previewed()
    await stack.coordinator.apply(admin(), job.id, overwrite=False, confirm=job.backup_id)
    await stack.coordinator.drain()
    await stack.coordinator.cancel(admin())
    assert stack.coordinator.current(admin()) is None
    assert not stack.maintenance.active


async def test__preview__rejected_while_backup_or_restore_in_progress(env: Env) -> None:  # noqa: F811
    stack = Stack(env, FakeTarget(EMPTY, fail_db=True))
    job = await stack.previewed()
    await stack.coordinator.apply(admin(), job.id, overwrite=False, confirm=job.backup_id)
    await stack.coordinator.drain()
    with pytest.raises(BackupError) as caught:  # режим обслуживания включён после неудачной записи
        await stack.coordinator.preview(admin(), job.destination_id, job.backup_id)
    assert caught.value.code is BackupErrorCode.restore_busy
