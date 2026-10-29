"""Временный каталог закрытого ключа: права 0700, каталога нет после блока и после исключения, уборка старых."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path

import pytest
from hse_doc_studio.infra.signatures.key_session import KEY_SESSION_PREFIX, key_directory, sweep_stale_key_sessions


def test__key_directory__has_private_mode_and_both_files_and_is_gone_after(tmp_path: Path) -> None:
    with key_directory(b"KEY", b"CERT", root=tmp_path) as directory:
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert (directory / "key.pem").read_bytes() == b"KEY"
        assert stat.S_IMODE((directory / "key.pem").stat().st_mode) == 0o600
        assert (directory / "cert.pem").read_bytes() == b"CERT"
    assert not directory.exists()
    assert list(tmp_path.iterdir()) == []


def test__key_directory__exception_in_block_still_removes_it(tmp_path: Path) -> None:
    seen: list[Path] = []

    def fail() -> None:
        with key_directory(b"KEY", None, root=tmp_path) as directory:
            seen.append(directory)
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        fail()
    assert not seen[0].exists()


def test__key_directory__overwrites_content_before_unlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[bytes] = []
    real_rmtree = __import__("shutil").rmtree

    def spy(path: Path, *args: object, **kwargs: object) -> None:
        seen.append((Path(path) / "key.pem").read_bytes())
        real_rmtree(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("hse_doc_studio.infra.signatures.key_session.shutil.rmtree", spy)
    with key_directory(b"SECRET-KEY", None, root=tmp_path):
        pass
    assert seen == [b"\0" * len(b"SECRET-KEY")]


def test__sweep_stale_key_sessions__removes_only_old_signing_dirs(tmp_path: Path) -> None:
    old = tmp_path / f"{KEY_SESSION_PREFIX}old"
    fresh = tmp_path / f"{KEY_SESSION_PREFIX}fresh"
    other = tmp_path / "unrelated"
    for directory in (old, fresh, other):
        directory.mkdir()
        (directory / "key.pem").write_bytes(b"k")
    past = time.time() - 7200
    os.utime(old, (past, past))
    os.utime(other, (past, past))

    assert sweep_stale_key_sessions(root=tmp_path) == 1
    assert not old.exists()
    assert fresh.exists()
    assert other.exists()
