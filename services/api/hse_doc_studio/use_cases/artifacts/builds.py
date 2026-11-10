"""Статус сборок проекта и выдача PDF облачной сборки локальной Студии (docs/design/connected-devices.md, часть 3).

По документу видно, где и когда он собран в последний раз (облако, Студия), из какого коммита и свежий ли PDF
относительно текущего проекта. Свежий значит, что входы сборки (`core.builds.inputs`) с того коммита не менялись:
запись состояния подписей, статус документа и коммиты сборок соседних документов сборку не старят. PDF без
записанного коммита свежим не объявляется.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.access.policy import Decision, decide
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.artifacts.entities import ArtifactError, ArtifactErrorCode, ArtifactKind, ProjectArtifact
from hse_doc_studio.core.artifacts.protocols import IProjectArtifactRepository
from hse_doc_studio.core.builds.entities import BuildStamp, DocumentCloudState, IBuildStampRepository
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.jobs.artifacts import IArtifactStore
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import ICompileRepository
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.use_cases.compile.cancel_compile import CancelCompileInput, CancelCompileUC
from hse_doc_studio.use_cases.vcs.build_freshness import BuildFreshness


@dataclass(frozen=True)
class BuildInfo:
    at: datetime
    commit: str | None
    pages: int | None
    # True: собран из текущих входов сборки; False: входы с тех пор изменились; None: коммит неизвестен.
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

    async def require_build(self, actor: Actor, project_id: UUID) -> None:
        """Право запускать и останавливать сборки: то же, что у кнопки «Остановить сборку» в вебе."""
        await self.require(actor, project_id)
        acl = await self._acl.load_for(actor, project_id, include_links=False)
        if acl is None or decide(actor, Action.BUILD_RUN, acl) is not Decision.allow:
            raise ArtifactError(
                ArtifactErrorCode.forbidden,
                localized_error(
                    "Для этого проекта нет права запускать и останавливать сборки.",
                    "You have no right to run or stop builds in this project.",
                ),
            )


class CancelCloudBuildsUC:
    """Остановить облачные сборки проекта по просьбе локальной Студии: в очереди и идущие на раннере.

    Идемпотентно: законченных сборок нет среди `unfinished`, повторный вызов даёт ноль остановленных.
    """

    def __init__(self, locator: IProjectLocator, compile_repo: ICompileRepository, cancel: CancelCompileUC) -> None:
        self._locator = locator
        self._compile_repo = compile_repo
        self._cancel = cancel

    async def execute(self, project_id: UUID, doc_id: str | None) -> int:
        located = await self._locator.locate(project_id)
        if located is None:
            raise _not_found()
        folder, _project = located
        stopped = 0
        for record in await self._compile_repo.list_unfinished(folder):
            if doc_id is not None and record.doc_id != doc_id:
                continue
            await self._cancel.execute(CancelCompileInput(project_id=project_id, compile_id=record.id))
            stopped += 1
        return stopped


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
        freshness = await BuildFreshness.load(self._vcs, project)
        cloud = {s.doc_id: s for s in await self._stamps.states(project_id)}
        latest = self._latest_uploads(await self._artifacts.list_for_project(project_id))
        documents: list[DocumentBuilds] = []
        for doc in project.documents:
            state: DocumentCloudState | None = cloud.get(doc.id)
            uploaded = latest.get(doc.id)
            last_ok = state.last_ok if state else None
            documents.append(
                DocumentBuilds(
                    doc_id=doc.id,
                    cloud=None if last_ok is None else _cloud_info(last_ok, await freshness.of(last_ok.source_commit)),
                    cloud_running=bool(state and state.running),
                    cloud_failed_at=state.last_failed_at if state else None,
                    studio=(
                        None if uploaded is None else _studio_info(uploaded, await freshness.of(uploaded.source_commit))
                    ),
                )
            )
        return ProjectBuilds(head=freshness.head, dirty=freshness.dirty, documents=tuple(documents))

    @staticmethod
    def _latest_uploads(items: list[ProjectArtifact]) -> dict[str, ProjectArtifact]:
        found: dict[str, ProjectArtifact] = {}
        for item in items:
            if item.kind is ArtifactKind.pdf and item.doc_id not in found:
                found[item.doc_id] = item
        return found


def _cloud_info(stamp: BuildStamp, fresh: bool | None) -> BuildInfo:
    return BuildInfo(
        at=stamp.finished_at,
        commit=stamp.source_commit,
        pages=stamp.pages,
        fresh=fresh,
        sha256=stamp.sha256,
        size=stamp.size,
        compile_id=stamp.compile_id,
    )


def _studio_info(artifact: ProjectArtifact, fresh: bool | None) -> StudioBuildInfo:
    return StudioBuildInfo(
        build=BuildInfo(
            at=artifact.built_at or artifact.uploaded_at,
            commit=artifact.source_commit,
            pages=artifact.pages,
            fresh=fresh,
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
