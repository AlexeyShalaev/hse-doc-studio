"""admin_list_mail_log: фильтры ложатся в `MailLogQuery`, ответ только сведения строки (mail-log.md, 6.4)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import EditFormat
from hse_doc_studio.core.identity.errors import IdentityError
from hse_doc_studio.core.mail.journal import (
    MailCause,
    MailLinkKind,
    MailLogEntry,
    MailLogPage,
    MailLogQuery,
    MailParams,
    MailStatus,
)
from hse_doc_studio.use_cases.mail.log import ListMailLogUC
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError
from hse_doc_studio.use_cases.mcp.tools.admin import MAIL_LOG_LIMIT, AdminListMailLogTool

from tests.fakes.mail_log import InMemoryMailLogRepository
from tests.fakes.mail_log_names import InMemoryMailLogNames

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
ADMIN = Actor.user("boss", is_instance_admin=True, source=ActorSource.pat)
PROJECT_ID = str(uuid4())
_ROW_KEYS = {
    "id",
    "at",
    "template",
    "to",
    "to_user_id",
    "subject",
    "status",
    "reason",
    "smtp_code",
    "cause",
    "actor_id",
    "project_id",
}


def _entry(**over: Any) -> MailLogEntry:
    fields: dict[str, Any] = {
        "at": NOW - timedelta(minutes=5),
        "duration_ms": 10,
        "template": "invite",
        "lang": "ru",
        "to_email": "Anna@Example.org",
        "subject": "Приглашение в Студию",
        "status": MailStatus.failed,
        "reason": "recipient_refused",
        "smtp_code": 550,
        "error_text": "550 mailbox unavailable",
        "cause": MailCause.user,
        "origin": "admin_invite",
        "params": MailParams(link=MailLinkKind.token, ttl_s=3600, note_len=12, server="https://studio.example.org"),
        "template_digest": "0000000000000000",
        "to_user_id": "anna",
        "actor_user_id": "boss",
        "project_id": PROJECT_ID,
        "message_id": None,
    }
    fields.update(over)
    return MailLogEntry(**fields)


class _Spy(InMemoryMailLogRepository):
    def __init__(self) -> None:
        super().__init__()
        self.queries: list[MailLogQuery] = []

    async def page(self, query: MailLogQuery) -> MailLogPage:
        self.queries.append(query)
        return await super().page(query)


class _Deps:
    def __init__(self, uc: ListMailLogUC) -> None:
        self._uc = uc

    async def get(self, dependency_type: Any, component: str | None = None) -> Any:
        assert dependency_type is ListMailLogUC
        return self._uc


@pytest.fixture(autouse=True)
def _admin() -> Iterator[None]:
    set_current_actor(ADMIN)
    yield
    set_current_actor(None)


def _setup(*entries: MailLogEntry) -> tuple[AdminListMailLogTool, _Spy]:
    log, names = _Spy(), InMemoryMailLogNames()
    names.add_person("anna", "Анна", "anna@example.org")
    names.add_person("boss", "Админ", "boss@example.org")
    names.project_names[PROJECT_ID] = "ВКР Анны"
    log.entries.extend(replace(entry, id=i) for i, entry in enumerate(entries, start=1))
    return AdminListMailLogTool(_Deps(ListMailLogUC(log, names))), log  # type: ignore[arg-type]


def _ctx() -> AgentToolContext:
    return AgentToolContext(project_id=uuid4(), model="mcp-client", edit_format=EditFormat.search_replace)


async def _rows(tool: AdminListMailLogTool, args: dict[str, object]) -> list[dict[str, Any]]:
    result = await tool.handle(_ctx(), args)
    assert result.is_error is False, result.text
    rows: list[dict[str, Any]] = json.loads(result.text)
    return rows


async def test__handle__row__only_compact_fields_without_names_links_or_error_text() -> None:
    tool, _ = _setup(_entry())

    (row,) = await _rows(tool, {})

    assert set(row) == _ROW_KEYS
    assert row == {
        "id": 1,
        "at": (NOW - timedelta(minutes=5)).isoformat(),
        "template": "invite",
        "to": "Anna@Example.org",
        "to_user_id": "anna",
        "subject": "Приглашение в Студию",
        "status": "failed",
        "reason": "recipient_refused",
        "smtp_code": 550,
        "cause": "user",
        "actor_id": "boss",
        "project_id": PROJECT_ID,
    }
    text = json.dumps(row, ensure_ascii=False)
    assert "Анна" not in text
    assert "ВКР" not in text
    assert "mailbox unavailable" not in text
    assert "studio.example.org" not in text


async def test__handle__filters__go_into_the_query() -> None:
    tool, log = _setup()

    await _rows(
        tool,
        {
            "recipient": "  ANNA@example.org ",
            "template": "invite",
            "status": "failed",
            "since": "2026-11-10T09:00:00+03:00",
            "limit": 5,
        },
    )

    (query,) = log.queries
    assert query.recipient == "ANNA@example.org"
    assert query.templates == ("invite",)
    assert query.statuses == (MailStatus.failed,)
    assert query.since == datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
    assert query.limit == 5
    assert query.before_id is None


async def test__handle__recipient__exact_match_ignoring_case() -> None:
    tool, _ = _setup(
        _entry(to_email="anna@example.org"),
        _entry(to_email="anna@example.org.evil"),
        _entry(to_email="boris@example.org"),
    )

    rows = await _rows(tool, {"recipient": "ANNA@EXAMPLE.ORG"})

    assert [r["to"] for r in rows] == ["anna@example.org"]


async def test__handle__since__naive_is_utc_and_date_alone_is_midnight() -> None:
    tool, log = _setup()

    await _rows(tool, {"since": "2026-11-10T09:00"})
    await _rows(tool, {"since": "2026-11-10"})

    assert [q.since for q in log.queries] == [
        datetime(2026, 11, 10, 9, 0, tzinfo=UTC),
        datetime(2026, 11, 10, 0, 0, tzinfo=UTC),
    ]


async def test__handle__since__keeps_newer_rows_only() -> None:
    tool, _ = _setup(_entry(at=NOW - timedelta(days=2), subject="старое"), _entry(at=NOW, subject="новое"))

    rows = await _rows(tool, {"since": (NOW - timedelta(days=1)).isoformat()})

    assert [r["subject"] for r in rows] == ["новое"]


@pytest.mark.parametrize(("raw", "expected"), [(None, 20), (500, MAIL_LOG_LIMIT), (0, 1), ("7", 7)])
async def test__handle__limit__default_and_capped_at_50(raw: object, expected: int) -> None:
    tool, log = _setup()

    await _rows(tool, {} if raw is None else {"limit": raw})

    assert log.queries[0].limit == expected


async def test__handle__newest_first() -> None:
    tool, _ = _setup(_entry(subject="первое"), _entry(subject="второе"))

    rows = await _rows(tool, {})

    assert [r["subject"] for r in rows] == ["второе", "первое"]


@pytest.mark.parametrize(
    "args",
    [
        {"status": "delivered"},
        {"template": "Invite!"},
        {"since": "вчера"},
        {"recipient": "a" * 321},
    ],
)
async def test__handle__bad_arguments__rejected(args: dict[str, object]) -> None:
    tool, log = _setup()

    with pytest.raises(ArgumentError):
        await tool.handle(_ctx(), args)
    assert not log.queries


async def test__handle__not_an_admin__refused_by_the_use_case() -> None:
    tool, log = _setup(_entry())
    set_current_actor(Actor.user("anna", source=ActorSource.pat))

    with pytest.raises(IdentityError):
        await tool.handle(_ctx(), {})
    assert not log.queries
