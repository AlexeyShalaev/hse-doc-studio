"""Провайдер трека invites (серверный режим): приглашения, запросы доступа, передача владения, «Входящие».

Подключается после остальных серверных провайдеров и перекрывает (`override=True`) сценарии, куда трек дописывает
своё: прямое добавление участника (S10), снятие участника (уведомление), регистрация и подтверждение почты
(привязка приглашений), уборка (уведомления старше 90 дней).
"""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.repositories import IProjectAccessDirectory, IProjectMemberRepository
from hse_doc_studio.core.access.sharing_policy import SharingEnvOverrides
from hse_doc_studio.core.identity.protocols import (
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
from hse_doc_studio.core.invitations.protocols import (
    IAccessRequestRepository,
    IEmailVerifiedHook,
    INotificationMailer,
    INotificationRepository,
    INotifier,
    IProjectCards,
    IProjectInvitationRepository,
    IProjectMemberLookup,
    IProjectPersonas,
    IProjectTransferRepository,
)
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.core.orgs.protocols import IOrgRepository
from hse_doc_studio.core.repositories import IProjectIndexRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.access_requests import PostgresAccessRequestRepository
from hse_doc_studio.infra.db.repositories.notifications import PostgresNotificationRepository
from hse_doc_studio.infra.db.repositories.project_acl import PostgresProjectAclRepository
from hse_doc_studio.infra.db.repositories.project_cards import PostgresProjectCards
from hse_doc_studio.infra.db.repositories.project_invitations import PostgresProjectInvitationRepository
from hse_doc_studio.infra.db.repositories.project_members import PostgresProjectMemberRepository
from hse_doc_studio.infra.db.repositories.project_transfers import PostgresProjectTransferRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.invitations.personas import ProjectFilePersonas
from hse_doc_studio.infra.invitations.signup_setting import ProjectInviteSignupSetting
from hse_doc_studio.infra.notifications.mailer import SmtpNotificationMailer
from hse_doc_studio.use_cases.identity.account_email import ConfirmEmailChangeUC
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService
from hse_doc_studio.use_cases.identity.housekeeping import AuthCleanupService
from hse_doc_studio.use_cases.identity.mail import LinkDelivery
from hse_doc_studio.use_cases.identity.recovery import VerifyEmailUC
from hse_doc_studio.use_cases.identity.register import RegisterUC
from hse_doc_studio.use_cases.notifications.inbox import (
    InboxSummaryUC,
    ListNotificationsUC,
    MarkNotificationsReadUC,
    PurgeNotificationsUC,
)
from hse_doc_studio.use_cases.notifications.notifier import Notifier
from hse_doc_studio.use_cases.projects.access_requests import (
    ApproveAccessRequestUC,
    CancelAccessRequestUC,
    CreateAccessRequestUC,
    DenyAccessRequestUC,
    ListAccessRequestsUC,
    ListMyAccessRequestsUC,
)
from hse_doc_studio.use_cases.projects.invitations import (
    AcceptInvitationTokenUC,
    AcceptInvitationUC,
    AttachInvitationsByEmailUC,
    CreateInvitationUC,
    DeclineInvitationUC,
    ListMyInvitationsUC,
    ListProjectInvitationsUC,
    PreviewInvitationTokenUC,
    ResendInvitationUC,
    RevokeInvitationUC,
)
from hse_doc_studio.use_cases.projects.members import RemoveProjectMemberUC
from hse_doc_studio.use_cases.projects.transfer import (
    AcceptTransferUC,
    ApplyTransferUC,
    CancelTransferUC,
    DeclineTransferUC,
    GetTransferStateUC,
    IPersonalWaitExpirer,
    ListMyTransfersUC,
    StartTransferUC,
)


class ServerInvitationsProvider(Provider):
    scope = Scope.APP

    # Хранилища и адаптеры

    @provide
    def get_notifications(self, sessions: SessionProvider) -> INotificationRepository:
        return PostgresNotificationRepository(sessions)

    @provide
    def get_invitations(self, sessions: SessionProvider) -> IProjectInvitationRepository:
        return PostgresProjectInvitationRepository(sessions)

    @provide
    def get_access_requests(self, sessions: SessionProvider) -> IAccessRequestRepository:
        return PostgresAccessRequestRepository(sessions)

    @provide
    def get_transfers(self, sessions: SessionProvider) -> IProjectTransferRepository:
        return PostgresProjectTransferRepository(sessions)

    @provide
    def get_cards(self, sessions: SessionProvider) -> IProjectCards:
        return PostgresProjectCards(sessions)

    @provide
    def get_member_lookup(self, sessions: SessionProvider) -> IProjectMemberLookup:
        return PostgresProjectMemberRepository(sessions)

    @provide
    def get_personas(self, index: IProjectIndexRepository) -> IProjectPersonas:
        return ProjectFilePersonas(index)

    @provide
    def get_signup_setting(
        self, instance: IInstanceSettingsRepository, env: SharingEnvOverrides
    ) -> ProjectInviteSignupSetting:
        return ProjectInviteSignupSetting(instance, env)

    @provide
    def get_notification_mailer(self, sender: IMailSender) -> INotificationMailer:
        return SmtpNotificationMailer(sender, settings.auth.public_url)

    @provide
    def get_notifier(
        self, notifications: INotificationRepository, users: IUserRepository, mailer: INotificationMailer
    ) -> INotifier:
        return Notifier(notifications, users, mailer)

    @provide
    def get_wait_expirer(self, queue: IJobQueue) -> IPersonalWaitExpirer:
        return queue

    # «Входящие»

    @provide
    def get_list_notifications_uc(self, notifications: INotificationRepository) -> ListNotificationsUC:
        return ListNotificationsUC(notifications)

    @provide
    def get_mark_notifications_uc(self, notifications: INotificationRepository) -> MarkNotificationsReadUC:
        return MarkNotificationsReadUC(notifications)

    @provide
    def get_purge_notifications_uc(self, notifications: INotificationRepository) -> PurgeNotificationsUC:
        return PurgeNotificationsUC(notifications)

    @provide
    def get_inbox_summary_uc(
        self,
        notifications: INotificationRepository,
        invitations: IProjectInvitationRepository,
        transfers: IProjectTransferRepository,
        requests: IAccessRequestRepository,
    ) -> InboxSummaryUC:
        return InboxSummaryUC(notifications, invitations, transfers, requests)

    # Приглашения

    @provide
    def get_create_invitation_uc(
        self,
        invitations: IProjectInvitationRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        acl: PostgresProjectAclRepository,
        directory: IProjectAccessDirectory,
        member_roles: IProjectMemberLookup,
        personas: IProjectPersonas,
        orgs: IOrgRepository,
        auth_settings: AuthSettingsService,
        registration_invites: IRegistrationInviteRepository,
        notifier: INotifier,
        mailer: INotificationMailer,
        signup: ProjectInviteSignupSetting,
    ) -> CreateInvitationUC:
        return CreateInvitationUC(
            invitations, cards, users, audit, uow,
            acl=acl, directory=directory, members=member_roles, personas=personas, orgs=orgs,
            auth_settings=auth_settings, registration_invites=registration_invites, notifier=notifier,
            mailer=mailer, signup_allowed=signup, public_url=settings.auth.public_url,
        )  # fmt: skip

    @provide
    def get_resend_invitation_uc(
        self,
        invitations: IProjectInvitationRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        acl: PostgresProjectAclRepository,
        registration_invites: IRegistrationInviteRepository,
        notifier: INotifier,
        mailer: INotificationMailer,
    ) -> ResendInvitationUC:
        return ResendInvitationUC(
            invitations, cards, users, audit, uow, acl=acl, registration_invites=registration_invites,
            notifier=notifier, mailer=mailer, public_url=settings.auth.public_url,
        )  # fmt: skip

    @provide
    def get_revoke_invitation_uc(
        self,
        invitations: IProjectInvitationRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        acl: PostgresProjectAclRepository,
        registration_invites: IRegistrationInviteRepository,
    ) -> RevokeInvitationUC:
        return RevokeInvitationUC(
            invitations, cards, users, audit, uow, acl=acl, registration_invites=registration_invites
        )

    @provide
    def get_list_project_invitations_uc(self, invitations: IProjectInvitationRepository) -> ListProjectInvitationsUC:
        return ListProjectInvitationsUC(invitations)

    @provide
    def get_attach_invitations_uc(
        self,
        invitations: IProjectInvitationRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        notifier: INotifier,
    ) -> AttachInvitationsByEmailUC:
        return AttachInvitationsByEmailUC(invitations, cards, users, audit, uow, notifier=notifier)

    @provide
    def get_email_hook(self, attach: AttachInvitationsByEmailUC) -> IEmailVerifiedHook:
        return attach

    @provide
    def get_list_my_invitations_uc(
        self, invitations: IProjectInvitationRepository, attach: AttachInvitationsByEmailUC, users: IUserRepository
    ) -> ListMyInvitationsUC:
        return ListMyInvitationsUC(invitations, attach, users)

    @provide
    def get_accept_invitation_uc(
        self,
        invitations: IProjectInvitationRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        members: IProjectMemberRepository,
        member_roles: IProjectMemberLookup,
        notifier: INotifier,
    ) -> AcceptInvitationUC:
        return AcceptInvitationUC(
            invitations, cards, users, audit, uow, members=members, member_roles=member_roles, notifier=notifier
        )

    @provide
    def get_decline_invitation_uc(
        self,
        invitations: IProjectInvitationRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        members: IProjectMemberRepository,
        member_roles: IProjectMemberLookup,
        notifier: INotifier,
    ) -> DeclineInvitationUC:
        return DeclineInvitationUC(
            invitations, cards, users, audit, uow, members=members, member_roles=member_roles, notifier=notifier
        )

    @provide
    def get_accept_invitation_token_uc(
        self,
        invitations: IProjectInvitationRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        members: IProjectMemberRepository,
        member_roles: IProjectMemberLookup,
        notifier: INotifier,
    ) -> AcceptInvitationTokenUC:
        return AcceptInvitationTokenUC(
            invitations, cards, users, audit, uow, members=members, member_roles=member_roles, notifier=notifier
        )

    @provide
    def get_preview_invitation_uc(
        self,
        invitations: IProjectInvitationRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> PreviewInvitationTokenUC:
        return PreviewInvitationTokenUC(invitations, cards, users, audit, uow)

    # Запросы доступа

    @provide
    def get_create_access_request_uc(
        self,
        requests: IAccessRequestRepository,
        cards: IProjectCards,
        acl: PostgresProjectAclRepository,
        notifier: INotifier,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> CreateAccessRequestUC:
        return CreateAccessRequestUC(requests, cards, acl, notifier, audit, uow)

    @provide
    def get_list_access_requests_uc(self, requests: IAccessRequestRepository) -> ListAccessRequestsUC:
        return ListAccessRequestsUC(requests)

    @provide
    def get_approve_access_request_uc(
        self,
        requests: IAccessRequestRepository,
        cards: IProjectCards,
        acl: PostgresProjectAclRepository,
        members: IProjectMemberRepository,
        member_roles: IProjectMemberLookup,
        personas: IProjectPersonas,
        users: IUserRepository,
        notifier: INotifier,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> ApproveAccessRequestUC:
        return ApproveAccessRequestUC(
            requests, cards, acl, members, member_roles, personas, users, notifier, audit, uow
        )

    @provide
    def get_deny_access_request_uc(
        self,
        requests: IAccessRequestRepository,
        cards: IProjectCards,
        acl: PostgresProjectAclRepository,
        members: IProjectMemberRepository,
        member_roles: IProjectMemberLookup,
        personas: IProjectPersonas,
        users: IUserRepository,
        notifier: INotifier,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> DenyAccessRequestUC:
        return DenyAccessRequestUC(requests, cards, acl, members, member_roles, personas, users, notifier, audit, uow)

    @provide
    def get_list_my_access_requests_uc(self, requests: IAccessRequestRepository) -> ListMyAccessRequestsUC:
        return ListMyAccessRequestsUC(requests)

    @provide
    def get_cancel_access_request_uc(
        self, requests: IAccessRequestRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> CancelAccessRequestUC:
        return CancelAccessRequestUC(requests, audit, uow)

    # Передача владения

    @provide
    def get_apply_transfer_uc(
        self,
        transfers: IProjectTransferRepository,
        cards: IProjectCards,
        members: IProjectMemberRepository,
        notifier: INotifier,
        audit: IAuditLog,
    ) -> ApplyTransferUC:
        return ApplyTransferUC(transfers, cards, members, notifier, audit)

    @provide
    def get_start_transfer_uc(
        self,
        transfers: IProjectTransferRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        orgs: IOrgRepository,
        apply: ApplyTransferUC,
        notifier: INotifier,
        queue: IPersonalWaitExpirer,
    ) -> StartTransferUC:
        return StartTransferUC(
            transfers, cards, users, audit, uow, orgs=orgs, apply=apply, notifier=notifier, queue=queue
        )

    @provide
    def get_cancel_transfer_uc(
        self,
        transfers: IProjectTransferRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> CancelTransferUC:
        return CancelTransferUC(transfers, cards, users, audit, uow)

    @provide
    def get_transfer_state_uc(
        self,
        transfers: IProjectTransferRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> GetTransferStateUC:
        return GetTransferStateUC(transfers, cards, users, audit, uow)

    @provide
    def get_my_transfers_uc(
        self,
        transfers: IProjectTransferRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> ListMyTransfersUC:
        return ListMyTransfersUC(transfers, cards, users, audit, uow)

    @provide
    def get_accept_transfer_uc(
        self,
        transfers: IProjectTransferRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        apply: ApplyTransferUC,
        notifier: INotifier,
        queue: IPersonalWaitExpirer,
    ) -> AcceptTransferUC:
        return AcceptTransferUC(transfers, cards, users, audit, uow, apply=apply, notifier=notifier, queue=queue)

    @provide
    def get_decline_transfer_uc(
        self,
        transfers: IProjectTransferRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        apply: ApplyTransferUC,
        notifier: INotifier,
    ) -> DeclineTransferUC:
        return DeclineTransferUC(transfers, cards, users, audit, uow, apply=apply, notifier=notifier)

    # Сценарии других зон, куда трек дописывает своё

    @provide(override=True)
    def get_remove_project_member_uc(
        self,
        members: IProjectMemberRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        notifier: INotifier,
        cards: IProjectCards,
        users: IUserRepository,
    ) -> RemoveProjectMemberUC:
        return RemoveProjectMemberUC(members, audit, uow, notifier=notifier, cards=cards, users=users)

    @provide(override=True)
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
        hook: IEmailVerifiedHook,
    ) -> RegisterUC:
        return RegisterUC(
            users, credentials, auth_tokens, invites, auth_settings, delivery, hasher, audit, uow,
            public_url=settings.auth.public_url, email_hook=hook,
        )  # fmt: skip

    @provide(override=True)
    def get_verify_email_uc(
        self,
        users: IUserRepository,
        auth_tokens: IAuthTokenRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        hook: IEmailVerifiedHook,
    ) -> VerifyEmailUC:
        return VerifyEmailUC(users, auth_tokens, audit, uow, email_hook=hook)

    @provide(override=True)
    def get_confirm_email_change_uc(
        self,
        users: IUserRepository,
        auth_tokens: IAuthTokenRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        hook: IEmailVerifiedHook,
    ) -> ConfirmEmailChangeUC:
        return ConfirmEmailChangeUC(users, auth_tokens, audit, uow, email_hook=hook)

    @provide(override=True)
    def get_auth_cleanup_service(
        self,
        sessions: ISessionRepository,
        auth_tokens: IAuthTokenRepository,
        outbox: IMailOutboxRepository,
        attempts: ILoginAttemptRepository,
        notifications: INotificationRepository,
    ) -> AuthCleanupService:
        return AuthCleanupService(sessions, auth_tokens, outbox, attempts, notifications=notifications)
