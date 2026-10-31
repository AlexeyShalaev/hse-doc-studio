"""Хранилища трека invites на настоящей Postgres: ограничения, уведомления, гонки принятия и одобрения."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.invitations.entities import (
    InvitationStatus,
    MemberTerms,
    NotificationKind,
    NotificationPayload,
    ProjectInvitation,
)
from hse_doc_studio.core.listing import Window
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.invitations import AccessRequestRow, ProjectTransferRow
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.repositories.notifications import PostgresNotificationRepository
from hse_doc_studio.infra.db.repositories.project_cards import PostgresProjectCards
from hse_doc_studio.infra.db.repositories.project_invitations import PostgresProjectInvitationRepository
from hse_doc_studio.infra.db.repositories.project_members import PostgresProjectMemberRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.db.uow import SqlUnitOfWork
from hse_doc_studio.use_cases.projects.invitations import AcceptInvitationUC
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

NOW = datetime.now(UTC)


async def _seed(sessions: SessionProvider, *user_ids: str) -> UUID:
    project_id = uuid4()
    async with sessions.use() as db:
        for uid in user_ids:
            db.add(
                UserRow(
                    id=uid,
                    email=f"{uid}@x.org",
                    email_normalized=f"{uid}@x.org",
                    name=uid,
                    status="active",
                    email_verified=True,
                    created_at=NOW,
                )
            )
        await db.flush()
        db.add(
            ProjectRow(
                id=project_id, name="ВКР", owner_user_id=user_ids[0], workspace_path="p", kind="thesis", lang="ru"
            )
        )
        await db.flush()
    return project_id


def _invitation(project_id: UUID, user_id: str | None, email: str | None = None) -> ProjectInvitation:
    return ProjectInvitation(
        id=f"inv_{uuid4().hex}",
        project_id=project_id,
        invitee_user_id=user_id,
        invitee_email=email,
        terms=MemberTerms(Role.reviewer),
        message=None,
        token_hash=None,
        invited_by=None,
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
        status=InvitationStatus.pending,
        last_sent_at=NOW,
    )


@pytest.fixture
def sessions(pg_migrated_engine: AsyncEngine) -> SessionProvider:
    return SessionProvider(create_sessionmaker(pg_migrated_engine))


async def test__constraints__one_pending_per_person_and_checks(sessions: SessionProvider) -> None:
    project = await _seed(sessions, "anna", "petr")
    repo = PostgresProjectInvitationRepository(sessions)
    await repo.add(_invitation(project, "petr"))
    with pytest.raises(IntegrityError):
        await repo.add(_invitation(project, "petr"))
    with pytest.raises(IntegrityError):
        await repo.add(_invitation(project, None, None))
    async with sessions.use() as db:
        db.add(AccessRequestRow(id="arq_1", project_id=project, user_id="petr", status="approved", created_at=NOW))
        with pytest.raises(IntegrityError):
            await db.flush()


async def test__constraints__one_pending_transfer(sessions: SessionProvider) -> None:
    project = await _seed(sessions, "anna", "vera")

    def _row(tid: str) -> ProjectTransferRow:
        return ProjectTransferRow(
            id=tid, project_id=project, from_kind="user", from_id="anna", to_kind="user", to_id="vera",
            status="pending", created_at=NOW, expires_at=NOW + timedelta(days=7),
        )  # fmt: skip

    async with sessions.use() as db:
        db.add(_row("trf_1"))
        await db.flush()

    async def _second() -> None:
        async with sessions.use() as db:
            db.add(_row("trf_2"))
            await db.flush()

    with pytest.raises(IntegrityError):
        await _second()


async def test__attach_email__binds_pending_and_lists_for_user(sessions: SessionProvider) -> None:
    project = await _seed(sessions, "anna", "petr")
    repo = PostgresProjectInvitationRepository(sessions)
    await repo.add(_invitation(project, None, "petr@x.org"))

    attached = await repo.attach_email("petr@x.org", "petr")

    assert [a.invitee_user_id for a in attached] == ["petr"]
    assert await repo.attach_email("petr@x.org", "petr") == []
    mine = await repo.list_for_user("petr")
    assert [(m.project_name, m.owner_name) for m in mine] == [("ВКР", "anna")]
    assert await repo.count_pending_for_user("petr", NOW) == 1


async def test__notifications__dedupe_mark_read_purge(sessions: SessionProvider) -> None:
    await _seed(sessions, "anna")
    repo = PostgresNotificationRepository(sessions)
    payload = NotificationPayload(project_name="ВКР", ref_id="inv_1")
    await repo.add("anna", NotificationKind.project_invitation, payload, dedupe_key="inv:1", now=NOW)
    await repo.add("anna", NotificationKind.project_invitation, payload, dedupe_key="inv:1", now=NOW)
    await repo.add("anna", NotificationKind.member_removed, payload, now=NOW - timedelta(days=100))

    assert await repo.unread_count("anna") == 2
    page = await repo.page("anna", unread_only=False, window=Window(10, 0))
    assert [n.kind for n in page.items] == [NotificationKind.project_invitation, NotificationKind.member_removed]
    assert page.items[0].payload.project_name == "ВКР"
    assert await repo.mark_read("anna", [page.items[0].id, "ntf_foreign"], NOW) == 1
    assert await repo.unread_count("anna") == 1
    assert await repo.mark_read("anna", None, NOW) == 1
    assert await repo.purge(NOW - timedelta(days=90)) == 1
    assert (await repo.page("anna", unread_only=False, window=Window(10, 0))).total == 1


class _Audit:
    async def record(self, *a: object, **kw: object) -> None:
        return None


class _Notifier:
    async def notify(self, *a: object, **kw: object) -> None:
        return None


class _Users:
    async def get(self, user_id: str) -> None:
        return None


async def test__race__two_accepts_of_one_invitation__one_wins(pg_migrated_engine: AsyncEngine) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    project = await _seed(sessions, "anna", "petr")
    repo = PostgresProjectInvitationRepository(sessions)
    invitation = _invitation(project, "petr")
    await repo.add(invitation)
    members = PostgresProjectMemberRepository(sessions)
    uc = AcceptInvitationUC(
        repo, PostgresProjectCards(sessions), _Users(), _Audit(), SqlUnitOfWork(sessions),  # type: ignore[arg-type]
        members=members, member_roles=members, notifier=_Notifier(),
    )  # fmt: skip

    results = await asyncio.gather(
        *(uc.execute(Actor.user("petr", "Пётр"), invitation.id) for _ in range(2)), return_exceptions=True
    )

    errors = [r for r in results if isinstance(r, Exception)]
    assert len(errors) == 1
    assert isinstance(errors[0], IdentityError)
    assert errors[0].code is IdentityErrorCode.invitation_not_pending
    assert await members.direct_user_role(project, "petr") is Role.reviewer
    async with sessions.use() as db:
        rows = (await db.execute(ProjectMemberRow.__table__.select())).all()
    assert len([r for r in rows if r.principal_id == "petr"]) == 1
