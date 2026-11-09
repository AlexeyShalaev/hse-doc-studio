"""Служба установки: порядок удаления с отзывом раннера и откат неудачного обновления на подменах хоста и реестра."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.jobs.errors import RunnerNotFoundError
from hse_doc_studio.core.jobs.wire import RUNNER_PROTOCOL_VERSION, RunnerRegisterRequest
from hse_doc_studio.core.runner_install import (
    InstallError,
    InstallTarget,
    LocalInstance,
    PreviousRelease,
    UpgradeError,
)
from hse_doc_studio.core.runner_install.entities import InstallJobState
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from hse_doc_studio.use_cases.runner_install import InstallJobStore, RunnerInstallService
from hse_doc_studio.use_cases.runner_install.service import InstallBusyError, install_token_label

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.runner_install import FakeLocalHost
from tests.fakes.runners import InMemoryRegistrationTokenRepository, InMemoryRunnerRepository

pytestmark = pytest.mark.unit

ADMIN = Actor(kind="user", id="admin", is_instance_admin=True)
NAME = "hse-runner-abc123"


class _Uow:
    @asynccontextmanager
    async def begin(self):  # type: ignore[no-untyped-def]
        yield


class _SpyRegistry(RunnerRegistry):
    """Настоящий реестр, который пишет отзывы в общий с хостом список событий и умеет на них упасть."""

    def __init__(self, events: list[str], *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.events = events
        self.revoke_fails = False

    async def revoke(self, actor: Actor, runner_id: str) -> None:
        self.events.append(f"revoke runner {runner_id}")
        if self.revoke_fails:
            raise RuntimeError("database is gone")
        await super().revoke(actor, runner_id)

    async def revoke_registration_token(self, actor: Actor, token_id: str) -> None:
        self.events.append(f"revoke token {token_id}")
        await super().revoke_registration_token(actor, token_id)


class World:
    def __init__(self) -> None:
        self.runners = InMemoryRunnerRepository()
        self.tokens = InMemoryRegistrationTokenRepository()
        self.audit = InMemoryAuditLog()
        self.host = FakeLocalHost()
        self.host.instances = [LocalInstance(InstallTarget.docker, NAME, "registry.example/hds:1.0.0", "running")]
        self.registry = _SpyRegistry(self.host.events, self.runners, self.tokens, self.audit, _Uow())
        self.jobs = InstallJobStore()
        self.service = RunnerInstallService(
            self.registry,
            {InstallTarget.docker: self.host},
            self.jobs,
            self.audit,
            _Uow(),
            image="registry.example/hds:1.2.3",
            data_dir="/var/lib/hse-runner",
            register_timeout_s=0.05,
            poll_s=0.01,
        )

    async def runner(self, *, version: str = "1.0.0") -> str:
        created = await self.registry.create_registration_token(ADMIN, label=install_token_label(NAME))
        registered = await self.registry.register(
            created.secret,
            RunnerRegisterRequest(
                name=NAME,
                protocol=RUNNER_PROTOCOL_VERSION,
                version=version,
                tags=frozenset({"tex"}),
                concurrency=1,
            ),
        )
        return registered.runner.id

    async def actions(self) -> list[str]:
        return [e.action for e in await self.audit.list()]


@pytest.fixture
def world() -> World:
    return World()


# ---- удаление установки ----


async def test__remove__revokes_the_token_then_the_runner_then_removes_the_install(world: World) -> None:
    runner_id = await world.runner()
    pending = await world.registry.create_registration_token(
        ADMIN, label=install_token_label(NAME), ttl=timedelta(hours=1)
    )
    foreign = await world.registry.create_registration_token(ADMIN, label="install other-runner")

    await world.service.remove(ADMIN, InstallTarget.docker, NAME)

    assert world.host.events == [
        f"revoke token {pending.token.id}",
        f"revoke runner {runner_id}",
        f"remove {NAME}",
    ]
    revoked = await world.runners.get(runner_id)
    assert revoked is not None
    assert revoked.revoked_at is not None
    tokens = {t.id: t for t in await world.tokens.list()}
    assert tokens[pending.token.id].revoked_at is not None
    # Чужой токен и уже потраченный токен этой установки не трогаются.
    assert tokens[foreign.token.id].revoked_at is None
    entry = next(e for e in await world.audit.list() if e.action == "runner_install.local.remove")
    assert entry.target == NAME
    assert entry.details["revoked_runner"] == runner_id
    assert entry.details["revoked_registrations"] == [pending.token.id]
    assert "runner.revoke" in await world.actions()


async def test__remove__install_without_runner_only_removes(world: World) -> None:
    await world.service.remove(ADMIN, InstallTarget.docker, NAME)

    assert world.host.events == [f"remove {NAME}"]
    entry = next(e for e in await world.audit.list() if e.action == "runner_install.local.remove")
    assert entry.details["revoked_runner"] is None
    assert "revoked_registrations" not in entry.details


async def test__remove__host_failure_leaves_a_revoked_runner_and_a_removable_install(world: World) -> None:
    runner_id = await world.runner()
    world.host.remove_fail_with = InstallError("remove_failed", "device busy")

    with pytest.raises(InstallError):
        await world.service.remove(ADMIN, InstallTarget.docker, NAME)

    # Раннер уже не работает, а установка осталась: она видна как «без раннера» и удаляется повтором.
    revoked = await world.runners.get(runner_id)
    assert revoked is not None
    assert revoked.revoked_at is not None
    listed = await world.service.instances(ADMIN)
    assert [(i.name, i.runner_id) for i in listed] == [(NAME, None)]
    failed = next(e for e in await world.audit.list() if e.action == "runner_install.local.remove_failed")
    assert (failed.details["code"], failed.details["revoked_runner"]) == ("remove_failed", runner_id)

    world.host.remove_fail_with = None
    await world.service.remove(ADMIN, InstallTarget.docker, NAME)

    assert world.host.removed == [NAME]
    assert world.host.events.count(f"revoke runner {runner_id}") == 1


async def test__remove__revoke_failure_leaves_the_install_untouched(world: World) -> None:
    await world.runner()
    world.registry.revoke_fails = True

    with pytest.raises(RuntimeError):
        await world.service.remove(ADMIN, InstallTarget.docker, NAME)

    assert not [e for e in world.host.events if e.startswith("remove")]
    assert world.host.removed == []
    assert "runner_install.local.remove" not in await world.actions()


async def test__remove__unknown_install_touches_nothing(world: World) -> None:
    runner_id = await world.runner()

    with pytest.raises(RunnerNotFoundError):
        await world.service.remove(ADMIN, InstallTarget.docker, "nope")

    assert world.host.events == []
    runner = await world.runners.get(runner_id)
    assert runner is not None
    assert runner.revoked_at is None


async def test__remove__refused_while_this_install_is_being_updated(world: World) -> None:
    runner_id = await world.runner()
    world.host.upgrade_gate = asyncio.Event()
    job = await world.service.start_upgrade(ADMIN, InstallTarget.docker, NAME)

    with pytest.raises(InstallBusyError):
        await world.service.remove(ADMIN, InstallTarget.docker, NAME)

    runner = await world.runners.get(runner_id)
    assert runner is not None
    assert runner.revoked_at is None
    world.host.upgrade_fail_with = InstallError("image_pull_failed")
    world.host.upgrade_gate.set()
    await _finished(world, job.id)


# ---- откат неудачного обновления ----


async def _finished(world: World, job_id: str):  # type: ignore[no-untyped-def]
    for _ in range(300):
        job = world.service.job(ADMIN, job_id)
        assert job is not None
        if job.state is not InstallJobState.running:
            return job
        await asyncio.sleep(0.01)
    raise AssertionError("upgrade did not finish")


def _back_on(world: World, runner_id: str, version: str) -> None:
    """Прежний процесс после отката: тот же раннер выходит на связь с прежней версией."""

    async def announce() -> None:
        await world.runners.touch(runner_id, datetime.now(UTC), version=version)

    world.host.on_rolled_back = announce


async def test__upgrade__runner_that_does_not_come_back_is_rolled_back(world: World) -> None:
    runner_id = await world.runner()
    _back_on(world, runner_id, "1.0.0")

    job = await _finished(world, (await world.service.start_upgrade(ADMIN, InstallTarget.docker, NAME)).id)

    assert job.error_code == "reconnect_timeout"
    assert (job.rolled_back, job.rollback_version, job.rollback_error) == (True, "1.0.0", None)
    assert job.rollback_reconnected is True
    assert [(s.key, s.state.value, s.detail) for s in job.steps][-2:] == [
        ("reconnect", "failed", ""),
        ("rollback", "done", "1.0.0"),
    ]
    assert world.host.rolled_back == [(NAME, "registry.example/hds:1.0.0")]
    failed = next(e for e in await world.audit.list() if e.action == "runner_install.local.upgrade_failed")
    assert (failed.details["rolled_back"], failed.details["code"]) == (True, "reconnect_timeout")
    assert failed.details["rollback_reconnected"] is True


async def test__upgrade__rollback_whose_runner_stays_offline_says_so(world: World) -> None:
    await world.runner()

    job = await _finished(world, (await world.service.start_upgrade(ADMIN, InstallTarget.docker, NAME)).id)

    # Прежний Deployment или контейнер вернулся, но раннер с прежней версией на связь не вышел.
    assert (job.rolled_back, job.rollback_version, job.rollback_reconnected) == (True, "1.0.0", False)
    assert (job.steps[-1].key, job.steps[-1].state.value) == ("rollback", "failed")
    failed = next(e for e in await world.audit.list() if e.action == "runner_install.local.upgrade_failed")
    assert (failed.details["rolled_back"], failed.details["rollback_reconnected"]) == (True, False)


async def test__upgrade__failure_after_replacement_rolls_back_to_the_image_tag(world: World) -> None:
    world.host.upgrade_fail_with = UpgradeError(
        "rollout_failed", "ProgressDeadlineExceeded", previous=PreviousRelease("registry.example/hds:0.9.1")
    )

    job = await _finished(world, (await world.service.start_upgrade(ADMIN, InstallTarget.docker, NAME)).id)

    # Раннера в Студии нет: версия берётся из тега прежнего образа, ждать на связи некого.
    assert (job.error_code, job.rolled_back, job.rollback_version) == ("rollout_failed", True, "0.9.1")
    assert job.rollback_reconnected is None
    assert (job.steps[-1].key, job.steps[-1].state.value) == ("rollback", "done")


async def test__upgrade__failed_rollback_is_reported_with_its_reason(world: World) -> None:
    await world.runner()
    world.host.rollback_fail_with = InstallError("rollout_timeout", "pod pending")

    job = await _finished(world, (await world.service.start_upgrade(ADMIN, InstallTarget.docker, NAME)).id)

    assert (job.error_code, job.rolled_back, job.rollback_error) == ("reconnect_timeout", False, "rollout_timeout")
    assert (job.steps[-1].key, job.steps[-1].state.value, job.steps[-1].detail) == (
        "rollback",
        "failed",
        "pod pending",
    )
    failed = next(e for e in await world.audit.list() if e.action == "runner_install.local.upgrade_failed")
    assert (failed.details["rolled_back"], failed.details["rollback_error"]) == (False, "rollout_timeout")


async def test__upgrade__failure_before_replacement_has_nothing_to_roll_back(world: World) -> None:
    world.host.upgrade_fail_with = InstallError("image_pull_failed", "denied")

    job = await _finished(world, (await world.service.start_upgrade(ADMIN, InstallTarget.docker, NAME)).id)

    assert (job.error_code, job.rolled_back) == ("image_pull_failed", None)
    assert "rollback" not in [s.key for s in job.steps]
    assert world.host.events == []
    failed = next(e for e in await world.audit.list() if e.action == "runner_install.local.upgrade_failed")
    assert failed.details["rolled_back"] is False
