"""Принятие и возврат предупреждений: хранение, права, аудит, срок, итог, уведомления."""

from __future__ import annotations

from datetime import timedelta

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.diagnostics.acceptance import KEY_ACCEPTED, REASON_MAX
from hse_doc_studio.core.diagnostics.entities import CheckId, DiagStatus, Verdict
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.use_cases.diagnostics.admin import (
    AcceptDiagnosticsWarningUC,
    CheckView,
    DiagnosticsOverview,
    GetDiagnosticsUC,
    RevokeDiagnosticsAcceptanceUC,
)

from tests.fakes.ops import NoopUow
from tests.unit.use_cases.diagnostics.test_service_and_admin import ADMIN, STUDENT, Env, ScriptedCheck, _ok

NO_BACKUPS = Verdict(DiagStatus.warn, "backups_disabled")
NO_RUNNERS = Verdict(DiagStatus.warn, "no_runners", {"registered": 0, "online": 0, "queued": 0})
DISK_WARN = Verdict(DiagStatus.warn, "disk_warning", {"volume": "data", "percent": 85})
DB_FAIL = Verdict(DiagStatus.fail, "db_unreachable", {"error": "OSError"})


class Ctx:
    def __init__(self, *checks: ScriptedCheck) -> None:
        self.env = Env(*checks)
        env = self.env
        self.get = GetDiagnosticsUC(env.service, env.settings, interval_s=300, enabled=True, clock=env.clock)
        self.accept = AcceptDiagnosticsWarningUC(
            env.settings,
            env.audit,
            NoopUow(),
            env.service,
            self.get,
            clock=env.clock,  # type: ignore[arg-type]
        )
        self.revoke = RevokeDiagnosticsAcceptanceUC(env.settings, env.audit, NoopUow(), self.get)  # type: ignore[arg-type]

    async def ready(self) -> None:
        await self.env.service.run(notify=False)


def _view(overview: DiagnosticsOverview, check: str) -> CheckView:
    return next(c for c in overview.checks if c.spec.id.value == check)


async def test__accept__stores_record_audits_and_drops_check_from_overall() -> None:
    ctx = Ctx(ScriptedCheck(CheckId.backups, NO_BACKUPS), ScriptedCheck(CheckId.database, _ok()))
    await ctx.ready()
    assert (await ctx.get.view()).overall is DiagStatus.warn

    overview = await ctx.accept.execute(ADMIN, "backups", "  Бэкапы делает хостер  ")

    view = _view(overview, "backups")
    assert view.accepted is not None
    assert view.accepted.reason == "Бэкапы делает хостер"
    assert view.accepted.by_id == "boss"
    assert view.state.result.status is DiagStatus.warn
    assert view.acceptable is False
    assert overview.overall is DiagStatus.ok
    assert [(a.acceptance.check_id, a.active) for a in overview.accepted] == [("backups", True)]
    stored = (await ctx.env.settings.get_all())[KEY_ACCEPTED]
    assert stored["backups"]["by"] == "boss"  # type: ignore[index]
    (event,) = await ctx.env.audit.list()
    assert (event.action, event.target, event.actor_id) == ("diagnostics.accept", "backups", "boss")
    assert event.details == {"reason": "Бэкапы делает хостер", "until": None, "cause": "backups_disabled"}


async def test__accept__offered_only_while_the_warning_is_acceptable() -> None:
    ctx = Ctx(ScriptedCheck(CheckId.backups, NO_BACKUPS), ScriptedCheck(CheckId.disk, DISK_WARN))
    await ctx.ready()

    overview = await ctx.get.view()

    assert _view(overview, "backups").acceptable is True
    assert _view(overview, "disk").acceptable is False
    assert _view(overview, "database").acceptable is False  # не проверялась


@pytest.mark.parametrize(
    ("check", "verdict"),
    [(CheckId.database, DB_FAIL), (CheckId.disk, DISK_WARN), (CheckId.migrations, _ok()), (CheckId.backups, _ok())],
)
async def test__accept__critical_failing_or_healthy_check_is_refused(check: CheckId, verdict: Verdict) -> None:
    ctx = Ctx(ScriptedCheck(check, verdict))
    await ctx.ready()

    with pytest.raises(IdentityError) as caught:
        await ctx.accept.execute(ADMIN, check.value, "не хочу")

    assert caught.value.code is IdentityErrorCode.input_invalid
    assert KEY_ACCEPTED not in await ctx.env.settings.get_all()
    assert await ctx.env.audit.list() == []


async def test__accept__bad_input_is_refused() -> None:
    ctx = Ctx(ScriptedCheck(CheckId.backups, NO_BACKUPS))
    await ctx.ready()
    past = ctx.env.clock.now - timedelta(minutes=1)

    for reason, until in [
        ("", None),
        ("   ", None),
        ("я" * (REASON_MAX + 1), None),
        ("ок", past),
        ("ок", ctx.env.clock.now),
    ]:
        with pytest.raises(IdentityError) as caught:
            await ctx.accept.execute(ADMIN, "backups", reason, until)
        assert caught.value.code is IdentityErrorCode.input_invalid
    with pytest.raises(IdentityError) as unknown:
        await ctx.accept.execute(ADMIN, "nope", "ок")
    assert unknown.value.code is IdentityErrorCode.not_found
    assert KEY_ACCEPTED not in await ctx.env.settings.get_all()

    await ctx.accept.execute(ADMIN, "backups", "я" * REASON_MAX)  # граница проходит


@pytest.mark.parametrize("actor", [STUDENT, Actor(kind=ActorKind.local)])
async def test__accept_and_revoke__only_the_installation_admin(actor: Actor) -> None:
    ctx = Ctx(ScriptedCheck(CheckId.backups, NO_BACKUPS))
    await ctx.ready()
    await ctx.accept.execute(ADMIN, "backups", "так надо")
    before = await ctx.env.settings.get_all()

    for call in (ctx.accept.execute(actor, "backups", "взлом"), ctx.revoke.execute(actor, "backups")):
        with pytest.raises(IdentityError) as caught:
            await call
        assert caught.value.code is IdentityErrorCode.not_found

    assert await ctx.env.settings.get_all() == before
    assert [e.action for e in await ctx.env.audit.list()] == ["diagnostics.accept"]


async def test__revoke__removes_record_and_audits() -> None:
    ctx = Ctx(ScriptedCheck(CheckId.backups, NO_BACKUPS))
    await ctx.ready()
    await ctx.accept.execute(ADMIN, "backups", "так надо")

    overview = await ctx.revoke.execute(ADMIN, "backups")

    assert _view(overview, "backups").accepted is None
    assert overview.accepted == []
    assert overview.overall is DiagStatus.warn
    assert KEY_ACCEPTED not in await ctx.env.settings.get_all()
    last = (await ctx.env.audit.list())[0]
    assert (last.action, last.target, last.details) == ("diagnostics.accept_revoke", "backups", {"reason": "так надо"})
    with pytest.raises(IdentityError):
        await ctx.revoke.execute(ADMIN, "backups")


async def test__accept__second_check_keeps_the_first_and_reaccept_replaces_the_reason() -> None:
    ctx = Ctx(ScriptedCheck(CheckId.backups, NO_BACKUPS), ScriptedCheck(CheckId.runners, NO_RUNNERS))
    await ctx.ready()

    await ctx.accept.execute(ADMIN, "backups", "первая")
    await ctx.accept.execute(ADMIN, "runners", "публичных нет")
    overview = await ctx.accept.execute(ADMIN, "backups", "вторая")

    assert {a.acceptance.check_id: a.acceptance.reason for a in overview.accepted} == {
        "backups": "вторая",
        "runners": "публичных нет",
    }
    assert overview.overall is DiagStatus.ok


async def test__expiry__after_until_the_warning_returns() -> None:
    ctx = Ctx(ScriptedCheck(CheckId.backups, NO_BACKUPS))
    await ctx.ready()
    until = ctx.env.clock.now + timedelta(days=1)
    await ctx.accept.execute(ADMIN, "backups", "до конца недели", until)
    assert (await ctx.get.view()).overall is DiagStatus.ok

    ctx.env.clock.now = until + timedelta(seconds=1)
    await ctx.ready()
    overview = await ctx.get.view()

    assert overview.overall is DiagStatus.warn
    assert _view(overview, "backups").accepted is None
    assert _view(overview, "backups").acceptable is True
    assert overview.accepted == []


async def test__situation_changed__record_stays_but_is_dormant_and_comes_back_with_the_problem() -> None:
    ctx = Ctx(ScriptedCheck(CheckId.backups, NO_BACKUPS, _ok(), NO_BACKUPS))
    await ctx.ready()
    await ctx.accept.execute(ADMIN, "backups", "так надо")

    await ctx.ready()  # бэкапы включили
    healed = await ctx.get.view()
    assert [(a.acceptance.check_id, a.active) for a in healed.accepted] == [("backups", False)]
    assert _view(healed, "backups").accepted is None
    assert healed.overall is DiagStatus.ok

    await ctx.ready()  # и снова выключили: принятие вернулось само
    again = await ctx.get.view()
    assert _view(again, "backups").accepted is not None
    assert again.overall is DiagStatus.ok


async def test__accepted_warning__is_silent_and_revoking_it_notifies_on_the_next_passes() -> None:
    ctx = Ctx(ScriptedCheck(CheckId.backups, NO_BACKUPS))
    env = ctx.env
    await ctx.ready()
    await ctx.accept.execute(ADMIN, "backups", "так надо")

    for _ in range(4):
        await env.service.tick()
        env.clock.step()
    assert env.notifier.sent == []
    assert "backups" in env.service.accepted

    await ctx.revoke.execute(ADMIN, "backups")
    for _ in range(2):
        await env.service.tick()
        env.clock.step()

    assert {p.outcome for _, _, p, _ in env.notifier.sent} == {"diag_warn"}
    assert env.service.accepted == {}


async def test__accepted_failure_of_the_same_check_still_notifies() -> None:
    ctx = Ctx(ScriptedCheck(CheckId.backups, NO_BACKUPS, NO_BACKUPS, Verdict(DiagStatus.fail, "backups_stale")))
    env = ctx.env
    await ctx.ready()
    await ctx.accept.execute(ADMIN, "backups", "так надо")

    await env.service.tick()
    await env.service.tick()  # третий прогон уже fail: принятие на него не действует
    await env.service.tick()
    await env.service.tick()

    assert [p.outcome for _, _, p, _ in env.notifier.sent][:1] == ["diag_fail"]
    assert env.service.accepted == {}
