from __future__ import annotations

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.team import prefix_path, project_bases
from hse_doc_studio.infra.project_init.template_renderer import version_files_dir


def template_protected_paths(template_repo: ITemplateRepository, project: Project) -> set[str]:
    """Project-relative paths that originate from the template and must not be
    deleted/renamed/moved: every file the pack materialises (``files/`` is copied
    into every base of the layout) plus every dynamic-include output (e.g.
    ``common/meta.tex``). Solo — база одна (корень); team — пути защищаются в
    КАЖДОЙ базе (``shared/…``, ``<slug>/…``). Content of these files is still
    editable — only structural changes are forbidden."""
    version = template_repo.get_version(
        project.lock.pack_id,
        project.lock.template_id,
        project.lock.version,
    )
    if version is None:
        return set()

    rel_paths: set[str] = set()
    files_dir = version_files_dir(template_repo, version)
    if files_dir is not None and files_dir.exists():
        for src in files_dir.rglob("*"):
            if src.is_file():
                rel_paths.add(src.relative_to(files_dir).as_posix())
    for include in version.dynamic_includes:
        rel_paths.add(include.output)

    protected: set[str] = set()
    for base_dir, _author in project_bases(project):
        protected.update(prefix_path(base_dir, rel) for rel in rel_paths)
    return protected


def is_protected_path(path: str, protected: set[str]) -> bool:
    """True if `path` is a protected file, or a folder containing one (so moving
    or deleting a whole template directory is refused too)."""
    norm = path.replace("\\", "/").strip("/")
    if not norm:
        return False
    if norm in protected:
        return True
    prefix = f"{norm}/"
    return any(p.startswith(prefix) for p in protected)
