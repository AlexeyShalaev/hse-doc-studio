"""PackExecutor: записи плана на диск и упаковка в архив."""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.jobs.files import InlineBlob, ManifestFile, StampSpec
from hse_doc_studio.core.jobs.pack import (
    ArchiveFormat,
    PackEntry,
    PackEntryKind,
    PackSubmissionPayload,
)
from hse_doc_studio.infra.submission.pack_executor import (
    REASON_ARCNAME_ESCAPES,
    REASON_WRITE_FAILED,
    PackExecutor,
    archive_ext,
    available_archive_formats,
    is_archive_format_available,
    stamp_from_spec,
)
from pypdf import PdfReader, PdfWriter


def _pdf(pages: int = 2) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _payload(
    *entries: PackEntry, base_name: str = "final-1", fmt: ArchiveFormat = ArchiveFormat.zip
) -> PackSubmissionPayload:
    return PackSubmissionPayload(
        base_name=base_name,
        profile_id="final",
        lang=Lang.ru,
        archive_format=fmt,
        keep_folder=True,
        entries=entries,
    )


def _text_stamp() -> StampSpec:
    return StampSpec(page=1, x_mm=20, y_mm=30, width_mm=60, png=None, aspect_ratio=0.4, text="Подписано")


@pytest.mark.unit
def test__pack_executor__applies_all_entry_kinds(tmp_path: Path) -> None:
    (tmp_path / "tz").mkdir()
    (tmp_path / "tz/tz.pdf").write_bytes(_pdf())
    (tmp_path / "tz/notes.txt").write_text("заметки", encoding="utf-8")
    payload = _payload(
        PackEntry(PackEntryKind.copy, "Заметки/Заметки.txt", source=ManifestFile("tz/notes.txt")),
        PackEntry(PackEntryKind.stamp_pdf, "ТЗ.pdf", source=ManifestFile("tz/tz.pdf"), stamps=(_text_stamp(),)),
        PackEntry(PackEntryKind.text, "ТЗ.README.txt", text="привет"),
        PackEntry(PackEntryKind.blob, "public-key.asc", blob=InlineBlob.from_bytes(b"\x00key\xff")),
    )

    executed = PackExecutor().execute(tmp_path, payload)

    folder = tmp_path / "submissions" / "final-1"
    assert executed.folder == folder
    assert executed.written == ("Заметки/Заметки.txt", "ТЗ.pdf", "ТЗ.README.txt", "public-key.asc")
    assert executed.skipped == ()
    assert (folder / "Заметки/Заметки.txt").read_text(encoding="utf-8") == "заметки"
    assert (folder / "ТЗ.README.txt").read_text(encoding="utf-8") == "привет"
    assert (folder / "public-key.asc").read_bytes() == b"\x00key\xff"
    stamped = folder / "ТЗ.pdf"
    assert len(PdfReader(str(stamped)).pages) == 2
    # Штамп дорисован в копию: исходник не тронут.
    assert stamped.read_bytes() != (tmp_path / "tz/tz.pdf").read_bytes()
    assert (tmp_path / "tz/tz.pdf").read_bytes() == _pdf()


@pytest.mark.unit
def test__pack_executor__empty_plan__creates_empty_folder(tmp_path: Path) -> None:
    executed = PackExecutor().execute(tmp_path, _payload())

    assert executed.written == ()
    assert executed.folder.is_dir()
    assert list(executed.folder.iterdir()) == []


@pytest.mark.unit
def test__pack_executor__escaping_arcname_skipped(tmp_path: Path) -> None:
    # Лексически безопасный arcname, который уходит из папки через символьную ссылку.
    outside = tmp_path / "outside"
    outside.mkdir()
    folder = tmp_path / "submissions" / "final-1"
    folder.mkdir(parents=True)
    (folder / "link").symlink_to(outside, target_is_directory=True)
    payload = _payload(
        PackEntry(PackEntryKind.text, "link/evil.txt", text="x"),
        PackEntry(PackEntryKind.text, "ok.txt", text="y"),
    )

    executed = PackExecutor().execute(tmp_path, payload)

    assert executed.written == ("ok.txt",)
    assert [(s.arcname, s.reason) for s in executed.skipped] == [("link/evil.txt", REASON_ARCNAME_ESCAPES)]
    assert not (outside / "evil.txt").exists()


@pytest.mark.unit
def test__pack_executor__oserror_per_file_recorded_in_skipped(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    payload = _payload(
        PackEntry(PackEntryKind.copy, "missing.txt", source=ManifestFile("gone.txt")),
        PackEntry(PackEntryKind.copy, "a.txt", source=ManifestFile("a.txt")),
    )

    executed = PackExecutor().execute(tmp_path, payload)

    assert executed.written == ("a.txt",)
    [skip] = executed.skipped
    assert (skip.arcname, skip.reason) == ("missing.txt", REASON_WRITE_FAILED)
    assert "gone.txt" in skip.detail


@pytest.mark.unit
def test__pack_executor__same_arcname_twice__last_wins_like_legacy(tmp_path: Path) -> None:
    payload = _payload(
        PackEntry(PackEntryKind.text, "x.txt", text="1"),
        PackEntry(PackEntryKind.text, "x.txt", text="2"),
    )

    executed = PackExecutor().execute(tmp_path, payload)

    assert executed.written == ("x.txt", "x.txt")
    assert (executed.folder / "x.txt").read_text(encoding="utf-8") == "2"


@pytest.mark.unit
def test__stamp_from_spec__png_resolved_under_workspace(tmp_path: Path) -> None:
    spec = StampSpec(
        page=2,
        x_mm=1,
        y_mm=2,
        width_mm=3,
        png=ManifestFile(".hse-studio/signatures/a.png"),
        aspect_ratio=0.5,
        details=(("Владелец", "Иван"),),
        subtitle="КЭП",
        date_label="Дата",
        date_text="12.05.2026",
    )

    stamp = stamp_from_spec(spec, tmp_path)

    assert stamp.png_path == tmp_path / ".hse-studio/signatures/a.png"
    assert (stamp.page, stamp.x_mm, stamp.y_mm, stamp.width_mm, stamp.aspect_ratio) == (2, 1, 2, 3, 0.5)
    assert (stamp.details, stamp.subtitle, stamp.date_label, stamp.date_text) == (
        (("Владелец", "Иван"),),
        "КЭП",
        "Дата",
        "12.05.2026",
    )
    assert stamp_from_spec(_text_stamp(), tmp_path).png_path is None


@pytest.mark.unit
def test__pack_executor__create_archive__zip_and_targz_contain_folder_contents(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "a.txt").write_text("a", encoding="utf-8")
    (src / "sub/b.txt").write_text("b", encoding="utf-8")
    executor = PackExecutor()

    zip_path = executor.create_archive(src, tmp_path / "out" / "final", "zip")
    tar_path = executor.create_archive(src, tmp_path / "out" / "final", "targz")

    assert zip_path.name == "final.zip"
    with zipfile.ZipFile(zip_path) as zf:
        assert {n for n in zf.namelist() if not n.endswith("/")} == {"a.txt", "sub/b.txt"}
    assert tar_path.name == "final.tar.gz"
    with tarfile.open(tar_path) as tf:
        assert {m.name.removeprefix("./") for m in tf.getmembers() if m.isfile()} == {"a.txt", "sub/b.txt"}


@pytest.mark.unit
def test__pack_executor__create_archive__unknown_and_missing_tool_same_texts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr("shutil.which", lambda _tool: None)
    executor = PackExecutor()

    with pytest.raises(ValueError, match="Unknown archive format: 'bogus'"):
        executor.create_archive(src, tmp_path / "out", "bogus")
    with pytest.raises(
        ValueError, match=r"Archive format '7z' requires an external tool \(7z/7za\) which is not installed"
    ):
        executor.create_archive(src, tmp_path / "out", "7z")
    with pytest.raises(
        ValueError, match=r"Archive format 'rar' requires an external tool \(rar\) which is not installed"
    ):
        executor.create_archive(src, tmp_path / "out", "rar")
    assert not is_archive_format_available("7z")
    assert is_archive_format_available("zip")


@pytest.mark.unit
def test__pack_executor__archive_catalog__ids_exts_and_native_available() -> None:
    catalog = {f["id"]: f for f in available_archive_formats()}

    assert list(catalog) == ["zip", "targz", "7z", "rar"]
    assert archive_ext("targz") == ".tar.gz"
    assert catalog["zip"]["available"] is True
    with pytest.raises(ValueError, match="Unknown archive format"):
        archive_ext("bogus")
