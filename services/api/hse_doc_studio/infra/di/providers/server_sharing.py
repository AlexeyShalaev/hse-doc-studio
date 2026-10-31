"""Ссылки доступа на сервере: хранилище ссылок, политика общего доступа и сценарии управления ссылками."""

from __future__ import annotations

from datetime import timedelta

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.links import (
    IBuildPayerResolver,
    IGuestSessionRepository,
    IShareLinkRepository,
    IShareLinkStore,
    LinkRole,
)
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.access.sharing_policy import ISharingPolicyReader, SharingEnvOverrides
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.identity.protocols import (
    IAuditLog,
    IInstanceSettingsRepository,
    ILoginAttemptRepository,
    IPasswordHasher,
)
from hse_doc_studio.core.orgs.protocols import IOrgRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.guest_sessions import PostgresGuestSessionRepository
from hse_doc_studio.infra.db.repositories.project_acl import PostgresProjectAclRepository
from hse_doc_studio.infra.db.repositories.share_links import PostgresShareLinkRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.sharing.policy_reader import PostgresSharingPolicyReader
from hse_doc_studio.use_cases.sharing.links import (
    CreateShareLinkUC,
    ListLinkVisitsUC,
    ListShareLinksUC,
    RevokeShareLinkUC,
    RotateShareLinkUC,
    ShareLinkService,
    UpdateShareLinkUC,
)
from hse_doc_studio.use_cases.sharing.open_link import (
    GuestInfoUC,
    GuestSessionService,
    LeaveGuestSessionUC,
    OpenShareLinkUC,
    PreviewShareLinkUC,
    ShareLinkResolver,
    UpdateGuestSessionUC,
)
from hse_doc_studio.use_cases.sharing.payer import GuestBuildPayer


class ServerSharingProvider(Provider):
    scope = Scope.APP

    @provide
    def get_sharing_env(self) -> SharingEnvOverrides:
        max_role = settings.sharing.max_link_role
        return SharingEnvOverrides(
            links_enabled=settings.sharing.links_enabled,
            max_link_role=LinkRole(max_role) if max_role else None,
            project_invites_allow_signup=settings.auth.project_invites_allow_signup,
        )

    @provide
    def get_share_link_store(self, sessions: SessionProvider) -> PostgresShareLinkRepository:
        return PostgresShareLinkRepository(sessions)

    @provide
    def get_share_link_store_port(self, store: PostgresShareLinkRepository) -> IShareLinkStore:
        return store

    @provide
    def get_share_link_repository(self, store: PostgresShareLinkRepository) -> IShareLinkRepository:
        return store

    @provide
    def get_policy_reader(
        self, sessions: SessionProvider, instance_settings: IInstanceSettingsRepository, env: SharingEnvOverrides
    ) -> PostgresSharingPolicyReader:
        return PostgresSharingPolicyReader(sessions, instance_settings, env)

    @provide
    def get_policy_reader_port(self, reader: PostgresSharingPolicyReader) -> ISharingPolicyReader:
        return reader

    @provide(scope=Scope.REQUEST)
    def get_share_link_service(  # noqa: PLR0913 — зависимости сценариев ссылок
        self,
        store: IShareLinkStore,
        acl: IProjectAclRepository,
        policy: ISharingPolicyReader,
        cipher: ISecretCipher,
        hasher: IPasswordHasher,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> ShareLinkService:
        return ShareLinkService(store, acl, policy, cipher, hasher, audit, uow, public_url=settings.auth.public_url)

    @provide(scope=Scope.REQUEST)
    def get_list_links_uc(self, service: ShareLinkService) -> ListShareLinksUC:
        return ListShareLinksUC(service)

    @provide(scope=Scope.REQUEST)
    def get_create_link_uc(self, service: ShareLinkService) -> CreateShareLinkUC:
        return CreateShareLinkUC(service)

    @provide(scope=Scope.REQUEST)
    def get_update_link_uc(self, service: ShareLinkService) -> UpdateShareLinkUC:
        return UpdateShareLinkUC(service)

    @provide(scope=Scope.REQUEST)
    def get_rotate_link_uc(self, service: ShareLinkService) -> RotateShareLinkUC:
        return RotateShareLinkUC(service)

    @provide(scope=Scope.REQUEST)
    def get_revoke_link_uc(self, service: ShareLinkService) -> RevokeShareLinkUC:
        return RevokeShareLinkUC(service)

    @provide(scope=Scope.REQUEST)
    def get_link_visits_uc(self, service: ShareLinkService) -> ListLinkVisitsUC:
        return ListLinkVisitsUC(service)

    @provide
    def get_guest_sessions(self, sessions: SessionProvider) -> IGuestSessionRepository:
        return PostgresGuestSessionRepository(sessions)

    @provide
    def get_guest_session_service(self, guests: IGuestSessionRepository) -> GuestSessionService:
        return GuestSessionService(guests, lifetime=timedelta(days=settings.sharing.guest_session_days))

    @provide
    def get_link_resolver(
        self, store: IShareLinkStore, policy: ISharingPolicyReader, orgs: IOrgRepository
    ) -> ShareLinkResolver:
        return ShareLinkResolver(store, policy, orgs)

    @provide
    def get_preview_uc(self, resolver: ShareLinkResolver) -> PreviewShareLinkUC:
        return PreviewShareLinkUC(resolver)

    @provide(scope=Scope.REQUEST)
    def get_open_uc(  # noqa: PLR0913 — зависимости открытия ссылки
        self,
        resolver: ShareLinkResolver,
        store: IShareLinkStore,
        guests: IGuestSessionRepository,
        guest_sessions: GuestSessionService,
        acl: IProjectAclRepository,
        hasher: IPasswordHasher,
        attempts: ILoginAttemptRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> OpenShareLinkUC:
        return OpenShareLinkUC(resolver, store, guests, guest_sessions, acl, hasher, attempts, audit, uow)

    @provide
    def get_guest_info_uc(
        self, guests: IGuestSessionRepository, store: IShareLinkStore, policy: ISharingPolicyReader
    ) -> GuestInfoUC:
        return GuestInfoUC(guests, store, policy)

    @provide
    def get_update_guest_uc(self, guests: IGuestSessionRepository, info: GuestInfoUC) -> UpdateGuestSessionUC:
        return UpdateGuestSessionUC(guests, info)

    @provide
    def get_leave_guest_uc(self, guests: IGuestSessionRepository) -> LeaveGuestSessionUC:
        return LeaveGuestSessionUC(guests)

    @provide
    def get_build_payer(self, store: IShareLinkStore, acl: PostgresProjectAclRepository) -> IBuildPayerResolver:
        return GuestBuildPayer(store, acl)
