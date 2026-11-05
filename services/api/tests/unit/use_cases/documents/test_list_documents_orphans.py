"""Документ «собирается» по чужому статусу (синхронизация из облака) не должен зависать в панели."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from hse_doc_studio.core.enums import CompileStatus, DocumentStatus
from hse_doc_studio.use_cases.documents.list_documents import ListDocumentsUC


def _uc(documents: list, record) -> tuple[ListDocumentsUC, MagicMock]:  # noqa: ANN001
    project = MagicMock()
    project.documents = documents
    project.folder = "/p"
    project_repo = MagicMock()
    uc = ListDocumentsUC(project_repo, MagicMock(), None, AsyncMock(get_for_project=AsyncMock(return_value=record)))
    return uc, project_repo


def _doc(status: DocumentStatus):  # noqa: ANN202
    from hse_doc_studio.core.entities import Document

    return Document(id="tz", status=status, chosen_variant=None, checks_override={}, last_compile_id=uuid.uuid4())


@pytest.mark.parametrize(
    ("record_status", "expected"),
    [
        (None, DocumentStatus.draft),
        (CompileStatus.cancelled, DocumentStatus.err),
        (CompileStatus.failure, DocumentStatus.err),
    ],
)
async def test__building_without_live_record__status_is_closed(record_status, expected) -> None:  # noqa: ANN001
    record = None if record_status is None else MagicMock(status=record_status)
    project = MagicMock(folder="/p")
    project.documents = [_doc(DocumentStatus.building)]
    uc, project_repo = _uc(project.documents, record)

    settled = await uc._settle_orphans(project)  # noqa: SLF001

    assert settled.documents[0].status is expected
    project_repo.save.assert_called_once()


@pytest.mark.parametrize("record_status", [CompileStatus.pending, CompileStatus.running])
async def test__building_with_unfinished_record__untouched(record_status) -> None:  # noqa: ANN001
    project = MagicMock(folder="/p")
    project.documents = [_doc(DocumentStatus.building)]
    uc, project_repo = _uc(project.documents, MagicMock(status=record_status))

    settled = await uc._settle_orphans(project)  # noqa: SLF001

    assert settled.documents[0].status is DocumentStatus.building
    project_repo.save.assert_not_called()
