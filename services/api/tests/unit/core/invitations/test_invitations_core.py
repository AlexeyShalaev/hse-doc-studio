"""Чистые правила трека invites: маска почты, внешние домены, предел выдаваемого, письма, уведомитель."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hse_doc_studio.core.access.entities import Grant, Role
from hse_doc_studio.core.background import _current_task
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
from hse_doc_studio.infra.notifications.mailer import SmtpNotificationMailer
from hse_doc_studio.use_cases.mail.dispatch import MailCounters, MailDispatcher
from hse_doc_studio.use_cases.notifications.notifier import Notifier
from hse_doc_studio.use_cases.projects.invitations import check_persona, check_terms_within

from tests.fakes.mail_log import InMemoryMailLogRepository

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


class _Sender:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.sent: list[str] = []

    async def send(self, to: str, subject: str, body: str, *, html: str | None = None) -> str:
        self.sent.append(to)
        return f"<{len(self.sent)}@fake.test>"


def _mailer(sender: _Sender, log: InMemoryMailLogRepository | None = None) -> SmtpNotificationMailer:
    dispatcher = MailDispatcher(sender, log or InMemoryMailLogRepository(), counters=MailCounters())
    return SmtpNotificationMailer(dispatcher, "https://s.ru/")


def test__mail_texts__ru_and_en_name_the_project_and_link_to_inbox() -> None:
    mailer = _mailer(_Sender())
    payload = NotificationPayload(project_name="ВКР", actor_name="Анна", role="reviewer")
    ru = mailer.render_notification("a@x.ru", NotificationKind.project_invitation, payload, locale="ru")
    assert ru is not None
    assert "Анна" in ru.subject
    assert "«Рецензент»" in ru.text
    assert "https://s.ru/inbox" in ru.text
    en = mailer.render_notification("a@x.ru", NotificationKind.transfer_request, payload, locale="en")
    assert en is not None
    assert "transferring" in en.subject
    assert mailer.render_notification("a@x.ru", NotificationKind.member_removed, payload, locale="ru") is None


class _Repo:
    def __init__(self) -> None:
        self.added: list[tuple[str, NotificationKind, str | None]] = []

    async def add(self, user_id: str, kind: NotificationKind, payload: NotificationPayload, **kw: object) -> None:
        self.added.append((user_id, kind, kw.get("dedupe_key")))  # type: ignore[arg-type]


class _Users:
    def __init__(self, verified: bool = True, status: UserStatus = UserStatus.active, *, exists: bool = True) -> None:
        self.verified = verified
        self.status = status
        self.exists = exists

    async def get(self, user_id: str) -> User | None:
        if not self.exists:
            return None
        return User(
            id=user_id,
            email=f"{user_id}@x.ru",
            email_normalized=f"{user_id}@x.ru",
            name=user_id,
            status=self.status,
            created_at=NOW,
            email_verified=self.verified,
        )


# Подписи как у настоящих уведомлений: у приглашения в проект письмо называет роль.
_PAYLOAD = NotificationPayload(project_name="ВКР", actor_name="Анна", role="editor")


class _World:
    def __init__(self, *, smtp: bool = True, users: _Users | None = None) -> None:
        self.repo, self.sender, self.log = _Repo(), _Sender(enabled=smtp), InMemoryMailLogRepository()
        self.notifier = Notifier(self.repo, users or _Users(), _mailer(self.sender, self.log), background=False)  # type: ignore[arg-type]

    @property
    def rows(self) -> list[tuple[str, str | None]]:
        return [(e.status.value, e.reason) for e in self.log.entries]


@pytest.mark.parametrize(
    ("kind", "smtp", "verified", "row"),
    [
        (NotificationKind.project_invitation, True, True, ("sent", None)),
        (NotificationKind.access_request, True, True, ("sent", None)),
        (NotificationKind.invitation_accepted, True, True, None),
        (NotificationKind.project_invitation, False, True, ("not_sent", "smtp_off")),
        (NotificationKind.project_invitation, True, False, ("suppressed", "email_unverified")),
        # Письмо не положено и с почтой: причина не «почта не настроена».
        (NotificationKind.project_invitation, False, False, ("suppressed", "email_unverified")),
        (NotificationKind.signing_request, True, True, ("sent", None)),
        (NotificationKind.signing_reminder, True, True, ("sent", None)),
        (NotificationKind.signing_returned, True, True, ("sent", None)),
        (NotificationKind.signing_completed, True, True, ("sent", None)),
        (NotificationKind.signing_paused, True, True, None),
        (NotificationKind.signing_cancelled, True, True, None),
    ],
)
async def test__notifier__writes_always_mails_only_s15_kinds_and_journals_each_letter(
    kind: NotificationKind, smtp: bool, verified: bool, row: tuple[str, str | None] | None
) -> None:
    w = _World(smtp=smtp, users=_Users(verified))

    await w.notifier.notify("petr", kind, _PAYLOAD, dedupe_key="k")

    assert w.repo.added == [("petr", kind, "k")]
    assert w.rows == ([row] if row else [])
    assert bool(w.sender.sent) is (row == ("sent", None))


@pytest.mark.parametrize(
    ("status", "verified", "reason"),
    [
        (UserStatus.disabled, True, "account_blocked"),
        (UserStatus.disabled, False, "account_blocked"),
        (UserStatus.pending_approval, True, "account_blocked"),
        (UserStatus.pending_verification, False, "email_unverified"),
    ],
)
async def test__notifier__closed_account_is_suppressed(status: UserStatus, verified: bool, reason: str) -> None:
    w = _World(users=_Users(verified, status))

    await w.notifier.notify("petr", NotificationKind.project_invitation, _PAYLOAD)

    assert w.rows == [("suppressed", reason)]
    assert w.sender.sent == []
    [entry] = w.log.entries
    assert (entry.to_email, entry.to_user_id, entry.origin) == ("petr@x.ru", "petr", "notification")


async def test__notifier__gone_user_has_no_address_and_no_row() -> None:
    w = _World(users=_Users(exists=False))

    await w.notifier.notify("petr", NotificationKind.project_invitation, _PAYLOAD)

    assert w.repo.added == [("petr", NotificationKind.project_invitation, None)]
    assert w.log.entries == []


async def test__notifier__mail_false__writes_the_notification_without_a_letter() -> None:
    w = _World()

    await w.notifier.notify("petr", NotificationKind.signing_returned, _PAYLOAD, mail=False)

    assert w.repo.added == [("petr", NotificationKind.signing_returned, None)]
    assert w.sender.sent == []
    assert w.log.entries == []


async def test__notifier__reminder_from_a_background_task_is_an_auto_reminder() -> None:
    w = _World()
    token = _current_task.set("signing_reminders")
    try:
        await w.notifier.notify("petr", NotificationKind.signing_reminder, _PAYLOAD)
        await w.notifier.notify("petr", NotificationKind.signing_request, _PAYLOAD)
    finally:
        _current_task.reset(token)
    await w.notifier.notify("petr", NotificationKind.signing_reminder, _PAYLOAD)

    auto, request, manual = w.log.entries
    assert (auto.origin, auto.cause.value, auto.task) == ("signing_auto_reminder", "system", "signing_reminders")
    assert (request.origin, manual.origin) == ("notification", "notification")
    assert manual.cause.value == "anonymous"


async def test__notifier__background_letter_is_journaled_after_drain() -> None:
    repo, sender, log = _Repo(), _Sender(enabled=False), InMemoryMailLogRepository()
    notifier = Notifier(repo, _Users(), _mailer(sender, log))  # type: ignore[arg-type]

    await notifier.notify("petr", NotificationKind.access_request, _PAYLOAD)
    await notifier.drain()

    assert [(e.status.value, e.reason) for e in log.entries] == [("not_sent", "smtp_off")]
