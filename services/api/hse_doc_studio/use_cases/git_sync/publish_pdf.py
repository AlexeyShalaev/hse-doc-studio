"""Выгрузка собранного PDF на сервер Студии (docs/design/local-sync.md, P7).

Срабатывает после успешной локальной сборки (фоном) и по кнопке. Сервер Студии здесь это тот, чей токен
получен входом по коду устройства (`origin = device`) и чей адрес клонирования `<сервер>/git/<id>.git`; проекты
GitHub и другие remotes не затрагиваются. Итог последней выгрузки записывается в состояние проекта, чтобы окно
показало «PDF выгружен» или причину отказа. Сбой выгрузки сборку не ломает: наружу идёт только результат.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_remote.client import (
    DEVICE_ORIGIN,
    PdfUpload,
    StudioServerError,
    StudioServerErrorCode,
    studio_project_id,
)
from hse_doc_studio.core.git_sync.entities import PdfUploadRecord, StoreRemoteConfig, SyncState
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import (
    IGitCredentialRepository,
    IGitRepoReader,
    IGitStoreRemotes,
    IGitSyncStateRepository,
)
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks
from hse_doc_studio.use_cases.documents.get_document import GetDocumentInput, GetDocumentUC
from hse_doc_studio.use_cases.git_sync.status import default_state
from hse_doc_studio.use_cases.git_sync.studio_servers import StudioServersService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()

HEADS_PREFIX = "refs/heads/"
BUILD_DIR = ".build"
_HASH_CHUNK = 1 << 20
_PDF_MAGIC = b"%PDF-"


class PdfPublishStatus(StrEnum):
    uploaded = "uploaded"
    unchanged = "unchanged"
    skipped = "skipped"
    failed = "failed"


class PdfSkipReason(StrEnum):
    no_remote = "no_remote"
    not_studio_server = "not_studio_server"
    disabled = "disabled"
    no_pdf = "no_pdf"


@dataclass(frozen=True)
class PdfPublishResult:
    status: PdfPublishStatus
    doc_id: str
    reason: PdfSkipReason | None = None
    code: str | None = None
    detail: str | None = None
    size: int | None = None


_MESSAGES: dict[str, tuple[str, str]] = {
    StudioServerErrorCode.pdf_forbidden: (
        "Выгружать PDF в этот проект может редактор или владелец",
        "Only an editor or the owner can upload a PDF to this project",
    ),
    StudioServerErrorCode.pdf_scope_missing: (
        "У входа на сервер нет права записи. Войдите на сервер заново с правом записи",
        "The server sign-in has no write access. Sign in again with write access",
    ),
    StudioServerErrorCode.pdf_too_large: (
        "PDF больше предела, который принимает сервер",
        "The PDF is larger than the server accepts",
    ),
    StudioServerErrorCode.pdf_rejected: (
        "Сервер отклонил файл как не PDF",
        "The server rejected the file as not a PDF",
    ),
    StudioServerErrorCode.pdf_unknown_document: (
        "На сервере нет такого документа. Отправьте изменения проекта и повторите",
        "The server has no such document. Sync the project and retry",
    ),
    StudioServerErrorCode.pdf_unsupported: (
        "Сервер не принимает PDF: версия сервера старше или проект недоступен",
        "The server does not accept PDFs: an older server version or the project is unavailable",
    ),
    StudioServerErrorCode.unreachable: ("Сервер недоступен", "The server is unreachable"),
    "no_pdf_file": ("PDF ещё не собран", "The PDF has not been built yet"),
    "not_pdf": ("Документ не выпускается как PDF", "The document is not produced as a PDF"),
}


def _message(code: str) -> str:
    pair = _MESSAGES.get(code)
    return localized_error(*pair) if pair else code


def pdf_upload_enabled(state: SyncState) -> bool:
    """Явный выбор человека побеждает; по умолчанию выгрузка включена (для проекта с сервера Студии)."""
    return True if state.pdf_upload is None else state.pdf_upload


def _now() -> datetime:
    return datetime.now(UTC)


def _fingerprint(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        head = handle.read(len(_PDF_MAGIC))
        if head != _PDF_MAGIC:
            raise ValueError("not a pdf")
        digest.update(head)
        size += len(head)
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


class PublishPdfUC:
    def __init__(  # noqa: PLR0913 — порты одного сценария
        self,
        *,
        project_repo_uc: GetProjectUC,
        document_uc: GetDocumentUC,
        store_remotes: IGitStoreRemotes,
        state_repo: IGitSyncStateRepository,
        credentials: IGitCredentialRepository,
        servers: StudioServersService,
        reader: IGitRepoReader,
        locks: IVcsFolderLocks,
        policy: GitSyncPolicy,
    ) -> None:
        self._projects = project_repo_uc
        self._documents = document_uc
        self._remotes = store_remotes
        self._states = state_repo
        self._credentials = credentials
        self._servers = servers
        self._reader = reader
        self._locks = locks
        self._policy = policy

    async def execute(
        self, project_id: UUID, doc_id: str, *, pages: int | None = None, manual: bool = False
    ) -> PdfPublishResult:
        """Ручной запуск (`manual`) работает и при выключенной автовыгрузке; сетевые отказы приходят результатом."""
        if manual:
            self._policy.require_enabled()
        project = (await self._projects.execute(GetProjectInput(project_id=project_id))).project
        found = await asyncio.to_thread(self._remote, project)
        if isinstance(found, PdfPublishResult):
            return replace(found, doc_id=doc_id)
        state, config = found
        credential_id = state.credential_id or config.credential_id
        server_project = studio_project_id(config.url)
        credential = await self._credentials.get(credential_id) if credential_id else None
        if credential is None or credential.origin != DEVICE_ORIGIN or server_project is None or credential_id is None:
            return PdfPublishResult(PdfPublishStatus.skipped, doc_id, reason=PdfSkipReason.not_studio_server)
        if not manual and not pdf_upload_enabled(state):
            return PdfPublishResult(PdfPublishStatus.skipped, doc_id, reason=PdfSkipReason.disabled)
        return await self._publish(project, state, doc_id, credential_id, server_project, pages)

    def _remote(self, project: Project) -> tuple[SyncState, StoreRemoteConfig] | PdfPublishResult:
        config = self._remotes.read(project)
        if config is None:
            return PdfPublishResult(PdfPublishStatus.skipped, "", reason=PdfSkipReason.no_remote)
        return self._states.get(project.folder) or default_state(config, None), config

    async def _publish(  # noqa: PLR0913 — состояние одной выгрузки
        self,
        project: Project,
        state: SyncState,
        doc_id: str,
        credential_id: UUID,
        server_project: UUID,
        pages: int | None,
    ) -> PdfPublishResult:
        prepared = await self._prepare(project, state, doc_id, server_project, pages)
        if isinstance(prepared, PdfPublishResult):
            return prepared
        try:
            reply = await self._servers.upload_pdf(credential_id, prepared)
        except GitSyncError as exc:
            return await self._failed(project, doc_id, exc.code.value, size=prepared.size, detail=exc.detail)
        except StudioServerError as exc:
            return await self._failed(project, doc_id, exc.code, size=prepared.size)
        except Exception:  # noqa: BLE001 — выгрузка вторична: любой сбой становится записью, а не падением сборки
            logger.warning("pdf upload failed", project_id=str(project.id), doc_id=doc_id, exc_info=True)
            return await self._failed(project, doc_id, StudioServerErrorCode.unreachable, size=prepared.size)
        await self._record(project, PdfUploadRecord(doc_id, _now(), ok=True, size=reply.size))
        status = PdfPublishStatus.uploaded if reply.created else PdfPublishStatus.unchanged
        return PdfPublishResult(status, doc_id, size=reply.size)

    async def _prepare(  # noqa: PLR0913 — состояние одной выгрузки
        self, project: Project, state: SyncState, doc_id: str, server_project: UUID, pages: int | None
    ) -> PdfUpload | PdfPublishResult:
        """Файл, его отпечаток и подпись к нему; отказ до сети приходит готовым результатом."""
        try:
            located = await self._locate(project, doc_id)
        except NotFoundError:
            return await self._failed(project, doc_id, StudioServerErrorCode.pdf_unknown_document, size=None)
        if isinstance(located, str):
            return await self._failed(project, doc_id, located, size=None)
        try:
            size, sha256 = await asyncio.to_thread(_fingerprint, located)
        except (OSError, ValueError):
            return await self._failed(project, doc_id, "no_pdf_file", size=None)
        if size > self._policy.max_pdf_upload_bytes:
            return await self._failed(project, doc_id, StudioServerErrorCode.pdf_too_large, size=size)
        commit = await asyncio.to_thread(self._reader.rev_parse, project.folder, f"{HEADS_PREFIX}{state.local_branch}")
        return PdfUpload(
            project_id=server_project,
            doc_id=doc_id,
            path=located,
            sha256=sha256,
            size=size,
            name=located.name,
            pages=pages,
            source_commit=commit,
            built_at=datetime.fromtimestamp(located.stat().st_mtime, tz=UTC),
        )

    async def _locate(self, project: Project, doc_id: str) -> Path | str:
        """Файл PDF документа или код отказа. Свежий PDF из `.build` важнее соседнего: перенос мог не удаться."""
        info = await self._documents.execute(GetDocumentInput(project_id=project.id, doc_id=doc_id))
        output = info.output_file
        if not output or not output.lower().endswith(".pdf"):
            return "not_pdf"
        rel = PurePosixPath(output)
        root = project.folder.resolve()
        for candidate in (rel.parent / BUILD_DIR / doc_id / rel.name, rel):
            path = (root / candidate).resolve()
            if path.is_relative_to(root) and path.is_file() and not path.is_symlink():
                return path
        return "no_pdf_file"

    async def _failed(
        self, project: Project, doc_id: str, code: str, *, size: int | None, detail: str | None = None
    ) -> PdfPublishResult:
        text = detail or _message(code)
        await self._record(project, PdfUploadRecord(doc_id, _now(), ok=False, size=size, code=code, detail=text))
        return PdfPublishResult(PdfPublishStatus.failed, doc_id, code=code, detail=text, size=size)

    async def _record(self, project: Project, record: PdfUploadRecord) -> None:
        """Запись под блокировкой папки, как у остальных изменений состояния; сбой записи выгрузку не отменяет."""
        with contextlib.suppress(Exception):
            async with self._locks.for_folder(project.folder):
                await asyncio.to_thread(self._save, project, record)

    def _save(self, project: Project, record: PdfUploadRecord) -> None:
        config = self._remotes.read(project)
        state = self._states.get(project.folder) or (default_state(config, None) if config else None)
        if state is not None:
            self._states.save(project.folder, replace(state, last_pdf_upload=record))
