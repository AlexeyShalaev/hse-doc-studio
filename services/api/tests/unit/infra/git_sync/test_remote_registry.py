from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.git_sync.remote_registry import ConfigScanRemoteRegistry, store_has_remote

pytestmark = pytest.mark.unit


class _Index:
    def __init__(self, folders: list[Path]) -> None:
        self.folders = folders
        self.calls = 0

    def list_known(self) -> list[Path]:
        self.calls += 1
        return list(self.folders)

    def register(self, folder: Path) -> None:
        self.folders.append(folder)

    def unregister(self, folder: Path) -> None:
        self.folders.remove(folder)


def _store_config(folder: Path, text: str) -> Path:
    config = folder / ".hse-studio" / "git" / "config"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(text, encoding="utf-8")
    return folder


_WITH_REMOTE = '[core]\n\tbare = false\n[remote "origin"]\n\turl = file:///srv/x.git\n'


def test__store_has_remote__detects_the_origin_section_in_the_text(tmp_path: Path) -> None:
    connected = _store_config(tmp_path / "a", _WITH_REMOTE)
    spaced = _store_config(tmp_path / "b", '[ Remote  "origin" ]\nurl = x\n')
    plain = _store_config(tmp_path / "c", "[core]\n\tbare = false\n")
    other = _store_config(tmp_path / "d", '[remote "backup"]\n\turl = x\n')

    assert store_has_remote(connected)
    assert store_has_remote(spaced)
    assert not store_has_remote(plain)
    assert not store_has_remote(other)
    assert not store_has_remote(tmp_path / "missing")


def test__list__first_use_scans_known_projects_once(tmp_path: Path) -> None:
    connected = _store_config(tmp_path / "a", _WITH_REMOTE)
    plain = _store_config(tmp_path / "b", "[core]\n")
    index = _Index([connected, plain, tmp_path / "gone"])
    registry = ConfigScanRemoteRegistry(index)

    assert registry.list() == [connected]
    assert registry.list() == [connected]
    assert index.calls == 1


def test__add_remove__keep_the_list_current_without_rescanning(tmp_path: Path) -> None:
    index = _Index([])
    registry = ConfigScanRemoteRegistry(index)
    folder = tmp_path / "p"

    registry.add(folder)
    registry.add(folder)
    assert registry.list() == [folder]
    registry.remove(folder)
    registry.remove(folder)

    assert registry.list() == []
    assert index.calls == 1


def test__scan__broken_index_does_not_break_registration(tmp_path: Path) -> None:
    class Broken(_Index):
        def list_known(self) -> list[Path]:
            raise RuntimeError("index.json is damaged")

    registry = ConfigScanRemoteRegistry(Broken([]))

    registry.add(tmp_path)

    assert registry.list() == [tmp_path]


def test__same_folder_through_a_symlink_is_one_entry(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    registry = ConfigScanRemoteRegistry(_Index([]))

    registry.add(real)
    registry.add(link)
    registry.remove(link)

    assert registry.list() == []


def test__subscribe__listeners_hear_every_add_but_not_remove(tmp_path: Path) -> None:
    registry = ConfigScanRemoteRegistry(_Index([]))
    heard: list[int] = []
    registry.subscribe(lambda: heard.append(1))

    registry.add(tmp_path / "a")
    registry.add(tmp_path / "b")
    registry.remove(tmp_path / "a")

    assert heard == [1, 1]


def test__subscribe__a_failing_listener_does_not_break_adding_a_project(tmp_path: Path) -> None:
    registry = ConfigScanRemoteRegistry(_Index([]))
    heard: list[int] = []

    def broken() -> None:
        raise RuntimeError("слушатель упал")

    registry.subscribe(broken)
    registry.subscribe(lambda: heard.append(1))

    registry.add(tmp_path / "a")

    assert registry.list() == [tmp_path / "a"]
    assert heard == [1]


def test__consider__folder_with_a_remote_added_after_the_scan__is_listed_and_wakes_the_listeners(
    tmp_path: Path,
) -> None:
    registry = ConfigScanRemoteRegistry(_Index([]))
    woken: list[bool] = []
    registry.subscribe(lambda: woken.append(True))
    assert registry.list() == []
    copied = _store_config(tmp_path / "copied", _WITH_REMOTE)
    plain = _store_config(tmp_path / "plain", "[core]\n")

    registry.consider(copied)
    registry.consider(plain)

    assert registry.list() == [copied]
    assert woken == [True]
