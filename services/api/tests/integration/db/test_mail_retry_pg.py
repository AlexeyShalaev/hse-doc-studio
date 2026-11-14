"""Повтор писем на Postgres (docs/design/mail-log.md, раздел 14): очередь шифртекстом, аренда, каскад, переживает
новый контейнер, актуальность по объектам и запросы журнала версии 2."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from dishka import AsyncContainer
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.identity.protocols import IMailLogRepository
from hse_doc_studio.core.mail import MailTemplate
from hse_doc_studio.core.mail.journal import (
    RETRY_DELAYS,
    MailFailure,
    MailFailureClass,
    MailLinkKind,
    MailLogQuery,
    MailOrigin,
    MailRefKind,
    MailRequest,
    MailSendError,
    MailStatus,
    ResendBlock,
)
from hse_doc_studio.core.mail.ports import IMailRelevance
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.di.containers.api import create_container
from hse_doc_studio.use_cases.mail.dispatch import RETRY_LEASE, MailCounters, MailDispatcher
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_mail_log_contract import make_entry

pytestmark = pytest.mark.pg

TOKEN = "Tk-retry-secret-0123456789"  # noqa: S105 — известная строка теста
SERVER = "https://studio.example.org"


async def _exec(engine: AsyncEngine, sql: str, **params: object) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(sql), params)


async def _scalar(engine: AsyncEngine, sql: str, **params: object) -> Any:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).scalar_one_or_none()


async def _user(engine: AsyncEngine, uid: str, *, status: str = "active", verified: bool = True) -> None:
    await _exec(
        engine,
        "INSERT INTO users (id, email, email_normalized, name, status, email_verified, created_at) "
        "VALUES (:i, :e, :en, :i, :s, :v, now())",
        i=uid,
        e=f"{uid}@Example.org",
        en=f"{uid}@example.org",
        s=status,
        v=verified,
    )


async def _project(engine: AsyncEngine, owner: str, *, trashed: bool = False) -> uuid.UUID:
    project_id = uuid.uuid4()
    await _exec(
        engine,
        "INSERT INTO projects (id, name, owner_user_id, workspace_path, kind, lang, deleted_at) "
        "VALUES (:p, 'ВКР', :o, '/x', 'thesis', 'ru', :d)",
        p=project_id,
        o=owner,
        d=datetime.now(UTC) if trashed else None,
    )
    return project_id


async def _route(engine: AsyncEngine, project: uuid.UUID, status: str, *, round_: int = 1) -> uuid.UUID:
    route_id = uuid.uuid4()
    await _exec(
        engine,
        "INSERT INTO signing_routes (id, project_id, profile_id, status, round, created_by) "
        "VALUES (:r, :p, :f, :s, :n, 'owner')",
        r=route_id,
        p=project,
        f=f"topic-{route_id.hex[:8]}",
        s=status,
        n=round_,
    )
    return route_id


async def _participant(engine: AsyncEngine, route: uuid.UUID, user: str, *, approved_round: int | None = None) -> None:
    approval = None if approved_round is None else f'{{"round": {approved_round}}}'
    await _exec(
        engine,
        "INSERT INTO signing_route_participants (route_id, id, position, step, persona, user_id, approval) "
        "VALUES (:r, :i, 0, 0, 'supervisor', :u, CAST(:a AS jsonb))",
        r=route,
        i=uuid.uuid4(),
        u=user,
        a=approval,
    )


@pytest_asyncio.fixture
async def container(pg_migrated_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "host_data_dir", None)
    monkeypatch.setattr(settings.secrets, "key", SecretStr(Fernet.generate_key().decode()))
    c = create_container(StudioMode.server, engine=pg_migrated_engine)
    yield c
    await c.close()


class _Sender:
    def __init__(self, *script: Exception | None) -> None:
        self.script = list(script)
        self.enabled = True
        self.sent: list[str] = []

    async def send(self, to: str, subject: str, body: str, *, html: str | None = None) -> str:
        error = self.script.pop(0) if self.script else None
        if error is not None:
            raise error
        self.sent.append(body)
        return f"<{len(self.sent)}@studio.example.org>"


TEMP = MailSendError(MailFailure(reason=MailFailureClass.connect, text="Connection refused"))


def _reset() -> MailRequest:
    return MailRequest(
        template=MailTemplate.reset_password,
        lang=Lang.ru,
        to="anna@example.org",
        server_url=SERVER,
        origin=MailOrigin.forgot_password,
        link_kind=MailLinkKind.token,
        link=f"{SERVER}/reset/{TOKEN}",
        ttl=timedelta(hours=1),
    )


async def test__retry__queue_is_ciphertext_and_survives_a_new_container(
    container: AsyncContainer, pg_migrated_engine: AsyncEngine, tmp_path: Path
) -> None:
    repo = await container.get(IMailLogRepository)
    start = datetime.now(UTC)
    first = MailDispatcher(_Sender(TEMP), repo, counters=MailCounters(), clock=lambda: start)

    outcome = await first.send(_reset())

    entry_id = outcome.entry_id
    assert entry_id is not None
    sealed = await _scalar(pg_migrated_engine, "SELECT request_enc FROM mail_retry WHERE entry_id = :i", i=entry_id)
    assert sealed is not None
    assert TOKEN not in sealed
    assert "reset" not in sealed
    row = await repo.get(entry_id)
    assert row is not None
    assert row.next_attempt_at == start + RETRY_DELAYS[0]
    # Токена нет ни в одной колонке журнала (L3 не меняется).
    async with pg_migrated_engine.connect() as conn:
        dumped = str((await conn.execute(text("SELECT * FROM mail_log"))).all())
    assert TOKEN not in dumped

    # «Перезапуск»: новый контейнер с тем же ключом находит письмо и отправляет его в ту же строку.
    again = create_container(StudioMode.server, engine=pg_migrated_engine)
    try:
        sender = _Sender()
        later = start + RETRY_DELAYS[0]
        second = MailDispatcher(
            sender, await again.get(IMailLogRepository), counters=MailCounters(), clock=lambda: later
        )
        assert await second.retry_due() == 1
    finally:
        await again.close()

    row = await repo.get(entry_id)
    assert row is not None
    assert (row.status, row.attempts, row.next_attempt_at) == (MailStatus.sent, 2, None)
    assert TOKEN in sender.sent[0]
    assert await _scalar(pg_migrated_engine, "SELECT count(*) FROM mail_retry") == 0


async def test__claim__lease_and_skip_locked_hand_out_each_row_once(container: AsyncContainer) -> None:
    repo = await container.get(IMailLogRepository)
    now = datetime.now(UTC)
    dispatcher = MailDispatcher(_Sender(TEMP, TEMP, TEMP), repo, counters=MailCounters(), clock=lambda: now)
    for _ in range(3):
        await dispatcher.send(_reset())
    due = now + RETRY_DELAYS[0]

    batches = await asyncio.gather(*(repo.claim_retries(due, RETRY_LEASE, 2) for _ in range(3)))

    ids = [job.entry_id for batch in batches for job in batch]
    assert sorted(ids) == sorted(set(ids))
    assert len(ids) == 3
    assert all(job.request == _reset() for batch in batches for job in batch)
    assert await repo.claim_retries(due, RETRY_LEASE, 10) == []
    assert len(await repo.claim_retries(due + RETRY_LEASE, RETRY_LEASE, 10)) == 3


async def test__retry__row_deleted_by_retention_takes_the_queue_along(
    container: AsyncContainer, pg_migrated_engine: AsyncEngine
) -> None:
    repo = await container.get(IMailLogRepository)
    now = datetime.now(UTC)
    outcome = await MailDispatcher(_Sender(TEMP), repo, counters=MailCounters(), clock=lambda: now).send(_reset())

    await _exec(pg_migrated_engine, "DELETE FROM mail_log WHERE id = :i", i=outcome.entry_id)

    assert await _scalar(pg_migrated_engine, "SELECT count(*) FROM mail_retry") == 0


async def test__queries__summary_filter_resends_candidates_and_last_attempt(container: AsyncContainer) -> None:
    repo = await container.get(IMailLogRepository)
    now = datetime.now(UTC)
    sent = await repo.add(make_entry(at=now - timedelta(minutes=50)))
    final = await repo.add(make_entry(at=now - timedelta(minutes=40), status=MailStatus.failed))
    waiting = await repo.add(
        make_entry(at=now - timedelta(minutes=30), status=MailStatus.failed, next_attempt_at=now + timedelta(minutes=1))
    )
    off = await repo.add(make_entry(at=now - timedelta(minutes=20), status=MailStatus.not_sent))
    old = await repo.add(make_entry(at=now - timedelta(days=4), status=MailStatus.failed))
    copy = await repo.add(make_entry(at=now - timedelta(minutes=10), resent_from_id=final, to="boris@example.org"))

    counts = await repo.summary(now - timedelta(hours=1))
    assert (counts.sent, counts.failed, counts.retrying, counts.not_sent) == (2, 1, 1, 1)
    assert [e.id for e in (await repo.page(MailLogQuery(retrying=True))).items] == [waiting]
    assert waiting not in [e.id for e in (await repo.page(MailLogQuery(retrying=False))).items]
    assert [e.id for e in await repo.resends_of(final)] == [copy]
    assert await repo.resent_ok([final, sent, off]) == {final}
    candidates = await repo.resend_candidates(MailLogQuery(statuses=(MailStatus.sent,)), now - timedelta(days=3), 10)
    assert [e.id for e in candidates] == [final, off]
    by_address = await repo.resend_candidates(MailLogQuery(recipient="ANNA@example.org"), now - timedelta(days=5), 10)
    assert [e.id for e in by_address] == [final, off, old]
    last = await repo.last_attempt()
    assert last is not None
    assert last.id == copy
    del sent


async def test__relevance__people_projects_and_objects(
    container: AsyncContainer, pg_migrated_engine: AsyncEngine
) -> None:
    relevance = await container.get(IMailRelevance)
    await _user(pg_migrated_engine, "anna")
    await _user(pg_migrated_engine, "blocked", status="disabled")
    await _user(pg_migrated_engine, "unverified", verified=False)
    project = await _project(pg_migrated_engine, "anna")
    trashed = await _project(pg_migrated_engine, "anna", trashed=True)
    active = await _route(pg_migrated_engine, project, "active", round_=2)
    await _participant(pg_migrated_engine, active, "anna", approved_round=1)
    signed = await _route(pg_migrated_engine, project, "active", round_=2)
    await _participant(pg_migrated_engine, signed, "anna", approved_round=2)
    returned = await _route(pg_migrated_engine, project, "returned")
    await _exec(
        pg_migrated_engine,
        "INSERT INTO project_invitations (id, project_id, invitee_user_id, role, can_share, show_sources, "
        "can_edit_all, created_at, expires_at, status, last_sent_at) VALUES "
        "('inv-live', :p, 'anna', 'editor', false, false, false, now(), now() + interval '1 day', 'pending', now()), "
        "('inv-done', :p, 'anna', 'editor', false, false, false, now(), now() + interval '1 day', 'accepted', now())",
        p=project,
    )

    def row(template: MailTemplate, **over: Any) -> Any:
        fields: dict[str, Any] = {
            "status": MailStatus.failed,
            "template": template.value,
            "to": "anna@example.org",
            "to_user_id": "anna",
            "project_id": str(project),
        }
        fields.update(over)
        return make_entry(fields.pop("to"), **fields)

    def route_row(template: MailTemplate, route: uuid.UUID, **over: Any) -> Any:
        return row(template, ref_kind=MailRefKind.signing_route.value, ref_id=str(route), **over)

    cases = [
        (route_row(MailTemplate.signing_reminder, active), None),
        (route_row(MailTemplate.signing_reminder, signed), ResendBlock.route_done),
        (route_row(MailTemplate.signing_returned, returned), None),
        (route_row(MailTemplate.signing_returned, active), ResendBlock.route_done),
        (route_row(MailTemplate.signing_completed, returned), ResendBlock.route_done),
        (route_row(MailTemplate.signing_reminder, uuid.uuid4()), ResendBlock.object_gone),
        (row(MailTemplate.project_invitation, ref_kind="project_invitation", ref_id="inv-live"), None),
        (
            row(MailTemplate.project_invitation, ref_kind="project_invitation", ref_id="inv-done"),
            ResendBlock.invitation_done,
        ),
        (row(MailTemplate.checkpoint_due, project_id=str(trashed)), ResendBlock.project_gone),
        (row(MailTemplate.checkpoint_due, to_user_id="gone"), ResendBlock.recipient_gone),
        (row(MailTemplate.checkpoint_due, to="anna.old@example.org"), ResendBlock.recipient_changed),
        (
            row(MailTemplate.checkpoint_due, to="blocked@example.org", to_user_id="blocked"),
            ResendBlock.recipient_blocked,
        ),
        (
            row(MailTemplate.checkpoint_due, to="unverified@example.org", to_user_id="unverified"),
            ResendBlock.recipient_blocked,
        ),
        # Уведомления об аккаунте уходят и на неподтверждённый адрес.
        (
            row(MailTemplate.passkey_added, to="unverified@example.org", to_user_id="unverified", project_id=None),
            None,
        ),
    ]

    found = [await relevance.check(entry) for entry, _ in cases]

    assert found == [expected for _, expected in cases]
