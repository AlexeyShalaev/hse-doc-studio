"""Сборка сценариев passkey поверх фикстуры `world`: настоящий py_webauthn и программный аутентификатор."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import timedelta

from hse_doc_studio.core.identity.entities import Session, User
from hse_doc_studio.core.identity.normalize import hash_token, new_token
from hse_doc_studio.core.identity.passkeys import Passkey, RelyingParty
from hse_doc_studio.infra.identity.webauthn import PyWebAuthn
from hse_doc_studio.use_cases.admin.passkeys import ListUserPasskeysUC, ResetUserPasskeysUC
from hse_doc_studio.use_cases.identity.passkey_ceremony import PasskeyChallenges, PasskeyPolicy
from hse_doc_studio.use_cases.identity.passkey_login import AssertionChecker, FinishPasskeyLoginUC, StartPasskeyLoginUC
from hse_doc_studio.use_cases.identity.passkey_signup import FinishPasskeySignupUC, StartPasskeySignupUC
from hse_doc_studio.use_cases.identity.passkeys import (
    DeletePasskeyUC,
    FinishPasskeyRegistrationUC,
    ListPasskeysUC,
    LoginMethods,
    RenamePasskeyUC,
    StartPasskeyRegistrationUC,
)
from hse_doc_studio.use_cases.identity.reauth import ReauthUC, StartReauthUC

from tests.fakes.authenticator import Json, SoftAuthenticator
from tests.fakes.passkeys import InMemoryPasskeyRepository

from .conftest import World

PARTY = RelyingParty(id="studio.test", name="HSE Doc Studio", origin="https://studio.test")


@dataclass
class PasskeyKit:
    world: World
    passkeys: InMemoryPasskeyRepository = field(default_factory=InMemoryPasskeyRepository)
    webauthn: PyWebAuthn = field(default_factory=PyWebAuthn)
    phone: SoftAuthenticator = field(default_factory=SoftAuthenticator)

    @property
    def challenges(self) -> PasskeyChallenges:
        return PasskeyChallenges(self.world.auth_tokens, self.world.clock)

    @property
    def policy(self) -> PasskeyPolicy:
        return PasskeyPolicy(self.world.settings_service())

    @property
    def methods(self) -> LoginMethods:
        w = self.world
        return LoginMethods(w.users, w.creds, self.passkeys, w.settings_service())

    @property
    def checker(self) -> AssertionChecker:
        return AssertionChecker(self.passkeys, self.challenges, self.webauthn)

    def start_registration(self) -> StartPasskeyRegistrationUC:
        w = self.world
        return StartPasskeyRegistrationUC(
            w.users, self.passkeys, w.sessions, self.challenges, self.policy, self.webauthn, w.clock
        )

    def finish_registration(self) -> FinishPasskeyRegistrationUC:
        w = self.world
        return FinishPasskeyRegistrationUC(
            w.users, self.passkeys, self.challenges, self.policy, self.webauthn, w.audit, w.uow, w.clock,
            delivery=w.delivery(),
        )  # fmt: skip

    def start_signup(self) -> StartPasskeySignupUC:
        w = self.world
        return StartPasskeySignupUC(w.invites, w.users, self.challenges, self.policy, self.webauthn, w.clock)

    def finish_signup(self) -> FinishPasskeySignupUC:
        w = self.world
        return FinishPasskeySignupUC(
            w.invites, w.users, self.passkeys, w.sessions, self.challenges, self.policy, self.webauthn,
            w.audit, w.uow, w.policy, w.clock,
        )  # fmt: skip

    def list_uc(self) -> ListPasskeysUC:
        return ListPasskeysUC(self.passkeys, self.methods, self.policy)

    def rename_uc(self) -> RenamePasskeyUC:
        return RenamePasskeyUC(self.passkeys, self.world.audit)

    def delete_uc(self) -> DeletePasskeyUC:
        w = self.world
        return DeletePasskeyUC(w.users, self.passkeys, w.sessions, self.methods, w.audit, w.uow, w.clock)

    def start_login(self) -> StartPasskeyLoginUC:
        return StartPasskeyLoginUC(self.challenges, self.policy, self.webauthn)

    def finish_login(self) -> FinishPasskeyLoginUC:
        w = self.world
        return FinishPasskeyLoginUC(
            w.users, self.passkeys, w.sessions, self.checker, self.policy, w.audit, w.uow, w.policy, w.clock
        )

    def start_reauth(self) -> StartReauthUC:
        return StartReauthUC(self.passkeys, self.challenges, self.policy, self.webauthn)

    def reauth_uc(self) -> ReauthUC:
        w = self.world
        return ReauthUC(
            w.sessions, w.creds, w.hasher, w.attempts, self.passkeys, self.checker, self.policy,
            w.settings_service(), w.audit, w.uow, w.clock,
        )  # fmt: skip

    def list_admin_uc(self) -> ListUserPasskeysUC:
        return ListUserPasskeysUC(self.world.users, self.passkeys)

    def reset_admin_uc(self) -> ResetUserPasskeysUC:
        w = self.world
        return ResetUserPasskeysUC(w.users, self.passkeys, w.audit, w.uow, delivery=w.delivery())

    async def session(self, user: User, *, minutes_ago: int = 0) -> str:
        """Сессия человека, открытая `minutes_ago` минут назад; возвращает хеш её id."""
        now = self.world.clock.now
        opened = now - timedelta(minutes=minutes_ago)
        session = Session(
            id_hash=hash_token(new_token()),
            user_id=user.id,
            csrf_token="csrf",
            created_at=opened,
            last_seen_at=opened,
            expires_at=now + timedelta(days=1),
        )
        await self.world.sessions.add(session)
        return session.id_hash

    async def register(self, user: User, *, name: str | None = None, phone: SoftAuthenticator | None = None) -> Passkey:
        session = await self.session(user)
        options = await self.start_registration().execute(user.id, session, PARTY)
        response = (phone or self.phone).create(options)
        return await self.finish_registration().execute(user.id, PARTY, response, name=name)

    async def login_response(self, **kw: object) -> Json:
        options = await self.start_login().execute(PARTY)
        return self.phone.get(options, **kw)  # type: ignore[arg-type]

    async def without_password(self, user: User) -> User:
        self.world.store.hashes.pop(user.id, None)
        return replace(user)
