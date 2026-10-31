from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import structlog

from hse_doc_studio.core.entities import ChangeLogEntry, CompileRecord
from hse_doc_studio.core.enums import ChangeLogKind, CheckSeverity, CompileStatus, DocumentStatus, VcsCommitKind
from hse_doc_studio.core.git_remote.pdf_observer import IBuiltPdfObserver
from hse_doc_studio.core.jobs.artifacts import IArtifactStore
from hse_doc_studio.core.jobs.entities import CompileResult, JobResult, JobSpec, compile_payload_of
from hse_doc_studio.core.jobs.enums import JobStatus, RunnerErrorCode
from hse_doc_studio.core.repositories import (
    IChangeLogRepository,
    ICompileRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.value_objects import CheckResult
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.use_cases.vcs.excludes import project_vcs_exclude

logger = structlog.get_logger()


class CompileJobHooks:
    """Запись состояния сборки: «идёт» при старте, итоговая запись, статус документа, журнал, VCS и архив.

    Держит только APP-областные коллабораторы и простые значения, объектов запроса нет.
    """

    def __init__(  # noqa: PLR0913
        self,
        compile_repo: ICompileRepository,
        project_repo: IProjectRepository,
        changelog_repo: IChangeLogRepository,
        template_repo: ITemplateRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
        artifacts: IArtifactStore,
        project_folder: Path,
        pdf_observer: IBuiltPdfObserver | None = None,
    ) -> None:
        self._compile_repo = compile_repo
        self._project_repo = project_repo
        self._changelog_repo = changelog_repo
        self._template_repo = template_repo
        self._vcs_service = vcs_service
        self._vcs_locks = vcs_locks
        self._artifacts = artifacts
        self._project_folder = project_folder
        self._pdf_observer = pdf_observer
        self._started_at: datetime | None = None

    @property
    def project_folder(self) -> Path:
        return self._project_folder

    async def on_started(self, spec: JobSpec) -> bool:
        record = await self._compile_repo.get_for_project(self._project_folder, spec.id)
        if record is None:
            logger.warning("compile task: record not found", compile_id=str(spec.id))
            return False
        self._started_at = record.started_at
        await self._compile_repo.save(
            CompileRecord(
                id=record.id,
                project_folder=record.project_folder,
                doc_id=record.doc_id,
                engine=record.engine,
                status=CompileStatus.running,
                started_at=record.started_at,
                finished_at=None,
                log="",
                output_path=record.output_path,
                check_results=record.check_results,
                pages=record.pages,
                words=record.words,
                chars=record.chars,
            )
        )
        return True

    async def on_finished(self, spec: JobSpec, result: JobResult, log: str) -> None:  # noqa: C901, PLR0912
        payload = compile_payload_of(spec)
        compile_id = spec.id
        doc_id = payload.doc_id
        data = result.data if isinstance(result.data, CompileResult) else None
        check_results: list[CheckResult] = list(data.check_results) if data is not None else []
        pages = data.pages if data is not None else None
        finished_at = (data.finished_at if data is not None else None) or datetime.now(tz=timezone.utc)

        if result.status is JobStatus.cancelled:
            final_status = CompileStatus.cancelled
        elif result.status is JobStatus.succeeded:
            final_status = CompileStatus.success
        else:
            final_status = CompileStatus.failure
        success = final_status is CompileStatus.success
        await self._restore_started_at(compile_id)

        has_errors = any(r.severity == CheckSeverity.err for r in check_results)
        has_warnings = any(r.severity == CheckSeverity.warn for r in check_results)

        await self._compile_repo.save(
            CompileRecord(
                id=compile_id,
                project_folder=self._project_folder,
                doc_id=doc_id,
                engine=payload.engine,
                status=final_status,
                started_at=self._started_at or finished_at,
                finished_at=finished_at,
                log=log,
                output_path=None,
                check_results=check_results,
                pages=pages,
                words=data.words if data is not None else None,
                chars=data.chars if data is not None else None,
            )
        )

        if result.error is not None and result.error.code == RunnerErrorCode.superseded.value:
            # Заменённую сборку закрываем одной записью: состояние документа уже принадлежит новой сборке.
            return

        if final_status in (CompileStatus.cancelled, CompileStatus.failure) or has_errors:
            new_doc_status = DocumentStatus.err
        elif has_warnings:
            new_doc_status = DocumentStatus.warn
        else:
            new_doc_status = DocumentStatus.ok

        try:
            updated_project = self._project_repo.get(self._project_folder)
            if updated_project is not None:
                updated_docs = [
                    replace(d, status=new_doc_status, last_compile_id=compile_id) if d.id == doc_id else d
                    for d in updated_project.documents
                ]
                updated_project.documents[:] = updated_docs
                self._project_repo.save(updated_project)
        except Exception as exc:
            logger.warning(
                "compile task: failed to update document status",
                compile_id=str(compile_id),
                exc=str(exc),
            )

        if final_status == CompileStatus.cancelled:
            kind = ChangeLogKind.compile_fail
            summary = f"Compile cancelled for {doc_id}"
        else:
            kind = ChangeLogKind.compile_ok if success else ChangeLogKind.compile_fail
            summary = f"Compile {'succeeded' if success else 'failed'} for {doc_id}"
        try:
            self._changelog_repo.append(
                self._project_folder,
                ChangeLogEntry(
                    id=uuid.uuid4(),
                    at=finished_at,
                    kind=kind,
                    doc_id=doc_id,
                    summary=summary,
                    note=None,
                ),
            )
        except Exception as exc:
            logger.warning(
                "compile task: failed to append changelog",
                compile_id=str(compile_id),
                exc=str(exc),
            )

        # ProjectVCS: после успешной сборки снимок исходников (и итогового PDF при
        # track_pdf). Идёт после записи итога и переноса PDF к исходнику, под общей
        # блокировкой папки, чтобы не гоняться с параллельным снимком.
        if success:
            await self._vcs_commit_on_success(doc_id, pages)
            # PDF сохраняется для визуального diff с последующими сборками.
            await self._artifacts.archive_pdf(
                spec.project_id, self._project_folder, doc_id, compile_id, payload.source_file
            )
            if not has_errors:
                self._notify_pdf_built(spec, doc_id, pages)

        logger.debug(
            "compile task finished",
            compile_id=str(compile_id),
            status=final_status,
            doc_id=doc_id,
        )

    def _notify_pdf_built(self, spec: JobSpec, doc_id: str, pages: int | None) -> None:
        """Выгрузка на сервер Студии (если проект оттуда) идёт фоном и сборку не задерживает."""
        if self._pdf_observer is None:
            return
        try:
            self._pdf_observer.on_pdf_built(spec.project_id, doc_id, pages)
        except Exception as exc:  # noqa: BLE001 — выгрузка вторична
            logger.warning("pdf observer failed", doc_id=doc_id, exc=str(exc))

    async def _restore_started_at(self, compile_id: uuid.UUID) -> None:
        """Хуки после рестарта не видели старт: время начала берём из записи сборки."""
        if self._started_at is None:
            existing = await self._compile_repo.get_for_project(self._project_folder, compile_id)
            self._started_at = existing.started_at if existing is not None else None

    async def _vcs_commit_on_success(self, doc_id: str, pages: int | None) -> None:
        """Record a `compile` snapshot in the project's VCS store. Best-effort:
        a VCS failure must never affect the build's outcome."""
        project_folder = self._project_folder
        try:
            project = self._project_repo.get(project_folder)
            if project is None or not self._vcs_service.is_available(project):
                return
            settings = VcsSettings.from_meta(project.meta)
            if not settings.auto_commit_on_compile:
                return
            pages_part = f" · {pages} стр." if pages else ""
            message = f"Сборка: {doc_id}{pages_part}"
            async with self._vcs_locks.for_folder(project_folder):
                if not self._vcs_service.is_initialized(project):
                    exclude = project_vcs_exclude(project, self._template_repo)
                    await asyncio.to_thread(self._vcs_service.init, project, exclude)
                await asyncio.to_thread(
                    lambda: self._vcs_service.commit(
                        project,
                        message=message,
                        kind=VcsCommitKind.compile,
                        include_pdf=settings.track_pdf,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("vcs compile-commit failed", doc_id=doc_id, exc=str(exc))
