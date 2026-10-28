"""Провайдер identity серверного режима.

Срезы identity регистрируют здесь репозитории пользователей и сессий, цепочку резолверов
актора, почтовик и ограничитель. Подключается лениво, только из ``create_container(server)``.
"""

from __future__ import annotations

from datetime import timedelta

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.identity.auth_settings import AuthEnvOverrides
from hse_doc_studio.core.identity.protocols import (
    IActorResolver,
    IAuditLog,
    IAuthTokenRepository,
    ICredentialRepository,
    IInstanceSettingsRepository,
    ILoginAttemptRepository,
    IMailOutboxRepository,
    IMailSender,
    IPasswordHasher,
    IRegistrationInviteRepository,
    ISessionRepository,
    IUserRepository,
)
from hse_doc_studio.core.identity.session_policy import SessionPolicy
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.auth import (
    SqlAuditLog,
    SqlAuthTokenRepository,
    SqlLoginAttemptRepository,
    SqlMailOutboxRepository,
    SqlRegistrationInviteRepository,
    SqlSessionRepository,
)
from hse_doc_studio.infra.db.repositories.identity import (
    SqlCredentialRepository,
    SqlInstanceSettingsRepository,
    SqlUserRepository,
)
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.identity.argon2_hasher import Argon2PasswordHasher
from hse_doc_studio.infra.identity.mail import LinkOnlyMailSender
from hse_doc_studio.infra.identity.resolvers import BearerActorResolver, ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService, UpdateAuthSettingsUC
from hse_doc_studio.use_cases.identity.bootstrap import BootstrapUC
from hse_doc_studio.use_cases.identity.invites import CreateInviteUC, InvitationInfoUC, ListInvitesUC, RevokeInviteUC
from hse_doc_studio.use_cases.identity.login import LoginUC
from hse_doc_studio.use_cases.identity.mail import LinkDelivery
from hse_doc_studio.use_cases.identity.register import RegisterUC
from hse_doc_studio.use_cases.identity.sessions import (
    ListSessionsUC,
    LogoutUC,
    RevokeOtherSessionsUC,
    RevokeSessionUC,
    SessionService,
)


class ServerIdentityProvider(Provider):
    scope = Scope.APP

    @provide
    def get_user_repository(self, sessions: SessionProvider) -> IUserRepository:
        return SqlUserRepository(sessions)

    @provide
    def get_session_repository(self, sessions: SessionProvider) -> ISessionRepository:
        return SqlSessionRepository(sessions)

    @provide
    def get_session_policy(self) -> SessionPolicy:
        return SessionPolicy(
            idle=timedelta(days=settings.auth.session_idle_days),
            absolute=timedelta(days=settings.auth.session_absolute_days),
        )

    @provide
    def get_session_service(
        self, sessions: ISessionRepository, users: IUserRepository, policy: SessionPolicy
    ) -> SessionService:
        return SessionService(sessions, users, policy)

    @provide
    def get_actor_resolver(self, sessions: SessionService) -> IActorResolver:
        return ChainActorResolver([SessionCookieResolver(sessions), BearerActorResolver()])

    @provide
    def get_credential_repository(self, sessions: SessionProvider) -> ICredentialRepository:
        return SqlCredentialRepository(sessions)

    @provide
    def get_login_attempt_repository(self, sessions: SessionProvider) -> ILoginAttemptRepository:
        return SqlLoginAttemptRepository(sessions)

    @provide
    def get_instance_settings(self, sessions: SessionProvider) -> IInstanceSettingsRepository:
        return SqlInstanceSettingsRepository(sessions)

    @provide
    def get_audit_log(self, sessions: SessionProvider) -> IAuditLog:
        return SqlAuditLog(sessions)

    @provide
    def get_password_hasher(self) -> IPasswordHasher:
        return Argon2PasswordHasher()

    @provide
    def get_login_uc(
        self,
        users: IUserRepository,
        credentials: ICredentialRepository,
        sessions: ISessionRepository,
        attempts: ILoginAttemptRepository,
        hasher: IPasswordHasher,
        audit: IAuditLog,
        uow: IUnitOfWork,
        policy: SessionPolicy,
    ) -> LoginUC:
        return LoginUC(users, credentials, sessions, attempts, hasher, audit, uow, policy)

    @provide
    def get_logout_uc(self, sessions: ISessionRepository, audit: IAuditLog) -> LogoutUC:
        return LogoutUC(sessions, audit)

    @provide
    def get_list_sessions_uc(self, sessions: ISessionRepository) -> ListSessionsUC:
        return ListSessionsUC(sessions)

    @provide
    def get_revoke_session_uc(self, sessions: ISessionRepository, audit: IAuditLog) -> RevokeSessionUC:
        return RevokeSessionUC(sessions, audit)

    @provide
    def get_revoke_other_sessions_uc(self, sessions: ISessionRepository, audit: IAuditLog) -> RevokeOtherSessionsUC:
        return RevokeOtherSessionsUC(sessions, audit)

    @provide
    def get_auth_token_repository(self, sessions: SessionProvider) -> IAuthTokenRepository:
        return SqlAuthTokenRepository(sessions)

    @provide
    def get_invite_repository(self, sessions: SessionProvider) -> IRegistrationInviteRepository:
        return SqlRegistrationInviteRepository(sessions)

    @provide
    def get_mail_outbox(self, sessions: SessionProvider) -> IMailOutboxRepository:
        return SqlMailOutboxRepository(sessions)

    @provide
    def get_mail_sender(self) -> IMailSender:
        # SMTP появится отдельным срезом; до него ссылки показываются копируемыми.
        return LinkOnlyMailSender()

    @provide
    def get_link_delivery(self, sender: IMailSender, outbox: IMailOutboxRepository) -> LinkDelivery:
        return LinkDelivery(sender, outbox)

    @provide
    def get_auth_env_overrides(self) -> AuthEnvOverrides:
        cfg = settings.auth
        return AuthEnvOverrides(
            registration_mode=cfg.registration_mode,
            registration_domains=tuple(cfg.registration_domains) if cfg.registration_domains is not None else None,
            require_approval=cfg.require_approval,
            password_enabled=cfg.password_enabled,
        )

    @provide
    def get_auth_settings_service(
        self, settings_repo: IInstanceSettingsRepository, env: AuthEnvOverrides
    ) -> AuthSettingsService:
        return AuthSettingsService(settings_repo, env)

    @provide
    def get_update_auth_settings_uc(
        self, service: AuthSettingsService, settings_repo: IInstanceSettingsRepository, audit: IAuditLog
    ) -> UpdateAuthSettingsUC:
        return UpdateAuthSettingsUC(service, settings_repo, audit)

    @provide
    def get_register_uc(
        self,
        users: IUserRepository,
        credentials: ICredentialRepository,
        auth_tokens: IAuthTokenRepository,
        invites: IRegistrationInviteRepository,
        auth_settings: AuthSettingsService,
        delivery: LinkDelivery,
        hasher: IPasswordHasher,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> RegisterUC:
        return RegisterUC(
            users, credentials, auth_tokens, invites, auth_settings, delivery, hasher, audit, uow,
            public_url=settings.auth.public_url,
        )  # fmt: skip

    @provide
    def get_create_invite_uc(
        self, invites: IRegistrationInviteRepository, delivery: LinkDelivery, audit: IAuditLog
    ) -> CreateInviteUC:
        return CreateInviteUC(invites, delivery, audit, public_url=settings.auth.public_url)

    @provide
    def get_list_invites_uc(self, invites: IRegistrationInviteRepository) -> ListInvitesUC:
        return ListInvitesUC(invites)

    @provide
    def get_revoke_invite_uc(self, invites: IRegistrationInviteRepository, audit: IAuditLog) -> RevokeInviteUC:
        return RevokeInviteUC(invites, audit)

    @provide
    def get_invitation_info_uc(
        self, invites: IRegistrationInviteRepository, users: IUserRepository
    ) -> InvitationInfoUC:
        return InvitationInfoUC(invites, users)

    @provide
    def get_bootstrap_uc(
        self, users: IUserRepository, auth_settings: AuthSettingsService, sessions: SessionService
    ) -> BootstrapUC:
        # SMTP появится вместе с почтовиком; до него ссылки показываются копируемыми.
        return BootstrapUC(users, auth_settings, sessions, smtp_enabled=False)
