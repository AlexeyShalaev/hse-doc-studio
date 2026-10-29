"""GetArchivedPdfUC: ссылка хранилища, если оно её выдаёт, иначе байты архива."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.storage.models import PresignedUrl
from hse_doc_studio.use_cases.compile.get_archived_pdf import GetArchivedPdfInput, GetArchivedPdfUC

from tests.factories import make_project
from tests.fakes.project_locator import InMemoryProjectLocator

PROJECT_ID = uuid4()
COMPILE_ID = uuid4()


def _uc(tmp_path: Path, artifacts: AsyncMock) -> GetArchivedPdfUC:
    locator = InMemoryProjectLocator()
    locator.add(replace(make_project(folder=tmp_path), id=PROJECT_ID))
    return GetArchivedPdfUC(locator=locator, artifacts=artifacts)


def _input() -> GetArchivedPdfInput:
    return GetArchivedPdfInput(project_id=PROJECT_ID, doc_id="tz", compile_id=COMPILE_ID)


async def test__execute__store_issues_link__redirects_without_reading(tmp_path: Path) -> None:
    artifacts = AsyncMock()
    artifacts.archived_pdf_link.return_value = PresignedUrl(url="https://s3/x", expires_at=datetime.now(UTC))

    out = await _uc(tmp_path, artifacts).execute(_input())

    assert out.redirect_url == "https://s3/x"
    assert out.content is None
    artifacts.read_archived_pdf.assert_not_called()


async def test__execute__no_link__returns_bytes(tmp_path: Path) -> None:
    artifacts = AsyncMock()
    artifacts.archived_pdf_link.return_value = None
    artifacts.read_archived_pdf.return_value = b"%PDF"

    out = await _uc(tmp_path, artifacts).execute(_input())

    assert out.content == b"%PDF"
    assert out.redirect_url is None


@pytest.mark.parametrize("failing", ["archived_pdf_link", "read_archived_pdf"])
async def test__execute__archive_missing__not_found(tmp_path: Path, failing: str) -> None:
    artifacts = AsyncMock()
    artifacts.archived_pdf_link.return_value = None
    getattr(artifacts, failing).side_effect = FileNotFoundError("нет")

    with pytest.raises(NotFoundError):
        await _uc(tmp_path, artifacts).execute(_input())
