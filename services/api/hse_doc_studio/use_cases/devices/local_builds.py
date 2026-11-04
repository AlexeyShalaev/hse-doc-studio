"""Сборки документов в локальной Студии и в облаке: статус и получение готового PDF (connected-devices.md, часть 3).

Облачный PDF скачивается по тому же входу, что и исходники, и ложится туда, куда лёг бы локальный: документ
открывается без пересборки. Тот же отпечаток не качается, более свежую локальную сборку без `force` не затираем,
автоматический заход берёт только сборку из той версии, что лежит у человека сейчас.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import UUID

import structlog

from hse_doc_studio.core.devices.builds import BuildRelation, FetchStatus, Side, decide_fetch, relate
from hse_doc_studio.core.entities import CompileRecord, Project
from hse_doc_studio.core.enums import CompileStatus, EngineType
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_remote.client import (
    DEVICE_ORIGIN,
    StudioServerError,
    StudioServerErrorCode,
    studio_project_id,
)
from hse_doc_studio.core.git_remote.cloud_builds import CloudBuild, CloudBuilds, parse_cloud_builds
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.git_sync.protocols import IGitCredentialRepository, IGitStoreRemotes, IGitSyncStateRepository
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ICompileRepository, IProjectRepository
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.use_cases.documents.get_document import GetDocumentInput, GetDocumentUC
from hse_doc_studio.use_cases.git_sync.status import default_state
from hse_doc_studio.use_cases.git_sync.studio_servers import StudioServersService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()

# Запись локальной сборки, созданная получением облачного PDF: первая строка лога служит меткой.
FETCHED_MARK = "# fetched-from-cloud"
BUILD_DIR = ".build"


@dataclass(frozen=True)
class LocalBuild:
    at: datetime
    commit: str | None
    fresh: bool | None
    sha256: str | None
    pages: int | None
    from_cloud: bool


@dataclass(frozen=True)
class DocumentBuildStatus:
    doc_id: str
    local: LocalBuild | None
    cloud: CloudBuild | None
    cloud_running: bool
    studio: CloudBuild | None
    relation: BuildRelation
    can_fetch: bool


@dataclass(frozen=True)
class LocalBuilds:
    # Проект связан с сервером Студии; иначе облачной стороны нет.
    connected: bool
    # Нет связи с сервером или он не знает маршрута (старая версия): облачная сторона не получена.
    cloud_error: str | None
    local_head: str | None
    local_dirty: bool
    cloud_head: str | None
    documents: tuple[DocumentBuildStatus, ...]


@dataclass(frozen=True)
class FetchOutcome:
    doc_id: str
    status: FetchStatus
    code: str | None = None
    size: int | None = None


@dataclass(frozen=True)
class _Link:
    credential_id: UUID
    server_project: UUID


def _side(build: LocalBuild | CloudBuild) -> Side:
    size = build.size if isinstance(build, CloudBuild) else None
    return Side(at=build.at, commit=build.commit, sha256=build.sha256, size=size)


class LocalBuildsUC:
    def __init__(  # noqa: PLR0913 — порты одного сценария
        self,
        *,
        project_uc: GetProjectUC,
        document_uc: GetDocumentUC,
        project_repo: IProjectRepository,
        compile_repo: ICompileRepository,
        vcs: IVcsService,
        servers: StudioServersService,
        credentials: IGitCredentialRepository,
        store_remotes: IGitStoreRemotes,
        state_repo: IGitSyncStateRepository,
    ) -> None:
        self._projects = project_uc
        self._documents = document_uc
        self._project_repo = project_repo
        self._compiles = compile_repo
        self._vcs = vcs
        self._servers = servers
        self._credentials = credentials
        self._remotes = store_remotes
        self._states = state_repo

    # --- статус ---------------------------------------------------------------------------------------------

    async def status(self, project_id: UUID) -> LocalBuilds:
        project = (await self._projects.execute(GetProjectInput(project_id=project_id))).project
        head, dirty = await self._local_head(project)
        link = await self._link(project)
        cloud: CloudBuilds | None = None
        error: str | None = None
        if link is not None:
            cloud, error = await self._cloud(link)
        documents = [await self._document(project, doc.id, head, dirty, cloud) for doc in project.documents]
        return LocalBuilds(
            connected=link is not None,
            cloud_error=error,
            local_head=head,
            local_dirty=dirty,
            cloud_head=cloud.head if cloud is not None else None,
            documents=tuple(documents),
        )

    async def _document(
        self, project: Project, doc_id: str, head: str | None, dirty: bool, cloud: CloudBuilds | None
    ) -> DocumentBuildStatus:
        local = await self._local_build(project, doc_id, head, dirty)
        found = cloud.of(doc_id) if cloud is not None else None
        remote = found.cloud if found is not None else None
        relation = relate(_side(local) if local else None, _side(remote) if remote else None)
        return DocumentBuildStatus(
            doc_id=doc_id,
            local=local,
            cloud=remote,
            cloud_running=found.cloud_running if found is not None else False,
            studio=found.studio if found is not None else None,
            relation=relation,
            can_fetch=remote is not None and relation in {BuildRelation.cloud_only, BuildRelation.cloud_newer},
        )

    async def _local_build(self, project: Project, doc_id: str, head: str | None, dirty: bool) -> LocalBuild | None:
        records = await self._compiles.list_for_document(project.folder, doc_id)
        done = [r for r in records if r.status is CompileStatus.success and r.finished_at is not None]
        if not done:
            return None
        last = max(done, key=lambda r: r.finished_at or r.started_at)
        commit = last.source_commit
        return LocalBuild(
            at=last.finished_at or last.started_at,
            commit=commit,
            fresh=None if not commit or not head else commit == head and not dirty,
            sha256=last.output_sha256,
            pages=last.pages,
            from_cloud=last.log.startswith(FETCHED_MARK),
        )

    async def _local_head(self, project: Project) -> tuple[str | None, bool]:
        try:
            state = await asyncio.to_thread(self._vcs.status, project, VcsSettings.from_meta(project.meta))
        except Exception:  # noqa: BLE001 — без истории версия неизвестна
            return None, False
        return (state.head, state.dirty) if state.available and state.initialized else (None, False)

    async def _link(self, project: Project) -> _Link | None:
        config = await asyncio.to_thread(self._remotes.read, project)
        if config is None:
            return None
        server_project = studio_project_id(config.url)
        state = await asyncio.to_thread(self._states.get, project.folder) or default_state(config, None)
        credential_id = state.credential_id or config.credential_id
        credential = await self._credentials.get(credential_id) if credential_id else None
        if server_project is None or credential is None or credential.origin != DEVICE_ORIGIN:
            return None
        return _Link(credential.id, server_project)

    async def _cloud(self, link: _Link) -> tuple[CloudBuilds | None, str | None]:
        try:
            return parse_cloud_builds(await self._servers.project_builds(link.credential_id, link.server_project)), None
        except StudioServerError as exc:
            return None, exc.code
        except GitSyncError as exc:
            return None, exc.code.value

    # --- получение --------------------------------------------------------------------------------------------

    async def fetch(
        self, project_id: UUID, doc_id: str | None, *, force: bool = False, auto: bool = False
    ) -> list[FetchOutcome]:
        project = (await self._projects.execute(GetProjectInput(project_id=project_id))).project
        link = await self._link(project)
        if link is None:
            raise NotFoundError(
                localized_error(
                    "Проект не подключён к серверу Студии", "The project is not connected to a Studio server"
                )
            )
        cloud, error = await self._cloud(link)
        if cloud is None:
            raise StudioServerError(error or StudioServerErrorCode.unreachable)
        head, dirty = await self._local_head(project)
        wanted = [d.doc_id for d in cloud.documents if doc_id is None or d.doc_id == doc_id]
        if doc_id is not None and not wanted:
            return [FetchOutcome(doc_id, FetchStatus.no_cloud_build)]
        outcomes: list[FetchOutcome] = []
        for wanted_doc in wanted:
            known = cloud.of(wanted_doc)
            if known is None or known.cloud is None:
                if doc_id is not None:
                    outcomes.append(FetchOutcome(wanted_doc, FetchStatus.no_cloud_build))
                continue
            outcomes.append(
                await self._fetch_one(project, link, wanted_doc, known.cloud, cloud, head, dirty, force, auto)
            )
        return outcomes

    async def _fetch_one(  # noqa: PLR0913 — состояние одного получения
        self,
        project: Project,
        link: _Link,
        doc_id: str,
        remote: CloudBuild,
        cloud: CloudBuilds,
        head: str | None,
        dirty: bool,
        force: bool,
        auto: bool,
    ) -> FetchOutcome:
        local = await self._local_build(project, doc_id, head, dirty)
        relation = relate(_side(local) if local else None, _side(remote))
        skip = decide_fetch(
            relation,
            _side(remote),
            force=force,
            auto=auto,
            local_head=head,
            local_dirty=dirty,
            max_bytes=cloud.max_pdf_bytes,
        )
        if skip is not None:
            return FetchOutcome(doc_id, skip, size=remote.size)
        try:
            target = await self._target(project, doc_id)
        except NotFoundError:
            return FetchOutcome(doc_id, FetchStatus.failed, code="not_pdf")
        part = target.parent / BUILD_DIR / doc_id / f"cloud-{uuid.uuid4().hex[:8]}.part"
        try:
            reply = await self._servers.download_cloud_pdf(
                link.credential_id,
                link.server_project,
                doc_id,
                part,
                known_sha256=local.sha256 if local is not None else None,
                max_bytes=cloud.max_pdf_bytes,
            )
            if reply.unchanged:
                return FetchOutcome(doc_id, FetchStatus.unchanged)
            await asyncio.to_thread(_install, part, target)
        except StudioServerError as exc:
            return self._failure(doc_id, exc.code)
        except GitSyncError as exc:
            return FetchOutcome(doc_id, FetchStatus.failed, code=exc.code.value)
        finally:
            await asyncio.to_thread(part.unlink, True)
        await self._record(
            project,
            doc_id,
            reply.sha256,
            reply.size,
            reply.source_commit or remote.commit,
            reply.built_at or remote.at,
            reply.pages or remote.pages,
            target,
            remote.compile_id,
        )
        return FetchOutcome(doc_id, FetchStatus.downloaded, size=reply.size)

    @staticmethod
    def _failure(doc_id: str, code: str) -> FetchOutcome:
        if code == StudioServerErrorCode.cloud_pdf_too_large:
            return FetchOutcome(doc_id, FetchStatus.too_large, code=code)
        if code == StudioServerErrorCode.cloud_pdf_missing:
            return FetchOutcome(doc_id, FetchStatus.no_cloud_build, code=code)
        return FetchOutcome(doc_id, FetchStatus.failed, code=code)

    async def _target(self, project: Project, doc_id: str) -> Path:
        """Куда лёг бы локально собранный PDF документа: рядом с исходником, внутри папки проекта."""
        info = await self._documents.execute(GetDocumentInput(project_id=project.id, doc_id=doc_id))
        output = info.output_file
        if not output or not output.lower().endswith(".pdf"):
            raise NotFoundError(
                localized_error("Документ не выпускается как PDF", "The document is not produced as a PDF")
            )
        root = project.folder.resolve()
        path = (root / PurePosixPath(output)).resolve()
        if not path.is_relative_to(root):
            raise NotFoundError(localized_error("Недопустимый путь результата", "Invalid output path"))
        return path

    async def _record(  # noqa: PLR0913 — поля одной записи
        self,
        project: Project,
        doc_id: str,
        sha256: str | None,
        size: int,
        commit: str | None,
        built_at: datetime,
        pages: int | None,
        target: Path,
        record_id: UUID | None,
    ) -> None:
        """Запись сборки, чтобы документ открылся без пересборки и показал, откуда взят PDF.

        Идентификатор тот же, что у облачной сборки: после синхронизации `last_compile_id` документа в project.json
        уже указывает на неё, поэтому файл проекта (общий с облаком) не правится и конфликтов не рождает.
        """
        now = datetime.now(UTC)
        record = CompileRecord(
            id=record_id or uuid.uuid4(),
            project_folder=project.folder,
            doc_id=doc_id,
            engine=EngineType(project.lock.engine) if project.lock.engine in set(EngineType) else EngineType.xelatex,
            status=CompileStatus.success,
            started_at=built_at,
            finished_at=built_at,
            log=f"{FETCHED_MARK}\nPDF получен из облачной сборки {built_at.isoformat()} "
            f"(fetched from the cloud build) в {now.isoformat()}.\n",
            output_path=target,
            check_results=[],
            pages=pages,
            source_commit=commit,
            output_sha256=sha256,
            output_size=size,
        )
        try:
            await self._compiles.save(record)
        except Exception:  # noqa: BLE001 — файл уже на месте: сбой записи не должен отменять получение
            logger.warning("cloud build record failed", doc_id=doc_id, exc_info=True)


def _install(part: Path, target: Path) -> None:
    """Атомарная замена: читатель видит либо старый PDF, либо новый, но не половину."""
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(part, target)
