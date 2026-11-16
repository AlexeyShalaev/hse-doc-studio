"""Чтение папки шаблона вне каталога версии (`LocalPackWorkspaceFiles.template_files`, `template_versions`, срез O6):
сценарии лежат в `scenarios/`, рядом с `examples/`."""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.infra.pack_studio.workspace_files import LocalPackWorkspaceFiles

_TEMPLATE = "p/templates/t"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / _TEMPLATE / "versions" / "1.0.0").mkdir(parents=True)
    (tmp_path / _TEMPLATE / "versions" / "1.0.10").mkdir()
    (tmp_path / _TEMPLATE / "versions" / "1.0.9").mkdir()
    (tmp_path / _TEMPLATE / "versions" / "stray.txt").write_text("not a version", encoding="utf-8")
    return tmp_path


def test__template_files__regular_files_only_by_name(root: Path) -> None:
    folder = root / _TEMPLATE / "scenarios"
    folder.mkdir()
    (folder / "a.yaml").write_text("a", encoding="utf-8")
    (folder / "b.yaml").write_bytes("б".encode())
    (folder / "nested").mkdir()
    (folder / "nested" / "c.yaml").write_text("c", encoding="utf-8")
    (folder / "dir.yaml").mkdir()
    (folder / "big.yaml").write_text("x" * 100, encoding="utf-8")
    (folder / "link.yaml").symlink_to(folder / "a.yaml")
    (folder / ".DS_Store").write_text("junk", encoding="utf-8")

    found = LocalPackWorkspaceFiles().template_files(root, "p", "t", "scenarios", max_bytes=50)

    assert found == {"a.yaml": b"a", "b.yaml": "б".encode()}


def test__template_files__missing_folder_or_a_symlinked_folder_is_empty(
    root: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    files = LocalPackWorkspaceFiles()
    assert files.template_files(root, "p", "t", "scenarios", max_bytes=100) == {}
    outside = tmp_path_factory.mktemp("outside")
    (outside / "a.yaml").write_text("secret", encoding="utf-8")
    (root / _TEMPLATE / "scenarios").symlink_to(outside)

    assert files.template_files(root, "p", "t", "scenarios", max_bytes=100) == {}


def test__template_versions__directories_sorted_by_name(root: Path) -> None:
    assert LocalPackWorkspaceFiles().template_versions(root, "p", "t") == ("1.0.0", "1.0.10", "1.0.9")


def test__template_versions__template_without_versions_is_empty_and_a_missing_template_is_not_found(root: Path) -> None:
    files = LocalPackWorkspaceFiles()
    (root / "p" / "templates" / "empty").mkdir()

    assert files.template_versions(root, "p", "empty") == ()
    with pytest.raises(PackStudioError) as raised:
        files.template_versions(root, "p", "ghost")
    assert raised.value.code is PackStudioErrorCode.version_not_found


def test__read__a_directory_is_file_not_found_not_a_crash(root: Path) -> None:
    with pytest.raises(PackStudioError) as raised:
        LocalPackWorkspaceFiles().read(root, f"{_TEMPLATE}/versions", max_bytes=100)

    assert raised.value.code is PackStudioErrorCode.file_not_found
