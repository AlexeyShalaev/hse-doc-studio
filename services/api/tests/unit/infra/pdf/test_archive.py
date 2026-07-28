from __future__ import annotations

from uuid import uuid4

from hse_doc_studio.infra.compile.pdf_archive import (
    archive_compiled_pdf,
    archived_pdf_path,
)


def _make_source_pdf(folder, source_file: str, data: bytes) -> None:  # type: ignore[no-untyped-def]
    p = folder / source_file
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def test__archive_compiled_pdf__source_present__copies_into_namespaced_archive_dir(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Source at vkr/vkr.tex → built PDF at vkr/vkr.pdf.
    _make_source_pdf(tmp_path, "vkr/vkr.pdf", b"%PDF-1.7 current")
    cid = uuid4()
    archive_compiled_pdf(tmp_path, "vkr", cid, "vkr/vkr.tex")
    dest = archived_pdf_path(tmp_path, "vkr", cid)
    assert dest.exists()
    assert dest.read_bytes() == b"%PDF-1.7 current"
    # Lives under the protected internal dir, namespaced by doc id.
    assert ".hse-studio" in dest.parts
    assert "pdf-archive" in dest.parts


def test__archive_compiled_pdf__source_missing__noop(tmp_path) -> None:  # type: ignore[no-untyped-def]
    cid = uuid4()
    archive_compiled_pdf(tmp_path, "vkr", cid, "vkr/vkr.tex")
    assert not archived_pdf_path(tmp_path, "vkr", cid).exists()


def test__archive_compiled_pdf__more_than_eight_builds__prunes_oldest(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ids = []
    for i in range(11):
        _make_source_pdf(tmp_path, "vkr/vkr.pdf", f"%PDF build {i}".encode())
        cid = uuid4()
        ids.append(cid)
        archive_compiled_pdf(tmp_path, "vkr", cid, "vkr/vkr.tex")
    archive_dir = archived_pdf_path(tmp_path, "vkr", ids[0]).parent
    remaining = list(archive_dir.glob("*.pdf"))
    assert len(remaining) == 8
    # The very first builds were pruned; the latest survives.
    assert archived_pdf_path(tmp_path, "vkr", ids[-1]).exists()
    assert not archived_pdf_path(tmp_path, "vkr", ids[0]).exists()


def test__archive_compiled_pdf__root_level_source__archives_correctly(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # A doc whose source sits at the project root (no subdir).
    _make_source_pdf(tmp_path, "main.pdf", b"%PDF root")
    cid = uuid4()
    archive_compiled_pdf(tmp_path, "main", cid, "main.tex")
    assert archived_pdf_path(tmp_path, "main", cid).read_bytes() == b"%PDF root"
