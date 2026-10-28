from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import (
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.infra.synctex.parser import (
    SyncTexDocument,
    load_synctex,
    normalize_input_path,
)

logger = structlog.get_logger()


@dataclass
class SyncTexForwardInput:
    project_id: UUID
    doc_id: str
    file: str
    line: int


@dataclass
class SyncTexBoxDTO:
    page: int
    x: float
    y: float
    width: float
    height: float


@dataclass
class SyncTexForwardOutput:
    boxes: list[SyncTexBoxDTO]


@dataclass
class SyncTexInverseInput:
    project_id: UUID
    doc_id: str
    page: int
    x: float
    y: float


@dataclass
class SyncTexInverseOutput:
    file: str
    line: int
    column: int


class SyncTexUC:
    """Resolves a document's ``.synctex.gz`` and answers forward/inverse queries.

    Path resolution mirrors the compile executor: the SyncTeX file lands at
    ``<src_parent>/.build/<doc_id>/<stem>.synctex.gz`` under the project folder,
    where ``stem`` is the document's main source file without its extension.
    """

    def __init__(
        self,
        locator: IProjectLocator,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
    ) -> None:
        self._locator = locator
        self._template_repo = template_repo
        self._template_service = template_service

    async def forward(self, inp: SyncTexForwardInput) -> SyncTexForwardOutput:
        doc = await self._load(inp.project_id, inp.doc_id)
        boxes = doc.forward(inp.file, inp.line)
        return SyncTexForwardOutput(
            boxes=[
                SyncTexBoxDTO(
                    page=b.page,
                    x=b.h,
                    y=b.v - b.height,
                    width=b.width,
                    height=b.height + b.depth,
                )
                for b in boxes[:50]
            ]
        )

    async def inverse(self, inp: SyncTexInverseInput) -> SyncTexInverseOutput | None:
        doc = await self._load(inp.project_id, inp.doc_id)
        hit = doc.inverse(inp.page, inp.x, inp.y)
        if hit is None:
            return None
        file, line, column = hit
        return SyncTexInverseOutput(file=normalize_input_path(file), line=line, column=column)

    # ── internals ────────────────────────────────────────────────────────────
    async def _load(self, project_id: UUID, doc_id: str) -> SyncTexDocument:
        path = await self._synctex_path(project_id, doc_id)
        doc = load_synctex(path)
        if doc is None:
            raise NotFoundError(
                localized_error(
                    "Данные SyncTeX не найдены — пересоберите документ (latexmk -synctex=1).",
                    "SyncTeX data not found — rebuild the document (latexmk -synctex=1).",
                )
            )
        return doc

    async def _synctex_path(self, project_id: UUID, doc_id: str) -> Path:
        located = await self._locator.locate(project_id)
        if located is None:
            raise NotFoundError(localized_error(f"Проект {project_id} не найден", f"Project not found: {project_id}"))
        project_folder, project = located
        doc = next((d for d in project.documents if d.id == doc_id), None)
        if doc is None:
            raise NotFoundError(localized_error(f"Документ {doc_id!r} не найден", f"Document {doc_id!r} not found"))
        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        if version is None:
            raise NotFoundError(localized_error("Версия шаблона не найдена", "Template version not found"))
        # Инстанс-путь (team: с префиксом базы владельца); join с паком по def_id.
        source_file, _output = self._template_service.resolve_instance_source(project, doc, version)

        src = PurePosixPath(source_file.replace("\\", "/"))
        src_parent = src.parent.as_posix() if src.parent.parts else ""
        stem = src.stem
        rel = (
            f".build/{doc_id}/{stem}.synctex.gz"
            if src_parent in ("", ".")
            else f"{src_parent}/.build/{doc_id}/{stem}.synctex.gz"
        )
        target = (project_folder / rel).resolve()
        if not target.is_relative_to(project_folder.resolve()):
            raise ValueError(
                localized_error(
                    "Разрешённый путь SyncTeX выходит за пределы папки проекта",
                    "Resolved SyncTeX path escapes the project folder",
                )
            )
        return target
