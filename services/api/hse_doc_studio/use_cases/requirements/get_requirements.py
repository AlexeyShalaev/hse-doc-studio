from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.repositories import (
    IFileRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import (
    CompiledRequirementFormat,
    ProjectTemplateService,
    RequirementMatchingService,
)
from hse_doc_studio.core.value_objects import RequirementsFormat
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class RequirementEntry:
    id: str
    title: str
    source: str  # doc_id where defined
    referenced_in: list[str] = field(default_factory=list)
    status: str = "ok"  # ok | warn | err


@dataclass
class GetRequirementsInput:
    project_id: UUID
    # Dry-run a candidate format without persisting it: when set, the matrix is
    # built from this format instead of the project override / pack default. Used
    # by the agent's preview_requirements_format tool to test an id_pattern/regex
    # before set_requirements_format commits it. None → resolve as usual.
    format_override: RequirementsFormat | None = None


@dataclass
class GetRequirementsOutput:
    items: list[RequirementEntry]
    # The format actually used to build the matrix, plus whether it came from a
    # per-project override (vs. the pack template default) — for the UI editor.
    requirements_format: RequirementsFormat
    overridden: bool


def _doc_for_path(rel_path: str, dir_to_doc: dict[str, str]) -> str | None:
    # Ключи карты — каталоги ИНСТАНСОВ: solo «tz», team «shalaev/tz». Матчим
    # самый длинный префикс, чтобы «shalaev/tz/tz.tex» не съел ключ «shalaev».
    parts = rel_path.replace("\\", "/").lower().split("/")
    for depth in (2, 1):
        if len(parts) > depth - 1:
            doc = dir_to_doc.get("/".join(parts[:depth]))
            if doc is not None:
                return doc
    return None


class GetRequirementsUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        matching_service: RequirementMatchingService,
    ) -> None:
        self._file_repo = file_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._matching_service = matching_service
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: GetRequirementsInput) -> GetRequirementsOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project
        version = self._resolve_version(project)

        # Document folders come from the pack template (each doc's source_file);
        # the detection format comes from the caller's dry-run override, else the
        # project override, else the pack default. Карта — instance-aware:
        # team-проект даёт «shalaev/tz» → «tz--shalaev», «shared/…» → shared-док.
        dir_to_doc = self._template_service.instance_dir_map(project, version)
        if inp.format_override is not None:
            fmt = inp.format_override
        elif project.requirements_format is not None:
            fmt = project.requirements_format
        else:
            fmt = version.requirements_format
        matcher = self._matching_service.compile(fmt)

        tex_paths = [p for p in self._file_repo.list_files(project.folder) if p.lower().endswith(".tex")]
        defs, refs = self._scan(project.folder, tex_paths, dir_to_doc, matcher)

        items = _build_items(defs, refs)
        items.sort(key=lambda x: x.id)
        return GetRequirementsOutput(
            items=items,
            requirements_format=fmt,
            overridden=project.requirements_format is not None,
        )

    def _resolve_version(self, project: Project) -> TemplateVersion:
        version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        if version is None:
            version_ref = f"{project.lock.pack_id}/{project.lock.template_id}/{project.lock.version}"
            raise NotFoundError(
                localized_error(
                    f"Версия шаблона не найдена: {version_ref}", f"Template version not found: {version_ref}"
                )
            )
        return version

    def _scan(
        self,
        project_folder: Path,
        tex_paths: list[str],
        dir_to_doc: dict[str, str],
        matcher: CompiledRequirementFormat,
    ) -> tuple[dict[str, RequirementEntry], dict[str, set[str]]]:
        defs: dict[str, RequirementEntry] = {}
        refs: dict[str, set[str]] = {}
        for rel_path in tex_paths:
            doc_id = _doc_for_path(rel_path, dir_to_doc)
            try:
                content_bytes = self._file_repo.read(project_folder, rel_path)
            except (FileNotFoundError, PermissionError) as exc:
                logger.warning("requirements_scan: cannot read", path=rel_path, exc=str(exc))
                continue
            # errors="replace" never raises, so no decode guard is needed.
            content = content_bytes.decode("utf-8", errors="replace")
            _extract(matcher, _strip_scan_noise(content), doc_id, rel_path, defs, refs)
        return defs, refs


# LaTeX comments and \verb|…| spans are documentation, not markup: template
# hints mention \req{ID}{Описание} in comments and \reqref{ТЗ-Ф-01} in \verb
# examples, which used to surface as ghost requirements in the matrix.
_VERB_RE = re.compile(r"\\verb\*?(?P<d>[^A-Za-z\s])(?:(?!(?P=d)).)*(?P=d)")
_COMMENT_RE = re.compile(r"(?<!\\)%.*")


def _strip_scan_noise(content: str) -> str:
    return _COMMENT_RE.sub("", _VERB_RE.sub(" ", content))


def _extract(
    matcher: CompiledRequirementFormat,
    content: str,
    doc_id: str | None,
    rel_path: str,
    defs: dict[str, RequirementEntry],
    refs: dict[str, set[str]],
) -> None:
    """Pull requirement definitions and references out of one file's text."""
    for rid, title in matcher.definitions(content, doc_id):
        if rid not in defs:  # first definition wins
            defs[rid] = RequirementEntry(id=rid, title=title, source=doc_id or _path_label(rel_path))

    if doc_id is None:  # references only count from a known document folder
        return
    for rid in matcher.references(content, doc_id):
        refs.setdefault(rid, set()).add(doc_id)


def _build_items(
    defs: dict[str, RequirementEntry],
    refs: dict[str, set[str]],
) -> list[RequirementEntry]:
    items: list[RequirementEntry] = []
    for rid, entry in defs.items():
        entry.referenced_in = sorted(refs.get(rid, set()) - {entry.source})
        if not entry.referenced_in:
            entry.status = "warn"  # defined but never referenced
        items.append(entry)

    # Orphan refs (referenced but not defined) — report as errors.
    undefined_title = "(undefined)" if current_interface_language() is Lang.en else "(не определено)"
    for rid, where in refs.items():
        if rid not in defs:
            items.append(
                RequirementEntry(
                    id=rid,
                    title=undefined_title,
                    source="",
                    referenced_in=sorted(where),
                    status="err",
                )
            )
    return items


def _path_label(rel_path: str) -> str:
    return Path(rel_path).parts[0] if rel_path else ""
