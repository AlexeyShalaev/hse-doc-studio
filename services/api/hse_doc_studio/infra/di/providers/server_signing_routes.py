"""Провайдер маршрутов подписания (серверный режим): хранилище в Postgres, факты, уведомления, задачи «На подпись»,
люди проекта, сценарии автора и подписанта, сторожа и сверка с проектом, напоминание о сроке контрольной точки.

Локальная Студия маршрутов не хранит (docs/design/signing-route.md, раздел 6.9): порта там нет, сценарии маршрута
подключаются только в `MODE=server`.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from dishka import AsyncContainer, Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.checker import IProjectAccessChecker
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.identity.protocols import IAuditLog, IUserRepository
from hse_doc_studio.core.invitations.protocols import IInvitationAcceptedHook, INotificationMailer, INotifier
from hse_doc_studio.core.jobs.artifacts import IArtifactStore
from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.projects.volume import IProjectVolume
from hse_doc_studio.core.repositories import (
    ICompileRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ISigningIdentityRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.signatures.key_policy import ISigningKeyPolicy
from hse_doc_studio.core.signatures.ports import (
    IMarkMeasure,
    IOpenPgpKeyImporter,
    IPadesSigner,
    ISignatureAudit,
    ISignerPlateData,
    ISignerScope,
    ITrustMaterialProvider,
)
from hse_doc_studio.core.signatures.signer_profile import IPublicKeyReader, ISignerProfileRepository
from hse_doc_studio.core.signing_route.ports import (
    IRouteFacts,
    IRouteLabels,
    IRoutePeople,
    IRouteWatch,
    ISigningNotifier,
    ISigningRouteGate,
    ISigningTaskCounter,
)
from hse_doc_studio.core.signing_route.reminders import ReminderPolicy
from hse_doc_studio.core.signing_route.repositories import ISigningRouteRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.checkpoint_reminders import PostgresCheckpointReminderStore
from hse_doc_studio.infra.db.repositories.signing_route_people import PostgresRoutePeople
from hse_doc_studio.infra.db.repositories.signing_routes import SqlSigningRouteRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring
from hse_doc_studio.infra.signatures.pdf_stamper import PdfStamper
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC
from hse_doc_studio.use_cases.projects.invitations import ResendInvitationUC
from hse_doc_studio.use_cases.signatures._studio_signer import StudioSigner
from hse_doc_studio.use_cases.signatures.default_key import DefaultSigningKey
from hse_doc_studio.use_cases.signatures.freeze_pdf import FreezePdfUC
from hse_doc_studio.use_cases.signatures.upload_signature_png import UploadSignaturePngUC
from hse_doc_studio.use_cases.signer_profile.profile import SaveProfileImageUC
from hse_doc_studio.use_cases.signing_route.audit import AuditedSigningRoutes, SigningRouteAudit
from hse_doc_studio.use_cases.signing_route.author import (
    SigningRouteControl,
    SigningRouteDrafts,
    SigningRouteSending,
)
from hse_doc_studio.use_cases.signing_route.delivery import SigningNotifier
from hse_doc_studio.use_cases.signing_route.effects import RouteFileEffects
from hse_doc_studio.use_cases.signing_route.facts import ProjectRouteFacts, RouteFactsLoader
from hse_doc_studio.use_cases.signing_route.gate import SigningRouteGate
from hse_doc_studio.use_cases.signing_route.invitations import SigningRouteInviteeHook
from hse_doc_studio.use_cases.signing_route.key_signer import RouteKeySigner
from hse_doc_studio.use_cases.signing_route.migration import BuildArchive, RouteMigration
from hse_doc_studio.use_cases.signing_route.pinning import RoutePinning
from hse_doc_studio.use_cases.signing_route.point import RoutePointLoader
from hse_doc_studio.use_cases.signing_route.reconcile import RouteReconciler
from hse_doc_studio.use_cases.signing_route.reminders import SigningReminderSweeper, SigningRouteReminding
from hse_doc_studio.use_cases.signing_route.scenario import RouteServices
from hse_doc_studio.use_cases.signing_route.signer import SignerTools, SigningTaskScenario
from hse_doc_studio.use_cases.signing_route.skipping import SigningRouteSkipping
from hse_doc_studio.use_cases.signing_route.tasks import ListSigningTasksUC
from hse_doc_studio.use_cases.signing_route.watch import RouteWatch, WatchedSignatureRepository
from hse_doc_studio.use_cases.submission.checkpoint_reminders import CheckpointReminderSweeper


class ServerSigningRoutesProvider(Provider):
    scope = Scope.APP

    @provide
    def get_signing_route_audit(self, audit: IAuditLog) -> SigningRouteAudit:
        return SigningRouteAudit(audit)

    @provide
    def get_signing_route_repository(
        self, sessions: SessionProvider, audit: SigningRouteAudit
    ) -> ISigningRouteRepository:
        # События истории маршрута попадают в журнал аудита вместе с записью маршрута (раздел 6.7).
        return AuditedSigningRoutes(SqlSigningRouteRepository(sessions), audit)

    @provide
    def get_route_context(  # noqa: PLR0913 — порты перечислены явно
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        templates: ITemplateRepository,
        signatures: ISignatureRepository,
        template_service: ProjectTemplateService,
        plates: ISignerPlateData,
    ) -> ProjectRouteFacts:
        return ProjectRouteFacts(project_repo, project_index_repo, templates, signatures, template_service, plates)

    @provide
    def get_route_facts(self, context: ProjectRouteFacts) -> IRouteFacts:
        return context

    @provide
    def get_route_labels(self, context: ProjectRouteFacts) -> IRouteLabels:
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

    @provide
    def get_signing_reminder_sweeper(
        self, routes: ISigningRouteRepository, facts: IRouteFacts, notifier: ISigningNotifier, uow: IUnitOfWork
    ) -> SigningReminderSweeper:
        """Автонапоминания (срез R11): периодическая задача лидера, правила из настроек `signing_route`."""
        cfg = settings.signing_route
        policy = ReminderPolicy(
            before_deadline=timedelta(hours=cfg.reminder_before_deadline_hours),
            waiting=timedelta(days=cfg.reminder_waiting_days),
            max_auto=cfg.reminder_max_auto,
        )
        return SigningReminderSweeper(routes, facts, notifier, uow, policy)

    @provide
    def get_checkpoint_reminder_sweeper(
        self, sessions: SessionProvider, notifier: INotifier, uow: IUnitOfWork
    ) -> CheckpointReminderSweeper:
        """Напоминание автору о сроке контрольной точки (16.7, срез R29): задача лидера, как автонапоминания
        маршрута; срок за сколько суток из настроек `checkpoint`."""
        return CheckpointReminderSweeper(
            PostgresCheckpointReminderStore(sessions), notifier, uow, days=settings.checkpoint.reminder_days
        )

    # --- сценарии автора (срез R5) ---

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
    def get_route_facts_loader(
        self,
        points: RoutePointLoader,
        signature_repo: ISignatureRepository,
        plate_data: ISignerPlateData,
        people: IRoutePeople,
    ) -> RouteFactsLoader:
        return RouteFactsLoader(points, signature_repo, plate_data, people)

    @provide(scope=Scope.REQUEST)
    def get_route_effects(
        self,
        signature_repo: ISignatureRepository,
        freeze_uc: FreezePdfUC,
        profiles: ISignerProfileRepository,
        key_importer: IOpenPgpKeyImporter,
    ) -> RouteFileEffects:
        return RouteFileEffects(signature_repo, freeze_uc, profiles, key_importer)

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
        audit: SigningRouteAudit,
        migration: RouteMigration,
    ) -> RouteServices:
        return RouteServices(
            routes,
            points,
            facts,
            effects,
            people,
            notifier,
            uow,
            access,
            audit=audit,
            migration=migration,
        )

    @provide(scope=Scope.REQUEST)
    def get_route_migration(
        self,
        signature_repo: ISignatureRepository,
        template_service: ProjectTemplateService,
        compiles: ICompileRepository,
        artifacts: IArtifactStore,
    ) -> RouteMigration:
        # Перенос маршрутов 0.20.0 (12.11): согласованная сборка из текущей или из архива сборок.
        return RouteMigration(RoutePinning(signature_repo, template_service), BuildArchive(compiles, artifacts))

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

    @provide(scope=Scope.REQUEST)
    def get_route_skipping(self, services: RouteServices) -> SigningRouteSkipping:
        return SigningRouteSkipping(services)

    @provide(scope=Scope.REQUEST)
    def get_route_reminding(
        self,
        services: RouteServices,
        invitations: ResendInvitationUC,
        users: IUserRepository,
        mailer: INotificationMailer,
    ) -> SigningRouteReminding:
        return SigningRouteReminding(services, invitations, users, mailer, public_url=settings.auth.public_url)

    # --- сценарии подписанта (срез R6) ---

    @provide
    def get_mark_measure(self, stamper: PdfStamper) -> IMarkMeasure:
        return stamper

    @provide(scope=Scope.REQUEST)
    def get_signer_tools(
        self,
        signature_repo: ISignatureRepository,
        upload_png: UploadSignaturePngUC,
        profile_image: SaveProfileImageUC,
        key_reader: IPublicKeyReader,
        key_importer: IOpenPgpKeyImporter,
        measure: IMarkMeasure,
    ) -> SignerTools:
        return SignerTools(signature_repo, upload_png, profile_image, key_reader, key_importer, measure)

    @provide(scope=Scope.REQUEST)
    def get_signing_task_scenario(
        self, services: RouteServices, signer: RouteKeySigner, tools: SignerTools
    ) -> SigningTaskScenario:
        return SigningTaskScenario(services, signer, tools)

    @provide(scope=Scope.REQUEST)
    def get_signing_route_gate(self, services: RouteServices) -> ISigningRouteGate:
        # Перекрывает локальный `NoSigningRoutes`: КриптоПро и готовая подпись идут в очередь маршрута (6.10).
        return SigningRouteGate(services)

    # --- сторожа и сверка с проектом (срез R7) ---

    @provide(scope=Scope.REQUEST)
    def get_route_reconciler(self, services: RouteServices) -> RouteReconciler:
        return RouteReconciler(services)

    @provide
    def get_route_watch_scheduler(self, container: AsyncContainer) -> RouteWatch:
        """Очередь сверок: по задаче на проект, каждая в своём запросном окружении и своей транзакции."""

        async def reconcile(project_id: UUID) -> None:
            async with container() as scope:
                await (await scope.get(RouteReconciler)).project(project_id)

        return RouteWatch(reconcile)

    @provide(override=True)
    def get_route_watch(self, watch: RouteWatch) -> IRouteWatch:
        return watch

    @provide(override=True)
    def get_signature_repo(self, volume: IProjectVolume, watch: IRouteWatch) -> ISignatureRepository:
        # Хук записи состояния подписей: кто бы ни записал `signatures.json`, маршруты проекта сверяются.
        return WatchedSignatureRepository(JsonSignatureRepository(), volume.id_of, watch)
