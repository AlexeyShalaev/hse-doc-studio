"""Tar входа и выхода пода: чужие .build и ссылки не уходят, выход не пишет за пределы своего каталога."""

from __future__ import annotations

import io
import os
import sys
import tarfile
from pathlib import Path

import pytest
from hse_doc_studio.infra.compile.k8s.transfer import (
    OutputSpool,
    OutputTooLargeError,
    extract_build,
    pack_workspace,
)


def _names(root: Path, build_rel: str) -> list[str]:
    archive, size = pack_workspace(root, build_rel)
    data = archive.read()
    assert len(data) == size
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        return sorted(member.name for member in tar.getmembers())


def test__pack__other_build_dirs_skipped_own_kept_and_created(tmp_path: Path) -> None:
    (tmp_path / "tz" / ".build" / "other").mkdir(parents=True)
    (tmp_path / "tz" / ".build" / "other" / "a.aux").write_text("x", encoding="utf-8")
    (tmp_path / "tz" / "main.tex").write_text("x", encoding="utf-8")
    (tmp_path / ".build" / "root").mkdir(parents=True)

    names = _names(tmp_path, "tz/.build/tz")

    assert names == ["tz", "tz/.build", "tz/.build/tz", "tz/main.tex"]


@pytest.mark.skipif(sys.platform == "win32", reason="симлинки на Windows требуют прав")
def test__pack__symlinks_skipped(tmp_path: Path) -> None:
    (tmp_path / "main.tex").write_text("x", encoding="utf-8")
    os.symlink("/etc/passwd", tmp_path / "leak")

    assert "leak" not in _names(tmp_path, ".build/d")


def test__pack__modes_and_owner_normalized(tmp_path: Path) -> None:
    source = tmp_path / "main.tex"
    source.write_text("x", encoding="utf-8")
    source.chmod(0o444)

    archive, _ = pack_workspace(tmp_path, ".build/d")
    with tarfile.open(fileobj=archive) as tar:
        member = tar.getmember("main.tex")

    assert (member.mode, member.uid, member.uname) == (0o644, 0, "")


def _tar(entries: dict[str, bytes]) -> io.BytesIO:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer


def test__extract__replaces_build_dir_and_ignores_foreign_paths(tmp_path: Path) -> None:
    build = tmp_path / "tz" / ".build" / "tz"
    build.mkdir(parents=True)
    (build / "old.aux").write_text("old", encoding="utf-8")

    extract_build(_tar({"tz/.build/tz/main.pdf": b"%PDF", "tz/main.tex": b"evil"}), tmp_path, "tz/.build/tz")

    assert (build / "main.pdf").read_bytes() == b"%PDF"
    assert not (build / "old.aux").exists()
    assert not (tmp_path / "tz" / "main.tex").exists()


def test__extract__traversal__rejected(tmp_path: Path) -> None:
    with pytest.raises(tarfile.FilterError):
        extract_build(_tar({"tz/.build/tz/../../../x": b"x"}), tmp_path, "tz/.build/tz")


def test__spool__over_limit__raises() -> None:
    spool = OutputSpool(4)
    spool.write(b"abcd")

    with pytest.raises(OutputTooLargeError):
        spool.write(b"e")
    spool.close()
