from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.projects.volume import UnsafePathError
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "projects"


@pytest.fixture
def volume(root: Path) -> LocalDiskProjectVolume:
    return LocalDiskProjectVolume(root)


def test__path_of__uuid__is_child_of_root(volume: LocalDiskProjectVolume, root: Path) -> None:
    project_id = uuid4()
    assert volume.path_of(project_id) == root / str(project_id)
    assert volume.path_of(str(project_id)) == root / str(project_id)


@pytest.mark.parametrize(
    "bad",
    ["..", "../other", "/etc/passwd", ".", "", "a/b", "not-a-uuid", "00000000000000000000000000000001", "X" * 36],
)
def test__path_of__not_canonical_id__rejected(volume: LocalDiskProjectVolume, bad: str) -> None:
    with pytest.raises(UnsafePathError):
        volume.path_of(bad)


def test__path_of__uppercase_uuid__rejected(volume: LocalDiskProjectVolume) -> None:
    with pytest.raises(UnsafePathError):
        volume.path_of(str(uuid4()).upper())


def test__path_of__symlinked_folder__rejected(volume: LocalDiskProjectVolume, root: Path, tmp_path: Path) -> None:
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    project_id = uuid4()
    (root / str(project_id)).symlink_to(outside)

    with pytest.raises(UnsafePathError):
        volume.path_of(project_id)
    assert not volume.exists(project_id)


def test__id_of__own_folder__returns_id(volume: LocalDiskProjectVolume) -> None:
    project_id = uuid4()
    assert volume.id_of(volume.allocate(project_id)) == project_id


def test__id_of__dotdot_traversal__rejected(volume: LocalDiskProjectVolume, root: Path) -> None:
    project_id = uuid4()
    volume.allocate(project_id)
    with pytest.raises(UnsafePathError):
        volume.id_of(root / str(project_id) / ".." / str(uuid4()) / "..")
    with pytest.raises(UnsafePathError):
        volume.id_of(root / ".." / str(project_id))


def test__id_of__relative_and_foreign_paths__rejected(volume: LocalDiskProjectVolume, tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError):
        volume.id_of(Path(str(uuid4())))
    with pytest.raises(UnsafePathError):
        volume.id_of(tmp_path / str(uuid4()))
    with pytest.raises(UnsafePathError):
        volume.id_of(Path("/"))


def test__id_of__nested_folder__rejected(volume: LocalDiskProjectVolume) -> None:
    folder = volume.allocate(uuid4())
    with pytest.raises(UnsafePathError):
        volume.id_of(folder / str(uuid4()))


def test__id_of__symlink_to_other_project__rejected(volume: LocalDiskProjectVolume, root: Path) -> None:
    victim = volume.allocate(uuid4())
    link = root / str(uuid4())
    link.symlink_to(victim)
    with pytest.raises(UnsafePathError):
        volume.id_of(link)


def test__allocate__twice__fails(volume: LocalDiskProjectVolume) -> None:
    project_id = uuid4()
    volume.allocate(project_id)
    with pytest.raises(FileExistsError):
        volume.allocate(project_id)


def test__remove__folder__deleted_with_content(volume: LocalDiskProjectVolume) -> None:
    project_id = uuid4()
    folder = volume.allocate(project_id)
    (folder / "a.tex").write_text("x")
    volume.remove(project_id)
    assert not volume.exists(project_id)


def test__remove__symlink_inside__target_untouched(volume: LocalDiskProjectVolume, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    folder = volume.allocate(uuid4())
    (folder / "link").symlink_to(outside)

    volume.remove(volume.id_of(folder))

    assert (outside / "keep.txt").read_text() == "keep"


def test__safe_open__write_then_read__roundtrip(volume: LocalDiskProjectVolume) -> None:
    folder = volume.allocate(uuid4())
    with volume.safe_open(folder, "sections/intro.tex", "wb", make_parents=True) as handle:
        handle.write(b"hello")
    with volume.safe_open(folder, "sections/intro.tex") as handle:
        assert handle.read() == b"hello"
    with volume.safe_open(folder, "sections/intro.tex", "ab") as handle:
        handle.write(b"!")
    assert (folder / "sections" / "intro.tex").read_bytes() == b"hello!"


def test__safe_open__missing_parent_without_make_parents__file_not_found(volume: LocalDiskProjectVolume) -> None:
    folder = volume.allocate(uuid4())
    with pytest.raises(FileNotFoundError):
        volume.safe_open(folder, "a/b.tex", "wb")


@pytest.mark.parametrize("bad", ["../x", "a/../../x", "/etc/passwd", "", ".", "a//b", "a\\b", "a/./b", "x\x00y"])
def test__safe_open__escaping_relative__rejected(volume: LocalDiskProjectVolume, bad: str) -> None:
    folder = volume.allocate(uuid4())
    with pytest.raises(UnsafePathError):
        volume.safe_open(folder, bad, "wb")


def test__safe_open__symlinked_file__rejected_and_target_untouched(
    volume: LocalDiskProjectVolume, tmp_path: Path
) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")
    folder = volume.allocate(uuid4())
    (folder / "doc.pdf").symlink_to(secret)

    with pytest.raises(UnsafePathError):
        volume.safe_open(folder, "doc.pdf")
    with pytest.raises(UnsafePathError):
        volume.safe_open(folder, "doc.pdf", "wb")
    assert secret.read_text() == "secret"


def test__safe_open__symlinked_parent_dir__rejected(volume: LocalDiskProjectVolume, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    folder = volume.allocate(uuid4())
    (folder / ".build").symlink_to(outside)

    with pytest.raises(UnsafePathError):
        volume.safe_open(folder, ".build/out.pdf", "wb", make_parents=True)
    assert list(outside.iterdir()) == []


def test__safe_open__symlink_in_middle_of_chain__rejected(volume: LocalDiskProjectVolume, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    (outside / "deep").mkdir(parents=True)
    folder = volume.allocate(uuid4())
    (folder / "a").mkdir()
    (folder / "a" / "b").symlink_to(outside)

    with pytest.raises(UnsafePathError):
        volume.safe_open(folder, "a/b/deep/x.txt", "wb")
    assert list((outside / "deep").iterdir()) == []


def test__safe_open__folder_outside_volume__rejected(volume: LocalDiskProjectVolume, tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError):
        volume.safe_open(tmp_path, "a.txt")


def test__safe_open__directory_as_file__rejected(volume: LocalDiskProjectVolume) -> None:
    folder = volume.allocate(uuid4())
    (folder / "d").mkdir()
    with pytest.raises((UnsafePathError, IsADirectoryError)):
        volume.safe_open(folder, "d")


def test__safe_open__fifo__rejected(volume: LocalDiskProjectVolume) -> None:
    folder = volume.allocate(uuid4())
    os.mkfifo(folder / "pipe")
    with pytest.raises(UnsafePathError):
        volume.safe_open(folder, "pipe", "r+b")
