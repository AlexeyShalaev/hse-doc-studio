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
    IFirstAdminRepository,
    IInstanceSettingsRepository,
    ILoginAttemptRepository,
    IMailOutboxRepository,
    IMailSender,
    IOidcProviderRepository,
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
    SqlOidcProviderRepository,
    SqlRegistrationInviteRepository,
    SqlSessionRepository,
)
from hse_doc_studio.infra.db.repositories.identity import (
    SqlCredentialRepository,
    SqlFirstAdminRepository,
    SqlInstanceSettingsRepository,
    SqlUserRepository,
)
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.identity.argon2_hasher import Argon2PasswordHasher
from hse_doc_studio.infra.identity.mail import LinkOnlyMailSender
from hse_doc_studio.infra.identity.resolvers import BearerActorResolver, ChainActorResolver, SessionCookieResolver
from hse_doc_studio.infra.identity.smtp_mailer import SmtpMailSender, SmtpSettings
from hse_doc_studio.use_cases.identity.account_email import ConfirmEmailChangeUC, RequestEmailChangeUC
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService, UpdateAuthSettingsUC
from hse_doc_studio.use_cases.identity.bootstrap import BootstrapUC
from hse_doc_studio.use_cases.identity.change_password import ChangePasswordUC
from hse_doc_studio.use_cases.identity.housekeeping import AuthCleanupService
from hse_doc_studio.use_cases.identity.invites import CreateInviteUC, InvitationInfoUC, ListInvitesUC, RevokeInviteUC
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
from hse_doc_studio.use_cases.identity.sessions import (
    ListSessionsUC,
    LogoutUC,
    RevokeOtherSessionsUC,
    RevokeSessionUC,
    SessionService,
)
from hse_doc_studio.use_cases.server_setup.admin import CreateFirstAdminUC, EnsureBootstrapAdminUC
from hse_doc_studio.use_cases.server_setup.settings import ApplyInitialSettingsUC, CompleteSetupUC
from hse_doc_studio.use_cases.server_setup.state import GetSetupStatusUC, SetupStateService
from hse_doc_studio.use_cases.server_setup.token import SetupToken

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


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
    def get_logout_uc(self, sessions: ISessionRepository, audit: IAuditLog, uow: IUnitOfWork) -> LogoutUC:
        return LogoutUC(sessions, audit, uow)

    @provide
    def get_list_sessions_uc(self, sessions: ISessionRepository) -> ListSessionsUC:
        return ListSessionsUC(sessions)

    @provide
    def get_revoke_session_uc(
        self, sessions: ISessionRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> RevokeSessionUC:
        return RevokeSessionUC(sessions, audit, uow)

    @provide
    def get_revoke_other_sessions_uc(
        self, sessions: ISessionRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> RevokeOtherSessionsUC:
        return RevokeOtherSessionsUC(sessions, audit, uow)

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
    def get_auth_cleanup_service(
        self,
        sessions: ISessionRepository,
        auth_tokens: IAuthTokenRepository,
        outbox: IMailOutboxRepository,
        attempts: ILoginAttemptRepository,
    ) -> AuthCleanupService:
        return AuthCleanupService(sessions, auth_tokens, outbox, attempts)

    @provide
    def get_mail_sender(self) -> IMailSender:
        cfg = settings.mail
        if not cfg.host:
            return LinkOnlyMailSender()
        return SmtpMailSender(
            SmtpSettings(
                host=cfg.host,
                port=cfg.port,
                security=cfg.security,
                username=cfg.username,
                password=cfg.password.get_secret_value() if cfg.password else None,
                from_address=cfg.from_address,
                from_name=cfg.from_name,
                timeout_s=cfg.timeout_s,
            )
        )

    @provide
    def get_link_delivery(self, sender: IMailSender, outbox: IMailOutboxRepository) -> LinkDelivery:
        return LinkDelivery(sender, outbox, background=True)

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
    def get_verify_email_uc(
        self, users: IUserRepository, auth_tokens: IAuthTokenRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> VerifyEmailUC:
        return VerifyEmailUC(users, auth_tokens, audit, uow)

    @provide
    def get_resend_verification_uc(
        self,
        users: IUserRepository,
        auth_tokens: IAuthTokenRepository,
        delivery: LinkDelivery,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> ResendVerificationUC:
        return ResendVerificationUC(users, auth_tokens, delivery, audit, uow, public_url=settings.auth.public_url)

    @provide
    def get_forgot_password_uc(
        self,
        users: IUserRepository,
        auth_tokens: IAuthTokenRepository,
        delivery: LinkDelivery,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> ForgotPasswordUC:
        return ForgotPasswordUC(users, auth_tokens, delivery, audit, uow, public_url=settings.auth.public_url)

    @provide
    def get_reset_password_uc(
        self,
        users: IUserRepository,
        credentials: ICredentialRepository,
        auth_tokens: IAuthTokenRepository,
        sessions: ISessionRepository,
        hasher: IPasswordHasher,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> ResetPasswordUC:
        return ResetPasswordUC(users, credentials, auth_tokens, sessions, hasher, audit, uow)

    @provide
    def get_issue_reset_link_uc(
        self,
        users: IUserRepository,
        auth_tokens: IAuthTokenRepository,
        delivery: LinkDelivery,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> IssueResetLinkUC:
        return IssueResetLinkUC(users, auth_tokens, delivery, audit, uow, public_url=settings.auth.public_url)

    @provide
    def get_change_password_uc(
        self,
        users: IUserRepository,
        credentials: ICredentialRepository,
        sessions: ISessionRepository,
        auth_tokens: IAuthTokenRepository,
        hasher: IPasswordHasher,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> ChangePasswordUC:
        return ChangePasswordUC(users, credentials, sessions, hasher, audit, uow, auth_tokens)

    @provide
    def get_request_email_change_uc(
        self,
        users: IUserRepository,
        credentials: ICredentialRepository,
        auth_tokens: IAuthTokenRepository,
        delivery: LinkDelivery,
        hasher: IPasswordHasher,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> RequestEmailChangeUC:
        return RequestEmailChangeUC(
            users, credentials, auth_tokens, delivery, hasher, audit, uow, public_url=settings.auth.public_url
        )

    @provide
    def get_confirm_email_change_uc(
        self, users: IUserRepository, auth_tokens: IAuthTokenRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> ConfirmEmailChangeUC:
        return ConfirmEmailChangeUC(users, auth_tokens, audit, uow)

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
        self,
        setup: SetupStateService,
        auth_settings: AuthSettingsService,
        sessions: SessionService,
        sender: IMailSender,
    ) -> BootstrapUC:
        return BootstrapUC(setup, auth_settings, sessions, smtp_enabled=sender.enabled)

    @provide
    def get_first_admin_repository(self, sessions: SessionProvider) -> IFirstAdminRepository:
        return SqlFirstAdminRepository(sessions)

    @provide
    def get_oidc_provider_repository(self, sessions: SessionProvider) -> IOidcProviderRepository:
        return SqlOidcProviderRepository(sessions)

    @provide
    def get_setup_token(self) -> SetupToken:
        # Токен одноразовый и живёт в памяти процесса: один экземпляр на приложение (APP-scope).
        required = settings.auth.setup_token_required
        if required is None:
            required = settings.server.host not in _LOOPBACK_HOSTS
        return SetupToken(required=required)

    @provide
    def get_setup_state(self, settings_repo: IInstanceSettingsRepository) -> SetupStateService:
        return SetupStateService(settings_repo)

    @provide
    def get_setup_status_uc(
        self,
        state: SetupStateService,
        settings_repo: IInstanceSettingsRepository,
        users: IUserRepository,
        token: SetupToken,
        env: AuthEnvOverrides,
    ) -> GetSetupStatusUC:
        return GetSetupStatusUC(state, settings_repo, users, token, env)

    @provide
    def get_create_first_admin_uc(
        self,
        first_admin: IFirstAdminRepository,
        hasher: IPasswordHasher,
        login: LoginUC,
        token: SetupToken,
        state: SetupStateService,
        audit: IAuditLog,
    ) -> CreateFirstAdminUC:
        return CreateFirstAdminUC(first_admin, hasher, login, token, state, audit)

    @provide
    def get_ensure_bootstrap_admin_uc(
        self,
        users: IUserRepository,
        first_admin: IFirstAdminRepository,
        hasher: IPasswordHasher,
        state: SetupStateService,
        audit: IAuditLog,
        env: AuthEnvOverrides,
    ) -> EnsureBootstrapAdminUC:
        return EnsureBootstrapAdminUC(users, first_admin, hasher, state, audit, env)

    @provide
    def get_apply_initial_settings_uc(
        self,
        service: AuthSettingsService,
        update: UpdateAuthSettingsUC,
        oidc: IOidcProviderRepository,
        state: SetupStateService,
    ) -> ApplyInitialSettingsUC:
        return ApplyInitialSettingsUC(service, update, oidc, state)

    @provide
    def get_complete_setup_uc(self, state: SetupStateService, audit: IAuditLog) -> CompleteSetupUC:
        return CompleteSetupUC(state, audit)
