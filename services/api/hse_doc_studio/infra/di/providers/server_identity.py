"""Провайдер identity серверного режима.

Срезы identity регистрируют здесь репозитории пользователей и сессий, цепочку резолверов
актора, почтовик и ограничитель. Подключается лениво, только из ``create_container(server)``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from urllib.parse import urlsplit

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.egress import IEgressPolicy
from hse_doc_studio.core.git_sync.protocols import ILocalAuthorProfile, ISecretCipher
from hse_doc_studio.core.identity.auth_settings import AuthEnvOverrides
from hse_doc_studio.core.identity.commit_identity import noreply_domain
from hse_doc_studio.core.identity.lifecycle import IUserLifecycle, RetentionPolicy
from hse_doc_studio.core.identity.oidc import IOidcClient, IOidcProviderCatalog, IOidcStateCodec, OidcProviderConfig
from hse_doc_studio.core.identity.protocols import (
    IActorResolver,
    IApiTokenRepository,
    IAuditLog,
    IAuditReader,
    IAuditRetention,
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
    IUserDirectory,
    IUserRepository,
)
from hse_doc_studio.core.identity.session_policy import SessionPolicy
from hse_doc_studio.core.identity.smtp_settings import SmtpEnv, SmtpParams
from hse_doc_studio.core.orgs.protocols import IGroupRepository, IOrgRepository
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.core.signatures.key_policy import ServerKeyPolicy, server_key_policy_from
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.auth import (
    SqlApiTokenRepository,
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
    SqlUserDirectory,
    SqlUserRepository,
)
from hse_doc_studio.infra.db.repositories.lifecycle import SqlUserLifecycle
from hse_doc_studio.infra.db.repositories.orgs import SqlGroupRepository, SqlOrgRepository
from hse_doc_studio.infra.db.repositories.settings import PostgresSettingsRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.identity.argon2_hasher import Argon2PasswordHasher
from hse_doc_studio.infra.identity.configured_mailer import ConfiguredMailSender
from hse_doc_studio.infra.identity.oidc.catalog import OidcProviderCatalog
from hse_doc_studio.infra.identity.oidc.client import OidcClient
from hse_doc_studio.infra.identity.oidc.state import OIDC_STATE_KEY_PURPOSE, HmacOidcStateCodec
from hse_doc_studio.infra.identity.resolvers import BearerActorResolver, ChainActorResolver, SessionCookieResolver
from hse_doc_studio.infra.identity.user_author_profile import UserAuthorProfile
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from hse_doc_studio.use_cases.admin.audit import ListAuditUC, PurgeAuditUC
from hse_doc_studio.use_cases.admin.invitations import ResendInviteUC
from hse_doc_studio.use_cases.admin.lifecycle import DeleteUserUC, ExportMyDataUC, GetRetentionUC
from hse_doc_studio.use_cases.admin.oidc import (
    CreateOidcProviderUC,
    DeleteOidcProviderUC,
    GetOidcProviderUC,
    ListOidcProvidersUC,
    UpdateOidcProviderUC,
)
from hse_doc_studio.use_cases.admin.orgs import (
    AddAdminMemberUC,
    CreateAdminGroupUC,
    CreateAdminOrgUC,
    DeleteAdminGroupUC,
    DeleteAdminOrgUC,
    GetAdminOrgUC,
    ListAdminGroupsUC,
    ListAdminMembersUC,
    ListAdminOrgsUC,
    RemoveAdminMemberUC,
    SetAdminMemberRoleUC,
    UpdateAdminGroupUC,
)
from hse_doc_studio.use_cases.admin.settings import GetAuthGroupUC, UpdateAuthMethodsUC, UpdateRegistrationUC
from hse_doc_studio.use_cases.admin.users import (
    ApproveUserUC,
    DisableUserUC,
    EnableUserUC,
    GetUserUC,
    ListApprovalsUC,
    ListUsersUC,
    RejectUserUC,
    RevokeUserSessionsUC,
    SetUserAdminUC,
)
from hse_doc_studio.use_cases.identity.account_email import ConfirmEmailChangeUC, RequestEmailChangeUC
from hse_doc_studio.use_cases.identity.account_profile import GetAccountUC, UpdateAccountUC
from hse_doc_studio.use_cases.identity.api_tokens import CreateApiTokenUC, ListApiTokensUC, RevokeApiTokenUC
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService, UpdateAuthSettingsUC
from hse_doc_studio.use_cases.identity.bootstrap import BootstrapUC
from hse_doc_studio.use_cases.identity.change_password import ChangePasswordUC
from hse_doc_studio.use_cases.identity.housekeeping import AuthCleanupService
from hse_doc_studio.use_cases.identity.invites import CreateInviteUC, InvitationInfoUC, ListInvitesUC, RevokeInviteUC
from hse_doc_studio.use_cases.identity.login import LoginUC
from hse_doc_studio.use_cases.identity.mail import LinkDelivery
from hse_doc_studio.use_cases.identity.oidc_identities import ListOidcIdentitiesUC, UnlinkOidcIdentityUC
from hse_doc_studio.use_cases.identity.oidc_login import CompleteOidcLoginUC, StartOidcLoginUC
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
from hse_doc_studio.use_cases.identity.smtp_settings import (
    GetSmtpSettingsUC,
    SendTestMailUC,
    SmtpSettingsService,
    UpdateSmtpSettingsUC,
)
from hse_doc_studio.use_cases.orgs.groups import (
    AddGroupMemberUC,
    CreateGroupUC,
    DeleteGroupUC,
    ListGroupMembersUC,
    ListGroupsUC,
    RemoveGroupMemberUC,
    UpdateGroupUC,
)
from hse_doc_studio.use_cases.orgs.members import (
    AddOrgMemberUC,
    ChangeOrgRoleUC,
    LeaveOrgUC,
    ListOrgMembersUC,
    RemoveOrgMemberUC,
)
from hse_doc_studio.use_cases.orgs.orgs import (
    CreateOrgUC,
    DeleteOrgUC,
    GetOrgUC,
    ListAccountOrgsUC,
    ListMyOrgsUC,
    UpdateOrgUC,
)
from hse_doc_studio.use_cases.profile.clear_profile import ClearProfileUC
from hse_doc_studio.use_cases.profile.server_profile import ServerClearProfileUC, ServerUpdateProfileUC
from hse_doc_studio.use_cases.profile.update_profile import UpdateProfileUC
from hse_doc_studio.use_cases.server_setup.admin import CreateFirstAdminUC, EnsureBootstrapAdminUC
from hse_doc_studio.use_cases.server_setup.settings import ApplyInitialSettingsUC, CompleteSetupUC
from hse_doc_studio.use_cases.server_setup.state import GetSetupStatusUC, SetupStateService
from hse_doc_studio.use_cases.server_setup.token import SetupToken

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def setup_token_required(
    *, override: bool | None, host: str, public_url: str | None, trusted_proxies: list[str]
) -> bool:
    """Нужен ли токен установки. Явное значение оператора главнее; иначе токен не нужен только при настоящем loopback.

    Приложение на 127.0.0.1 за nginx доступно из сети, хотя слушает loopback: поэтому внешний `public_url` или
    доверенные прокси означают, что первый посетитель мастера стал бы администратором без токена.
    """
    if override is not None:
        return override
    if host not in _LOOPBACK_HOSTS or trusted_proxies:
        return True
    if not public_url:
        return False
    public_host = (urlsplit(public_url).hostname or "").lower()
    return public_host not in _LOOPBACK_HOSTS and not public_host.endswith(".localhost")


class ServerIdentityProvider(Provider):
    scope = Scope.APP

    @provide
    def get_user_repository(self, sessions: SessionProvider) -> IUserRepository:
        return SqlUserRepository(sessions)

    @provide
    def get_user_directory(self, sessions: SessionProvider) -> IUserDirectory:
        return SqlUserDirectory(sessions)

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
    def get_api_token_repository(self, sessions: SessionProvider) -> IApiTokenRepository:
        return SqlApiTokenRepository(sessions)

    @provide
    def get_actor_resolver(
        self, sessions: SessionService, tokens: IApiTokenRepository, users: IUserRepository
    ) -> IActorResolver:
        domain = noreply_domain(settings.auth.public_url)
        return ChainActorResolver(
            [SessionCookieResolver(sessions, domain), BearerActorResolver(tokens, users, noreply_domain=domain)]
        )

    @provide(override=True)
    def get_local_author_profile(self) -> ILocalAuthorProfile:
        """Подпись коммитов берётся из актора запроса, а не из config.json машины."""
        return UserAuthorProfile()

    @provide(override=True)
    def get_settings_repo(self, sessions: SessionProvider) -> ISettingsRepository:
        """Настройки живут в Postgres: свои у пользователя, общие ключи только у админа."""
        return PostgresSettingsRepository(sessions)

    @provide
    def get_account_uc(self, users: IUserRepository) -> GetAccountUC:
        return GetAccountUC(users, noreply_domain(settings.auth.public_url))

    @provide
    def get_update_account_uc(self, users: IUserRepository, audit: IAuditLog, uow: IUnitOfWork) -> UpdateAccountUC:
        return UpdateAccountUC(users, audit, uow, noreply_domain(settings.auth.public_url))

    @provide(override=True)
    def get_update_profile_uc(self, accounts: UpdateAccountUC) -> UpdateProfileUC:
        return ServerUpdateProfileUC(accounts)

    @provide(override=True)
    def get_clear_profile_uc(self, accounts: UpdateAccountUC) -> ClearProfileUC:
        return ServerClearProfileUC(accounts)

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
    def get_audit_reader(self, sessions: SessionProvider) -> IAuditReader:
        return SqlAuditLog(sessions)

    @provide
    def get_audit_retention(self, sessions: SessionProvider) -> IAuditRetention:
        return SqlAuditLog(sessions)

    @provide
    def get_list_audit_uc(self, reader: IAuditReader) -> ListAuditUC:
        return ListAuditUC(reader)

    @provide
    def get_purge_audit_uc(self, retention: IAuditRetention, audit: IAuditLog) -> PurgeAuditUC:
        return PurgeAuditUC(retention, audit, timedelta(days=settings.server.audit_retention_days))

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
    def get_oidc_provider_catalog(self, repo: IOidcProviderRepository, cipher: ISecretCipher) -> IOidcProviderCatalog:
        env = settings.auth.oidc
        from_env = (
            OidcProviderConfig(
                id=env.id,
                label=env.label,
                issuer=env.issuer or "",
                client_id=env.client_id or "",
                client_secret=env.resolved_secret(),
                scopes=env.scopes,
                auto_provision=env.auto_provision,
            )
            if env.configured
            else None
        )
        return OidcProviderCatalog(repo, cipher, from_env)

    @provide
    async def get_oidc_client(self, egress: IEgressPolicy) -> AsyncIterator[IOidcClient]:
        client = OidcClient(egress)
        yield client
        await client.aclose()

    @provide
    def get_oidc_state_codec(self, key_store: KeyFileStore) -> IOidcStateCodec:
        """Ключи подписи производные от связки секретов: ротация ключа не рвёт входы, начатые до неё."""
        return HmacOidcStateCodec(key_store.ensure_primary().derive_all(OIDC_STATE_KEY_PURPOSE))

    @provide
    def get_start_oidc_login_uc(
        self, catalog: IOidcProviderCatalog, client: IOidcClient, codec: IOidcStateCodec
    ) -> StartOidcLoginUC:
        return StartOidcLoginUC(catalog, client, codec)

    @provide
    def get_complete_oidc_login_uc(
        self,
        catalog: IOidcProviderCatalog,
        client: IOidcClient,
        codec: IOidcStateCodec,
        users: IUserRepository,
        sessions: ISessionRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        policy: SessionPolicy,
        auth_settings: AuthSettingsService,
    ) -> CompleteOidcLoginUC:
        return CompleteOidcLoginUC(
            catalog, client, codec, users, sessions, audit, uow, policy, auth_settings=auth_settings
        )

    @provide
    def get_list_oidc_identities_uc(
        self, users: IUserRepository, catalog: IOidcProviderCatalog
    ) -> ListOidcIdentitiesUC:
        return ListOidcIdentitiesUC(users, catalog)

    @provide
    def get_unlink_oidc_identity_uc(
        self,
        users: IUserRepository,
        credentials: ICredentialRepository,
        settings: AuthSettingsService,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> UnlinkOidcIdentityUC:
        return UnlinkOidcIdentityUC(users, credentials, settings, audit, uow)

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
    def get_list_api_tokens_uc(self, tokens: IApiTokenRepository) -> ListApiTokensUC:
        return ListApiTokensUC(tokens)

    @provide
    def get_create_api_token_uc(
        self, tokens: IApiTokenRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> CreateApiTokenUC:
        return CreateApiTokenUC(tokens, audit, uow)

    @provide
    def get_revoke_api_token_uc(
        self, tokens: IApiTokenRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> RevokeApiTokenUC:
        return RevokeApiTokenUC(tokens, audit, uow)

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
    def get_smtp_env(self) -> SmtpEnv:
        cfg = settings.mail
        if not cfg.host:
            return SmtpEnv()
        return SmtpEnv(
            SmtpParams(
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
    def get_smtp_settings_service(
        self, settings_repo: IInstanceSettingsRepository, cipher: ISecretCipher, env: SmtpEnv
    ) -> SmtpSettingsService:
        return SmtpSettingsService(settings_repo, cipher, env)

    @provide
    async def get_configured_mail_sender(self, service: SmtpSettingsService) -> ConfiguredMailSender:
        sender = ConfiguredMailSender(service)
        await sender.refresh()
        return sender

    @provide
    def get_mail_sender(self, sender: ConfiguredMailSender) -> IMailSender:
        return sender

    @provide
    def get_update_smtp_settings_uc(
        self,
        service: SmtpSettingsService,
        settings_repo: IInstanceSettingsRepository,
        audit: IAuditLog,
        sender: ConfiguredMailSender,
    ) -> UpdateSmtpSettingsUC:
        return UpdateSmtpSettingsUC(service, settings_repo, audit, on_change=sender.refresh)

    @provide
    def get_smtp_settings_uc(self, service: SmtpSettingsService) -> GetSmtpSettingsUC:
        return GetSmtpSettingsUC(service)

    @provide
    def get_send_test_mail_uc(self, sender: IMailSender, users: IUserRepository, audit: IAuditLog) -> SendTestMailUC:
        return SendTestMailUC(sender, users, audit)

    @provide
    def get_auth_group_uc(self, service: AuthSettingsService, oidc: IOidcProviderRepository) -> GetAuthGroupUC:
        return GetAuthGroupUC(service, oidc)

    @provide
    def get_update_registration_uc(self, update: UpdateAuthSettingsUC, group: GetAuthGroupUC) -> UpdateRegistrationUC:
        return UpdateRegistrationUC(update, group)

    @provide
    def get_update_auth_methods_uc(
        self,
        update: UpdateAuthSettingsUC,
        service: AuthSettingsService,
        oidc: IOidcProviderRepository,
        group: GetAuthGroupUC,
    ) -> UpdateAuthMethodsUC:
        return UpdateAuthMethodsUC(update, service, oidc, group)

    @provide
    def get_list_oidc_providers_uc(self, oidc: IOidcProviderRepository) -> ListOidcProvidersUC:
        return ListOidcProvidersUC(oidc)

    @provide
    def get_oidc_provider_uc(self, oidc: IOidcProviderRepository) -> GetOidcProviderUC:
        return GetOidcProviderUC(oidc)

    @provide
    def get_create_oidc_provider_uc(
        self, oidc: IOidcProviderRepository, cipher: ISecretCipher, audit: IAuditLog
    ) -> CreateOidcProviderUC:
        return CreateOidcProviderUC(oidc, cipher, audit)

    @provide
    def get_update_oidc_provider_uc(
        self, oidc: IOidcProviderRepository, cipher: ISecretCipher, service: AuthSettingsService, audit: IAuditLog
    ) -> UpdateOidcProviderUC:
        return UpdateOidcProviderUC(oidc, cipher, service, audit)

    @provide
    def get_delete_oidc_provider_uc(
        self, oidc: IOidcProviderRepository, service: AuthSettingsService, audit: IAuditLog
    ) -> DeleteOidcProviderUC:
        return DeleteOidcProviderUC(oidc, service, audit)

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
    def get_list_users_uc(self, directory: IUserDirectory) -> ListUsersUC:
        return ListUsersUC(directory)

    @provide
    def get_get_user_uc(self, directory: IUserDirectory) -> GetUserUC:
        return GetUserUC(directory)

    @provide
    def get_user_lifecycle(self, sessions: SessionProvider) -> IUserLifecycle:
        return SqlUserLifecycle(sessions)

    @provide
    def get_delete_user_uc(
        self, users: IUserRepository, lifecycle: IUserLifecycle, audit: IAuditLog, uow: IUnitOfWork
    ) -> DeleteUserUC:
        return DeleteUserUC(users, lifecycle, audit, uow)

    @provide
    def get_export_my_data_uc(self, lifecycle: IUserLifecycle, audit: IAuditLog) -> ExportMyDataUC:
        return ExportMyDataUC(lifecycle, audit)

    @provide
    def get_retention_uc(self) -> GetRetentionUC:
        return GetRetentionUC(
            RetentionPolicy(
                audit_days=settings.server.audit_retention_days,
                deleted_projects_days=settings.server.project_retention_days,
                unused_blobs_days=round(settings.server.blob_gc_min_age_days),
            )
        )

    @provide
    def get_disable_user_uc(
        self, users: IUserRepository, sessions: ISessionRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> DisableUserUC:
        return DisableUserUC(users, sessions, audit, uow)

    @provide
    def get_enable_user_uc(self, users: IUserRepository, audit: IAuditLog, uow: IUnitOfWork) -> EnableUserUC:
        return EnableUserUC(users, audit, uow)

    @provide
    def get_set_user_admin_uc(self, users: IUserRepository, audit: IAuditLog, uow: IUnitOfWork) -> SetUserAdminUC:
        return SetUserAdminUC(users, audit, uow)

    @provide
    def get_revoke_user_sessions_uc(
        self, users: IUserRepository, sessions: ISessionRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> RevokeUserSessionsUC:
        return RevokeUserSessionsUC(users, sessions, audit, uow)

    @provide
    def get_list_approvals_uc(self, directory: IUserDirectory) -> ListApprovalsUC:
        return ListApprovalsUC(directory)

    @provide
    def get_approve_user_uc(self, users: IUserRepository, audit: IAuditLog, uow: IUnitOfWork) -> ApproveUserUC:
        return ApproveUserUC(users, audit, uow)

    @provide
    def get_reject_user_uc(self, users: IUserRepository, audit: IAuditLog, uow: IUnitOfWork) -> RejectUserUC:
        return RejectUserUC(users, audit, uow)

    @provide
    def get_resend_invite_uc(
        self, invites: IRegistrationInviteRepository, create: CreateInviteUC, audit: IAuditLog, uow: IUnitOfWork
    ) -> ResendInviteUC:
        return ResendInviteUC(invites, create, audit, uow)

    @provide
    def get_bootstrap_uc(
        self,
        setup: SetupStateService,
        auth_settings: AuthSettingsService,
        sessions: SessionService,
        sender: IMailSender,
        oidc: IOidcProviderCatalog,
        settings_repo: IInstanceSettingsRepository,
    ) -> BootstrapUC:
        async def signing_keys_allowed() -> bool:
            return server_key_policy_from(await settings_repo.get_all()) is ServerKeyPolicy.allowed

        return BootstrapUC(
            setup,
            auth_settings,
            sessions,
            smtp_enabled=lambda: sender.enabled,
            oidc_providers=oidc.list_enabled,
            signing_keys_allowed=signing_keys_allowed,
        )

    @provide
    def get_first_admin_repository(self, sessions: SessionProvider) -> IFirstAdminRepository:
        return SqlFirstAdminRepository(sessions)

    @provide
    def get_oidc_provider_repository(self, sessions: SessionProvider) -> IOidcProviderRepository:
        return SqlOidcProviderRepository(sessions)

    @provide
    def get_setup_token(self) -> SetupToken:
        # Токен одноразовый и живёт в памяти процесса: один экземпляр на приложение (APP-scope).
        required = setup_token_required(
            override=settings.auth.setup_token_required,
            host=settings.server.host,
            public_url=settings.auth.public_url,
            trusted_proxies=settings.auth.trusted_proxies,
        )
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

    @provide
    def get_org_repository(self, sessions: SessionProvider) -> IOrgRepository:
        return SqlOrgRepository(sessions)

    @provide
    def get_group_repository(self, sessions: SessionProvider) -> IGroupRepository:
        return SqlGroupRepository(sessions)

    @provide
    def get_list_my_orgs_uc(self, orgs: IOrgRepository) -> ListMyOrgsUC:
        return ListMyOrgsUC(orgs)

    @provide
    def get_get_org_uc(self, orgs: IOrgRepository) -> GetOrgUC:
        return GetOrgUC(orgs)

    @provide
    def get_create_org_uc(
        self,
        orgs: IOrgRepository,
        users: IUserRepository,
        settings_repo: IInstanceSettingsRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> CreateOrgUC:
        return CreateOrgUC(orgs, users, settings_repo, audit, uow)

    @provide
    def get_update_org_uc(self, orgs: IOrgRepository, audit: IAuditLog, uow: IUnitOfWork) -> UpdateOrgUC:
        return UpdateOrgUC(orgs, audit, uow)

    @provide
    def get_delete_org_uc(self, orgs: IOrgRepository, audit: IAuditLog, uow: IUnitOfWork) -> DeleteOrgUC:
        return DeleteOrgUC(orgs, audit, uow)

    @provide
    def get_list_org_members_uc(self, orgs: IOrgRepository) -> ListOrgMembersUC:
        return ListOrgMembersUC(orgs)

    @provide
    def get_add_org_member_uc(
        self, orgs: IOrgRepository, users: IUserRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> AddOrgMemberUC:
        return AddOrgMemberUC(orgs, users, audit, uow)

    @provide
    def get_change_org_role_uc(
        self, orgs: IOrgRepository, users: IUserRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> ChangeOrgRoleUC:
        return ChangeOrgRoleUC(orgs, users, audit, uow)

    @provide
    def get_remove_org_member_uc(
        self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> RemoveOrgMemberUC:
        return RemoveOrgMemberUC(orgs, groups, audit, uow)

    @provide
    def get_leave_org_uc(
        self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> LeaveOrgUC:
        return LeaveOrgUC(orgs, groups, audit, uow)

    @provide
    def get_list_groups_uc(self, orgs: IOrgRepository, groups: IGroupRepository) -> ListGroupsUC:
        return ListGroupsUC(orgs, groups)

    @provide
    def get_create_group_uc(
        self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> CreateGroupUC:
        return CreateGroupUC(orgs, groups, audit, uow)

    @provide
    def get_update_group_uc(
        self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> UpdateGroupUC:
        return UpdateGroupUC(orgs, groups, audit, uow)

    @provide
    def get_delete_group_uc(
        self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> DeleteGroupUC:
        return DeleteGroupUC(orgs, groups, audit, uow)

    @provide
    def get_list_group_members_uc(self, orgs: IOrgRepository, groups: IGroupRepository) -> ListGroupMembersUC:
        return ListGroupMembersUC(orgs, groups)

    @provide
    def get_add_group_member_uc(
        self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> AddGroupMemberUC:
        return AddGroupMemberUC(orgs, groups, audit, uow)

    @provide
    def get_remove_group_member_uc(
        self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> RemoveGroupMemberUC:
        return RemoveGroupMemberUC(orgs, groups, audit, uow)

    @provide
    def get_list_account_orgs_uc(self, orgs: IOrgRepository, groups: IGroupRepository) -> ListAccountOrgsUC:
        return ListAccountOrgsUC(orgs, groups)

    @provide
    def get_list_admin_orgs_uc(self, orgs: IOrgRepository) -> ListAdminOrgsUC:
        return ListAdminOrgsUC(orgs)

    @provide
    def get_get_admin_org_uc(self, orgs: IOrgRepository) -> GetAdminOrgUC:
        return GetAdminOrgUC(orgs)

    @provide
    def get_create_admin_org_uc(self, orgs: IOrgRepository, audit: IAuditLog, uow: IUnitOfWork) -> CreateAdminOrgUC:
        return CreateAdminOrgUC(orgs, audit, uow)

    @provide
    def get_delete_admin_org_uc(self, orgs: IOrgRepository, audit: IAuditLog, uow: IUnitOfWork) -> DeleteAdminOrgUC:
        return DeleteAdminOrgUC(orgs, audit, uow)

    @provide
    def get_list_admin_members_uc(self, orgs: IOrgRepository) -> ListAdminMembersUC:
        return ListAdminMembersUC(orgs)

    @provide
    def get_add_admin_member_uc(
        self, orgs: IOrgRepository, users: IUserRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> AddAdminMemberUC:
        return AddAdminMemberUC(orgs, users, audit, uow)

    @provide
    def get_set_admin_member_role_uc(
        self, orgs: IOrgRepository, users: IUserRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> SetAdminMemberRoleUC:
        return SetAdminMemberRoleUC(orgs, users, audit, uow)

    @provide
    def get_remove_admin_member_uc(
        self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> RemoveAdminMemberUC:
        return RemoveAdminMemberUC(orgs, groups, audit, uow)

    @provide
    def get_list_admin_groups_uc(self, orgs: IOrgRepository, groups: IGroupRepository) -> ListAdminGroupsUC:
        return ListAdminGroupsUC(orgs, groups)

    @provide
    def get_create_admin_group_uc(
        self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> CreateAdminGroupUC:
        return CreateAdminGroupUC(orgs, groups, audit, uow)

    @provide
    def get_update_admin_group_uc(
        self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> UpdateAdminGroupUC:
        return UpdateAdminGroupUC(orgs, groups, audit, uow)

    @provide
    def get_delete_admin_group_uc(
        self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> DeleteAdminGroupUC:
        return DeleteAdminGroupUC(orgs, groups, audit, uow)
