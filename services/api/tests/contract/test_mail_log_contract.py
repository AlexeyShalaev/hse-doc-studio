"""Контракт журнала писем (docs/design/mail-log.md, 5.1): одни и те же проверки на InMemory и Postgres."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from hse_doc_studio.core.identity.protocols import IMailLogRepository
from hse_doc_studio.core.mail.journal import (
    MailCause,
    MailLinkKind,
    MailLogEntry,
    MailLogQuery,
    MailParams,
    MailStatus,
)
from pytest_lazy_fixtures import lf

from tests.fakes.mail_log import InMemoryMailLogRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
PROJECT = str(uuid.UUID(int=7))


def make_entry(
    to: str = "anna@example.org",
    *,
    minutes: int = 0,
    status: MailStatus = MailStatus.sent,
    template: str = "signing_request",
    **fields: object,
) -> MailLogEntry:
    defaults: dict[str, object] = {
        "reason": None,
        "message_id": f"<{uuid.uuid4().hex}@studio.example.org>" if status is MailStatus.sent else None,
    }
    if status is MailStatus.failed:
        defaults |= {"reason": "recipient_refused", "smtp_code": 550, "error_text": "550 5.1.1 no such user"}
    if status is MailStatus.not_sent:
        defaults["reason"] = "smtp_off"
    if status is MailStatus.suppressed:
        defaults["reason"] = "email_unverified"
    return MailLogEntry(
        **{  # type: ignore[arg-type]
            "at": NOW + timedelta(minutes=minutes),
            "duration_ms": 120,
            "template": template,
            "lang": "ru",
            "to_email": to,
            "subject": f"Подпишите документ ({to})",
            "status": status,
            "cause": MailCause.user,
            "origin": "notification",
            "params": MailParams(
                values={"actor": "Анна Петрова", "project": "Курсовая"}, link=MailLinkKind.page, link_path="/sign/p/r"
            ),
            "template_digest": "0123456789abcdef",
            **defaults,
            **fields,
        }
    )


@pytest_asyncio.fixture
async def memory_repo() -> IMailLogRepository:
    return InMemoryMailLogRepository()


@pytest_asyncio.fixture
async def pg_repo(pg_migrated_engine: AsyncEngine) -> IMailLogRepository:
    from hse_doc_studio.infra.db.engine import create_sessionmaker
    from hse_doc_studio.infra.db.repositories.mail_log import SqlMailLogRepository
    from hse_doc_studio.infra.db.session import SessionProvider

    return SqlMailLogRepository(SessionProvider(create_sessionmaker(pg_migrated_engine)))


@pytest.fixture(params=[lf("memory_repo"), pytest.param(lf("pg_repo"), marks=pytest.mark.pg)], ids=["in_memory", "pg"])
def repo(request: pytest.FixtureRequest) -> IMailLogRepository:
    return request.param


async def test__add__then_get__roundtrips_every_column(repo: IMailLogRepository) -> None:
    entry = make_entry(
        to="Boris@Example.org",
        status=MailStatus.failed,
        template="project_invitation_link",
        to_user_id="u-boris",
        attempts=1,
        cause=MailCause.system,
        task="signing_reminders",
        origin="signing_auto_reminder",
        request_id="req-1",
        project_id=PROJECT,
        ref_kind="signing_route",
        ref_id="route-1",
        lang="en",
        params=MailParams(
            values={"actor": "Anna", "project": "Thesis", "role": "editor"},
            link=MailLinkKind.token,
            ttl_s=3600,
            expires_at=NOW + timedelta(days=7),
            note_len=42,
            server="https://studio.example.org",
        ),
    )

    entry_id = await repo.add(entry)
    got = await repo.get(entry_id)

    assert got == replace(entry, id=entry_id)
    assert await repo.get(entry_id + 1000) is None


async def test__add__ids_grow__and_unknown_template_is_kept_as_string(repo: IMailLogRepository) -> None:
    first = await repo.add(make_entry())
    second = await repo.add(make_entry(template="removed_kind"))

    assert second > first
    got = await repo.get(second)
    assert got is not None
    assert (got.template, got.template_known) == ("removed_kind", False)


async def test__page__newest_first_with_cursor(repo: IMailLogRepository) -> None:
    ids = [await repo.add(make_entry(minutes=i)) for i in range(5)]

    first = await repo.page(MailLogQuery(limit=2))
    second = await repo.page(MailLogQuery(limit=2, before_id=first.next_before_id))
    last = await repo.page(MailLogQuery(limit=2, before_id=second.next_before_id))

    assert [e.id for e in first.items] == [ids[4], ids[3]]
    assert [e.id for e in second.items] == [ids[2], ids[1]]
    assert [e.id for e in last.items] == [ids[0]]
    assert (first.next_before_id, last.next_before_id) == (ids[3], None)


async def test__page__exact_page_size__has_no_next(repo: IMailLogRepository) -> None:
    for i in range(2):
        await repo.add(make_entry(minutes=i))

    page = await repo.page(MailLogQuery(limit=2))

    assert (len(page.items), page.next_before_id) == (2, None)


async def test__page__filters_combine_with_and(repo: IMailLogRepository) -> None:
    anna_sent = await repo.add(make_entry("anna@example.org", to_user_id="u-anna", project_id=PROJECT))
    anna_failed = await repo.add(
        make_entry("ANNA@example.org", minutes=1, status=MailStatus.failed, to_user_id="u-anna", project_id=PROJECT)
    )
    boris_failed = await repo.add(make_entry("boris@example.org", minutes=2, status=MailStatus.failed))
    skipped = await repo.add(make_entry("vera@example.org", minutes=3, status=MailStatus.not_sent, template="invite"))
    blocked = await repo.add(make_entry("gleb@example.org", minutes=4, status=MailStatus.suppressed))

    async def ids(**query: object) -> list[int | None]:
        return [e.id for e in (await repo.page(MailLogQuery(**query))).items]  # type: ignore[arg-type]

    assert await ids(statuses=(MailStatus.failed,)) == [boris_failed, anna_failed]
    assert await ids(statuses=(MailStatus.not_sent, MailStatus.suppressed)) == [blocked, skipped]
    assert await ids(templates=("invite",)) == [skipped]
    assert await ids(templates=("invite", "signing_request"), statuses=(MailStatus.sent,)) == [anna_sent]
    assert await ids(reason="email_unverified") == [blocked]
    assert await ids(recipient_id="u-anna") == [anna_failed, anna_sent]
    assert await ids(recipient=" Anna@Example.ORG ") == [anna_failed, anna_sent]
    assert await ids(project_id=PROJECT, statuses=(MailStatus.failed,)) == [anna_failed]
    assert await ids(since=NOW + timedelta(minutes=1), until=NOW + timedelta(minutes=3)) == [boris_failed, anna_failed]
    assert await ids(recipient="nobody@example.org") == []


async def test__page__search_by_address_or_subject_case_insensitive_and_literal(repo: IMailLogRepository) -> None:
    by_address = await repo.add(make_entry("percent_100@example.org", subject="Проверка"))
    by_subject = await repo.add(make_entry("vera@example.org", minutes=1, subject="Сброс ПАРОЛЯ"))
    await repo.add(make_entry("percent-100@example.org", minutes=2, subject="Другое"))

    async def found(q: str) -> list[int | None]:
        return [e.id for e in (await repo.page(MailLogQuery(q=q))).items]

    assert await found("PERCENT_") == [by_address]
    assert await found("пароля") == [by_subject]
    assert await found("%") == []


async def test__page__total_estimate_only_without_filters(repo: IMailLogRepository) -> None:
    await repo.add(make_entry())

    filtered = await repo.page(MailLogQuery(statuses=(MailStatus.sent,)))

    assert filtered.total_estimate is None


async def test__summary__window_counts_and_last_failure(repo: IMailLogRepository) -> None:
    await repo.add(make_entry(minutes=-60 * 25, status=MailStatus.failed, reason="auth"))
    await repo.add(make_entry())
    await repo.add(make_entry(minutes=1))
    await repo.add(make_entry(minutes=2, status=MailStatus.failed, reason="connect"))
    await repo.add(make_entry(minutes=3, status=MailStatus.failed, reason="timeout"))
    await repo.add(make_entry(minutes=4, status=MailStatus.not_sent))
    await repo.add(make_entry(minutes=5, status=MailStatus.suppressed))

    counts = await repo.summary(NOW - timedelta(hours=24))

    assert (counts.sent, counts.failed, counts.not_sent, counts.suppressed) == (2, 2, 1, 1)
    assert (counts.last_failure_at, counts.last_failure_reason) == (NOW + timedelta(minutes=3), "timeout")


async def test__summary__quiet_window__zeros_and_no_failure(repo: IMailLogRepository) -> None:
    await repo.add(make_entry(minutes=-60 * 25, status=MailStatus.failed, reason="auth"))

    counts = await repo.summary(NOW - timedelta(hours=24))

    assert (counts.sent, counts.failed, counts.not_sent, counts.suppressed) == (0, 0, 0, 0)
    assert (counts.last_failure_at, counts.last_failure_reason) == (None, None)
