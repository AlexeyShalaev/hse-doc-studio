"""Статус сборок проекта и выдача PDF облачной сборки локальной Студии (docs/design/connected-devices.md, часть 3).

По документу видно, где и когда он собран в последний раз (облако, Студия), из какого коммита и свежий ли PDF
относительно текущей версии проекта. Версия «текущая» это вершина истории проекта на сервере без несохранённых
правок; PDF без записанного коммита свежим не объявляется.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.access.policy import Decision, decide
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.artifacts.entities import ArtifactError, ArtifactErrorCode, ArtifactKind, ProjectArtifact
from hse_doc_studio.core.artifacts.protocols import IProjectArtifactRepository
from hse_doc_studio.core.builds.entities import BuildStamp, DocumentCloudState, IBuildStampRepository
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.jobs.artifacts import IArtifactStore
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.core.vcs.protocols import IVcsService

logger = structlog.get_logger()


@dataclass(frozen=True)
class BuildInfo:
    at: datetime
    commit: str | None
    pages: int | None
    # True: собран из текущей версии проекта; False: версия с тех пор изменилась; None: коммит неизвестен.
    fresh: bool | None
    sha256: str | None
    size: int | None
    compile_id: UUID | None = None


@dataclass(frozen=True)
class StudioBuildInfo:
    build: BuildInfo
    artifact_id: UUID
    by_name: str | None


@dataclass(frozen=True)
class DocumentBuilds:
    doc_id: str
    cloud: BuildInfo | None
    cloud_running: bool
    cloud_failed_at: datetime | None
    studio: StudioBuildInfo | None


@dataclass(frozen=True)
class ProjectBuilds:
    head: str | None
    dirty: bool
    documents: tuple[DocumentBuilds, ...]


def _fresh(commit: str | None, head: str | None, dirty: bool) -> bool | None:
    if not commit or not head:
        return None
    return commit == head and not dirty


def _not_found() -> ArtifactError:
    return ArtifactError(ArtifactErrorCode.not_found, localized_error("Проект не найден.", "Project not found."))


class GitProjectGate:
    """Право локальной Студии читать результат проекта по токену: то же, что на чтение исходников (git fetch)."""

    def __init__(self, acl: IProjectAclRepository) -> None:
        self._acl = acl

    async def require(self, actor: Actor, project_id: UUID) -> None:
        acl = await self._acl.load_for(actor, project_id, include_links=False)
        if acl is None or acl.grant_for(actor) is None:
            raise _not_found()
        if decide(actor, Action.GIT_FETCH, acl) is not Decision.allow:
            raise ArtifactError(
                ArtifactErrorCode.forbidden,
                localized_error(
                    "Для этого проекта нет права читать исходники и результат.",
                    "You have no right to read the sources and the result of this project.",
                ),
            )


class ProjectBuildsUC:
    def __init__(
        self,
        locator: IProjectLocator,
        vcs: IVcsService,
        stamps: IBuildStampRepository,
        artifacts: IProjectArtifactRepository,
    ) -> None:
        self._locator = locator
        self._vcs = vcs
        self._stamps = stamps
        self._artifacts = artifacts

    async def execute(self, project_id: UUID) -> ProjectBuilds:
        located = await self._locator.locate(project_id)
        if located is None:
            raise _not_found()
        _folder, project = located
        head, dirty = self._head(project)
        cloud = {s.doc_id: s for s in await self._stamps.states(project_id)}
        latest = self._latest_uploads(await self._artifacts.list_for_project(project_id))
        documents: list[DocumentBuilds] = []
        for doc in project.documents:
            state: DocumentCloudState | None = cloud.get(doc.id)
            uploaded = latest.get(doc.id)
            documents.append(
                DocumentBuilds(
                    doc_id=doc.id,
                    cloud=_cloud_info(state.last_ok, head, dirty) if state and state.last_ok else None,
                    cloud_running=bool(state and state.running),
                    cloud_failed_at=state.last_failed_at if state else None,
                    studio=None if uploaded is None else _studio_info(uploaded, head, dirty),
                )
            )
        return ProjectBuilds(head=head, dirty=dirty, documents=tuple(documents))

    def _head(self, project: Project) -> tuple[str | None, bool]:
        try:
            status = self._vcs.status(project, VcsSettings.from_meta(project.meta))
        except Exception:  # noqa: BLE001 — без истории статус показывает «версия неизвестна», а не падает
            logger.warning("project head unavailable", exc_info=True)
            return None, False
        return (status.head, status.dirty) if status.available and status.initialized else (None, False)

    @staticmethod
    def _latest_uploads(items: list[ProjectArtifact]) -> dict[str, ProjectArtifact]:
        found: dict[str, ProjectArtifact] = {}
        for item in items:
            if item.kind is ArtifactKind.pdf and item.doc_id not in found:
                found[item.doc_id] = item
        return found


def _cloud_info(stamp: BuildStamp, head: str | None, dirty: bool) -> BuildInfo:
    return BuildInfo(
        at=stamp.finished_at,
        commit=stamp.source_commit,
        pages=stamp.pages,
        fresh=_fresh(stamp.source_commit, head, dirty),
        sha256=stamp.sha256,
        size=stamp.size,
        compile_id=stamp.compile_id,
    )


def _studio_info(artifact: ProjectArtifact, head: str | None, dirty: bool) -> StudioBuildInfo:
    return StudioBuildInfo(
        build=BuildInfo(
            at=artifact.built_at or artifact.uploaded_at,
            commit=artifact.source_commit,
            pages=artifact.pages,
            fresh=_fresh(artifact.source_commit, head, dirty),
            sha256=artifact.sha256,
            size=artifact.size,
        ),
        artifact_id=artifact.id,
        by_name=artifact.uploaded_by_name,
    )


@dataclass(frozen=True)
class CloudPdf:
    stamp: BuildStamp
    content: bytes
    sha256: str


class OpenCloudBuildPdfUC:
    """PDF последней удачной облачной сборки документа для локальной Студии; повтор того же файла она не качает."""

    def __init__(
        self,
        gate: GitProjectGate,
        locator: IProjectLocator,
        stamps: IBuildStampRepository,
        store: IArtifactStore,
        max_bytes: int,
    ) -> None:
        self._gate = gate
        self._locator = locator
        self._stamps = stamps
        self._store = store
        self._max_bytes = max_bytes

    async def stamp(self, actor: Actor, project_id: UUID, doc_id: str) -> BuildStamp:
        await self._gate.require(actor, project_id)
        stamp = await self._stamps.last_ok(project_id, doc_id)
        if stamp is None:
            raise ArtifactError(
                ArtifactErrorCode.not_found,
                localized_error("Облачной сборки этого документа нет.", "This document has no cloud build."),
            )
        return stamp

    async def read(self, project_id: UUID, stamp: BuildStamp) -> CloudPdf:
        if stamp.size is not None and stamp.size > self._max_bytes:
            raise self._too_large()
        folder = await self._locator.folder_of(project_id)
        if folder is None:
            raise _not_found()
        try:
            content = await self._store.read_archived_pdf(project_id, folder, stamp.doc_id, stamp.compile_id)
        except FileNotFoundError:
            raise ArtifactError(
                ArtifactErrorCode.not_found,
                localized_error("Файл облачной сборки уже удалён.", "The cloud build file has already been removed."),
            ) from None
        if len(content) > self._max_bytes:
            raise self._too_large()
        return CloudPdf(stamp, content, hashlib.sha256(content).hexdigest())

    def _too_large(self) -> ArtifactError:
        limit_mb = self._max_bytes // (1024 * 1024)
        return ArtifactError(
            ArtifactErrorCode.too_large,
            localized_error(f"PDF больше {limit_mb} МБ.", f"The PDF is larger than {limit_mb} MB."),
        )
