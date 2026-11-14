"""«Диск» раннера в админке и «Моих раннерах»: права раздела 7, ошибки 9.1, аудит 8.1, уведомление 8.2, метрики 8.3."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import User, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.invitations.entities import NotificationKind
from hse_doc_studio.core.jobs.codec import decode
from hse_doc_studio.core.jobs.disk import (
    CommandProgress,
    CommandStep,
    CommandStepKind,
    CommandStepStatus,
    DiskAutoPolicy,
    RunnerCommandKind,
    RunnerCommandState,
    RunnerDiskReport,
    disk_cleanable_bytes,
)
from hse_doc_studio.core.jobs.errors import RunnerNotFoundError
from hse_doc_studio.core.jobs.runners import Runner, RunnerOwnerKind
from hse_doc_studio.core.jobs.wire import (
    FEATURE_ANNOUNCE,
    FEATURE_CONTROL,
    FEATURE_DISK,
    FEATURE_DISK_AUTO,
    CommandProgressRequest,
    ControlPollRequest,
    DiskCheckRequest,
)
from hse_doc_studio.use_cases.jobs.runner_control import RunnerCommandWakeup, RunnerControlService
from hse_doc_studio.use_cases.jobs.runner_disk import (
    DiskScope,
    RunnerDiskMetrics,
    RunnerDiskObserver,
    RunnerDiskUC,
)
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.data_lifecycle import FakeNotifier
from tests.fakes.identity import InMemoryIdentityStore, InMemoryUserRepository
from tests.fakes.runner_commands import InMemoryRunnerCommandRepository, InMemoryRunnerDiskStore
from tests.fakes.runners import InMemoryRegistrationTokenRepository, InMemoryRunnerRepository

pytestmark = pytest.mark.unit

_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "runner" / "fixtures"
_DISK = frozenset({FEATURE_ANNOUNCE, FEATURE_CONTROL, FEATURE_DISK})
_ADMIN = Actor(kind="user", id="admin", is_instance_admin=True)
_ANNA = Actor(kind="user", id="anna")
_BORIS = Actor(kind="user", id="boris")


def _report(name: str = "docker") -> RunnerDiskReport:
    raw = json.loads((_FIXTURES / "RunnerDiskReportBody" / f"{name}.json").read_text(encoding="utf-8"))
    return decode(RunnerDiskReport, raw)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class _Uow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


class _Env:
    def __init__(self) -> None:
        self.clock = _Clock()
        self.runners = InMemoryRunnerRepository()
        people = InMemoryIdentityStore()
        for user_id, name in (("admin", "Админ"), ("anna", "Анна"), ("boris", "Борис")):
            people.users[user_id] = User(
                id=user_id,
                email=f"{user_id}@example.org",
                email_normalized=f"{user_id}@example.org",
                name=name,
                status=UserStatus.active,
                created_at=self.clock.now,
            )
        self.people = people
        self.users = InMemoryUserRepository(people)
        self.audit = InMemoryAuditLog()
        self.notifier = FakeNotifier()
        self.metrics = RunnerDiskMetrics()
        self.disks = InMemoryRunnerDiskStore(self.runners)
        self.control = RunnerControlService(
            InMemoryRunnerCommandRepository(self.runners),
            self.disks,
            self.runners,
            RunnerCommandWakeup(),
            clock=self.clock,
            observers=(RunnerDiskObserver(self.runners, self.users, self.audit, self.notifier, self.metrics),),
        )
        registry = RunnerRegistry(
            self.runners, InMemoryRegistrationTokenRepository(), self.audit, _Uow(), clock=self.clock
        )
        self.uc = RunnerDiskUC(
            registry, self.control, self.runners, self.users, self.audit, metrics=self.metrics, clock=self.clock
        )

    async def runner(
        self,
        *,
        owner: str | None = None,
        features: frozenset[str] = _DISK,
        report: str | None = "docker",
        seen_s: float = 5,
        name: str = "r",
    ) -> Runner:
        runner = Runner(
            id=uuid4().hex,
            name=name,
            token_hash=uuid4().hex,
            tags=frozenset({"compile"}),
            concurrency=1,
            resource_class="standard",
            version="0.22.0",
            created_at=self.clock.now,
            last_seen_at=self.clock.now - timedelta(seconds=seen_s),
            features=features,
            owner_kind=RunnerOwnerKind.user if owner else RunnerOwnerKind.instance,
            owner_id=owner,
        )
        await self.runners.add(runner)
        if report is not None:
            await self.disks.set_disk(runner.id, _report(report), self.clock.now)
        return runner

    async def finish(self, runner: Runner, state: RunnerCommandState = RunnerCommandState.done) -> None:
        """Раннер забирает очистку и закрывает её итогом с одним шагом на 1 КиБ."""
        polled = await self.control.poll(runner, ControlPollRequest(wait_s=0))
        assert polled.command is not None
        step = CommandStep(CommandStepKind.build_cache, None, CommandStepStatus.done, 1024, None)
        failed = CommandStep(CommandStepKind.runner_blobs, None, CommandStepStatus.error, 0, "OSError")
        progress = CommandProgress(steps=(step, failed), freed_bytes=1024, error=None)
        await self.control.progress(runner, polled.command.id, CommandProgressRequest(state, progress))


def _code(exc: pytest.ExceptionInfo[IdentityError]) -> IdentityErrorCode:
    return exc.value.code


# --- права (раздел 7) ---


@pytest.mark.parametrize(
    ("actor", "scope", "owner", "rollback"),
    [
        (_ADMIN, "admin", None, True),
        (_ADMIN, "admin", "anna", False),
        (_ANNA, "account", "anna", True),
    ],
    ids=["admin_shared", "admin_foreign_personal", "owner"],
)
async def test__view__who_sees_the_disk_and_who_may_remove_the_rollback(
    actor: Actor, scope: DiskScope, owner: str | None, rollback: bool
) -> None:
    env = _Env()
    runner = await env.runner(owner=owner)

    view = await env.uc.view(actor, runner.id, scope=scope)

    assert (view.supported, view.online, view.can_clean, view.stale) == (True, True, True, False)
    assert view.stored is not None
    assert view.can_include_rollback is rollback
    seen_owner = (view.personal_owner.id, view.personal_owner.name) if view.personal_owner else None
    assert seen_owner == (("anna", "Анна") if scope == "admin" and owner else None)


async def test__view__strangers_get_404() -> None:
    env = _Env()
    personal = await env.runner(owner="anna")
    shared = await env.runner()

    with pytest.raises(RunnerNotFoundError):
        await env.uc.view(_BORIS, personal.id, scope="account")
    with pytest.raises(RunnerNotFoundError):
        await env.uc.view(_BORIS, shared.id, scope="account")
    # Админка не админу не существует: тот же 404, что у `admin_guard`.
    with pytest.raises(IdentityError) as refused:
        await env.uc.view(_ANNA, personal.id, scope="admin")
    assert _code(refused) is IdentityErrorCode.not_found
    with pytest.raises(RunnerNotFoundError):
        env.uc._registry.require_disk_access(_BORIS, personal, rollback=False)  # noqa: SLF001


async def test__view__revoked_runner_is_404_even_for_its_owner_and_admin() -> None:
    env = _Env()
    runner = await env.runner(owner="anna")
    await env.runners.revoke(runner.id, env.clock.now)

    for actor, scope in ((_ANNA, "account"), (_ADMIN, "admin")):
        with pytest.raises(RunnerNotFoundError):
            await env.uc.view(actor, runner.id, scope=scope)  # type: ignore[arg-type]


async def test__cleanup__admin_cannot_remove_rollback_of_foreign_personal_runner_but_owner_can() -> None:
    env = _Env()
    runner = await env.runner(owner="anna")

    with pytest.raises(IdentityError) as refused:
        await env.uc.cleanup(_ADMIN, runner.id, ["old_versions"], include_rollback=True, scope="admin")
    assert _code(refused) is IdentityErrorCode.forbidden

    own = await env.uc.cleanup(_ANNA, runner.id, ["old_versions"], include_rollback=True, scope="account")
    assert own.command.payload.include_rollback is True  # type: ignore[union-attr]
    assert own.created_by is not None
    assert own.created_by.name == "Анна"


async def test__view__admin_on_own_personal_runner_is_its_owner() -> None:
    env = _Env()
    runner = await env.runner(owner="admin")

    view = await env.uc.view(_ADMIN, runner.id, scope="admin")

    assert view.can_include_rollback is True


# --- состояния вида и отказы ---


async def test__view__outdated_runner_hides_its_report_and_refuses_commands() -> None:
    env = _Env()
    runner = await env.runner(features=frozenset({FEATURE_ANNOUNCE}))

    view = await env.uc.view(_ADMIN, runner.id, scope="admin")

    assert (view.supported, view.stored, view.can_clean) == (False, None, False)
    for call in (
        env.uc.refresh(_ADMIN, runner.id, scope="admin"),
        env.uc.cleanup(_ADMIN, runner.id, ["build_cache"], include_rollback=False, scope="admin"),
    ):
        with pytest.raises(IdentityError) as refused:
            await call
        assert _code(refused) is IdentityErrorCode.runner_disk_unsupported


async def test__offline_runner__last_report_is_shown_but_nothing_is_queued() -> None:
    env = _Env()
    runner = await env.runner(seen_s=3600)

    view = await env.uc.view(_ADMIN, runner.id, scope="admin")
    assert (view.online, view.can_clean) == (False, False)
    assert view.stored is not None
    with pytest.raises(IdentityError) as refused:
        await env.uc.refresh(_ADMIN, runner.id, scope="admin")
    assert _code(refused) is IdentityErrorCode.runner_offline


async def test__paused_runner__is_still_online_for_the_disk() -> None:
    env = _Env()
    runner = await env.runner()
    await env.runners.set_paused(runner.id, True)

    assert (await env.uc.view(_ADMIN, runner.id, scope="admin")).can_clean is True


async def test__view__stale_report_and_no_report() -> None:
    env = _Env()
    stale = await env.runner()
    env.clock.now += timedelta(hours=25)
    await env.runners.touch(stale.id, env.clock.now)
    empty = await env.runner(report=None)

    assert (await env.uc.view(_ADMIN, stale.id, scope="admin")).stale is True
    view = await env.uc.view(_ADMIN, empty.id, scope="admin")
    assert (view.stored, view.can_clean, view.can_include_rollback) == (None, False, False)


@pytest.mark.parametrize(
    ("targets", "rollback"),
    [([], False), (["build_cache", "build_cache"], False), (["build_cache"], True), (["images"], False)],
    ids=["empty", "repeated", "rollback_without_old_versions", "unknown"],
)
async def test__cleanup__bad_targets_are_input_invalid(targets: list[str], rollback: bool) -> None:
    env = _Env()
    runner = await env.runner()

    with pytest.raises(IdentityError) as refused:
        await env.uc.cleanup(_ADMIN, runner.id, targets, include_rollback=rollback, scope="admin")
    assert _code(refused) is IdentityErrorCode.input_invalid


async def test__cleanup__target_missing_from_the_report_is_unavailable() -> None:
    env = _Env()
    kubernetes = await env.runner(report="kubernetes")
    silent = await env.runner(report=None)

    for runner in (kubernetes, silent):
        with pytest.raises(IdentityError) as refused:
            await env.uc.cleanup(_ADMIN, runner.id, ["build_cache"], include_rollback=False, scope="admin")
        assert _code(refused) is IdentityErrorCode.disk_target_unavailable
    queued = await env.uc.cleanup(_ADMIN, kubernetes.id, ["runner_cache"], include_rollback=False, scope="admin")
    assert queued.command.state is RunnerCommandState.queued


async def test__cleanup__second_cleanup_and_refresh_during_it_are_busy() -> None:
    env = _Env()
    runner = await env.runner()
    await env.uc.cleanup(_ADMIN, runner.id, ["build_cache"], include_rollback=False, scope="admin")

    for call in (
        env.uc.cleanup(_ADMIN, runner.id, ["runner_cache"], include_rollback=False, scope="admin"),
        env.uc.refresh(_ADMIN, runner.id, scope="admin"),
    ):
        with pytest.raises(IdentityError) as refused:
            await call
        assert _code(refused) is IdentityErrorCode.runner_disk_busy
    view = await env.uc.view(_ADMIN, runner.id, scope="admin")
    assert view.can_clean is False
    assert view.command is not None
    assert view.command.command.state is RunnerCommandState.queued


async def test__refresh__returns_the_measure_already_queued_and_shows_measuring() -> None:
    env = _Env()
    runner = await env.runner()

    first = await env.uc.refresh(_ADMIN, runner.id, scope="admin")
    again = await env.uc.refresh(_ADMIN, runner.id, scope="admin")

    assert first.command.id == again.command.id
    assert first.command.kind is RunnerCommandKind.disk_measure
    view = await env.uc.view(_ADMIN, runner.id, scope="admin")
    assert (view.measuring, view.command) == (True, None)
    assert await env.audit.list() == []


# --- остановка ---


async def test__cancel__queued_cleanup_stops_at_once_and_is_audited() -> None:
    env = _Env()
    runner = await env.runner(owner="anna")
    started = await env.uc.cleanup(_ADMIN, runner.id, ["build_cache"], include_rollback=False, scope="admin")

    stopped = await env.uc.cancel(_ADMIN, runner.id, str(started.command.id), scope="admin")

    assert stopped.command.state is RunnerCommandState.cancelled
    actions = [e.action for e in reversed(await env.audit.list())]
    assert actions == ["runner.disk_cleanup", "runner.disk_cleaned", "runner.disk_cleanup_cancel"]
    # До доставки на раннере ничего не удалилось: владельцу сообщать не о чем.
    assert env.notifier.sent == []
    with pytest.raises(IdentityError) as refused:
        await env.uc.cancel(_ADMIN, runner.id, str(started.command.id), scope="admin")
    assert _code(refused) is IdentityErrorCode.command_finished


async def test__cancel__delivered_cleanup_goes_cancelling() -> None:
    env = _Env()
    runner = await env.runner()
    started = await env.uc.cleanup(_ADMIN, runner.id, ["build_cache"], include_rollback=False, scope="admin")
    await env.control.poll(runner, ControlPollRequest(wait_s=0))

    stopped = await env.uc.cancel(_ADMIN, runner.id, str(started.command.id), scope="admin")

    assert stopped.command.state is RunnerCommandState.cancelling


async def test__cancel__unknown_foreign_or_measure_command_is_not_found() -> None:
    env = _Env()
    runner = await env.runner()
    other = await env.runner()
    foreign = await env.uc.cleanup(_ADMIN, other.id, ["build_cache"], include_rollback=False, scope="admin")
    measure = await env.uc.refresh(_ADMIN, runner.id, scope="admin")

    for command_id in ("nope", str(uuid4()), str(foreign.command.id), str(measure.command.id)):
        with pytest.raises(IdentityError) as refused:
            await env.uc.cancel(_ADMIN, runner.id, command_id, scope="admin")
        assert _code(refused) is IdentityErrorCode.not_found


# --- аудит, уведомление, метрика ---


async def test__admin_cleans_personal_runner__audit_metric_and_owner_notice() -> None:
    env = _Env()
    runner = await env.runner(owner="anna", name="MacBook")
    started = await env.uc.cleanup(
        _ADMIN, runner.id, ["build_cache", "runner_cache"], include_rollback=False, scope="admin"
    )
    await env.finish(runner)

    (cleaned,) = await env.audit.list(action="runner.disk_cleaned")
    assert (cleaned.actor_id, cleaned.target) == ("admin", runner.id)
    assert cleaned.details == {
        "command_id": str(started.command.id),
        "state": "done",
        "freed_bytes": 1024,
        "errors": 1,
        "steps": 2,
    }
    (queued,) = await env.audit.list(action="runner.disk_cleanup")
    assert queued.details == {
        "targets": ["build_cache", "runner_cache"],
        "include_rollback": False,
        "owner_kind": "user",
        "owner_id": "anna",
        "command_id": str(started.command.id),
    }
    ((user_id, kind, payload, dedupe),) = env.notifier.sent
    assert (user_id, kind) == ("anna", NotificationKind.runner_disk_cleaned)
    assert (payload.ref_id, payload.excerpt, payload.actor_name, payload.outcome, payload.freed_bytes) == (
        runner.id,
        "MacBook",
        "Админ",
        "done",
        1024,
    )
    assert dedupe == f"runner_disk_cleaned:{started.command.id}"
    assert env.metrics.cleanups == {"done": 1}
    view = await env.uc.view(_ANNA, runner.id, scope="account")
    assert view.command is not None
    assert view.command.command.state is RunnerCommandState.done


@pytest.mark.parametrize("owner", [None, "anna"], ids=["shared", "own"])
async def test__cleanup_by_owner_or_of_shared_runner__no_notice(owner: str | None) -> None:
    env = _Env()
    runner = await env.runner(owner=owner)
    actor, scope = (_ANNA, "account") if owner else (_ADMIN, "admin")
    await env.uc.cleanup(actor, runner.id, ["build_cache"], include_rollback=False, scope=scope)  # type: ignore[arg-type]
    await env.finish(runner, RunnerCommandState.error)

    assert env.notifier.sent == []
    (cleaned,) = await env.audit.list(action="runner.disk_cleaned")
    assert cleaned.details["state"] == "error"


async def test__creator_gone__command_has_no_author() -> None:
    env = _Env()
    runner = await env.runner()
    started = await env.uc.cleanup(_ADMIN, runner.id, ["build_cache"], include_rollback=False, scope="admin")
    del env.people.users["admin"]

    view = await env.uc.view(_ADMIN, runner.id, scope="admin")

    assert view.command is not None
    assert view.command.command.id == started.command.id
    assert view.command.created_by is None


async def test__view__finished_cleanup_is_shown_for_a_day() -> None:
    env = _Env()
    runner = await env.runner()
    await env.uc.cleanup(_ADMIN, runner.id, ["build_cache"], include_rollback=False, scope="admin")
    await env.finish(runner)

    env.clock.now += timedelta(hours=23)
    await env.runners.touch(runner.id, env.clock.now)
    assert (await env.uc.view(_ADMIN, runner.id, scope="admin")).command is not None
    env.clock.now += timedelta(hours=2)
    await env.runners.touch(runner.id, env.clock.now)
    assert (await env.uc.view(_ADMIN, runner.id, scope="admin")).command is None


# --- списки, сводка, метрика ---


async def test__briefs__revoked_null_outdated_unsupported_reported_with_cleanable() -> None:
    env = _Env()
    reported = await env.runner()
    silent = await env.runner(report=None)
    outdated = await env.runner(features=frozenset({FEATURE_ANNOUNCE}))
    revoked = await env.runner()
    await env.runners.revoke(revoked.id, env.clock.now)
    revoked = replace(revoked, revoked_at=env.clock.now)

    briefs = await env.uc.briefs([reported, silent, outdated, revoked])

    report = _report()
    assert briefs[revoked.id] is None
    assert briefs[reported.id] is not None
    assert (briefs[reported.id].cleanable_bytes, briefs[reported.id].measured_at) == (  # type: ignore[union-attr]
        disk_cleanable_bytes(report),
        report.measured_at,
    )
    assert (briefs[silent.id].supported, briefs[silent.id].cleanable_bytes) == (True, None)  # type: ignore[union-attr]
    assert briefs[outdated.id].supported is False  # type: ignore[union-attr]


async def test__cleanable__docker_cleanable_plus_whole_runner_cache_without_rollback() -> None:
    report = _report()
    assert report.docker is not None
    expected = report.docker.cleanable_bytes + report.cache.blobs.bytes + report.cache.workspaces.bytes
    assert disk_cleanable_bytes(report) == expected
    kubernetes = _report("kubernetes")
    assert disk_cleanable_bytes(kubernetes) == kubernetes.cache.blobs.bytes + kubernetes.cache.workspaces.bytes
    unavailable = _report("docker_unavailable")
    assert disk_cleanable_bytes(unavailable) == unavailable.cache.blobs.bytes + unavailable.cache.workspaces.bytes


async def test__summary__shared_runners_only_top_three_by_cleanable() -> None:
    env = _Env()
    big = await env.runner(name="big")
    small = await env.runner(name="small", report="kubernetes")
    mid = await env.runner(name="mid", report="desktop")
    await env.runner(name="outdated", features=frozenset({FEATURE_ANNOUNCE}))
    await env.runner(name="silent", report=None)
    await env.runner(name="personal", owner="anna")
    gone = await env.runner(name="gone")
    await env.runners.revoke(gone.id, env.clock.now)
    tiny = await env.runner(name="tiny", report="docker_unavailable")

    summary = await env.uc.summary(_ADMIN)

    reports = {r.id: _report(n) for r, n in ((big, "docker"), (small, "kubernetes"), (mid, "desktop"))}
    reports[tiny.id] = _report("docker_unavailable")
    assert (summary.reporting, summary.outdated) == (4, 1)
    assert summary.cleanable_bytes == sum(disk_cleanable_bytes(r) for r in reports.values())
    # У Kubernetes и локальной Студии в эталонах одинаковый кэш: сравниваются объёмы, а не порядок равных.
    ranked = sorted((disk_cleanable_bytes(r) for r in reports.values()), reverse=True)
    assert [row.cleanable_bytes for row in summary.top] == ranked[:3]
    assert summary.top[0].runner_id == big.id
    assert {row.runner_id for row in summary.top} <= set(reports)
    with pytest.raises(IdentityError):
        await env.uc.summary(_ANNA)


async def test__refresh_metrics__sums_by_scope() -> None:
    env = _Env()
    await env.runner()
    await env.runner(owner="anna", report="kubernetes")
    await env.runner(features=frozenset({FEATURE_ANNOUNCE}))

    await env.uc.refresh_metrics()

    assert env.metrics.cleanable == {
        "shared": disk_cleanable_bytes(_report()),
        "personal": disk_cleanable_bytes(_report("kubernetes")),
    }


def test__collector__prints_gauge_after_first_refresh_and_counter_by_state() -> None:
    from hse_doc_studio.api.observability.runner_disk_metrics import runner_disk_collector  # noqa: PLC0415

    state = RunnerDiskMetrics()
    collect = runner_disk_collector(state)
    assert list(collect()) == []

    state.cleanable = {"shared": 10, "personal": 0}
    state.cleanups["done"] += 2
    lines = list(collect())

    assert 'hse_runner_disk_cleanable_bytes{scope="personal"} 0' in lines
    assert 'hse_runner_disk_cleanable_bytes{scope="shared"} 10' in lines
    assert 'hse_runner_disk_cleanups_total{state="done"} 2' in lines
    assert "# TYPE hse_runner_disk_cleanups_total counter" in lines


# --- автоочистка (раздел 14) ---

_AUTO = _DISK | {FEATURE_DISK_AUTO}
_LOW = DiskCheckRequest(free_bytes=5 * 1024**3, total_bytes=100 * 1024**3)


async def test__view__auto_block_only_for_shared_runners_in_admin() -> None:
    env = _Env()
    shared = await env.runner(features=_AUTO)
    personal = await env.runner(owner="anna", features=_AUTO)

    state = await env.uc.view(_ADMIN, shared.id, scope="admin")
    assert state.auto is not None
    assert (state.auto.supported, state.auto.reason, state.auto.policy) == (True, None, DiskAutoPolicy())
    assert state.auto.last is None
    assert (await env.uc.view(_ADMIN, personal.id, scope="admin")).auto is None
    assert (await env.uc.view(_ANNA, personal.id, scope="account")).auto is None


@pytest.mark.parametrize(
    ("version", "report", "reason"),
    [
        ("0.27.0", "docker", "outdated"),
        ("0.28.0", "docker", "runner_disabled"),
        ("0.28.0", "kubernetes", "kubernetes"),
        ("0.28.0", "desktop", "managed_locally"),
    ],
)
async def test__view__why_auto_is_unsupported(version: str, report: str, reason: str) -> None:
    env = _Env()
    runner = await env.runner(report=report)
    await env.runners.add(replace(runner, version=version))

    state = await env.uc.view(_ADMIN, runner.id, scope="admin")

    assert state.auto is not None
    assert (state.auto.supported, state.auto.reason) == (False, reason)


async def test__set_auto__saves_policy_and_audits_before_and_after() -> None:
    env = _Env()
    runner = await env.runner(features=_AUTO)

    state = await env.uc.set_auto(_ADMIN, runner.id, enabled=False, min_free_percent=25)

    assert state.policy == DiskAutoPolicy(enabled=False, min_free_percent=25)
    (entry,) = await env.audit.list(action="runner.disk_auto_policy")
    assert entry.actor_id == "admin"
    assert entry.target == runner.id
    assert entry.details == {
        "enabled": False,
        "min_free_percent": 25,
        "was_enabled": True,
        "was_min_free_percent": 10,
    }
    assert (await env.uc.view(_ADMIN, runner.id, scope="admin")).auto.policy.min_free_percent == 25  # type: ignore[union-attr]


@pytest.mark.parametrize("percent", [0, 51])
async def test__set_auto__percent_out_of_range__input_invalid(percent: int) -> None:
    env = _Env()
    runner = await env.runner(features=_AUTO)

    with pytest.raises(IdentityError) as exc:
        await env.uc.set_auto(_ADMIN, runner.id, enabled=True, min_free_percent=percent)
    assert _code(exc) is IdentityErrorCode.input_invalid


async def test__set_auto__personal_runner_forbidden_and_not_admin_not_found() -> None:
    env = _Env()
    personal = await env.runner(owner="anna", features=_AUTO)
    shared = await env.runner(features=_AUTO)

    with pytest.raises(IdentityError) as exc:
        await env.uc.set_auto(_ADMIN, personal.id, enabled=True, min_free_percent=10)
    assert _code(exc) is IdentityErrorCode.forbidden
    with pytest.raises(IdentityError):
        await env.uc.set_auto(_ANNA, shared.id, enabled=True, min_free_percent=10)
    with pytest.raises(RunnerNotFoundError):
        await env.uc.set_auto(_ADMIN, "missing", enabled=True, min_free_percent=10)


async def test__auto_cleanup__audited_as_system_without_notification_and_shown_in_view() -> None:
    env = _Env()
    runner = await env.runner(features=_AUTO)
    command = (await env.control.disk_check(runner, _LOW)).command
    assert command is not None

    state = await env.uc.view(_ADMIN, runner.id, scope="admin")
    assert state.command is not None
    assert state.command.auto
    assert state.command.created_by is None
    assert not state.can_clean
    with pytest.raises(IdentityError) as exc:
        await env.uc.cleanup(_ADMIN, runner.id, ["build_cache"], include_rollback=False, scope="admin")
    assert _code(exc) is IdentityErrorCode.runner_disk_busy

    step = CommandStep(CommandStepKind.build_cache, None, CommandStepStatus.done, 2048, None)
    await env.control.progress(
        runner,
        command.id,
        CommandProgressRequest(RunnerCommandState.done, CommandProgress(steps=(step,), freed_bytes=2048, error=None)),
    )

    (started,) = await env.audit.list(action="runner.disk_auto_cleanup")
    assert started.actor_id is None
    assert started.details["targets"] == ["dangling_images", "build_cache", "old_versions"]
    assert started.details["min_free_percent"] == 10
    (cleaned,) = await env.audit.list(action="runner.disk_cleaned")
    assert cleaned.actor_id is None
    assert cleaned.details["auto"] is True
    assert cleaned.details["freed_bytes"] == 2048
    assert env.notifier.sent == []
    after = await env.uc.view(_ADMIN, runner.id, scope="admin")
    assert after.auto is not None
    assert after.auto.last is not None
    assert (after.auto.last.state, after.auto.last.freed_bytes) == (RunnerCommandState.done, 2048)
