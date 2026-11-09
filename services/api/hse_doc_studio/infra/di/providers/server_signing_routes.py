"""Провайдер маршрутов подписания (серверный режим): хранилище в Postgres, люди проекта, сценарии автора.

Локальная Студия маршрутов не хранит (docs/design/signing-route.md, раздел 6.9): порта там нет, сценарии маршрута
подключаются только в `MODE=server`. Уведомления маршрута до среза R8 никуда не доставляются
(`SilentSigningNotifier`); R8 подменяет здесь только `ISigningNotifier`.
"""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.core.access.checker import IProjectAccessChecker
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ISigningIdentityRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.signatures.key_policy import ISigningKeyPolicy
from hse_doc_studio.core.signatures.ports import (
    IPadesSigner,
    ISignatureAudit,
    ISignerPlateData,
    ISignerScope,
    ITrustMaterialProvider,
)
from hse_doc_studio.core.signing_route.ports import IRoutePeople, ISigningNotifier
from hse_doc_studio.core.signing_route.repositories import ISigningRouteRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.signing_route_people import PostgresRoutePeople
from hse_doc_studio.infra.db.repositories.signing_routes import SqlSigningRouteRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC
from hse_doc_studio.use_cases.signatures._studio_signer import StudioSigner
from hse_doc_studio.use_cases.signatures.default_key import DefaultSigningKey
from hse_doc_studio.use_cases.signatures.freeze_pdf import FreezePdfUC
from hse_doc_studio.use_cases.signing_route.author import (
    SigningRouteControl,
    SigningRouteDrafts,
    SigningRouteSending,
)
from hse_doc_studio.use_cases.signing_route.effects import RouteFileEffects
from hse_doc_studio.use_cases.signing_route.facts import RouteFactsLoader
from hse_doc_studio.use_cases.signing_route.key_signer import RouteKeySigner
from hse_doc_studio.use_cases.signing_route.notifier import SilentSigningNotifier
from hse_doc_studio.use_cases.signing_route.point import RoutePointLoader
from hse_doc_studio.use_cases.signing_route.scenario import RouteServices


class ServerSigningRoutesProvider(Provider):
    scope = Scope.APP

    @provide
    def get_signing_route_repository(self, sessions: SessionProvider) -> ISigningRouteRepository:
        return SqlSigningRouteRepository(sessions)

    @provide
    def get_signing_notifier(self) -> ISigningNotifier:
        return SilentSigningNotifier()

    @provide(scope=Scope.REQUEST)
    def get_route_people(self, sessions: SessionProvider, acl: IProjectAclRepository) -> IRoutePeople:
        return PostgresRoutePeople(sessions, acl)

    @provide(scope=Scope.REQUEST)
    def get_route_points(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
    ) -> RoutePointLoader:
        return RoutePointLoader(project_repo, project_index_repo, template_repo, template_service)

    @provide(scope=Scope.REQUEST)
    def get_route_facts(
        self,
        points: RoutePointLoader,
        signature_repo: ISignatureRepository,
        plate_data: ISignerPlateData,
        people: IRoutePeople,
    ) -> RouteFactsLoader:
        return RouteFactsLoader(points, signature_repo, plate_data, people)

    @provide(scope=Scope.REQUEST)
    def get_route_effects(self, signature_repo: ISignatureRepository, freeze_uc: FreezePdfUC) -> RouteFileEffects:
        return RouteFileEffects(signature_repo, freeze_uc)

    @provide(scope=Scope.REQUEST)
    def get_route_services(
        self,
        routes: ISigningRouteRepository,
        points: RoutePointLoader,
        facts: RouteFactsLoader,
        effects: RouteFileEffects,
        people: IRoutePeople,
        notifier: ISigningNotifier,
        uow: IUnitOfWork,
        access: IProjectAccessChecker,
    ) -> RouteServices:
        return RouteServices(routes, points, facts, effects, people, notifier, uow, access)

    @provide(scope=Scope.REQUEST)
    def get_route_key_signer(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        signature_repo: ISignatureRepository,
        signing_identity_repo: ISigningIdentityRepository,
        keyring: GpgKeyring,
        dispatcher: IJobDispatcher,
        trust_provider: ITrustMaterialProvider,
        pades: IPadesSigner,
        signer_scope: ISignerScope,
        audit: ISignatureAudit,
        key_policy: ISigningKeyPolicy,
        default_key: DefaultSigningKey,
        access: IProjectAccessChecker,
    ) -> RouteKeySigner:
        signer = StudioSigner(
            signing_identity_repo, keyring, dispatcher, trust_provider, pades, signer_scope, audit, key_policy
        )
        return RouteKeySigner(
            GetProjectUC(project_repo, project_index_repo),
            template_repo,
            template_service,
            signature_repo,
            signer,
            default_key,
            access,
        )

    @provide(scope=Scope.REQUEST)
    def get_route_drafts(self, services: RouteServices) -> SigningRouteDrafts:
        return SigningRouteDrafts(services)

    @provide(scope=Scope.REQUEST)
    def get_route_sending(self, services: RouteServices, signer: RouteKeySigner) -> SigningRouteSending:
        return SigningRouteSending(services, signer)

    @provide(scope=Scope.REQUEST)
    def get_route_control(self, services: RouteServices) -> SigningRouteControl:
        return SigningRouteControl(services)
