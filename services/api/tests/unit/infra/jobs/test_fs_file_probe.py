from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from hse_doc_studio.infra.jobs.fs_file_probe import FsProjectFileProbe, FsProjectFileProbeFactory


def _project(tmp_path: Path) -> Path:
    (tmp_path / "tz/_custom").mkdir(parents=True)
    (tmp_path / "tz/_custom/ТЗ.docx").write_bytes(b"docx")
    (tmp_path / "tz/note.txt").write_text("заметка", encoding="utf-8")
    (tmp_path / "top.txt").write_text("top", encoding="utf-8")
    return tmp_path


def test__fs_file_probe__is_file__files_only(tmp_path) -> None:
    probe = FsProjectFileProbe(_project(tmp_path))

    assert probe.is_file("tz/_custom/ТЗ.docx") is True
    assert probe.is_file("tz") is False
    assert probe.is_file("missing.docx") is False


@pytest.mark.parametrize("path", ["../outside.txt", "tz/../../x", "/etc/passwd", "tz\\x.docx", ""])
def test__fs_file_probe__unsafe_path__not_a_file_and_reads_refused(tmp_path, path: str) -> None:
    probe = FsProjectFileProbe(_project(tmp_path))

    assert probe.is_file(path) is False
    with pytest.raises(ValueError, match="project-relative"):
        probe.read_bytes(path)


def test__fs_file_probe__reads_size_hash_text_bytes(tmp_path) -> None:
    probe = FsProjectFileProbe(_project(tmp_path))

    assert probe.size("tz/_custom/ТЗ.docx") == 4
    assert probe.sha256("tz/_custom/ТЗ.docx") == hashlib.sha256(b"docx").hexdigest()
    assert probe.read_bytes("tz/_custom/ТЗ.docx") == b"docx"
    assert probe.read_text("tz/note.txt") == "заметка"


def test__fs_file_probe__list_files__sorted_relative_posix_under_prefix(tmp_path) -> None:
    probe = FsProjectFileProbe(_project(tmp_path))

    assert probe.list_files() == ("top.txt", "tz/_custom/ТЗ.docx", "tz/note.txt")
    assert probe.list_files("tz") == ("tz/_custom/ТЗ.docx", "tz/note.txt")
    assert probe.list_files("missing") == ()
    assert probe.list_files("../x") == ()


def test__fs_file_probe_factory__binds_probe_to_root(tmp_path) -> None:
    probe = FsProjectFileProbeFactory().for_root(_project(tmp_path))

    assert probe.is_file("top.txt") is True
