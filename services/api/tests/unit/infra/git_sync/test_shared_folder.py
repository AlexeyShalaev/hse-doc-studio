from __future__ import annotations

import os
from pathlib import Path

import pytest
from hse_doc_studio.core.git_sync.entities import SharedFolderProvider as Provider
from hse_doc_studio.core.paths import Mount, PathMapping
from hse_doc_studio.infra.git_sync.shared_folder import SharedFolderDetector

pytestmark = pytest.mark.unit

_P = Provider


@pytest.mark.parametrize(
    ("folder", "provider", "root"),
    [
        # Папка владельца проекта: macOS локализует имя каталога Яндекс Диска.
        (
            "/Users/anna/Yandex.Disk.localized/Education/HSE/course-paper",
            _P.yandex_disk,
            "/Users/anna/Yandex.Disk.localized",
        ),
        ("/Users/anna/YandexDisk/work/p", _P.yandex_disk, "/Users/anna/YandexDisk"),
        ("/home/anna/Яндекс.Диск/учёба/p", _P.yandex_disk, "/home/anna/Яндекс.Диск"),
        ("/home/anna/Dropbox/work/p", _P.dropbox, "/home/anna/Dropbox"),
        ("/home/anna/dropbox (personal)/p", _P.dropbox, "/home/anna/dropbox (personal)"),
        ("/Users/anna/OneDrive - HSE/p", _P.onedrive, "/Users/anna/OneDrive - HSE"),
        ("/Users/anna/Nextcloud/p", _P.nextcloud, "/Users/anna/Nextcloud"),
        (
            "/Users/anna/Library/Mobile Documents/com~apple~CloudDocs/p",
            _P.icloud,
            "/Users/anna/Library/Mobile Documents",
        ),
        ("/Users/anna/iCloud Drive/p", _P.icloud, "/Users/anna/iCloud Drive"),
        (
            "/Users/anna/Library/CloudStorage/GoogleDrive-anna@gmail.com/My Drive/p",
            _P.google_drive,
            "/Users/anna/Library/CloudStorage/GoogleDrive-anna@gmail.com",
        ),
        (
            "/Users/anna/Library/CloudStorage/Dropbox-HSE/p",
            _P.dropbox,
            "/Users/anna/Library/CloudStorage/Dropbox-HSE",
        ),
        (
            "/Users/anna/Library/CloudStorage/Box-Box/p",
            _P.unknown,
            "/Users/anna/Library/CloudStorage/Box-Box",
        ),
        ("/home/anna/pCloudDrive/p", _P.unknown, "/home/anna/pCloudDrive"),
    ],
)
def test__detect__service_folder_in_ancestors__names_provider_and_root(
    folder: str, provider: Provider, root: str
) -> None:
    info = SharedFolderDetector().detect(Path(folder))

    assert info is not None
    assert (info.provider, info.root) == (provider, root)
    assert root in info.evidence


@pytest.mark.parametrize(
    "folder",
    [
        "/Users/anna/Documents/project",
        "/home/anna/work/dropbox-notes/p",
        "/home/anna/work/yandex-notes/p",
        "/srv/data/projects/course-paper",
        "/Users/anna/Library/Application Support/hse/projects/p",
        "/home/anna/my-drive-backup/p",
    ],
)
def test__detect__plain_folder__no_false_positive(folder: str) -> None:
    assert SharedFolderDetector().detect(Path(folder)) is None


@pytest.mark.parametrize(
    ("marker", "provider", "is_dir"),
    [
        (".dropbox", _P.dropbox, False),
        (".dropbox.cache", _P.dropbox, True),
        (".stfolder", _P.syncthing, True),
        (".stignore", _P.syncthing, False),
        (".nextcloudsync.log", _P.nextcloud, False),
        (".owncloudsync.log", _P.nextcloud, False),
        (".sync", _P.yandex_disk, True),
    ],
)
def test__detect__marker_in_ancestor__finds_it_without_help_of_names(
    tmp_path: Path, marker: str, provider: Provider, is_dir: bool
) -> None:
    root = tmp_path / "files"
    folder = root / "a" / "b" / "project"
    folder.mkdir(parents=True)
    (root / marker).mkdir() if is_dir else (root / marker).write_text("")

    info = SharedFolderDetector().detect(folder)

    assert info is not None
    assert info.provider is provider
    assert info.root == str(root)
    assert info.evidence == (f"{root}/{marker}",)


def test__detect__marker_in_project_folder_itself__is_found(tmp_path: Path) -> None:
    folder = tmp_path / "project"
    (folder / ".stfolder").mkdir(parents=True)

    info = SharedFolderDetector().detect(folder)

    assert info is not None
    assert (info.provider, info.root) == (_P.syncthing, str(folder))


def test__detect__name_and_marker_of_same_service__root_is_the_outermost_and_evidence_lists_both(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Dropbox"
    folder = root / "course" / "project"
    folder.mkdir(parents=True)
    (root / ".dropbox").write_text("")

    info = SharedFolderDetector().detect(folder)

    assert info is not None
    assert info.root == str(root)
    assert info.evidence == (str(root), f"{root}/.dropbox")


def test__detect__two_services__nearest_names_the_provider(tmp_path: Path) -> None:
    folder = tmp_path / "Dropbox" / "Yandex.Disk" / "project"
    folder.mkdir(parents=True)

    info = SharedFolderDetector().detect(folder)

    assert info is not None
    assert (info.provider, info.root) == (_P.yandex_disk, str(tmp_path / "Dropbox" / "Yandex.Disk"))


@pytest.mark.skipif(os.name != "posix", reason="символьные ссылки")
def test__detect__symlink_into_service_folder__is_found_by_real_location(tmp_path: Path) -> None:
    real = tmp_path / "Dropbox" / "project"
    real.mkdir(parents=True)
    link = tmp_path / "elsewhere" / "project"
    link.parent.mkdir()
    link.symlink_to(real)

    info = SharedFolderDetector().detect(link)

    assert info is not None
    assert info.provider is _P.dropbox


def test__detect__folder_does_not_exist__still_judged_by_path(tmp_path: Path) -> None:
    info = SharedFolderDetector().detect(tmp_path / "Dropbox" / "not-created-yet")

    assert info is not None
    assert info.provider is _P.dropbox


def test__detect__ancestors_beyond_the_cap__are_not_looked_at() -> None:
    deep = Path("/Users/anna/Dropbox").joinpath(*[f"d{i}" for i in range(14)])

    assert SharedFolderDetector().detect(deep) is None


def test__detect__docker_path__judged_by_host_path_of_the_mount() -> None:
    mapping = PathMapping([Mount(container="/projects", host="/Users/anna/Yandex.Disk.localized/projects")])

    info = SharedFolderDetector(mapping).detect(Path("/projects/course-paper"))

    assert info is not None
    assert info.provider is _P.yandex_disk
    assert info.root == "/Users/anna/Yandex.Disk.localized"
    assert info.evidence == ("/Users/anna/Yandex.Disk.localized",)


def test__detect__docker_path_without_mapping__container_name_says_nothing() -> None:
    assert SharedFolderDetector().detect(Path("/projects/course-paper")) is None


def test__detect__docker_path_to_windows_host__root_keeps_host_form() -> None:
    mapping = PathMapping([Mount(container="/projects", host="C:/Users/anna/OneDrive/projects")])

    info = SharedFolderDetector(mapping).detect(Path("/projects/course-paper"))

    assert info is not None
    assert (info.provider, info.root) == (_P.onedrive, "C:/Users/anna/OneDrive")


def test__detect__docker_marker_inside_mount__reported_with_host_path(tmp_path: Path) -> None:
    mount = tmp_path / "projects"
    folder = mount / "course-paper"
    folder.mkdir(parents=True)
    (mount / ".stfolder").mkdir()
    mapping = PathMapping([Mount(container=str(mount), host="/Users/anna/Sync/projects")])

    info = SharedFolderDetector(mapping).detect(folder)

    assert info is not None
    assert (info.provider, info.root) == (_P.syncthing, "/Users/anna/Sync/projects")
    assert info.evidence == ("/Users/anna/Sync/projects/.stfolder",)
