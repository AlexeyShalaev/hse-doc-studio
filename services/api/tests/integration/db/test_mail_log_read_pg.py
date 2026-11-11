"""Чтение журнала писем на Postgres (docs/design/mail-log.md, 6, срез B6): имена людей и проектов одной выборкой,
use cases из настоящего контейнера."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from dishka import AsyncContainer
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.identity.protocols import IMailLogRepository
from hse_doc_studio.core.mail.journal import MailLogQuery, MailStatus
from hse_doc_studio.core.mail.ports import IMailLogNames, MailPerson
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.di.containers.api import create_container
from hse_doc_studio.use_cases.mail.log import GetMailLogEntryUC, ListMailLogUC, MailLogSummaryUC
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_mail_log_contract import make_entry

pytestmark = pytest.mark.pg

ADMIN = Actor.user("boss", is_instance_admin=True, source=ActorSource.session)


async def _exec(engine: AsyncEngine, sql: str, **params: object) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(sql), params)


async def _user(engine: AsyncEngine, uid: str, name: str) -> None:
    await _exec(
        engine,
        "INSERT INTO users (id, email, email_normalized, name, status, created_at) "
        "VALUES (:i, :e, :en, :n, 'active', now())",
        i=uid,
        e=f"{uid}@Example.org",
        en=f"{uid}@example.org",
        n=name,
    )


async def _project(engine: AsyncEngine, project_id: uuid.UUID, name: str, owner: str, *, trashed: bool = False) -> None:
    await _exec(
        engine,
        "INSERT INTO projects (id, name, owner_user_id, workspace_path, kind, lang, deleted_at) "
        "VALUES (:p, :n, :o, '/x', 'thesis', 'ru', :d)",
        p=project_id,
        n=name,
        o=owner,
        d=datetime.now(UTC) if trashed else None,
    )


@pytest_asyncio.fixture
async def container(pg_migrated_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "host_data_dir", None)
    monkeypatch.setattr(settings.secrets, "key", SecretStr(Fernet.generate_key().decode()))
    c = create_container(StudioMode.server, engine=pg_migrated_engine)
    yield c
    await c.close()


async def test__names__people_and_projects_by_id_in_one_lookup(
    container: AsyncContainer, pg_migrated_engine: AsyncEngine
) -> None:
    await _user(pg_migrated_engine, "anna", "Анна Петрова")
    await _user(pg_migrated_engine, "ivan", "Иван Сидоров")
    live, trashed = uuid.uuid4(), uuid.uuid4()
    await _project(pg_migrated_engine, live, "Курсовая", "anna")
    await _project(pg_migrated_engine, trashed, "В корзине", "anna", trashed=True)
    names = await container.get(IMailLogNames)

    people = await names.people(["anna", "ivan", "gone"])
    projects = await names.projects([str(live), str(trashed), str(uuid.uuid4()), "not-a-uuid"])

    assert people == {
        "anna": MailPerson("anna", "Анна Петрова", "anna@Example.org"),
        "ivan": MailPerson("ivan", "Иван Сидоров", "ivan@Example.org"),
    }
    assert projects == {str(live): "Курсовая", str(trashed): "В корзине"}
    assert await names.people([]) == {}
    assert await names.projects([]) == {}


async def test__use_cases__list_detail_and_summary_from_the_real_container(
    container: AsyncContainer, pg_migrated_engine: AsyncEngine
) -> None:
    await _user(pg_migrated_engine, "anna", "Анна Петрова")
    project = uuid.uuid4()
    await _project(pg_migrated_engine, project, "Курсовая", "anna")
    repo = await container.get(IMailLogRepository)
    now = datetime.now(UTC)
    first = await repo.add(make_entry(at=now - timedelta(hours=30), to_user_id="anna", project_id=str(project)))
    second = await repo.add(
        make_entry(at=now - timedelta(minutes=5), status=MailStatus.failed, actor_user_id="anna", task=None)
    )

    page = await (await container.get(ListMailLogUC)).execute(ADMIN, MailLogQuery(limit=1))
    detail = await (await container.get(GetMailLogEntryUC)).execute(ADMIN, first)
    summary = await (await container.get(MailLogSummaryUC)).execute(ADMIN)

    assert [view.entry.id for view in page.items] == [second]
    assert page.next_before_id == second
    assert page.items[0].actor == MailPerson("anna", "Анна Петрова", "anna@Example.org")
    assert detail is not None
    assert detail.view.to_user == MailPerson("anna", "Анна Петрова", "anna@Example.org")
    assert detail.view.project_name == "Курсовая"
    assert detail.preview is not None
    assert "/sign/p/r" in detail.preview.text
    # Строка старше суток в сводку не входит.
    assert (summary.counts.sent, summary.counts.failed) == (0, 1)
    assert summary.counts.last_failure_reason == "recipient_refused"
    assert summary.retention_days == 90
    assert summary.smtp_configured is False
