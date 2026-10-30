"""Чтение и стирание журнала аудита: права, страницы по ключу, срок хранения."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.identity.entities import AuditQuery
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.use_cases.admin.audit import MAX_AUDIT_PAGE, ListAuditUC, PurgeAuditUC

from tests.fakes.auth import InMemoryAuditLog

ADMIN = Actor(kind=ActorKind.user, id="boss", is_instance_admin=True)
STUDENT = Actor(kind=ActorKind.user, id="anna")


async def _log(count: int) -> InMemoryAuditLog:
    audit = InMemoryAuditLog()
    for n in range(count):
        await audit.record(f"e.{n}", actor_id="boss")
    return audit


async def test__list__not_admin__not_found() -> None:
    uc = ListAuditUC(await _log(1))

    for actor in (STUDENT, Actor(kind=ActorKind.guest), Actor(kind=ActorKind.local)):
        with pytest.raises(IdentityError) as exc:
            await uc.execute(actor, AuditQuery())
        assert exc.value.code is IdentityErrorCode.not_found


async def test__list__walks_all_pages_without_gaps_or_repeats() -> None:
    audit = await _log(7)
    uc = ListAuditUC(audit)

    seen: list[int] = []
    cursor = None
    pages = 0
    while True:
        page = await uc.execute(ADMIN, AuditQuery(limit=3, before_id=cursor))
        seen += [e.entry.id for e in page.items]
        pages += 1
        if page.next_before_id is None:
            break
        cursor = page.next_before_id

    assert seen == [7, 6, 5, 4, 3, 2, 1]
    assert pages == 3


async def test__list__new_events_during_paging_do_not_shift_the_next_page() -> None:
    audit = await _log(6)
    uc = ListAuditUC(audit)
    first = await uc.execute(ADMIN, AuditQuery(limit=3))

    await audit.record("late", actor_id="boss")
    second = await uc.execute(ADMIN, AuditQuery(limit=3, before_id=first.next_before_id))

    assert [e.entry.id for e in second.items] == [3, 2, 1]


async def test__list__limit_is_clamped() -> None:
    uc = ListAuditUC(await _log(MAX_AUDIT_PAGE + 5))

    assert len((await uc.execute(ADMIN, AuditQuery(limit=10_000))).items) == MAX_AUDIT_PAGE
    assert len((await uc.execute(ADMIN, AuditQuery(limit=0))).items) == 1


async def test__purge__removes_old_and_records_one_event() -> None:
    audit = InMemoryAuditLog()
    now = datetime(2027, 1, 1, tzinfo=UTC)
    await audit.record("fresh", actor_id=None)
    uc = PurgeAuditUC(audit, audit, timedelta(days=365), clock=lambda: now + timedelta(days=366))

    report = await uc.execute()

    assert report.purged == 1
    (event,) = await audit.list()
    assert (event.action, event.actor_id, dict(event.details)) == ("audit.purged", None, {"count": 1, "keep_days": 365})


async def test__purge__nothing_old_writes_nothing() -> None:
    audit = await _log(2)
    uc = PurgeAuditUC(audit, audit, timedelta(days=365))

    assert (await uc.execute()).purged == 0
    assert len(await audit.list()) == 2


async def test__purge__zero_retention_keeps_everything() -> None:
    audit = await _log(2)
    uc = PurgeAuditUC(audit, audit, timedelta(0), clock=lambda: datetime(2100, 1, 1, tzinfo=UTC))

    assert (await uc.execute()).purged == 0
    assert len(await audit.list()) == 2


async def test__list__estimate_only_without_filters() -> None:
    uc = ListAuditUC(await _log(4))

    assert (await uc.execute(ADMIN, AuditQuery())).total_estimate == 4
    assert (await uc.execute(ADMIN, AuditQuery(q="x"))).total_estimate is None
    assert (await uc.execute(ADMIN, AuditQuery(categories=("admin",)))).total_estimate is None
