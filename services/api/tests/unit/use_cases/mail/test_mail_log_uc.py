"""Use cases журнала писем (docs/design/mail-log.md, 6, срез B6): права, размер страницы, имена, сводка."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.lifecycle.policies import POLICY_BY_KEY
from hse_doc_studio.core.mail.journal import (
    MailCause,
    MailLinkKind,
    MailLogCounts,
    MailLogEntry,
    MailLogPage,
    MailLogQuery,
    MailParams,
    MailStatus,
)
from hse_doc_studio.core.mail.ports import MailPerson
from hse_doc_studio.use_cases.mail.log import (
    SUMMARY_WINDOW,
    GetMailLogEntryUC,
    ListMailLogUC,
    MailLogSummaryUC,
)

from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.mail_log import InMemoryMailLogRepository
from tests.fakes.mail_log_names import InMemoryMailLogNames

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
ADMIN = Actor.user("boss", is_instance_admin=True, source=ActorSource.session)
USER = Actor.user("anna", source=ActorSource.session)
_KEY = POLICY_BY_KEY["mail_log"].setting_key


def _entry(**over: Any) -> MailLogEntry:
    fields: dict[str, Any] = {
        "at": NOW - timedelta(minutes=5),
        "duration_ms": 10,
        "template": "invite",
        "lang": "ru",
        "to_email": "boris@example.org",
        "subject": "Приглашение в Студию",
        "status": MailStatus.not_sent,
        "reason": "smtp_off",
        "cause": MailCause.user,
        "origin": "admin_invite",
        "params": MailParams(link=MailLinkKind.token, ttl_s=3600, note_len=12, server="https://studio.example.org"),
        "template_digest": "0000000000000000",
    }
    fields.update(over)
    return MailLogEntry(**fields)


class _Spy(InMemoryMailLogRepository):
    def __init__(self) -> None:
        super().__init__()
        self.queries: list[MailLogQuery] = []
        self.since: list[datetime] = []

    async def page(self, query: MailLogQuery) -> MailLogPage:
        self.queries.append(query)
        return await super().page(query)

    async def summary(self, since: datetime) -> MailLogCounts:
        self.since.append(since)
        return await super().summary(since)


class _Sender:
    enabled = False


async def test__every_use_case__is_for_the_instance_admin_only() -> None:
    log, names = _Spy(), InMemoryMailLogNames()
    calls = [
        ListMailLogUC(log, names).execute(USER, MailLogQuery()),
        GetMailLogEntryUC(log, names).execute(USER, 1),
        MailLogSummaryUC(log, _Sender(), InMemoryInstanceSettingsRepository()).execute(USER),
    ]
    for call in calls:
        with pytest.raises(IdentityError) as caught:
            await call
        assert caught.value.code is IdentityErrorCode.not_found


@pytest.mark.parametrize(("asked", "used"), [(10_000, 200), (0, 1), (-5, 1), (37, 37)])
async def test__list__bounds_the_page_size_even_without_http(asked: int, used: int) -> None:
    log = _Spy()

    await ListMailLogUC(log, InMemoryMailLogNames()).execute(ADMIN, MailLogQuery(limit=asked))

    assert log.queries[-1].limit == used


async def test__list__names_people_and_projects_and_skips_lookup_without_ids() -> None:
    log, names = _Spy(), InMemoryMailLogNames()
    names.add_person("anna", "Анна Петрова", "anna@example.org")
    names.project_names["5b0c1d2e-3f40-4152-8364-758697a8b9c0"] = "Курсовая"
    await log.add(_entry())
    await log.add(
        _entry(
            to_user_id="anna",
            actor_user_id="gone",
            project_id="5b0c1d2e-3f40-4152-8364-758697a8b9c0",
        )
    )
    await log.add(_entry(project_id="8f1e2d3c-4b5a-4697-a8b9-c0d1e2f3a4b5"))

    page = await ListMailLogUC(log, names).execute(ADMIN, MailLogQuery())

    gone, named, bare = page.items
    assert named.to_user == MailPerson("anna", "Анна Петрова", "anna@example.org")
    assert named.actor is None
    assert named.project_name == "Курсовая"
    assert gone.project_name is None
    assert (bare.to_user, bare.actor, bare.project_name) == (None, None, None)
    assert names.calls == 2

    names.calls = 0
    only_bare = await ListMailLogUC(log, names).execute(ADMIN, MailLogQuery(before_id=2))
    assert len(only_bare.items) == 1
    assert names.calls == 0


async def test__entry__missing_row_is_none_and_flags_follow_the_params() -> None:
    log, names = _Spy(), InMemoryMailLogNames()
    await log.add(_entry())
    uc = GetMailLogEntryUC(log, names)

    detail = await uc.execute(ADMIN, 1)

    assert await uc.execute(ADMIN, 2) is None
    assert detail is not None
    assert detail.link_hidden is True
    assert detail.note_hidden is True
    # Отпечаток из строки не совпадает с текущим шаблоном: письмо перерисовано.
    assert detail.rerendered is True
    assert detail.preview is not None


async def test__summary__window_is_a_day_back_and_mail_is_not_configured() -> None:
    log = _Spy()
    await log.add(_entry(status=MailStatus.failed, reason="auth", at=NOW - timedelta(hours=2)))

    summary = await MailLogSummaryUC(log, _Sender(), InMemoryInstanceSettingsRepository(), clock=lambda: NOW).execute(
        ADMIN
    )

    assert log.since == [NOW - SUMMARY_WINDOW]
    assert summary.smtp_configured is False
    assert summary.counts.failed == 1
    assert summary.counts.last_failure_reason == "auth"
    assert summary.retention_days == 90


@pytest.mark.parametrize(("stored", "days"), [(30, 30), (730, 730), (5, 90), (10_000, 90), ("x", 90)])
async def test__summary__retention_is_the_admin_value_within_bounds(stored: object, days: int) -> None:
    settings = InMemoryInstanceSettingsRepository()
    assert _KEY is not None
    await settings.set(_KEY, stored, source="admin")

    summary = await MailLogSummaryUC(_Spy(), _Sender(), settings, clock=lambda: NOW).execute(ADMIN)

    assert summary.retention_days == days
