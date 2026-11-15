"""Раскладка ревизии источника: архив без выхода за папку и ссылок, пределы, обёрточные папки, снимок папки."""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest
from hse_doc_studio.core.pack_catalog.errors import CatalogError, CatalogErrorCode
from hse_doc_studio.core.pack_catalog.protocols import StageLimits
from hse_doc_studio.infra.pack_catalog.stage import (
    check_tree,
    extract_tar,
    extract_zip,
    packs_root,
    ref_candidates,
    tree_digest,
)

LIMITS = StageLimits(max_files=100, max_bytes=1_000_000, max_archive_bytes=1_000_000)


def _zip(path: Path, entries: dict[str, bytes], *, symlink: str | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = 0o120777 << 16
            zf.writestr(info, "/etc/passwd")
    return path


def _tar(path: Path, entries: dict[str, bytes], *, link: str | None = None) -> Path:
    with tarfile.open(path, "w:gz") as tf:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        if link:
            info = tarfile.TarInfo(link)
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tf.addfile(info)
    return path


def _code(exc: pytest.ExceptionInfo[CatalogError]) -> CatalogErrorCode:
    return exc.value.code


def test__zip__extracts_regular_files(tmp_path: Path) -> None:
    archive = _zip(tmp_path / "a.zip", {"repo-main/packs/acme/pack.yaml": b"id: acme\n"})
    extract_zip(archive, tmp_path / "out", LIMITS)

    assert (tmp_path / "out" / "repo-main" / "packs" / "acme" / "pack.yaml").read_bytes() == b"id: acme\n"
    assert packs_root(tmp_path / "out", ".") == tmp_path / "out" / "repo-main" / "packs"


@pytest.mark.parametrize("name", ["../evil.txt", "/abs.txt", "a/../../b", "c:/x", "a\\b"])
def test__zip__path_traversal_is_refused(tmp_path: Path, name: str) -> None:
    archive = _zip(tmp_path / "a.zip", {name: b"x", "ok.txt": b"y"})

    with pytest.raises(CatalogError) as exc:
        extract_zip(archive, tmp_path / "out", LIMITS)

    assert _code(exc) is CatalogErrorCode.archive_unsafe
    assert not (tmp_path / "out" / "ok.txt").exists()


def test__zip_and_tar__symlinks_are_refused(tmp_path: Path) -> None:
    with pytest.raises(CatalogError) as zexc:
        extract_zip(_zip(tmp_path / "a.zip", {"a": b"x"}, symlink="link"), tmp_path / "z", LIMITS)
    with pytest.raises(CatalogError) as texc:
        extract_tar(_tar(tmp_path / "a.tgz", {"a": b"x"}, link="link"), tmp_path / "t", LIMITS)

    assert _code(zexc) is CatalogErrorCode.archive_unsafe
    assert _code(texc) is CatalogErrorCode.archive_unsafe


def test__tar__file_count_and_bytes_are_limited(tmp_path: Path) -> None:
    many = _tar(tmp_path / "many.tgz", {f"f{i}": b"x" for i in range(5)})
    big = _tar(tmp_path / "big.tgz", {"big": b"x" * 2048})
    small = StageLimits(max_files=3, max_bytes=1024, max_archive_bytes=10_000)

    with pytest.raises(CatalogError) as files:
        extract_tar(many, tmp_path / "a", small)
    with pytest.raises(CatalogError) as size:
        extract_tar(big, tmp_path / "b", small)

    assert _code(files) is CatalogErrorCode.tree_too_large
    assert _code(size) is CatalogErrorCode.tree_too_large


def test__broken_archive__archive_invalid(tmp_path: Path) -> None:
    bad = tmp_path / "bad.tgz"
    bad.write_bytes(b"not an archive")

    with pytest.raises(CatalogError) as exc:
        extract_tar(bad, tmp_path / "out", LIMITS)

    assert _code(exc) is CatalogErrorCode.archive_invalid


def test__packs_root__explicit_path_must_exist(tmp_path: Path) -> None:
    (tmp_path / "packs" / "acme").mkdir(parents=True)

    assert packs_root(tmp_path, "packs") == tmp_path / "packs"
    with pytest.raises(CatalogError) as exc:
        packs_root(tmp_path, "missing")
    assert _code(exc) is CatalogErrorCode.packs_path_missing


def test__check_tree__symlink_is_unsafe(tmp_path: Path) -> None:
    (tmp_path / "acme").mkdir()
    (tmp_path / "acme" / "link").symlink_to("/etc/hosts")

    with pytest.raises(CatalogError) as exc:
        check_tree(tmp_path, LIMITS)

    assert _code(exc) is CatalogErrorCode.tree_unsafe


def test__tree_digest__follows_content(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    first = tree_digest(tmp_path)
    (tmp_path / "a.txt").write_text("2", encoding="utf-8")

    assert tree_digest(tmp_path) != first


def test__ref_candidates__tag_then_branch_then_full_sha() -> None:
    sha = "a" * 40

    assert ref_candidates(None) == ["+HEAD:refs/catalog/head"]
    assert ref_candidates("v1") == ["+refs/tags/v1:refs/catalog/head", "+refs/heads/v1:refs/catalog/head"]
    assert ref_candidates(sha)[-1] == f"+{sha}:refs/catalog/head"
    assert len(ref_candidates("abc1234")) == 2  # noqa: PLR2004 — короткий sha сервер по sha не отдаёт
