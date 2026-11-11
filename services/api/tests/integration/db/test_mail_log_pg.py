"""Журнал писем на Postgres (docs/design/mail-log.md, 5.1, L12, L15): своя транзакция, ограничения, срок хранения."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from dishka import AsyncContainer
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.identity.protocols import IMailLogRepository
from hse_doc_studio.core.mail.journal import MailLogQuery, MailStatus
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.mail_log import SqlMailLogRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.di.containers.api import create_container
from hse_doc_studio.use_cases.lifecycle.engine import LifecycleEngine
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_mail_log_contract import make_entry

pytestmark = pytest.mark.pg


class _RequestFailedError(Exception):
    pass


def _repo(engine: AsyncEngine) -> tuple[SessionProvider, SqlMailLogRepository]:
    sessions = SessionProvider(create_sessionmaker(engine))
    return sessions, SqlMailLogRepository(sessions)


async def _count(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text("SELECT count(*) FROM mail_log"))).scalar_one())


_INSERT = (
    "INSERT INTO mail_log (at, duration_ms, template, lang, to_email, subject, status, cause, origin, params, "
    "template_digest, message_id) VALUES (now() - make_interval(days => :days), 1, 'smtp_test', 'ru', "
    "'a@example.org', 's', :status, :cause, 'smtp_test', '{}', '0123456789abcdef', :mid)"
)


async def _insert(engine: AsyncEngine, *, days: int = 0, status: str = "sent", cause: str = "user") -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(_INSERT),
            {"days": days, "status": status, "cause": cause, "mid": "<m@x>" if status == "sent" else None},
        )


async def _add_in_failed_request(sessions: SessionProvider, repo: SqlMailLogRepository) -> int:
    """Запрос пишет свою строку и строку журнала, затем падает: его транзакция откатывается."""
    entry_id = 0
    with contextlib.suppress(_RequestFailedError):
        async with sessions.begin():
            async with sessions.use() as db:
                await db.execute(text("INSERT INTO instance_meta (key, value) VALUES ('probe', 'x')"))
            entry_id = await repo.add(make_entry())
            raise _RequestFailedError
    return entry_id


async def test__add__inside_rolled_back_ambient__row_survives(pg_migrated_engine: AsyncEngine) -> None:
    sessions, repo = _repo(pg_migrated_engine)

    entry_id = await _add_in_failed_request(sessions, repo)

    async with pg_migrated_engine.connect() as conn:
        meta = (await conn.execute(text("SELECT count(*) FROM instance_meta WHERE key = 'probe'"))).scalar_one()
    assert meta == 0
    assert await repo.get(entry_id) is not None


async def test__own__inside_ambient__uses_a_separate_transaction(pg_migrated_engine: AsyncEngine) -> None:
    sessions, _ = _repo(pg_migrated_engine)

    async with sessions.begin():
        async with sessions.use() as ambient:
            outer = (await ambient.execute(text("SELECT txid_current()"))).scalar_one()
        async with sessions.own() as own:
            inner = (await own.execute(text("SELECT txid_current()"))).scalar_one()

    assert inner != outer


@pytest.mark.parametrize(
    ("status", "cause", "mid"),
    [("sent", "user", None), ("sending", "user", "<m@x>"), ("sent", "robot", "<m@x>")],
    ids=["sent_without_message_id", "unknown_status", "unknown_cause"],
)
async def test__checks__reject_broken_rows(pg_migrated_engine: AsyncEngine, status: str, cause: str, mid: str) -> None:
    with pytest.raises(IntegrityError):
        async with pg_migrated_engine.begin() as conn:
            await conn.execute(text(_INSERT), {"days": 0, "status": status, "cause": cause, "mid": mid})


async def test__page__total_estimate_from_table_statistics(pg_migrated_engine: AsyncEngine) -> None:
    _, repo = _repo(pg_migrated_engine)
    for _ in range(3):
        await repo.add(make_entry())
    async with pg_migrated_engine.begin() as conn:
        await conn.execute(text("ANALYZE mail_log"))

    page = await repo.page(MailLogQuery())

    assert page.total_estimate == 3


async def test__page__recipient_filter_uses_the_lower_email_index(pg_migrated_engine: AsyncEngine) -> None:
    async with pg_migrated_engine.begin() as conn:
        await conn.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in await conn.execute(
                text("EXPLAIN SELECT * FROM mail_log WHERE lower(to_email) = 'a@example.org' ORDER BY id DESC LIMIT 51")
            )
        )
    assert "ix_mail_log_to_email_id" in plan


@pytest_asyncio.fixture
async def container(pg_migrated_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "host_data_dir", None)
    monkeypatch.setattr(settings.secrets, "key", SecretStr(Fernet.generate_key().decode()))
    c = create_container(StudioMode.server, engine=pg_migrated_engine)
    yield c
    await c.close()


async def test__lifecycle__mail_log_source_counts_and_deletes_only_expired(
    container: AsyncContainer, pg_migrated_engine: AsyncEngine
) -> None:
    for days in (200, 120, 91):
        await _insert(pg_migrated_engine, days=days, status="failed")
    await _insert(pg_migrated_engine, days=10)
    engine = await container.get(LifecycleEngine)

    preview = await engine.count_expired("mail_log", cap=100)
    outcome = await engine.run_one("mail_log")

    assert preview.count == 3
    assert preview.cutoff is not None
    assert (outcome.error, outcome.removed) == (None, 3)
    assert await _count(pg_migrated_engine) == 1


async def test__container__provides_the_repository(container: AsyncContainer) -> None:
    repo = await container.get(IMailLogRepository)

    entry_id = await repo.add(make_entry(at=datetime.now(UTC) - timedelta(minutes=1)))
    counts = await repo.summary(datetime.now(UTC) - timedelta(hours=24))

    assert await repo.get(entry_id) is not None
    assert (counts.sent, counts.failed) == (1, 0)
    assert [e.status for e in (await repo.page(MailLogQuery())).items] == [MailStatus.sent]
