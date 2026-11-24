"""Обновить все раннеры разом: кого предлагать, порядок и учёт нагрузки, сбой одного, отказ и журнал аудита."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError
from hse_doc_studio.core.jobs.deployment import BuildExecutor, RunnerDeployment, RunnerPlatform
from hse_doc_studio.core.jobs.runners import Runner, RunnerOwnerKind
from hse_doc_studio.core.runner_install import (
    HostKey,
    InstallError,
    InstallJob,
    InstallTarget,
    LocalInstance,
    ProgressReporter,
    SavedSshCredential,
    SshAuthKind,
    UpgradeOutcome,
)
from hse_doc_studio.core.runner_install.entities import InstallJobState
from hse_doc_studio.core.runner_install.fleet import (
    FleetBatch,
    FleetBatchState,
    FleetItemState,
    FleetKind,
    ManualReason,
)
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from hse_doc_studio.use_cases.runner_install import (
    FleetBusyError,
    FleetSelectionError,
    InstallJobStore,
    RunnerFleetService,
    RunnerInstallService,
)
from hse_doc_studio.use_cases.runner_install.fleet import KEY_OFFER_DISMISSED

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.runner_install import FakeLocalHost
from tests.fakes.runners import InMemoryRegistrationTokenRepository, InMemoryRunnerRepository

pytestmark = pytest.mark.unit

ADMIN = Actor(kind="user", id="admin", is_instance_admin=True)
NEW = "1.2.3"
OLD = "1.0.0"


class _Uow:
    @asynccontextmanager
    async def begin(self):  # type: ignore[no-untyped-def]
        yield


class _Registry(RunnerRegistry):
    """Реестр, у которого нагрузку раннеров задаёт тест."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.load: dict[str, int] = {}

    async def running_jobs(self, runner_ids: set[str]) -> dict[str, int]:
        return {i: self.load.get(i, 0) for i in runner_ids}


class _Host(FakeLocalHost):
    """Хост, после обновления которого раннер выходит на связь с новой версией (если ему не велено молчать)."""

    def __init__(self, target: InstallTarget, runners: InMemoryRunnerRepository, ids: dict[str, str]) -> None:
        super().__init__(target)
        self._runners = runners
        self._ids = ids
        self.silent: set[str] = set()
        self.log: list[str] = []
        self._tasks: list[asyncio.Task[None]] = []

    async def upgrade(self, name: str, image: str, report: ProgressReporter) -> UpgradeOutcome:
        self.log.append(name)
        result = await super().upgrade(name, image, report)
        if name not in self.silent:
            self._tasks.append(asyncio.create_task(self._announce(name)))
        return result

    async def _announce(self, name: str) -> None:
        # Новый процесс выходит на связь чуть позже, чем хост закончил замену.
        await asyncio.sleep(0.03)
        await self._runners.touch(self._ids[name], datetime.now(UTC), version=NEW)


class _Ssh:
    """Служба SSH на подмене: «Обновить» по сохранённому доступу, раннер после него сообщает новую версию."""

    def __init__(self, jobs: InstallJobStore, runners: InMemoryRunnerRepository, ids: dict[str, str]) -> None:
        self._jobs = jobs
        self._runners = runners
        self._ids = ids
        self.credentials: list[SavedSshCredential] = []
        self.runs: list[tuple[str, str, str]] = []
        self.report_new_version = True

    async def list_credentials(self, actor: Actor) -> list[SavedSshCredential]:
        return list(self.credentials)

    async def run_saved(self, actor: Actor, credential_id: str, *, action: str, studio_url: str) -> InstallJob:
        self.runs.append((credential_id, action, studio_url))
        credential = next(c for c in self.credentials if c.id == credential_id)
        name = credential.runner_name or ""
        job = self._jobs.create(InstallTarget.ssh, name, "admin", ("connect", "service"))
        job.state = InstallJobState.succeeded
        if self.report_new_version:
            await self._runners.touch(self._ids[name], datetime.now(UTC), version=NEW)
        return job


class World:
    def __init__(self) -> None:
        self.runners = InMemoryRunnerRepository()
        self.audit = InMemoryAuditLog()
        self.settings = InMemoryInstanceSettingsRepository()
        self.ids: dict[str, str] = {}
        self.docker = _Host(InstallTarget.docker, self.runners, self.ids)
        self.kube = _Host(InstallTarget.kubernetes, self.runners, self.ids)
        self.registry = _Registry(self.runners, InMemoryRegistrationTokenRepository(), self.audit, _Uow())
        self.jobs = InstallJobStore()
        self.installs = RunnerInstallService(
            self.registry,
            {InstallTarget.docker: self.docker, InstallTarget.kubernetes: self.kube},
            self.jobs,
            self.audit,
            _Uow(),
            image=f"registry.example/hds:{NEW}",
            data_dir="/var/lib/hse-runner",
            register_timeout_s=0.5,
            poll_s=0.005,
        )
        self.ssh = _Ssh(self.jobs, self.runners, self.ids)
        self.sleeps: list[float] = []
        self.fleet = self.make_fleet()

    def make_fleet(self, **over: float) -> RunnerFleetService:
        async def sleep(seconds: float) -> None:
            self.sleeps.append(seconds)
            await asyncio.sleep(0.001)

        self.clock = 0.0

        def monotonic() -> float:
            # Каждое обращение к часам сдвигает их на секунду: ожидание «занят» кончается без настоящих пауз.
            self.clock += 1.0
            return self.clock

        options: dict[str, float] = {
            "busy_wait_s": 30,
            "busy_poll_s": 5,
            "job_timeout_s": 1e9,
            "job_poll_s": 0.005,
            "reconnect_timeout_s": 1e9,
            **over,
        }
        return RunnerFleetService(
            self.registry,
            self.installs,
            self.ssh,
            self.settings,
            self.audit,
            _Uow(),
            studio_url="https://studio.example",
            sleep=sleep,
            monotonic=monotonic,
            **options,
        )

    async def runner(
        self,
        name: str,
        *,
        version: str = OLD,
        target: InstallTarget | None = InstallTarget.docker,
        owner: RunnerOwnerKind = RunnerOwnerKind.instance,
        revoked: bool = False,
        deployment: RunnerDeployment | None = None,
    ) -> str:
        runner_id = uuid4().hex
        now = datetime.now(UTC)
        await self.runners.add(
            Runner(
                id=runner_id,
                name=name,
                token_hash=f"hash-{name}",
                tags=frozenset(),
                concurrency=1,
                resource_class="standard",
                version=version,
                created_at=now,
                last_seen_at=now,
                owner_kind=owner,
                owner_id="u1" if owner is RunnerOwnerKind.user else None,
                revoked_at=now if revoked else None,
                deployment=deployment,
            )
        )
        self.ids[name] = runner_id
        host = {InstallTarget.docker: self.docker, InstallTarget.kubernetes: self.kube}.get(target)  # type: ignore[arg-type]
        if host is not None:
            host.instances.append(LocalInstance(host.target, name, f"registry.example/hds:{version}", "running"))
        return runner_id

    async def actions(self) -> list[str]:
        return [e.action for e in await self.audit.list()]

    async def done(self, batch: FleetBatch) -> FleetBatch:
        for _ in range(2000):
            if batch.state is FleetBatchState.finished:
                return batch
            await asyncio.sleep(0.005)
        raise AssertionError(f"batch is still running: {[(i.name, i.state) for i in batch.items]}")


@pytest.fixture
def world() -> World:
    return World()


def _states(batch: FleetBatch) -> dict[str, tuple[str, str | None]]:
    return {i.name: (i.state.value, i.code) for i in batch.items}


# ---- кого предлагать ----


async def test__plan__lists_outdated_runners_by_how_they_can_be_updated(world: World) -> None:
    docker = await world.runner("docker-1")
    kube = await world.runner("kube-1", target=InstallTarget.kubernetes)
    ssh = await world.runner("ssh-1", target=None)
    helm = await world.runner(
        "chart",
        target=None,
        deployment=RunnerDeployment(executor=BuildExecutor.kubernetes, platform=RunnerPlatform.kubernetes),
    )
    await world.runner("current", version=NEW)
    await world.runner("personal", owner=RunnerOwnerKind.user)
    await world.runner("gone", revoked=True)
    world.ssh.credentials = [
        SavedSshCredential(
            "cred1",
            "box",
            "10.0.0.5",
            22,
            "root",
            False,
            SshAuthKind.key,
            HostKey("ed25519", "SHA256:x", "k"),
            "admin",
            datetime.now(UTC),
            runner_name="ssh-1",
        )
    ]
    world.registry.load[docker] = 2

    plan = await world.fleet.plan(ADMIN)

    got = {c.name: (c.runner_id, c.kind, c.version, c.target_version, c.running_jobs) for c in plan.items}
    assert got == {
        "chart": (helm, FleetKind.manual, OLD, NEW, 0),
        "docker-1": (docker, FleetKind.docker, OLD, NEW, 2),
        "kube-1": (kube, FleetKind.kubernetes, OLD, NEW, 0),
        "ssh-1": (ssh, FleetKind.ssh, OLD, NEW, 0),
    }
    chart = next(c for c in plan.items if c.name == "chart")
    assert chart.manual_reason is ManualReason.helm
    assert [c.name for c in plan.upgradable] == ["docker-1", "kube-1", "ssh-1"]
    assert plan.offer is True


async def test__plan__without_outdated_runners_there_is_no_offer(world: World) -> None:
    await world.runner("current", version=NEW)
    await world.runner("personal", owner=RunnerOwnerKind.user)

    plan = await world.fleet.plan(ADMIN)

    assert plan.items == ()
    assert plan.offer is False


async def test__plan__only_manual_runners_make_no_offer(world: World) -> None:
    await world.runner("chart", target=None)

    plan = await world.fleet.plan(ADMIN)

    assert [(c.name, c.kind, c.manual_reason) for c in plan.items] == [
        ("chart", FleetKind.manual, ManualReason.unknown)
    ]
    assert plan.offer is False


async def test__plan__host_that_does_not_answer_leaves_its_runners_manual(world: World) -> None:
    await world.runner("docker-1")

    async def broken() -> list[LocalInstance]:
        raise OSError("docker is gone")

    world.docker.list_instances = broken  # type: ignore[method-assign]

    plan = await world.fleet.plan(ADMIN)

    assert [(c.name, c.kind) for c in plan.items] == [("docker-1", FleetKind.manual)]


async def test__dismiss__hides_the_offer_for_this_version_only(world: World) -> None:
    await world.runner("docker-1")

    await world.fleet.dismiss(ADMIN, NEW)

    assert (await world.fleet.plan(ADMIN)).offer is False
    assert (await world.settings.get_all())[KEY_OFFER_DISMISSED] == NEW
    entry = next(e for e in await world.audit.list() if e.action == "runner_fleet.offer.dismiss")
    assert (entry.actor_id, entry.target) == ("admin", NEW)
    # Отказ от старой версии новую не скрывает: после следующего обновления Студии предложение вернётся.
    await world.settings.set(KEY_OFFER_DISMISSED, "1.1.0", source="admin")
    assert (await world.fleet.plan(ADMIN)).offer is True


async def test__plan__and_start_need_an_instance_admin(world: World) -> None:
    user = Actor(kind="user", id="u", is_instance_admin=False)

    with pytest.raises(IdentityError):
        await world.fleet.plan(user)
    with pytest.raises(IdentityError):
        await world.fleet.start(user, ["x"])
    with pytest.raises(IdentityError):
        await world.fleet.dismiss(user, NEW)


# ---- запуск ----


async def test__start__updates_the_selected_runners_one_by_one_and_audits_it(world: World) -> None:
    a = await world.runner("docker-a")
    b = await world.runner("kube-b", target=InstallTarget.kubernetes)
    await world.runner("docker-c")

    batch = await world.fleet.start(ADMIN, [b, a])
    assert (await world.fleet.plan(ADMIN)).batch is batch
    await world.done(batch)

    assert _states(batch) == {"kube-b": ("succeeded", None), "docker-a": ("succeeded", None)}
    assert [(i.from_version, i.to_version) for i in batch.items] == [(OLD, NEW), (OLD, NEW)]
    # Не выбранный раннер не тронут.
    assert world.docker.log == ["docker-a"]
    assert world.kube.log == ["kube-b"]
    assert (await world.fleet.plan(ADMIN)).batch is None
    started = next(e for e in await world.audit.list() if e.action == "runner_fleet.upgrade.start")
    assert started.details["to_version"] == NEW
    assert [r["name"] for r in started.details["runners"]] == ["kube-b", "docker-a"]  # type: ignore[attr-defined]
    finished = next(e for e in await world.audit.list() if e.action == "runner_fleet.upgrade.finished")
    assert finished.details["counts"] == {"succeeded": 2}
    # Каждый раннер обновлён тем же путём, что и по одному, со своей записью в журнале.
    assert (await world.actions()).count("runner_install.local.upgrade_succeeded") == 2


async def test__start__one_failure_does_not_stop_the_others(world: World) -> None:
    a = await world.runner("docker-a")
    b = await world.runner("docker-b")
    c = await world.runner("docker-c")
    world.docker.silent.add("docker-b")

    batch = await world.fleet.start(ADMIN, [a, b, c])
    await world.done(batch)

    assert _states(batch) == {
        "docker-a": ("succeeded", None),
        "docker-b": ("failed", "reconnect_timeout"),
        "docker-c": ("succeeded", None),
    }
    finished = next(e for e in await world.audit.list() if e.action == "runner_fleet.upgrade.finished")
    assert finished.details["counts"] == {"succeeded": 2, "failed": 1}


async def test__start__refused_update_is_reported_with_its_code(world: World) -> None:
    a = await world.runner("docker-a")
    world.docker.upgrade_fail_with = InstallError("image_pull_failed", "denied")

    batch = await world.fleet.start(ADMIN, [a])
    await world.done(batch)

    item = batch.items[0]
    assert (item.state, item.code, item.detail) == (FleetItemState.failed, "image_pull_failed", "denied")
    assert item.rolled_back is None


async def test__start__runner_with_a_build_is_updated_after_it_and_others_go_first(world: World) -> None:
    busy = await world.runner("docker-busy")
    idle = await world.runner("docker-idle")
    world.registry.load[busy] = 1
    release = asyncio.Event()
    original = world.fleet._sleep

    async def sleep(seconds: float) -> None:
        # Сборка закончилась, пока Студия ждала: раннер свободен.
        if world.docker.log == ["docker-idle"]:
            world.registry.load[busy] = 0
            release.set()
        await original(seconds)

    world.fleet._sleep = sleep  # type: ignore[method-assign]

    batch = await world.fleet.start(ADMIN, [busy, idle])
    await world.done(batch)

    assert release.is_set()
    assert world.docker.log == ["docker-idle", "docker-busy"]
    assert _states(batch) == {"docker-busy": ("succeeded", None), "docker-idle": ("succeeded", None)}


async def test__start__runner_that_stays_busy_is_skipped_not_interrupted(world: World) -> None:
    busy = await world.runner("docker-busy")
    idle = await world.runner("docker-idle")
    world.registry.load[busy] = 3

    batch = await world.fleet.start(ADMIN, [busy, idle])
    await world.done(batch)

    assert _states(batch) == {"docker-busy": ("skipped", "busy"), "docker-idle": ("succeeded", None)}
    assert world.docker.log == ["docker-idle"]
    assert "docker-busy" not in world.docker.log


async def test__start__host_taken_by_another_update_waits_for_it(world: World) -> None:
    a = await world.runner("docker-a")
    world.docker.upgrade_gate = asyncio.Event()
    manual = await world.installs.start_upgrade(ADMIN, InstallTarget.docker, "docker-a")
    original = world.fleet._sleep

    async def sleep(seconds: float) -> None:
        if world.docker.upgrade_gate is not None and not world.docker.upgrade_gate.is_set():
            world.docker.upgrade_gate.set()
        await original(seconds)

    world.fleet._sleep = sleep  # type: ignore[method-assign]
    batch = await world.fleet.start(ADMIN, [a])
    await world.done(batch)

    assert world.jobs.get(manual.id) is not None
    assert _states(batch) == {"docker-a": ("succeeded", None)}


async def test__start__host_that_stays_taken_skips_the_runner(world: World) -> None:
    a = await world.runner("docker-a")
    world.docker.upgrade_gate = asyncio.Event()
    await world.installs.start_upgrade(ADMIN, InstallTarget.docker, "docker-a")

    batch = await world.fleet.start(ADMIN, [a])
    await world.done(batch)
    world.docker.upgrade_gate.set()

    assert _states(batch) == {"docker-a": ("skipped", "install_busy")}


async def test__start__cancel_skips_the_rest_after_the_current_runner(world: World) -> None:
    a = await world.runner("docker-a")
    b = await world.runner("docker-b")
    world.docker.upgrade_gate = asyncio.Event()

    batch = await world.fleet.start(ADMIN, [a, b])
    for _ in range(200):
        if batch.items[0].state is FleetItemState.running:
            break
        await asyncio.sleep(0.005)
    cancelled = await world.fleet.cancel(ADMIN, batch.id)
    world.docker.upgrade_gate.set()
    await world.done(batch)

    assert cancelled.cancel_requested is True
    assert _states(batch) == {"docker-a": ("succeeded", None), "docker-b": ("skipped", "cancelled")}
    assert "runner_fleet.upgrade.cancel" in await world.actions()


async def test__start__ssh_runner_is_done_when_it_reports_the_new_version(world: World) -> None:
    ssh = await world.runner("ssh-1", target=None)
    world.ssh.credentials = [
        SavedSshCredential(
            "cred1",
            "box",
            "10.0.0.5",
            22,
            "root",
            False,
            SshAuthKind.key,
            HostKey("ed25519", "SHA256:x", "k"),
            "admin",
            datetime.now(UTC),
            runner_name="ssh-1",
        )
    ]

    batch = await world.fleet.start(ADMIN, [ssh])
    await world.done(batch)

    assert world.ssh.runs == [("cred1", "update", "https://studio.example")]
    assert (batch.items[0].state, batch.items[0].to_version) == (FleetItemState.succeeded, NEW)


async def test__start__ssh_runner_that_stays_old_is_a_failure(world: World) -> None:
    ssh = await world.runner("ssh-1", target=None)
    world.ssh.report_new_version = False
    world.ssh.credentials = [
        SavedSshCredential(
            "cred1",
            "box",
            "10.0.0.5",
            22,
            "root",
            False,
            SshAuthKind.key,
            HostKey("ed25519", "SHA256:x", "k"),
            "admin",
            datetime.now(UTC),
            runner_name="ssh-1",
        )
    ]
    world.fleet = world.make_fleet(reconnect_timeout_s=3)

    batch = await world.fleet.start(ADMIN, [ssh])
    await world.done(batch)

    assert _states(batch) == {"ssh-1": ("failed", "reconnect_timeout")}


async def test__start__refuses_manual_unknown_and_empty_selections(world: World) -> None:
    await world.runner("docker-a")
    manual = await world.runner("chart", target=None)

    with pytest.raises(FleetSelectionError) as manual_error:
        await world.fleet.start(ADMIN, [manual])
    with pytest.raises(FleetSelectionError) as unknown_error:
        await world.fleet.start(ADMIN, ["nope"])
    with pytest.raises(FleetSelectionError):
        await world.fleet.start(ADMIN, [])

    assert manual_error.value.runner_ids == [manual]
    assert unknown_error.value.runner_ids == ["nope"]
    assert world.docker.log == []
    assert "runner_fleet.upgrade.start" not in await world.actions()


async def test__start__second_run_is_refused_while_one_is_going(world: World) -> None:
    a = await world.runner("docker-a")
    world.docker.upgrade_gate = asyncio.Event()

    batch = await world.fleet.start(ADMIN, [a])
    with pytest.raises(FleetBusyError):
        await world.fleet.start(ADMIN, [a])
    world.docker.upgrade_gate.set()
    await world.done(batch)

    # После окончания можно начать снова (раннер уже новый, поэтому выбирать нечего).
    with pytest.raises(FleetSelectionError):
        await world.fleet.start(ADMIN, [a])


async def test__batch__is_readable_by_id_after_it_finished(world: World) -> None:
    a = await world.runner("docker-a")

    batch = await world.fleet.start(ADMIN, [a])
    await world.done(batch)

    assert world.fleet.batch(ADMIN, batch.id) is batch
    assert world.fleet.batch(ADMIN, "other") is None
    assert batch.finished_at is not None
    assert batch.finished_at - batch.created_at < timedelta(minutes=1)
