"""Сборка документов проекта без интерфейса: то, что запускает `hse-doc-studio build` (локально и в CI).

Каждая сборка идёт тем же путём, что и кнопка «Собрать»: `TriggerCompileUC`, диспетчер задач,
проверки, запись результата и документа. Здесь только выбор документов, ожидание итога и
копирование готовых файлов в выходную папку.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from uuid import UUID

from hse_doc_studio.core.compile.errors import ImageMissingError
from hse_doc_studio.core.entities import CompileRecord, Document, Project
from hse_doc_studio.core.enums import CheckSeverity, CompileStatus
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ICompileRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.use_cases.compile.trigger_compile import TriggerCompileInput, TriggerCompileUC

_POLL_INTERVAL_S = 0.5
_FINAL_STATUSES = frozenset({CompileStatus.success, CompileStatus.failure, CompileStatus.cancelled})
_LOG_TAIL_LINES = 60

ReportFn = Callable[[str], None]
# Вызывается, когда образа LaTeX нет: обязан его скачать или бросить исключение.
InstallImageFn = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class BuildProjectInput:
    folder: Path
    out_dir: Path
    # None — все документы проекта.
    doc_ids: tuple[str, ...] | None = None
    report: ReportFn | None = None
    install_image: InstallImageFn | None = None


@dataclass(frozen=True)
class DocumentBuild:
    doc_id: str
    status: CompileStatus
    pages: int | None
    errors: int
    warnings: int
    outputs: tuple[str, ...] = ()
    log_tail: str = ""

    @property
    def ok(self) -> bool:
        return self.status is CompileStatus.success


@dataclass(frozen=True)
class BuildProjectOutput:
    documents: list[DocumentBuild] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(doc.ok for doc in self.documents)


class BuildProjectUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        compile_repo: ICompileRepository,
        trigger_compile: TriggerCompileUC,
    ) -> None:
        self._project_repo = project_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._compile_repo = compile_repo
        self._trigger = trigger_compile

    async def execute(self, inp: BuildProjectInput) -> BuildProjectOutput:
        folder = inp.folder.expanduser().resolve()
        project = self._project_repo.get(folder)
        if project is None:
            raise ValueError(
                localized_error(
                    f"'{folder}' не проект HSE Studio (нет .hse-studio/project.json).",
                    f"'{folder}' is not an HSE Studio project (missing .hse-studio/project.json).",
                )
            )
        documents = self._select(project, inp.doc_ids)
        if not documents:
            raise ValueError(localized_error("В проекте нет документов.", "The project has no documents."))

        report = inp.report or (lambda _line: None)
        built: list[DocumentBuild] = []
        for doc in documents:
            report(localized_error(f"Сборка {doc.id}...", f"Building {doc.id}..."))
            result = await self._build_one(project, folder, doc, inp, report)
            built.append(result)
            report(_summary(result))
        return BuildProjectOutput(documents=built)

    @staticmethod
    def _select(project: Project, doc_ids: tuple[str, ...] | None) -> list[Document]:
        if doc_ids is None:
            return list(project.documents)
        by_id = {doc.id: doc for doc in project.documents}
        missing = [doc_id for doc_id in doc_ids if doc_id not in by_id]
        if missing:
            known = ", ".join(sorted(by_id)) or "-"
            raise ValueError(
                localized_error(
                    f"В проекте нет документов: {', '.join(missing)}. Есть: {known}.",
                    f"The project has no documents: {', '.join(missing)}. Available: {known}.",
                )
            )
        return [by_id[doc_id] for doc_id in dict.fromkeys(doc_ids)]

    async def _build_one(
        self, project: Project, folder: Path, doc: Document, inp: BuildProjectInput, report: ReportFn
    ) -> DocumentBuild:
        try:
            compile_id = (await self._trigger.execute(TriggerCompileInput(project.id, doc.id))).compile_id
        except ImageMissingError as exc:
            if inp.install_image is None:
                raise
            report(localized_error(f"Скачивание образа {exc.image}...", f"Pulling image {exc.image}..."))
            await inp.install_image(exc.image)
            compile_id = (await self._trigger.execute(TriggerCompileInput(project.id, doc.id))).compile_id

        record = await self._wait(folder, compile_id)
        if record.status is not CompileStatus.success:
            return _from_record(doc.id, record)
        outputs = self._collect(project, folder, doc, inp.out_dir)
        return _from_record(doc.id, record, outputs)

    async def _wait(self, folder: Path, compile_id: UUID) -> CompileRecord:
        while True:
            record = self._compile_repo.get_for_project(folder, compile_id)
            if record is not None and record.status in _FINAL_STATUSES:
                return record
            await asyncio.sleep(_POLL_INTERVAL_S)

    def _collect(self, project: Project, folder: Path, doc: Document, out_dir: Path) -> tuple[str, ...]:
        """Копирует готовые файлы документа в `out_dir` под именем `<id документа><суффикс>`."""
        out_dir.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        for relative in self._deliverables(project, doc):
            source = (folder / relative).resolve()
            # Путь взят из проекта, который мог прислать соавтор: наружу из папки не выходим.
            if not source.is_file() or not source.is_relative_to(folder):
                continue
            target = out_dir / f"{doc.id}{source.suffix}"
            shutil.copyfile(source, target)
            copied.append(target.name)
        return tuple(copied)

    def _deliverables(self, project: Project, doc: Document) -> list[str]:
        """Пути готовых файлов от корня проекта: PDF рядом с исходником и сам выходной файл варианта."""
        if doc.custom_file is not None:
            return [doc.custom_file.stored_path]
        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        if version is None:
            return []
        source, output = self._template_service.resolve_instance_source(project, doc, version)
        return list(dict.fromkeys([str(PurePosixPath(source).with_suffix(".pdf")), output]))


def _from_record(doc_id: str, record: CompileRecord, outputs: tuple[str, ...] = ()) -> DocumentBuild:
    severities = [check.severity for check in record.check_results]
    return DocumentBuild(
        doc_id=doc_id,
        status=record.status,
        pages=record.pages,
        errors=severities.count(CheckSeverity.err),
        warnings=severities.count(CheckSeverity.warn),
        outputs=outputs,
        log_tail=""
        if record.status is CompileStatus.success
        else "\n".join(record.log.splitlines()[-_LOG_TAIL_LINES:]),
    )


def _tail(log: str) -> str:
    return "\n".join(log.splitlines()[-_LOG_TAIL_LINES:])


def _summary(result: DocumentBuild) -> str:
    if not result.ok:
        return localized_error(f"{result.doc_id}: сборка не удалась", f"{result.doc_id}: build failed")
    files = ", ".join(result.outputs) or "-"
    counts = f"{result.errors}/{result.warnings}"
    return localized_error(
        f"{result.doc_id}: готово, страниц {result.pages or '-'}, файлы: {files}; "
        f"проверки (ошибки/предупреждения): {counts}",
        f"{result.doc_id}: done, pages {result.pages or '-'}, files: {files}; checks (errors/warnings): {counts}",
    )
