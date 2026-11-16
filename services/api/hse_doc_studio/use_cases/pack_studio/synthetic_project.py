"""Синтетический проект предпросмотра как `Project` в памяти (без папки и файлов).

Лежит отдельно от `submission.py` и `preview.py`: его читают и предпросмотр (какие документы собираются), и маршрут
в комбинации, и вычислитель результата, а `submission` сам зависит от предпросмотра.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from pathlib import Path
from uuid import uuid4

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.meta_defaults import apply_meta_defaults
from hse_doc_studio.core.pack_studio.preview import SyntheticProject
from hse_doc_studio.core.value_objects import ProjectLock
from hse_doc_studio.use_cases.projects.create_project import _build_documents


def synthetic_core_project(
    pack_id: str, template_id: str, version: TemplateVersion, synthetic: SyntheticProject
) -> Project:
    """`Project` в памяти из синтетических данных, документы и мета как у `CreateProjectUC` (без папки и файлов)."""
    authors = list(synthetic.authors)
    created = datetime.combine(synthetic.today, time(12, 0), tzinfo=UTC)
    return Project(
        id=uuid4(),
        name=synthetic.name,
        folder=Path(),
        lock=ProjectLock(
            pack_id=pack_id, template_id=template_id, version=version.version, engine=version.engine_config.default
        ),
        kind=synthetic.kind,
        staffing=synthetic.staffing,
        lang=synthetic.lang,
        authors=authors,
        meta=apply_meta_defaults(version, dict(synthetic.meta), synthetic.today),
        supervisor=synthetic.supervisor,
        co_supervisor=synthetic.co_supervisor,
        academic_supervisor=synthetic.academic_supervisor,
        documents=_build_documents(
            version, None, staffing=synthetic.staffing, authors=authors, shared_enabled=True, kind=synthetic.kind
        ),
        created_at=created,
        updated_at=created,
    )
