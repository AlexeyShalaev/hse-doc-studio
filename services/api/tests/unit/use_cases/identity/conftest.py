from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hse_doc_studio.core.identity.auth_settings import AuthEnvOverrides
from hse_doc_studio.core.identity.entities import MailKind, User, UserStatus
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.identity.session_policy import SessionPolicy
from hse_doc_studio.use_cases.identity.account_email import ConfirmEmailChangeUC, RequestEmailChangeUC
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService, UpdateAuthSettingsUC
from hse_doc_studio.use_cases.identity.change_password import ChangePasswordUC
from hse_doc_studio.use_cases.identity.invites import (
    CreateInviteUC,
    InvitationInfoUC,
    ListInvitesUC,
    RevokeInviteUC,
)
from hse_doc_studio.use_cases.identity.login import LoginUC
from hse_doc_studio.use_cases.identity.mail import LinkDelivery
from hse_doc_studio.use_cases.identity.recovery import (
    ForgotPasswordUC,
    IssueResetLinkUC,
    ResendVerificationUC,
    ResetPasswordUC,
    VerifyEmailUC,
)
from hse_doc_studio.use_cases.identity.register import RegisterUC
from hse_doc_studio.use_cases.identity.sessions import SessionService

from tests.fakes.auth import (
    InMemoryAuditLog,
    InMemoryAuthTokenRepository,
    InMemoryLoginAttemptRepository,
    InMemoryMailOutboxRepository,
    InMemoryRegistrationInviteRepository,
    InMemorySessionRepository,
)
from tests.fakes.identity import (
    InMemoryCredentialRepository,
    InMemoryIdentityStore,
    InMemoryInstanceSettingsRepository,
    InMemoryUserRepository,
)

T0 = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


class FakeHasher:
    """Считает вызовы: по ним проверяется, что неизвестный e-mail стоит столько же, сколько известный."""

    def __init__(self) -> None:
        self.hash_calls = 0
        self.verify_calls = 0
        self.stale_prefix = "v2"

    def hash(self, password: str) -> str:
        self.hash_calls += 1
        return f"{self.stale_prefix}:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        self.verify_calls += 1
        return password_hash == f"{password_hash.split(':', 1)[0]}:{password}"

    def needs_rehash(self, password_hash: str) -> bool:
        return not password_hash.startswith(f"{self.stale_prefix}:")


class FakeUow:
    def __init__(self) -> None:
        self.begins = 0

    @asynccontextmanager
    async def begin(self):  # type: ignore[no-untyped-def]
        self.begins += 1
        yield


class FakeSender:
    def __init__(self, *, enabled: bool = False, fail: bool = False) -> None:
        self._enabled = enabled
        self.fail = fail
        self.sent: list[tuple[str, str, str]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def send(self, to: str, subject: str, body: str) -> None:
        if self.fail:
            raise OSError("smtp down")
        self.sent.append((to, subject, body))


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)


class RecordingDelivery(LinkDelivery):
    """Запоминает ссылки: в outbox их больше нет, а тестам нужны токены."""

    def __init__(self, *args: Any, links: list[str], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._links = links

    async def deliver(self, kind: MailKind, to_email: str, link: str, now: datetime, **kwargs: Any) -> str | None:
        self._links.append(link)
        return await super().deliver(kind, to_email, link, now, **kwargs)


@dataclass
class World:
    clock: Clock
    hasher: FakeHasher
    store: InMemoryIdentityStore
    users: InMemoryUserRepository
    creds: InMemoryCredentialRepository
    sessions: InMemorySessionRepository
    attempts: InMemoryLoginAttemptRepository
    audit: InMemoryAuditLog
    uow: FakeUow
    policy: SessionPolicy
    auth_tokens: InMemoryAuthTokenRepository
    invites: InMemoryRegistrationInviteRepository
    outbox: InMemoryMailOutboxRepository
    settings: InMemoryInstanceSettingsRepository
    sender: FakeSender
    env: AuthEnvOverrides
    links: list[str] = field(default_factory=list)

    def login_uc(self) -> LoginUC:
        return LoginUC(
            self.users, self.creds, self.sessions, self.attempts, self.hasher, self.audit, self.uow,
            self.policy, self.clock,
        )  # fmt: skip

    def service(self) -> SessionService:
        return SessionService(self.sessions, self.users, self.policy, self.clock)

    def settings_service(self) -> AuthSettingsService:
        return AuthSettingsService(self.settings, self.env)

    def delivery(self) -> LinkDelivery:
        return RecordingDelivery(self.sender, self.outbox, links=self.links)

    def register_uc(self) -> RegisterUC:
        return RegisterUC(
            self.users, self.creds, self.auth_tokens, self.invites, self.settings_service(), self.delivery(),
            self.hasher, self.audit, self.uow, public_url="https://studio.test", clock=self.clock,
        )  # fmt: skip

    def verify_uc(self) -> VerifyEmailUC:
        return VerifyEmailUC(self.users, self.auth_tokens, self.audit, self.uow, self.clock)

    def resend_uc(self) -> ResendVerificationUC:
        return ResendVerificationUC(
            self.users, self.auth_tokens, self.delivery(), self.audit, self.uow,
            public_url="https://studio.test", clock=self.clock,
        )  # fmt: skip

    def forgot_uc(self) -> ForgotPasswordUC:
        return ForgotPasswordUC(
            self.users, self.auth_tokens, self.delivery(), self.audit, self.uow,
            public_url="https://studio.test", clock=self.clock,
        )  # fmt: skip

    def reset_uc(self) -> ResetPasswordUC:
        return ResetPasswordUC(
            self.users, self.creds, self.auth_tokens, self.sessions, self.hasher, self.audit, self.uow, self.clock
        )

    def issue_reset_link_uc(self) -> IssueResetLinkUC:
        return IssueResetLinkUC(
            self.users, self.auth_tokens, self.delivery(), self.audit, self.uow,
            public_url="https://studio.test", clock=self.clock,
        )  # fmt: skip

    def request_email_change_uc(self) -> RequestEmailChangeUC:
        return RequestEmailChangeUC(
            self.users, self.creds, self.auth_tokens, self.delivery(), self.hasher, self.audit, self.uow,
            public_url="https://studio.test", clock=self.clock,
        )  # fmt: skip

    def confirm_email_change_uc(self) -> ConfirmEmailChangeUC:
        return ConfirmEmailChangeUC(self.users, self.auth_tokens, self.audit, self.uow, self.clock)

    def update_settings_uc(self) -> UpdateAuthSettingsUC:
        return UpdateAuthSettingsUC(self.settings_service(), self.settings, self.audit, self.uow)

    def create_invite_uc(self) -> CreateInviteUC:
        return CreateInviteUC(
            self.invites, self.delivery(), self.audit, self.uow, public_url="https://studio.test", clock=self.clock
        )

    def list_invites_uc(self) -> ListInvitesUC:
        return ListInvitesUC(self.invites)

    def revoke_invite_uc(self) -> RevokeInviteUC:
        return RevokeInviteUC(self.invites, self.audit)

    def invitation_info_uc(self) -> InvitationInfoUC:
        return InvitationInfoUC(self.invites, self.users, self.clock)

    def change_uc(self) -> ChangePasswordUC:
        return ChangePasswordUC(
            self.users, self.creds, self.sessions, self.hasher, self.audit, self.uow, self.auth_tokens, self.clock
        )

    async def add_user(
        self, email: str = "ann@example.org", password: str = "correct horse battery", *,
        status: UserStatus = UserStatus.active, user_id: str = "u1",
    ) -> User:  # fmt: skip
        user = User(
            id=user_id, email=email, email_normalized=normalize_email(email), name="Ann", status=status,
            created_at=T0, email_verified=True,
        )  # fmt: skip
        await self.users.add(user)
        await self.creds.set_hash(user.id, self.hasher.hash(password))
        return replace(user)


@pytest.fixture
def world() -> World:
    store = InMemoryIdentityStore()
    return World(
        clock=Clock(),
        hasher=FakeHasher(),
        store=store,
        users=InMemoryUserRepository(store),
        creds=InMemoryCredentialRepository(store),
        sessions=InMemorySessionRepository(),
        attempts=InMemoryLoginAttemptRepository(),
        audit=InMemoryAuditLog(),
        uow=FakeUow(),
        policy=SessionPolicy(),
        auth_tokens=InMemoryAuthTokenRepository(),
        invites=InMemoryRegistrationInviteRepository(),
        outbox=InMemoryMailOutboxRepository(),
        settings=InMemoryInstanceSettingsRepository(),
        sender=FakeSender(),
        env=AuthEnvOverrides(),
    )
