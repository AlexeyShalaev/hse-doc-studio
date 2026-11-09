"""Провайдер маршрутов подписания (серверный режим): хранилище в Postgres, факты, уведомления, задачи «На подпись».

Локальная Студия маршрутов не хранит (docs/design/signing-route.md, раздел 6.9): порта там нет, сценарии маршрута
подключаются только в `MODE=server`.
"""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.invitations.protocols import IInvitationAcceptedHook, INotifier
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.signatures.ports import ISignerPlateData
from hse_doc_studio.core.signing_route.ports import IRouteFacts, IRouteLabels, ISigningNotifier, ISigningTaskCounter
from hse_doc_studio.core.signing_route.repositories import ISigningRouteRepository
from hse_doc_studio.infra.db.repositories.signing_routes import SqlSigningRouteRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.use_cases.signing_route.context import ProjectRouteContext
from hse_doc_studio.use_cases.signing_route.delivery import SigningNotifier
from hse_doc_studio.use_cases.signing_route.invitations import SigningRouteInviteeHook
from hse_doc_studio.use_cases.signing_route.tasks import ListSigningTasksUC


class ServerSigningRoutesProvider(Provider):
    scope = Scope.APP

    @provide
    def get_signing_route_repository(self, sessions: SessionProvider) -> ISigningRouteRepository:
        return SqlSigningRouteRepository(sessions)

    @provide
    def get_route_context(  # noqa: PLR0913 — порты перечислены явно
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        templates: ITemplateRepository,
        signatures: ISignatureRepository,
        template_service: ProjectTemplateService,
        plates: ISignerPlateData,
    ) -> ProjectRouteContext:
        return ProjectRouteContext(project_repo, project_index_repo, templates, signatures, template_service, plates)

    @provide
    def get_route_facts(self, context: ProjectRouteContext) -> IRouteFacts:
        return context

    @provide
    def get_route_labels(self, context: ProjectRouteContext) -> IRouteLabels:
        return context

    @provide
    def get_signing_notifier(
        self, notifier: INotifier, users: IUserRepository, labels: IRouteLabels
    ) -> ISigningNotifier:
        return SigningNotifier(notifier, users, labels)

    @provide
    def get_list_signing_tasks_uc(
        self, routes: ISigningRouteRepository, facts: IRouteFacts, labels: IRouteLabels, users: IUserRepository
    ) -> ListSigningTasksUC:
        return ListSigningTasksUC(routes, facts, labels, users)

    @provide
    def get_signing_task_counter(self, tasks: ListSigningTasksUC) -> ISigningTaskCounter:
        return tasks

    @provide
    def get_signing_route_invitee_hook(
        self, routes: ISigningRouteRepository, facts: IRouteFacts, notifier: ISigningNotifier
    ) -> IInvitationAcceptedHook:
        return SigningRouteInviteeHook(routes, facts, notifier)
