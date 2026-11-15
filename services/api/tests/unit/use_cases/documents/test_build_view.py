"""Сведения о сборке для превью: итог последней сборки и есть ли выпущенный файл."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from hse_doc_studio.core.entities import Document
from hse_doc_studio.core.enums import CompileStatus, DocumentStatus
from hse_doc_studio.use_cases.documents.build_view import build_view_of, last_compile_record, output_available


def _doc(last_compile_id: uuid.UUID | None) -> Document:
    return Document(
        id="tz", status=DocumentStatus.err, chosen_variant=None, checks_override={}, last_compile_id=last_compile_id
    )


def test__output_available__file_in_project__true(tmp_path: Path) -> None:
    (tmp_path / "tz").mkdir()
    (tmp_path / "tz" / "tz.pdf").write_bytes(b"%PDF")

    assert output_available(tmp_path, "tz/tz.pdf") is True


def test__output_available__missing_empty_or_directory__false(tmp_path: Path) -> None:
    (tmp_path / "tz").mkdir()

    assert output_available(tmp_path, "tz/tz.pdf") is False
    assert output_available(tmp_path, None) is False
    assert output_available(tmp_path, "tz") is False


def test__output_available__path_outside_project__false(tmp_path: Path) -> None:
    project = tmp_path / "p"
    project.mkdir()
    (tmp_path / "secret.pdf").write_bytes(b"%PDF")

    assert output_available(project, "../secret.pdf") is False


def test__build_view__record_status_and_file(tmp_path: Path) -> None:
    (tmp_path / "tz.pdf").write_bytes(b"%PDF")
    record = MagicMock(status=CompileStatus.success)

    view = build_view_of(record, tmp_path, "tz.pdf")

    assert (view.last_compile_status, view.output_available) == (CompileStatus.success, True)
    assert build_view_of(None, tmp_path, "other.pdf").last_compile_status is None


async def test__last_compile_record__no_pointer_or_unreadable_journal__none(tmp_path: Path) -> None:
    broken = AsyncMock()
    broken.get_for_project.side_effect = OSError("journal gone")

    assert await last_compile_record(broken, tmp_path, _doc(None)) is None
    assert await last_compile_record(broken, tmp_path, _doc(uuid.uuid4())) is None
    assert await last_compile_record(None, tmp_path, _doc(uuid.uuid4())) is None
