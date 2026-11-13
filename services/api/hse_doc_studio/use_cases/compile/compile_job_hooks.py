from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import structlog

from hse_doc_studio.core.compile.failure import (
    BUILD_FAILED,
    CANCELLED,
    UNKNOWN,
    CompileFailure,
    clip_detail,
    failure_log_block,
)
from hse_doc_studio.core.entities import ChangeLogEntry, CompileRecord
from hse_doc_studio.core.enums import ChangeLogKind, CheckSeverity, CompileStatus, DocumentStatus, VcsCommitKind
from hse_doc_studio.core.git_remote.pdf_observer import IBuiltPdfObserver
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.jobs.artifacts import IArtifactStore
from hse_doc_studio.core.jobs.entities import CompileResult, JobResult, JobSpec, compile_payload_of
from hse_doc_studio.core.jobs.enums import JobStatus, RunnerErrorCode
from hse_doc_studio.core.quotas.errors import QUOTA_EXCEEDED
from hse_doc_studio.core.repositories import (
    IChangeLogRepository,
    ICompileRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.signatures.ports import IBuildPlaces
from hse_doc_studio.core.value_objects import CheckResult
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.use_cases.vcs.excludes import project_vcs_exclude

logger = structlog.get_logger()


def compile_failure(final_status: CompileStatus, result: JobResult, data: CompileResult | None) -> CompileFailure:
    """Причина неудачной или отменённой сборки: код раннера или сервера, иначе ошибка самого LaTeX."""
    error = result.error
    if error is not None and error.code:
        detail = clip_detail(error.detail)
        if error.code == QUOTA_EXCEEDED or (detail is not None and detail.startswith("{")):
            # Расход квоты и прочие JSON-детали читает интерфейс по коду; в записи нужен только текст.
            detail = None
        if detail == error.code:
            detail = None
        return CompileFailure(error.code, detail)
    if final_status is CompileStatus.cancelled:
        return CompileFailure(CANCELLED)
    if data is None or not data.build_ok:
        return CompileFailure(BUILD_FAILED)
    return CompileFailure(UNKNOWN)


def _with_failure(log: str, failure: CompileFailure) -> str:
    """Журнал закрывается объяснением: без него упавшая сборка с пустым выводом читалась бы как «ничего не было»."""
    block = failure_log_block(failure, current_interface_language())
    text = log.rstrip("\n")
    return f"{text}\n{block}\n" if text else f"{block}\n"


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
        build_places: IBuildPlaces | None = None,
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
        self._build_places = build_places
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
        failure = None if success else compile_failure(final_status, result, data)
        if failure is not None:
            log = _with_failure(log, failure)
        await self._restore_started_at(compile_id)

        has_errors = any(r.severity == CheckSeverity.err for r in check_results)
        has_warnings = any(r.severity == CheckSeverity.warn for r in check_results)

        final_record = CompileRecord(
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
            error_code=failure.code if failure is not None else None,
            error_detail=failure.detail if failure is not None else None,
        )
        await self._compile_repo.save(final_record)

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
            await self._after_success(spec, final_record, pages=pages, has_errors=has_errors)

        logger.debug(
            "compile task finished",
            compile_id=str(compile_id),
            status=final_status,
            doc_id=doc_id,
        )

    async def _after_success(
        self, spec: JobSpec, record: CompileRecord, *, pages: int | None, has_errors: bool
    ) -> None:
        """Места подписей по строкам шаблона, снимок исходников, архив PDF для визуального diff, коммит и отпечаток в
        записи, выгрузка на сервер."""
        source_file = compile_payload_of(spec).source_file
        record = await self._rebuild_places(spec, record)
        commit = await self._vcs_commit_on_success(record.doc_id, pages)
        await self._artifacts.archive_pdf(spec.project_id, self._project_folder, record.doc_id, record.id, source_file)
        await self._stamp_build(record, commit, source_file)
        if not has_errors:
            self._notify_pdf_built(spec, record.doc_id, pages)

    async def _rebuild_places(self, spec: JobSpec, record: CompileRecord) -> CompileRecord:
        """Места подписей «из шаблона» на якорях по строкам этой сборки (signing-route.md, 15.17.9), до снимка VCS,
        чтобы снимок их включал. Сбой пересчёта сборку не роняет: места останутся прежними до следующей сборки."""
        if self._build_places is None:
            return record
        try:
            moved = await self._build_places.after_build(spec.project_id, self._project_folder, record.doc_id)
        except Exception as exc:  # noqa: BLE001 — пересчёт мест вторичен
            logger.warning("signature places after build failed", doc_id=record.doc_id, exc=str(exc))
            return record
        if not moved:
            return record
        updated = replace(record, signature_places_moved=moved)
        try:
            await self._compile_repo.save(updated)
        except Exception as exc:  # noqa: BLE001 — число в записи вторично
            logger.warning("compile record save failed", compile_id=str(record.id), exc=str(exc))
        return updated

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

    async def _vcs_commit_on_success(self, doc_id: str, pages: int | None) -> str | None:
        """Record a `compile` snapshot in the project's VCS store. Best-effort:
        a VCS failure must never affect the build's outcome.

        Возвращает коммит, с которого собран PDF: новый снимок или текущая вершина, если снимать нечего;
        без снимка (выключен или сбой) и с несохранёнными правками коммита нет: PDF нельзя связать с версией.
        """
        project_folder = self._project_folder
        try:
            project = self._project_repo.get(project_folder)
            if project is None or not self._vcs_service.is_available(project):
                return None
            settings = VcsSettings.from_meta(project.meta)
            if not settings.auto_commit_on_compile:
                return None
            pages_part = f" · {pages} стр." if pages else ""
            message = f"Сборка: {doc_id}{pages_part}"
            async with self._vcs_locks.for_folder(project_folder):
                if not self._vcs_service.is_initialized(project):
                    exclude = project_vcs_exclude(project, self._template_repo)
                    await asyncio.to_thread(self._vcs_service.init, project, exclude)
                made = await asyncio.to_thread(
                    lambda: self._vcs_service.commit(
                        project,
                        message=message,
                        kind=VcsCommitKind.compile,
                        include_pdf=settings.track_pdf,
                    )
                )
                if made is not None:
                    return str(made.id)
                state = await asyncio.to_thread(self._vcs_service.status, project, settings)
                return state.head if not state.dirty else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("vcs compile-commit failed", doc_id=doc_id, exc=str(exc))
        return None

    async def _stamp_build(self, record: CompileRecord, commit: str | None, source_file: str) -> None:
        """Коммит и отпечаток PDF в запись сборки: по ним видно, свежая ли сборка и одна ли она у облака и Студии."""
        try:
            fingerprint = await self._artifacts.fingerprint_pdf(self._project_folder, record.doc_id, source_file)
            if commit is None and fingerprint is None:
                return
            await self._compile_repo.save(
                replace(
                    record,
                    source_commit=commit,
                    output_sha256=fingerprint.sha256 if fingerprint is not None else None,
                    output_size=fingerprint.size if fingerprint is not None else None,
                )
            )
        except Exception as exc:  # noqa: BLE001 — отпечаток вторичен: сборка от него не зависит
            logger.warning("compile stamp failed", compile_id=str(record.id), exc=str(exc))
