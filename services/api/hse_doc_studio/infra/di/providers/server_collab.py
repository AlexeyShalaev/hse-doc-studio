"""Провайдер этапа 5 (серверный режим): ревью-комментарии и совместная правка в реальном времени.

Подключается последним: подменяет замок папки проекта замком, который сбрасывает комнаты Yjs на диск перед
операциями над папкой (синхронизация, снимки, приём push).
"""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.checker import IProjectAccessChecker
from hse_doc_studio.core.access.repositories import IProjectAccessDirectory
from hse_doc_studio.core.collab.ports import ITextStore
from hse_doc_studio.core.invitations.protocols import INotifier, IProjectCards
from hse_doc_studio.core.projects.usage import IProjectQuota
from hse_doc_studio.core.repositories import (
    IFileRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.review.protocols import IReviewEvents, IReviewRepository
from hse_doc_studio.core.template_update.protocols import IUpdateJournalRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.core.vcs.protocols import IVcsEditThrottle, IVcsFolderLocks, IVcsService
from hse_doc_studio.infra.collab.locks import CollabAwareFolderLocks, FlushHub
from hse_doc_studio.infra.collab.manager import CollabManager
from hse_doc_studio.infra.collab.state_store import YStateStore
from hse_doc_studio.infra.db.repositories.project_acl import PostgresProjectAclRepository
from hse_doc_studio.infra.db.repositories.review import PostgresReviewRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.vcs.folder_locks import VcsFolderLocks
from hse_doc_studio.use_cases.collab.access import AuthorizeCollabUC
from hse_doc_studio.use_cases.collab.store import ProjectTextStore
from hse_doc_studio.use_cases.files.put_file import PutFileUC
from hse_doc_studio.use_cases.projects.get_project_access import GetProjectAccessUC, ProjectAccessService
from hse_doc_studio.use_cases.review.threads import (
    CreateReviewThreadUC,
    DeleteReviewCommentUC,
    EditReviewCommentUC,
    ListMentionCandidatesUC,
    ListReviewThreadsUC,
    ReplyReviewThreadUC,
    SetReviewThreadStatusUC,
)


class ServerCollabProvider(Provider):
    scope = Scope.APP

    # Совместная правка

    @provide
    def get_flush_hub(self) -> FlushHub:
        return FlushHub()

    @provide(override=True)
    def get_vcs_folder_locks(self, hub: FlushHub) -> IVcsFolderLocks:
        return CollabAwareFolderLocks(VcsFolderLocks(), hub)

    @provide
    def get_text_store(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        vcs: IVcsService,
        vcs_locks: IVcsFolderLocks,
        vcs_throttle: IVcsEditThrottle,
        quota: IProjectQuota,
    ) -> ITextStore:
        put_file = PutFileUC(project_repo, project_index_repo, file_repo, vcs, vcs_locks, vcs_throttle, quota)
        return ProjectTextStore(project_repo, project_index_repo, file_repo, put_file, vcs, vcs_locks)

    @provide
    def get_collab_manager(self, store: ITextStore, hub: FlushHub) -> CollabManager:
        manager = CollabManager(store, YStateStore(settings.data_dir.expanduser() / "collab"), settings.collab)
        hub.attach(manager)
        return manager

    @provide
    def get_review_events(self, manager: CollabManager) -> IReviewEvents:
        return manager

    @provide
    def get_authorize_collab_uc(
        self,
        access: IProjectAccessChecker,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        journal_repo: IUpdateJournalRepository,
    ) -> AuthorizeCollabUC:
        project_access = GetProjectAccessUC(
            project_repo, project_index_repo, ProjectAccessService(template_repo, journal_repo)
        )
        return AuthorizeCollabUC(access, project_access)

    # Ревью-комментарии

    @provide
    def get_review_repository(self, sessions: SessionProvider) -> IReviewRepository:
        return PostgresReviewRepository(sessions)

    @provide
    def get_list_review_threads_u_c(
        self,
        reviews: IReviewRepository,
        access: IProjectAccessChecker,
        acls: PostgresProjectAclRepository,
        cards: IProjectCards,
        directory: IProjectAccessDirectory,
        notifier: INotifier,
        events: IReviewEvents,
        store: ITextStore,
        uow: IUnitOfWork,
    ) -> ListReviewThreadsUC:
        return ListReviewThreadsUC(reviews, access, acls, cards, directory, notifier, events, store, uow)

    @provide
    def get_create_review_thread_u_c(
        self,
        reviews: IReviewRepository,
        access: IProjectAccessChecker,
        acls: PostgresProjectAclRepository,
        cards: IProjectCards,
        directory: IProjectAccessDirectory,
        notifier: INotifier,
        events: IReviewEvents,
        store: ITextStore,
        uow: IUnitOfWork,
    ) -> CreateReviewThreadUC:
        return CreateReviewThreadUC(reviews, access, acls, cards, directory, notifier, events, store, uow)

    @provide
    def get_reply_review_thread_u_c(
        self,
        reviews: IReviewRepository,
        access: IProjectAccessChecker,
        acls: PostgresProjectAclRepository,
        cards: IProjectCards,
        directory: IProjectAccessDirectory,
        notifier: INotifier,
        events: IReviewEvents,
        store: ITextStore,
        uow: IUnitOfWork,
    ) -> ReplyReviewThreadUC:
        return ReplyReviewThreadUC(reviews, access, acls, cards, directory, notifier, events, store, uow)

    @provide
    def get_edit_review_comment_u_c(
        self,
        reviews: IReviewRepository,
        access: IProjectAccessChecker,
        acls: PostgresProjectAclRepository,
        cards: IProjectCards,
        directory: IProjectAccessDirectory,
        notifier: INotifier,
        events: IReviewEvents,
        store: ITextStore,
        uow: IUnitOfWork,
    ) -> EditReviewCommentUC:
        return EditReviewCommentUC(reviews, access, acls, cards, directory, notifier, events, store, uow)

    @provide
    def get_delete_review_comment_u_c(
        self,
        reviews: IReviewRepository,
        access: IProjectAccessChecker,
        acls: PostgresProjectAclRepository,
        cards: IProjectCards,
        directory: IProjectAccessDirectory,
        notifier: INotifier,
        events: IReviewEvents,
        store: ITextStore,
        uow: IUnitOfWork,
    ) -> DeleteReviewCommentUC:
        return DeleteReviewCommentUC(reviews, access, acls, cards, directory, notifier, events, store, uow)

    @provide
    def get_set_review_thread_status_u_c(
        self,
        reviews: IReviewRepository,
        access: IProjectAccessChecker,
        acls: PostgresProjectAclRepository,
        cards: IProjectCards,
        directory: IProjectAccessDirectory,
        notifier: INotifier,
        events: IReviewEvents,
        store: ITextStore,
        uow: IUnitOfWork,
    ) -> SetReviewThreadStatusUC:
        return SetReviewThreadStatusUC(reviews, access, acls, cards, directory, notifier, events, store, uow)

    @provide
    def get_list_mention_candidates_u_c(
        self,
        reviews: IReviewRepository,
        access: IProjectAccessChecker,
        acls: PostgresProjectAclRepository,
        cards: IProjectCards,
        directory: IProjectAccessDirectory,
        notifier: INotifier,
        events: IReviewEvents,
        store: ITextStore,
        uow: IUnitOfWork,
    ) -> ListMentionCandidatesUC:
        return ListMentionCandidatesUC(reviews, access, acls, cards, directory, notifier, events, store, uow)
