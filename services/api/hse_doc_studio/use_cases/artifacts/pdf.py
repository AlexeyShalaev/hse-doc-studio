"""PDF проекта, выгруженные локальной Студией: приём, список, выдача и удаление (docs/design/local-sync.md, P1-P6).

Приём идёт по токену доступа git (маршрут `/git/-/projects/{id}/documents/{doc}/pdf`), чтение и удаление по
обычным правам `/api/v1`. Права принимающего маршрута проверяются здесь же: гард `/api/v1` их не видит.
Побочные эффекты вне БД (объект в хранилище) делаются до записи и убираются, если запись не удалась.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import BinaryIO
from uuid import UUID

import structlog

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.access.paths import scope_path_of_instance_id
from hse_doc_studio.core.access.policy import Decision, decide
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.artifacts.entities import (
    PDF_MAGIC,
    PDF_MEDIA_TYPE,
    ArtifactError,
    ArtifactErrorCode,
    ArtifactKind,
    PdfUploadLimits,
    ProjectArtifact,
    artifact_key,
    is_safe_doc_id,
    safe_file_name,
)
from hse_doc_studio.core.artifacts.protocols import IProjectArtifactRepository
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.storage import ObjectNotFoundError, ObjectStoreError
from hse_doc_studio.core.storage.ports import IObjectStore
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()

AUDIT_UPLOADED = "artifact.pdf_uploaded"
AUDIT_DELETED = "artifact.deleted"
_HASH_CHUNK = 1 << 20


@dataclass(frozen=True)
class PdfUploadMeta:
    """Что клиент сообщает о файле; sha256 сверяется, остальное только подпись записи."""

    sha256: str | None = None
    file_name: str | None = None
    pages: int | None = None
    source_commit: str | None = None
    built_at: datetime | None = None
    client_name: str | None = None


@dataclass(frozen=True)
class PdfUploadResult:
    artifact: ProjectArtifact
    created: bool


def _forbidden() -> ArtifactError:
    return ArtifactError(
        ArtifactErrorCode.forbidden,
        localized_error(
            "Выгружать PDF в этот проект может редактор или владелец (свой документ в командном проекте).",
            "Only an editor or the owner can upload a PDF to this project (own document in a team project).",
        ),
    )


def _not_found() -> ArtifactError:
    return ArtifactError(ArtifactErrorCode.not_found, localized_error("Проект не найден.", "Project not found."))


def _scan(source: BinaryIO) -> tuple[int, str, bytes]:
    """(размер, sha256, первые байты) за один проход; блокирует, вызывающий уводит в поток."""
    source.seek(0)
    digest = hashlib.sha256()
    size = 0
    head = b""
    while chunk := source.read(_HASH_CHUNK):
        if not head:
            head = chunk[: len(PDF_MAGIC)]
        digest.update(chunk)
        size += len(chunk)
    source.seek(0)
    return size, digest.hexdigest(), head


class UploadProjectPdfUC:
    def __init__(  # noqa: PLR0913 — порты одного сценария
        self,
        acl: IProjectAclRepository,
        project_repo: IProjectRepository,
        project_index: IProjectIndexRepository,
        artifacts: IProjectArtifactRepository,
        objects: IObjectStore,
        audit: IAuditLog,
        uow: IUnitOfWork,
        limits: PdfUploadLimits,
    ) -> None:
        self._acl = acl
        self._projects = GetProjectUC(project_repo, project_index)
        self._artifacts = artifacts
        self._objects = objects
        self._audit = audit
        self._uow = uow
        self._limits = limits

    @property
    def max_bytes(self) -> int:
        return self._limits.max_bytes

    def too_large(self) -> ArtifactError:
        limit_mb = self._limits.max_bytes // (1024 * 1024)
        return ArtifactError(
            ArtifactErrorCode.too_large,
            localized_error(f"PDF больше {limit_mb} МБ.", f"The PDF is larger than {limit_mb} MB."),
        )

    async def authorize(self, actor: Actor, project_id: UUID, doc_id: str) -> None:
        """Право загрузить PDF документа: сборка проекта и запись в область документа. Чужому проект не виден."""
        acl = await self._acl.load_for(actor, project_id, include_links=False)
        if acl is None or acl.grant_for(actor) is None:
            raise _not_found()
        scope = scope_path_of_instance_id(doc_id)
        allowed = (
            decide(actor, Action.BUILD_RUN, acl) is Decision.allow
            and decide(actor, Action.FILES_WRITE, acl, scope) is Decision.allow
        )
        if not allowed:
            raise _forbidden()

    async def execute(  # noqa: PLR0913 — запрос и файл
        self, actor: Actor, project_id: UUID, doc_id: str, source: BinaryIO, meta: PdfUploadMeta
    ) -> PdfUploadResult:
        await self.authorize(actor, project_id, doc_id)
        await self._require_document(project_id, doc_id)
        size, sha256, head = await asyncio.to_thread(_scan, source)
        self._validate(size, sha256, head, meta)
        previous = await self._artifacts.latest(project_id, doc_id, ArtifactKind.pdf)
        if previous is not None and previous.sha256 == sha256:
            return PdfUploadResult(previous, created=False)
        artifact = self._new_artifact(actor, project_id, doc_id, size, sha256, meta)
        await self._store(artifact, source)
        try:
            pruned = await self._record(actor, artifact)
        except BaseException:
            await self._discard(artifact.object_key)
            raise
        for old in pruned:
            await self._discard(old.object_key)
        return PdfUploadResult(artifact, created=True)

    async def _require_document(self, project_id: UUID, doc_id: str) -> None:
        project = (await self._projects.execute(GetProjectInput(project_id=project_id))).project
        if not is_safe_doc_id(doc_id) or all(d.id != doc_id for d in project.documents):
            raise ArtifactError(
                ArtifactErrorCode.unknown_document,
                localized_error("В проекте нет такого документа.", "The project has no such document."),
            )

    def _validate(self, size: int, sha256: str, head: bytes, meta: PdfUploadMeta) -> None:
        if size > self._limits.max_bytes:
            raise self.too_large()
        if head != PDF_MAGIC:
            raise ArtifactError(
                ArtifactErrorCode.not_pdf, localized_error("Файл не похож на PDF.", "The file is not a PDF.")
            )
        if meta.sha256 is not None and meta.sha256.lower() != sha256:
            raise ArtifactError(
                ArtifactErrorCode.checksum_mismatch,
                localized_error("Контрольная сумма не совпала: загрузка повреждена.", "Checksum mismatch."),
            )

    @staticmethod
    def _new_artifact(
        actor: Actor, project_id: UUID, doc_id: str, size: int, sha256: str, meta: PdfUploadMeta
    ) -> ProjectArtifact:
        artifact_id = uuid.uuid4()
        return ProjectArtifact(
            id=artifact_id,
            project_id=project_id,
            kind=ArtifactKind.pdf,
            doc_id=doc_id,
            file_name=safe_file_name(doc_id, meta.file_name),
            size=size,
            sha256=sha256,
            object_key=artifact_key(project_id, doc_id, artifact_id),
            uploaded_at=datetime.now(UTC),
            pages=meta.pages if meta.pages is not None and meta.pages > 0 else None,
            source_commit=meta.source_commit[:64] if meta.source_commit else None,
            built_at=meta.built_at,
            uploaded_by=actor.id,
            uploaded_by_name=actor.name,
            client_name=meta.client_name[:128] if meta.client_name else None,
        )

    async def _store(self, artifact: ProjectArtifact, source: BinaryIO) -> None:
        try:
            await self._objects.put(artifact.object_key, source, content_type=PDF_MEDIA_TYPE, sha256=artifact.sha256)
        except ObjectStoreError:
            logger.warning("artifact upload: object store refused", project_id=str(artifact.project_id), exc_info=True)
            raise

    async def _record(self, actor: Actor, artifact: ProjectArtifact) -> list[ProjectArtifact]:
        async with self._uow.begin():
            await self._artifacts.add(artifact)
            pruned = await self._artifacts.prune(
                artifact.project_id, artifact.doc_id, artifact.kind, keep=self._limits.keep_per_document
            )
            await self._audit.record(
                AUDIT_UPLOADED,
                actor_id=actor.id,
                target=str(artifact.project_id),
                details={
                    "artifact_id": str(artifact.id),
                    "doc_id": artifact.doc_id,
                    "size": artifact.size,
                    "sha256": artifact.sha256,
                    "client": artifact.client_name,
                },
            )
        return pruned

    async def _discard(self, key: str) -> None:
        try:
            await self._objects.delete(key)
        except Exception:  # noqa: BLE001 — лишний объект подберёт сборка мусора, основная ошибка важнее
            logger.warning("artifact object cleanup failed", key=key, exc_info=True)


class ListProjectArtifactsUC:
    def __init__(self, artifacts: IProjectArtifactRepository) -> None:
        self._artifacts = artifacts

    async def execute(self, project_id: UUID, *, doc_id: str | None = None) -> list[ProjectArtifact]:
        return await self._artifacts.list_for_project(project_id, doc_id=doc_id)


@dataclass(frozen=True)
class ArtifactFile:
    artifact: ProjectArtifact
    chunks: AsyncIterator[bytes]


class OpenProjectArtifactUC:
    def __init__(self, artifacts: IProjectArtifactRepository, objects: IObjectStore) -> None:
        self._artifacts = artifacts
        self._objects = objects

    async def execute(self, project_id: UUID, artifact_id: UUID) -> ArtifactFile:
        artifact = await self._artifacts.get(project_id, artifact_id)
        if artifact is None:
            raise ArtifactError(
                ArtifactErrorCode.not_found, localized_error("PDF не найден.", "The PDF was not found.")
            )
        # Объект проверяется до ответа: потом статус уже не изменить.
        info = await self._objects.head(artifact.object_key)
        if info is None:
            raise ArtifactError(
                ArtifactErrorCode.not_found, localized_error("PDF не найден.", "The PDF was not found.")
            )
        return ArtifactFile(artifact, self._objects.stream(artifact.object_key))


class DeleteProjectArtifactUC:
    def __init__(
        self, artifacts: IProjectArtifactRepository, objects: IObjectStore, audit: IAuditLog, uow: IUnitOfWork
    ) -> None:
        self._artifacts = artifacts
        self._objects = objects
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, project_id: UUID, artifact_id: UUID) -> None:
        async with self._uow.begin():
            removed = await self._artifacts.delete(project_id, artifact_id)
            if removed is None:
                raise ArtifactError(
                    ArtifactErrorCode.not_found, localized_error("PDF не найден.", "The PDF was not found.")
                )
            await self._audit.record(
                AUDIT_DELETED,
                actor_id=actor.id,
                target=str(project_id),
                details={"artifact_id": str(artifact_id), "doc_id": removed.doc_id, "sha256": removed.sha256},
            )
        try:
            await self._objects.delete(removed.object_key)
        except (ObjectNotFoundError, ObjectStoreError):
            logger.warning("artifact object cleanup failed", key=removed.object_key, exc_info=True)
