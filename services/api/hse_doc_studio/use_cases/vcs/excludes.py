from __future__ import annotations

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.vcs.constants import vcs_exclude_for


def project_vcs_exclude(project: Project, template_repo: ITemplateRepository | None) -> list[str]:
    """Исключения истории проекта с учётом выходов dynamic include его версии шаблона."""
    version = (
        template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        if template_repo is not None
        else None
    )
    return vcs_exclude_for(version)
