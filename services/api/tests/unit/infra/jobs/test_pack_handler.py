"""PackHandler: тело сборки в потоке, проверка манифеста, отмена, итог."""

from __future__ import annotations

import asyncio
import hashlib
import io
import shutil
import threading
import zipfile
from pathlib import Path

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.jobs.enums import JobErrorCategory
from hse_doc_studio.core.jobs.errors import JobFailure
from hse_doc_studio.core.jobs.files import InlineBlob, ManifestFile, StampSpec
from hse_doc_studio.core.jobs.pack import (
    ArchiveFormat,
    PackEntry,
    PackEntryKind,
    PackResult,
    PackSubmissionPayload,
)
from hse_doc_studio.core.jobs.protocols import JobContext
from hse_doc_studio.infra.jobs.outputs import LocalJobOutputs
from hse_doc_studio.infra.jobs.pack_handler import (
    CODE_ARCHIVE_FAILED,
    CODE_MANIFEST_FILE_MISSING,
    CODE_MANIFEST_MISMATCH,
    PackHandler,
)
from hse_doc_studio.infra.submission.pack_executor import ExecutedPack, PackExecutor
from pypdf import PdfReader, PdfWriter

from tests.unit.core.jobs.samples import JOB_ID, PROJECT_ID

_BASE = "final-20260101T000000-abcd1234"


def _pdf(pages: int = 2) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ctx(workspace: Path) -> JobContext:
    return JobContext(
        job_id=JOB_ID,
        project_id=PROJECT_ID,
        actor=Actor.local(),
        locale=Lang.ru,
        workspace=workspace,
        outputs=LocalJobOutputs(),
    )


def _payload(
    *entries: PackEntry,
    fmt: ArchiveFormat = ArchiveFormat.zip,
    keep_folder: bool = True,
    verify_manifest: bool = False,
) -> PackSubmissionPayload:
    return PackSubmissionPayload(
        base_name=_BASE,
        profile_id="final",
        lang=Lang.ru,
        archive_format=fmt,
        keep_folder=keep_folder,
        entries=entries,
        verify_manifest=verify_manifest,
    )


def _stamp() -> StampSpec:
    return StampSpec(page=1, x_mm=20, y_mm=30, width_mm=60, png=None, aspect_ratio=0.4, text="Подписано")


def _entries(pdf: bytes, notes: bytes) -> tuple[PackEntry, ...]:
    return (
        PackEntry(
            PackEntryKind.stamp_pdf, "ТЗ.pdf", source=ManifestFile("tz/tz.pdf", sha256=_sha(pdf)), stamps=(_stamp(),)
        ),
        PackEntry(PackEntryKind.copy, "Заметки.txt", source=ManifestFile("tz/notes.txt", sha256=_sha(notes))),
        PackEntry(PackEntryKind.text, "ТЗ.README.txt", text="привет"),
        PackEntry(PackEntryKind.blob, "key.asc", blob=InlineBlob.from_bytes(b"key")),
    )


def _write_project(root: Path, pdf: bytes, notes: bytes) -> None:
    (root / "tz").mkdir(parents=True)
    (root / "tz/tz.pdf").write_bytes(pdf)
    (root / "tz/notes.txt").write_bytes(notes)


@pytest.mark.unit
async def test__pack_handler__hermetic_manifest_copy__builds_archive(tmp_path: Path) -> None:
    pdf, notes = _pdf(), "заметки".encode()
    project = tmp_path / "project"
    _write_project(project, pdf, notes)
    (project / "unrelated.txt").write_text("не из манифеста", encoding="utf-8")
    payload = _payload(*_entries(pdf, notes), verify_manifest=True)
    # Раннер видит только входы из манифеста: в пустую папку копируем лишь их.
    workspace = tmp_path / "runner"
    workspace.mkdir()
    for file in payload.manifest_files():
        (workspace / file.path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project / file.path, workspace / file.path)

    result = await PackHandler().handle(payload, _ctx(workspace))

    assert isinstance(result, PackResult)
    assert result.written == ("ТЗ.pdf", "Заметки.txt", "ТЗ.README.txt", "key.asc")
    assert result.skipped == ()
    archive = workspace / result.archive.path
    assert result.archive.path == f"submissions/{_BASE}.zip"
    assert result.archive.sha256 == _sha(archive.read_bytes())
    assert result.archive.size == archive.stat().st_size
    with zipfile.ZipFile(archive) as zf:
        assert {n for n in zf.namelist() if not n.endswith("/")} == set(result.written)
        assert zf.read("Заметки.txt") == notes
        assert len(PdfReader(io.BytesIO(zf.read("ТЗ.pdf"))).pages) == 2
    assert result.folder is not None
    assert result.folder.path == f"submissions/{_BASE}"
    assert result.folder.size == sum(f.stat().st_size for f in (workspace / result.folder.path).iterdir())
    assert not (workspace / "unrelated.txt").exists()


@pytest.mark.unit
async def test__pack_handler__keep_folder_false__folder_removed_and_not_in_result(tmp_path: Path) -> None:
    payload = _payload(PackEntry(PackEntryKind.text, "a.txt", text="a"), keep_folder=False)

    result = await PackHandler().handle(payload, _ctx(tmp_path))

    assert result.folder is None
    assert (tmp_path / result.archive.path).is_file()
    assert not (tmp_path / "submissions" / _BASE).exists()


@pytest.mark.unit
async def test__pack_handler__skipped_entries_reported_in_result(tmp_path: Path) -> None:
    payload = _payload(
        PackEntry(PackEntryKind.copy, "gone.txt", source=ManifestFile("gone.txt")),
        PackEntry(PackEntryKind.text, "a.txt", text="a"),
    )

    result = await PackHandler().handle(payload, _ctx(tmp_path))

    assert result.written == ("a.txt",)
    assert [s.arcname for s in result.skipped] == ["gone.txt"]


class _ThreadSpy(PackExecutor):
    def __init__(self) -> None:
        super().__init__()
        self.threads: list[int] = []

    def execute(self, workspace: Path, payload: PackSubmissionPayload) -> ExecutedPack:
        self.threads.append(threading.get_ident())
        return super().execute(workspace, payload)


@pytest.mark.unit
async def test__pack_handler__runs_body_off_event_loop(tmp_path: Path) -> None:
    spy = _ThreadSpy()

    await PackHandler(spy).handle(_payload(PackEntry(PackEntryKind.text, "a.txt", text="a")), _ctx(tmp_path))

    assert spy.threads
    assert threading.get_ident() not in spy.threads


@pytest.mark.unit
async def test__pack_handler__sha_mismatch_with_verify_on__invalid_input(tmp_path: Path) -> None:
    pdf, notes = _pdf(), b"notes"
    _write_project(tmp_path, pdf, notes)
    (tmp_path / "tz/notes.txt").write_bytes(b"tampered")
    payload = _payload(*_entries(pdf, notes), verify_manifest=True)

    with pytest.raises(JobFailure) as caught:
        await PackHandler().handle(payload, _ctx(tmp_path))

    error = caught.value.error
    assert (error.category, error.code, error.detail) == (
        JobErrorCategory.invalid_input,
        CODE_MANIFEST_MISMATCH,
        "tz/notes.txt",
    )
    assert not (tmp_path / "submissions").exists()


@pytest.mark.unit
async def test__pack_handler__manifest_file_missing_with_verify_on__invalid_input(tmp_path: Path) -> None:
    payload = _payload(*_entries(_pdf(), b"notes"), verify_manifest=True)

    with pytest.raises(JobFailure) as caught:
        await PackHandler().handle(payload, _ctx(tmp_path))

    assert caught.value.error.code == CODE_MANIFEST_FILE_MISSING
    assert caught.value.error.category is JobErrorCategory.invalid_input


@pytest.mark.unit
async def test__pack_handler__sha_mismatch_with_verify_off__not_checked(tmp_path: Path) -> None:
    pdf, notes = _pdf(), b"notes"
    _write_project(tmp_path, pdf, notes)
    (tmp_path / "tz/notes.txt").write_bytes(b"tampered")

    result = await PackHandler().handle(_payload(*_entries(pdf, notes)), _ctx(tmp_path))

    assert result.skipped == ()


@pytest.mark.unit
async def test__pack_handler__archive_tool_missing__invalid_input_with_legacy_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("shutil.which", lambda _tool: None)
    payload = _payload(PackEntry(PackEntryKind.text, "a.txt", text="a"), fmt=ArchiveFormat.sevenz)

    with pytest.raises(JobFailure) as caught:
        await PackHandler().handle(payload, _ctx(tmp_path))

    error = caught.value.error
    assert (error.category, error.code) == (JobErrorCategory.invalid_input, CODE_ARCHIVE_FAILED)
    assert error.detail == "Archive format '7z' requires an external tool (7z/7za) which is not installed"


class _GatedExecutor(PackExecutor):
    """Собирает все как обычно, но потом держит поток, пока тест не отпустит."""

    def __init__(self) -> None:
        super().__init__()
        self.archived = threading.Event()
        self.gate = threading.Event()
        self.settled = threading.Event()

    def create_archive(self, src_dir: Path, dest_base: Path, fmt: str) -> Path:
        archive = super().create_archive(src_dir, dest_base, fmt)
        self.archived.set()
        self.gate.wait(10)
        self.settled.set()
        return archive


@pytest.mark.unit
async def test__pack_handler__caller_cancelled__artifacts_removed_after_thread_settles(tmp_path: Path) -> None:
    executor = _GatedExecutor()
    payload = _payload(PackEntry(PackEntryKind.text, "a.txt", text="a"))
    task = asyncio.create_task(PackHandler(executor).handle(payload, _ctx(tmp_path)))
    assert await asyncio.to_thread(executor.archived.wait, 10)
    assert (tmp_path / "submissions" / f"{_BASE}.zip").exists()

    task.cancel()
    # Поток не прервать: пока он держит артефакты, обработчик ждет и ничего не трогает.
    await asyncio.sleep(0.05)
    assert not task.done()
    assert (tmp_path / "submissions" / f"{_BASE}.zip").exists()
    executor.gate.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert executor.settled.is_set()
    assert not (tmp_path / "submissions" / _BASE).exists()
    assert not (tmp_path / "submissions" / f"{_BASE}.zip").exists()
