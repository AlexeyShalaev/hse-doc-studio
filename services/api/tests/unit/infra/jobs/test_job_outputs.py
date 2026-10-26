"""LocalJobOutputs: атомарная запись выходов задач и описание файлов."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from hse_doc_studio.infra.jobs import outputs as outputs_module
from hse_doc_studio.infra.jobs.outputs import LocalJobOutputs


@pytest.mark.unit
def test__write_output__writes_file_and_describes_it(tmp_path: Path) -> None:
    ref = LocalJobOutputs().write_output(tmp_path, "submissions/pack.zip", b"zip-bytes")

    assert (tmp_path / "submissions/pack.zip").read_bytes() == b"zip-bytes"
    assert ref.path == "submissions/pack.zip"
    assert ref.size == len(b"zip-bytes")
    assert ref.sha256 == hashlib.sha256(b"zip-bytes").hexdigest()


@pytest.mark.unit
def test__write_output__overwrites_and_leaves_no_temp_files(tmp_path: Path) -> None:
    store = LocalJobOutputs()
    store.write_output(tmp_path, "out/a.bin", b"one")
    store.write_output(tmp_path, "out/a.bin", b"two")

    assert (tmp_path / "out/a.bin").read_bytes() == b"two"
    assert [p.name for p in (tmp_path / "out").iterdir()] == ["a.bin"]


@pytest.mark.unit
def test__write_output__failure_before_replace__keeps_old_file_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalJobOutputs()
    store.write_output(tmp_path, "a.bin", b"old")

    def boom(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(outputs_module.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        store.write_output(tmp_path, "a.bin", b"new")

    assert (tmp_path / "a.bin").read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["a.bin"]


@pytest.mark.unit
@pytest.mark.parametrize("rel_path", ["../escape.bin", "/abs.bin", "a\\b.bin", "a/../../b.bin", ""])
def test__write_output__path_outside_workspace__rejected(tmp_path: Path, rel_path: str) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    with pytest.raises(ValueError, match=r"path"):
        LocalJobOutputs().write_output(workspace, rel_path, b"x")

    assert list(tmp_path.iterdir()) == [workspace]
    assert list(workspace.iterdir()) == []


@pytest.mark.unit
def test__write_output__symlink_escaping_workspace__rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="escapes"):
        LocalJobOutputs().write_output(workspace, "link/a.bin", b"x")

    assert list(outside.iterdir()) == []


@pytest.mark.unit
def test__describe__existing_file__sha_and_size(tmp_path: Path) -> None:
    (tmp_path / "x.bin").write_bytes(b"abc")

    ref = LocalJobOutputs().describe(tmp_path, "x.bin")

    assert ref.path == "x.bin"
    assert ref.size == 3
    assert ref.sha256 == hashlib.sha256(b"abc").hexdigest()


@pytest.mark.unit
def test__describe__missing_file__file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        LocalJobOutputs().describe(tmp_path, "none.bin")
