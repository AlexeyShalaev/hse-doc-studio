"""Откат на выбранную версию (политика схемы, гонки, апдейтер без поддержки) и переключатель автоустановки."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.server_update.entities import (
    ReleaseInfo,
    RunKind,
    RunStatus,
    RunTrigger,
    UpdatePolicy,
    UpdateRun,
    Verify,
)
from hse_doc_studio.core.server_update.errors import UpdateError, UpdateErrorCode
from hse_doc_studio.core.server_update.settings import settings_from
from hse_doc_studio.core.server_update.versions import SchemaVerdict
from hse_doc_studio.use_cases.server_update.service import EventReport, PollReport

from tests.unit.use_cases.server_update.test_update_service import NOW, Env, configure, make

HEAD = "rev_b"
D = "https://example.org/d.json"
RELEASES = (
    ReleaseInfo("0.3.3", digests_url=D),
    ReleaseInfo("0.3.2", digests_url=D),
    ReleaseInfo("0.3.1", digests_url=D),
    ReleaseInfo("0.3.0", digests_url=""),
)


def _env(*, history: tuple[UpdateRun, ...] = (), executor: bool = True) -> Env:
    env = make(current="0.3.3", executor=executor, releases=RELEASES)
    env.service._options = replace(env.service._options, db_head=HEAD)
    for run in history:
        env.runs.items[run.id] = run
    return env


def _done(rid: str, frm: str, to: str, frm_rev: str, to_rev: str, minutes: int) -> UpdateRun:
    return UpdateRun(
        id=rid,
        kind=RunKind.update,
        trigger=RunTrigger.manual,
        status=RunStatus.succeeded,
        from_version=frm,
        to_version=to,
        created_at=NOW.replace(minute=minutes),
        from_revision=frm_rev,
        to_revision=to_rev,
    )


# 0.3.1 жила на rev_a, 0.3.2 и 0.3.3 на rev_b.
HISTORY = (_done("a", "0.3.1", "0.3.2", "rev_a", "rev_b", 1),)


async def _ready(env: Env, *, downgrade: bool = True) -> None:
    await configure(env, policy=UpdatePolicy.notify, backup_first=False)
    await env.service.check_now("boss")
    caps = ("downgrade",) if downgrade else ()
    await env.service.poll(PollReport(updater_version="0.3.3", busy=True, capabilities=caps))


async def test__status__lists_older_releases_with_a_schema_verdict() -> None:
    env = _env(history=HISTORY)
    await _ready(env)

    status = await env.service.status()

    got = {t.release.version: (t.verdict, t.revision) for t in status.downgrade_targets}
    assert got == {
        "0.3.2": (SchemaVerdict.compatible, "rev_b"),
        "0.3.1": (SchemaVerdict.incompatible, "rev_a"),
        "0.3.0": (SchemaVerdict.unknown, None),
    }
    assert [t.release.version for t in status.downgrade_targets] == ["0.3.2", "0.3.1", "0.3.0"]
    assert status.updater_can_downgrade is True
    assert status.db_revision == HEAD


async def test__downgrade__to_a_compatible_version_queues_a_run_and_audits_it() -> None:
    env = _env(history=HISTORY)
    await _ready(env)

    run = await env.service.request_downgrade("boss", "0.3.2")

    assert (run.kind, run.status, run.to_version, run.from_version) == (
        RunKind.downgrade,
        RunStatus.queued,
        "0.3.2",
        "0.3.3",
    )
    assert run.digests_url == D
    audit = [e for e in await env.audit.list() if e.action == "update.downgrade_request"]
    assert len(audit) == 1
    assert audit[0].actor_id == "boss"


async def test__downgrade__to_a_schema_incompatible_version_is_refused_and_nothing_is_created() -> None:
    env = _env(history=HISTORY)
    await _ready(env)

    with pytest.raises(UpdateError) as exc:
        await env.service.request_downgrade("boss", "0.3.1")

    assert exc.value.code is UpdateErrorCode.schema_incompatible
    assert "rev_a" in exc.value.message
    assert await env.runs.active() is None
    assert not [e for e in await env.audit.list() if e.action == "update.downgrade_request"]


async def test__downgrade__unknown_schema_is_left_to_the_updater() -> None:
    env = _env()
    await _ready(env)
    await env.service.update_settings("boss", replace(settings_from(await env.settings.get_all()), verify=Verify.none))

    run = await env.service.request_downgrade("boss", "0.3.0")

    assert run.kind is RunKind.downgrade


@pytest.mark.parametrize(
    ("version", "code"),
    [
        ("9.9.9", UpdateErrorCode.unknown_version),
        ("0.3.3", UpdateErrorCode.invalid_input),  # не старше текущей
        ("0.3.0", UpdateErrorCode.digest_missing),  # проверка образа включена, дайджеста у релиза нет
    ],
)
async def test__downgrade__validates_the_target(version: str, code: UpdateErrorCode) -> None:
    env = _env()
    await _ready(env)
    with pytest.raises(UpdateError) as exc:
        await env.service.request_downgrade("boss", version)
    assert exc.value.code is code


async def test__downgrade__needs_a_live_updater_that_supports_it() -> None:
    env = _env(history=HISTORY)
    await _ready(env, downgrade=False)  # старый апдейтер: возможности не сообщает
    with pytest.raises(UpdateError) as old:
        await env.service.request_downgrade("boss", "0.3.2")
    assert old.value.code is UpdateErrorCode.updater_outdated

    helm = _env(history=HISTORY, executor=False)
    with pytest.raises(UpdateError) as manual:
        await helm.service.request_downgrade("boss", "0.3.2")
    assert manual.value.code is UpdateErrorCode.executor_unavailable


async def test__downgrade__concurrent_update_and_rollback_cannot_both_start() -> None:
    env = _env(history=HISTORY)
    await _ready(env)

    await env.service.request_downgrade("boss", "0.3.2")
    with pytest.raises(UpdateError) as second:
        await env.service.request_downgrade("boss", "0.3.2")
    with pytest.raises(UpdateError) as update:
        await env.service.request_update("boss", None)

    assert second.value.code is UpdateErrorCode.already_running
    assert update.value.code in {UpdateErrorCode.already_running, UpdateErrorCode.nothing_to_update}


async def test__downgrade__success_switches_auto_install_off_so_the_new_version_does_not_come_back() -> None:
    env = _env(history=HISTORY)
    await _ready(env)
    await configure(env, policy=UpdatePolicy.auto, backup_first=False)
    run = await env.service.request_downgrade("boss", "0.3.2")
    spec = await env.service.poll(PollReport(updater_version="0.3.3", capabilities=("downgrade",)))
    assert spec is not None
    assert (spec.kind, spec.run_id) == (RunKind.downgrade, run.id)

    await env.service.report(
        run.id,
        EventReport(seq=1, at=NOW, phase="finish", level="info", message="ok", status=RunStatus.succeeded),
    )

    assert settings_from(await env.settings.get_all()).policy is UpdatePolicy.notify
    toggles = [e for e in await env.audit.list() if e.action == "update.auto_toggle"]
    assert toggles
    assert toggles[-1].details["reason"] == "downgrade"


async def test__downgrade__failed_run_is_recorded_and_leaves_auto_install_alone() -> None:
    env = _env(history=HISTORY)
    await _ready(env)
    await configure(env, policy=UpdatePolicy.auto, backup_first=False)
    run = await env.service.request_downgrade("boss", "0.3.2")
    await env.service.poll(PollReport(updater_version="0.3.3", capabilities=("downgrade",)))

    done = await env.service.report(
        run.id,
        EventReport(
            seq=1,
            at=NOW,
            phase="finish",
            level="error",
            message="schema mismatch",
            status=RunStatus.cancelled,
            error_code="schema_incompatible",
        ),
    )

    assert (done.status, done.error_code) == (RunStatus.cancelled, "schema_incompatible")
    assert settings_from(await env.settings.get_all()).policy is UpdatePolicy.auto


async def test__downgrade__takes_a_backup_first_when_one_is_configured() -> None:
    from tests.unit.use_cases.server_update.test_update_service import _destination

    env = _env(history=HISTORY)
    await _ready(env)
    await configure(env, policy=UpdatePolicy.notify, backup_first=True)
    await _destination(env)

    run = await env.service.request_downgrade("boss", "0.3.2")

    assert run.status is RunStatus.waiting_backup
    assert env.backup.started == 1


# ---- переключатель автоустановки ----


async def test__auto_toggle__off_keeps_checks_and_notifications_but_installs_nothing() -> None:
    env = make(releases=(ReleaseInfo("0.3.2", digests_url=D), ReleaseInfo("0.3.1")))
    await configure(env)
    await env.service.poll(PollReport(updater_version="0.3.1", busy=True))

    await env.service.set_auto_update("boss", enabled=False)
    await env.service.tick()

    assert await env.runs.active() is None
    assert env.source.calls == 1  # проверка идёт
    status = await env.service.status()
    assert (status.auto_update_enabled, status.settings.policy, status.checked_at is not None) == (
        False,
        UpdatePolicy.notify,
        True,
    )
    sent = [(p.outcome, p.path) for _u, _k, p, _d in env.notifier.sent]  # type: ignore[attr-defined]
    assert sent == [("update_available", "0.3.2")]  # уведомление остаётся


async def test__auto_toggle__state_lives_in_instance_settings_and_survives_a_restart() -> None:
    env = make(releases=(ReleaseInfo("0.3.2", digests_url=D),))
    await configure(env)
    await env.service.set_auto_update("boss", enabled=False)

    # «Перезапуск»: новый сервис над теми же настройками читает то же состояние.
    again = make(releases=(ReleaseInfo("0.3.2", digests_url=D),))
    again.service._repo = env.settings  # type: ignore[attr-defined]
    assert (await again.service.status()).auto_update_enabled is False

    await env.service.set_auto_update("boss", enabled=True)
    assert (await again.service.status()).auto_update_enabled is True


async def test__auto_toggle__is_audited_and_idempotent() -> None:
    env = make(releases=())
    await configure(env)

    await env.service.set_auto_update("boss", enabled=False)
    await env.service.set_auto_update("boss", enabled=False)

    toggles = [e for e in await env.audit.list() if e.action == "update.auto_toggle"]
    assert len(toggles) == 1
    assert toggles[0].details == {"enabled": False, "before": "auto", "after": "notify"}


async def test__auto_toggle__off_cancels_an_auto_run_the_updater_has_not_taken_yet() -> None:
    env = make(releases=(ReleaseInfo("0.3.2", digests_url=D), ReleaseInfo("0.3.1")))
    await configure(env)
    await env.service.poll(PollReport(updater_version="0.3.1", busy=True))
    await env.service.tick()
    assert (await env.runs.active()) is not None

    await env.service.set_auto_update("boss", enabled=False)

    assert await env.runs.active() is None
    last = await env.runs.last_finished()
    assert last is not None
    assert (last.status, last.error_code) == (RunStatus.cancelled, "auto_update_disabled")


async def test__auto_toggle__an_auto_run_queued_before_the_switch_is_not_handed_to_the_updater() -> None:
    env = make(releases=(ReleaseInfo("0.3.2", digests_url=D), ReleaseInfo("0.3.1")))
    await configure(env)
    await env.service.poll(PollReport(updater_version="0.3.1", busy=True))
    await env.service.tick()
    # переключение дошло до базы, но отмену ещё не сделали (гонка): поллинг сам не отдаёт запуск
    await configure(env, policy=UpdatePolicy.notify)

    assert await env.service.poll(PollReport(updater_version="0.3.1")) is None
    assert await env.runs.active() is None


async def test__auto_toggle__manual_runs_are_not_cancelled_by_the_switch() -> None:
    env = make(releases=(ReleaseInfo("0.3.2", digests_url=D), ReleaseInfo("0.3.1")))
    await configure(env, policy=UpdatePolicy.notify)
    await env.service.check_now("boss")
    await env.service.poll(PollReport(updater_version="0.3.1", busy=True))
    await env.service.request_update("boss", None)
    await configure(env, policy=UpdatePolicy.auto)

    await env.service.set_auto_update("boss", enabled=False)

    assert (await env.runs.active()) is not None


async def test__auto_toggle__enabling_needs_the_executor() -> None:
    env = make(executor=False, releases=())
    await configure(env, policy=UpdatePolicy.notify)
    with pytest.raises(UpdateError) as exc:
        await env.service.set_auto_update("boss", enabled=True)
    assert exc.value.code is UpdateErrorCode.executor_unavailable


async def test__auto_toggle__off_policy_stays_off_when_switched_off() -> None:
    env = make(releases=())
    await configure(env, policy=UpdatePolicy.off)
    await env.service.set_auto_update("boss", enabled=False)
    assert (await env.service.status()).settings.policy is UpdatePolicy.off
