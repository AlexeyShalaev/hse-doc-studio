"""Чистые правила трека invites: маска почты, внешние домены, предел выдаваемого, письма, уведомитель."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hse_doc_studio.core.access.entities import Grant, Role
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.identity.entities import User, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.invitations.entities import (
    InvitationStatus,
    MemberTerms,
    NotificationKind,
    NotificationPayload,
    ProjectInvitation,
    mask_email,
    role_at_most,
    stronger,
)
from hse_doc_studio.core.invitations.policy import email_allowed_for_org, external_invites_allowed
from hse_doc_studio.infra.notifications.mailer import render_invitation, render_notification
from hse_doc_studio.use_cases.notifications.notifier import Notifier
from hse_doc_studio.use_cases.projects.invitations import check_persona, check_terms_within

NOW = datetime(2026, 11, 1, 9, tzinfo=UTC)


def test__mask_email() -> None:
    assert mask_email("petr@hse.ru") == "p***@hse.ru"
    assert mask_email(None) is None
    assert mask_email("broken") == "***"


def test__role_order_helpers() -> None:
    assert role_at_most(Role.reader, Role.editor)
    assert not role_at_most(Role.editor, Role.reviewer)
    assert stronger(Role.reader, Role.editor) is Role.editor
    assert stronger(Role.editor, Role.editor) is Role.editor


def test__external_invites__default_true_and_domains() -> None:
    assert external_invites_allowed({})
    assert external_invites_allowed({"sharing": "garbage"})
    assert external_invites_allowed({"sharing": {"external_invites": "no"}})
    closed = {"sharing": {"external_invites": False}, "domains": ["HSE.ru"]}
    assert email_allowed_for_org(closed, "a@hse.ru")
    assert not email_allowed_for_org(closed, "a@gmail.com")
    # Без известных доменов проверка не делается.
    assert email_allowed_for_org({"sharing": {"external_invites": False}}, "a@gmail.com")


def test__effective_status__pending_past_deadline_is_expired() -> None:
    inv = ProjectInvitation(
        id="inv_1",
        project_id=uuid4(),
        invitee_user_id="u",
        invitee_email=None,
        terms=MemberTerms(Role.reader),
        message=None,
        token_hash=None,
        invited_by="o",
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
        status=InvitationStatus.pending,
        last_sent_at=NOW,
    )
    assert inv.effective_status(NOW) is InvitationStatus.pending
    assert inv.effective_status(NOW + timedelta(days=8)) is InvitationStatus.expired


@pytest.mark.parametrize(
    ("grant", "terms", "ok"),
    [
        (Grant(Role.owner), MemberTerms(Role.editor, can_share=True, can_edit_all=True), True),
        (Grant(Role.editor, can_share=True), MemberTerms(Role.editor, can_share=True), True),
        (Grant(Role.editor, can_share=True), MemberTerms(Role.editor, can_edit_all=True), False),
        (Grant(Role.editor, can_share=True, can_edit_all=True), MemberTerms(Role.editor, can_edit_all=True), True),
        (Grant(Role.reviewer, can_share=True), MemberTerms(Role.editor), False),
    ],
)
def test__check_terms_within(grant: Grant, terms: MemberTerms, ok: bool) -> None:
    if ok:
        check_terms_within(terms, grant)
        return
    with pytest.raises(IdentityError) as exc:
        check_terms_within(terms, grant)
    assert exc.value.code is IdentityErrorCode.invitation_role_too_high


def test__check_terms_within__owner_role_is_never_granted() -> None:
    with pytest.raises(IdentityError) as exc:
        check_terms_within(MemberTerms(Role.owner), Grant(Role.owner))
    assert exc.value.code is IdentityErrorCode.input_invalid


class _Personas:
    async def personas(self, project_id: object) -> frozenset[str] | None:
        return frozenset({"ivanov", "supervisor"})


async def test__check_persona() -> None:
    await check_persona(_Personas(), uuid4(), None)
    await check_persona(_Personas(), uuid4(), "ivanov")
    with pytest.raises(IdentityError) as exc:
        await check_persona(_Personas(), uuid4(), "ghost")
    assert exc.value.code is IdentityErrorCode.persona_unknown


def test__mail_texts__ru_and_en_name_the_project_and_link_to_inbox() -> None:
    payload = NotificationPayload(project_name="ВКР", actor_name="Анна", role="reviewer")
    subject, body = render_notification(NotificationKind.project_invitation, payload, Lang.ru, "https://s.ru/")  # type: ignore[misc]
    assert "Анна" in subject
    assert "«Рецензент»" in body
    assert "https://s.ru/inbox" in body
    en = render_notification(NotificationKind.transfer_request, payload, Lang.en, "https://s.ru")
    assert en is not None
    assert "transferring" in en[0]
    assert render_notification(NotificationKind.member_removed, payload, Lang.ru, None) is None
    subject, body = render_invitation(
        project_name="ВКР", inviter_name="Анна", role="editor", link="https://x/project-invite/t", message="Привет",
        lang=Lang.ru,
    )  # fmt: skip
    assert "https://x/project-invite/t" in body
    assert "«Привет»" in body
    assert "Редактор" in body


class _Repo:
    def __init__(self) -> None:
        self.added: list[tuple[str, NotificationKind, str | None]] = []

    async def add(self, user_id: str, kind: NotificationKind, payload: NotificationPayload, **kw: object) -> None:
        self.added.append((user_id, kind, kw.get("dedupe_key")))  # type: ignore[arg-type]


class _Users:
    def __init__(self, verified: bool) -> None:
        self.verified = verified

    async def get(self, user_id: str) -> User:
        return User(
            id=user_id,
            email=f"{user_id}@x.ru",
            email_normalized=f"{user_id}@x.ru",
            name=user_id,
            status=UserStatus.active,
            created_at=NOW,
            email_verified=self.verified,
        )


class _Mailer:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.sent: list[tuple[str, NotificationKind]] = []

    async def send_notification(self, to: str, kind: NotificationKind, payload: object, *, locale: object) -> bool:
        self.sent.append((to, kind))
        return True

    async def send_invitation(self, *a: object, **kw: object) -> bool:
        return True


@pytest.mark.parametrize(
    ("kind", "smtp", "verified", "mailed"),
    [
        (NotificationKind.project_invitation, True, True, True),
        (NotificationKind.access_request, True, True, True),
        (NotificationKind.invitation_accepted, True, True, False),
        (NotificationKind.project_invitation, False, True, False),
        (NotificationKind.project_invitation, True, False, False),
    ],
)
async def test__notifier__writes_always_mails_only_s15_kinds(
    kind: NotificationKind, smtp: bool, verified: bool, mailed: bool
) -> None:
    repo, mailer = _Repo(), _Mailer(smtp)
    notifier = Notifier(repo, _Users(verified), mailer, background=False)  # type: ignore[arg-type]

    await notifier.notify("petr", kind, NotificationPayload(), dedupe_key="k")

    assert repo.added == [("petr", kind, "k")]
    assert bool(mailer.sent) is mailed
