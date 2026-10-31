"""Артефакты проекта на сервере: PDF, выгруженные локальной Студией после её сборки."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.artifacts.entities import PdfUploadLimits
from hse_doc_studio.core.artifacts.protocols import IProjectArtifactRepository
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.projects.usage import IProjectQuota
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.storage import IObjectStore
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.artifacts import PostgresProjectArtifactRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.use_cases.artifacts.pdf import (
    DeleteProjectArtifactUC,
    ListProjectArtifactsUC,
    OpenProjectArtifactUC,
    UploadProjectPdfUC,
)


class ServerArtifactsProvider(Provider):
    scope = Scope.APP

    @provide
    def get_artifact_repository(self, sessions: SessionProvider) -> IProjectArtifactRepository:
        return PostgresProjectArtifactRepository(sessions)

    @provide(scope=Scope.REQUEST)
    def get_upload_pdf(  # noqa: PLR0913 — порты одного сценария
        self,
        acl: IProjectAclRepository,
        project_repo: IProjectRepository,
        project_index: IProjectIndexRepository,
        artifacts: IProjectArtifactRepository,
        objects: IObjectStore,
        audit: IAuditLog,
        uow: IUnitOfWork,
        quota: IProjectQuota,
    ) -> UploadProjectPdfUC:
        cfg = settings.artifacts
        limits = PdfUploadLimits(max_bytes=cfg.max_pdf_bytes, keep_per_document=cfg.keep_per_document)
        return UploadProjectPdfUC(acl, project_repo, project_index, artifacts, objects, audit, uow, limits, quota)

    @provide
    def get_list_artifacts(self, artifacts: IProjectArtifactRepository) -> ListProjectArtifactsUC:
        return ListProjectArtifactsUC(artifacts)

    @provide
    def get_open_artifact(self, artifacts: IProjectArtifactRepository, objects: IObjectStore) -> OpenProjectArtifactUC:
        return OpenProjectArtifactUC(artifacts, objects)

    @provide
    def get_delete_artifact(
        self, artifacts: IProjectArtifactRepository, objects: IObjectStore, audit: IAuditLog, uow: IUnitOfWork
    ) -> DeleteProjectArtifactUC:
        return DeleteProjectArtifactUC(artifacts, objects, audit, uow)
