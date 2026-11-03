"""Провайдер DI входа по passkey (серверный режим): репозиторий ключей, WebAuthn и сценарии."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.core.identity.passkeys import IPasskeyRepository, IWebAuthn
from hse_doc_studio.core.identity.protocols import (
    IAuditLog,
    IAuthTokenRepository,
    ICredentialRepository,
    ILoginAttemptRepository,
    IPasswordHasher,
    ISessionRepository,
    IUserRepository,
)
from hse_doc_studio.core.identity.session_policy import SessionPolicy
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.passkeys import SqlPasskeyRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.identity.webauthn import PyWebAuthn
from hse_doc_studio.use_cases.admin.passkeys import ListUserPasskeysUC, ResetUserPasskeysUC
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService
from hse_doc_studio.use_cases.identity.passkey_ceremony import PasskeyChallenges, PasskeyPolicy
from hse_doc_studio.use_cases.identity.passkey_login import AssertionChecker, FinishPasskeyLoginUC, StartPasskeyLoginUC
from hse_doc_studio.use_cases.identity.passkeys import (
    DeletePasskeyUC,
    FinishPasskeyRegistrationUC,
    ListPasskeysUC,
    LoginMethods,
    RenamePasskeyUC,
    StartPasskeyRegistrationUC,
)
from hse_doc_studio.use_cases.identity.reauth import ReauthUC, StartReauthUC


class ServerPasskeyProvider(Provider):
    scope = Scope.APP

    @provide
    def get_passkey_repository(self, sessions: SessionProvider) -> IPasskeyRepository:
        return SqlPasskeyRepository(sessions)

    @provide
    def get_webauthn(self) -> IWebAuthn:
        return PyWebAuthn()

    @provide
    def get_challenges(self, tokens: IAuthTokenRepository) -> PasskeyChallenges:
        return PasskeyChallenges(tokens)

    @provide
    def get_policy(self, settings: AuthSettingsService) -> PasskeyPolicy:
        return PasskeyPolicy(settings)

    @provide
    def get_login_methods(
        self,
        users: IUserRepository,
        credentials: ICredentialRepository,
        passkeys: IPasskeyRepository,
        settings: AuthSettingsService,
    ) -> LoginMethods:
        return LoginMethods(users, credentials, passkeys, settings)

    @provide
    def get_checker(
        self, passkeys: IPasskeyRepository, challenges: PasskeyChallenges, webauthn: IWebAuthn
    ) -> AssertionChecker:
        return AssertionChecker(passkeys, challenges, webauthn)

    @provide
    def get_list_uc(self, passkeys: IPasskeyRepository, methods: LoginMethods, policy: PasskeyPolicy) -> ListPasskeysUC:
        return ListPasskeysUC(passkeys, methods, policy)

    @provide
    def get_start_registration_uc(
        self,
        users: IUserRepository,
        passkeys: IPasskeyRepository,
        sessions: ISessionRepository,
        challenges: PasskeyChallenges,
        policy: PasskeyPolicy,
        webauthn: IWebAuthn,
    ) -> StartPasskeyRegistrationUC:
        return StartPasskeyRegistrationUC(users, passkeys, sessions, challenges, policy, webauthn)

    @provide
    def get_finish_registration_uc(
        self,
        users: IUserRepository,
        passkeys: IPasskeyRepository,
        challenges: PasskeyChallenges,
        policy: PasskeyPolicy,
        webauthn: IWebAuthn,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> FinishPasskeyRegistrationUC:
        return FinishPasskeyRegistrationUC(users, passkeys, challenges, policy, webauthn, audit, uow)

    @provide
    def get_rename_uc(self, passkeys: IPasskeyRepository, audit: IAuditLog) -> RenamePasskeyUC:
        return RenamePasskeyUC(passkeys, audit)

    @provide
    def get_delete_uc(
        self,
        users: IUserRepository,
        passkeys: IPasskeyRepository,
        sessions: ISessionRepository,
        methods: LoginMethods,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> DeletePasskeyUC:
        return DeletePasskeyUC(users, passkeys, sessions, methods, audit, uow)

    @provide
    def get_start_login_uc(
        self, challenges: PasskeyChallenges, policy: PasskeyPolicy, webauthn: IWebAuthn
    ) -> StartPasskeyLoginUC:
        return StartPasskeyLoginUC(challenges, policy, webauthn)

    @provide
    def get_finish_login_uc(
        self,
        users: IUserRepository,
        passkeys: IPasskeyRepository,
        sessions: ISessionRepository,
        checker: AssertionChecker,
        policy: PasskeyPolicy,
        audit: IAuditLog,
        uow: IUnitOfWork,
        session_policy: SessionPolicy,
    ) -> FinishPasskeyLoginUC:
        return FinishPasskeyLoginUC(users, passkeys, sessions, checker, policy, audit, uow, session_policy)

    @provide
    def get_start_reauth_uc(
        self, passkeys: IPasskeyRepository, challenges: PasskeyChallenges, policy: PasskeyPolicy, webauthn: IWebAuthn
    ) -> StartReauthUC:
        return StartReauthUC(passkeys, challenges, policy, webauthn)

    @provide
    def get_reauth_uc(
        self,
        sessions: ISessionRepository,
        credentials: ICredentialRepository,
        hasher: IPasswordHasher,
        attempts: ILoginAttemptRepository,
        passkeys: IPasskeyRepository,
        checker: AssertionChecker,
        policy: PasskeyPolicy,
        settings: AuthSettingsService,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> ReauthUC:
        return ReauthUC(sessions, credentials, hasher, attempts, passkeys, checker, policy, settings, audit, uow)

    @provide
    def get_list_user_passkeys_uc(self, users: IUserRepository, passkeys: IPasskeyRepository) -> ListUserPasskeysUC:
        return ListUserPasskeysUC(users, passkeys)

    @provide
    def get_reset_user_passkeys_uc(
        self, users: IUserRepository, passkeys: IPasskeyRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> ResetUserPasskeysUC:
        return ResetUserPasskeysUC(users, passkeys, audit, uow)
