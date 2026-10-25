"""Shared lookup for the detached-signature use cases: project, document, compiled PDF."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.team import author_by_slug
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

FROZEN_DIR = ".hse-studio/frozen"
DETACHED_DIR = ".hse-studio/detached"


@dataclass(frozen=True)
class DocContext:
    project: Project
    version: TemplateVersion
    doc: Document
    lang: str
    # Path of the compiled PDF; may not exist yet.
    compiled_path: Path
    # Human file name of the document without extension («Заявка — Шалаев»).
    base_name: str


async def load_doc_context(
    get_uc: GetProjectUC,
    template_repo: ITemplateRepository,
    template_service: ProjectTemplateService,
    project_id: UUID,
    doc_id: str,
) -> DocContext:
    project = (await get_uc.execute(GetProjectInput(project_id=project_id))).project
    version = template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
    if version is None:
        raise NotFoundError(
            localized_error(
                f"Версия шаблона не найдена для проекта {project_id}",
                f"Template version not found for project {project_id}",
            )
        )
    doc = next((d for d in project.documents if d.id == doc_id), None)
    if doc is None:
        raise NotFoundError(
            localized_error(f"Документ {doc_id!r} не найден в проекте", f"Document {doc_id!r} not found in project")
        )
    doc_def = template_service.find_definition(version, doc)
    if doc_def is None:
        raise NotFoundError(
            localized_error(
                f"Определение документа {doc.def_id!r} не найдено в версии шаблона",
                f"Document definition {doc.def_id!r} not found in template version",
            )
        )
    _, output_file = template_service.resolve_instance_source(project, doc, version)
    lang = str(project.lang)
    name = doc_def.output_name.get(lang) or doc_def.output_name.get("ru") or output_file
    stem = name.rsplit(".", 1)[0] if "." in name else name
    owner = author_by_slug(project, doc.owner)
    if owner is not None:
        stem = f"{stem} — {owner.name.split()[0] if owner.name.split() else owner.slug}"
    return DocContext(
        project=project,
        version=version,
        doc=doc,
        lang=lang,
        compiled_path=project.folder / output_file if output_file else project.folder,
        base_name=stem,
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(doc_id: str) -> str:
    """Doc ids are slugs already; this only guards path separators."""
    return doc_id.replace("/", "_").replace("\\", "_")
