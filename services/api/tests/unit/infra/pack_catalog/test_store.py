"""Хранилище подключённых паков: только дописывается, ключ по дайджесту, `catalog.json` терпим и атомарен."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from hse_doc_studio.core.pack_catalog.store import CatalogState, is_store_name, version_store_path
from hse_doc_studio.infra.pack_catalog.store import PacksStore, StoreIntegrityError, StoreLockTimeoutError, file_lock
from hse_doc_studio.infra.template.releases import version_digest

from tests.fixtures.pack_catalog import subscribe, write_pack


def _version(tmp_path: Path) -> tuple[Path, str]:
    pack = write_pack(tmp_path / "src")
    version_dir = pack / "templates" / "report" / "versions" / "2026.1.0"
    return version_dir, version_digest(version_dir)


def test__put_version__lands_by_digest_and_is_not_overwritten(tmp_path: Path) -> None:
    store = PacksStore(tmp_path / "store")
    version_dir, digest = _version(tmp_path)

    rel = store.put_version(version_dir, "acme", "report", "2026.1.0", digest)
    (version_dir / "files" / "report" / "main.tex").write_text("changed", encoding="utf-8")
    again = store.put_version(version_dir, "acme", "report", "2026.1.0", digest)

    assert rel == again == f"acme/report/2026.1.0@{digest.removeprefix('sha256:')}"
    assert version_digest(store.root / rel) == digest
    assert not list((store.root / ".staging").iterdir())


def test__put_version__refuses_a_copy_with_another_digest(tmp_path: Path) -> None:
    store = PacksStore(tmp_path / "store")
    version_dir, _ = _version(tmp_path)

    with pytest.raises(StoreIntegrityError):
        store.put_version(version_dir, "acme", "report", "2026.1.0", "sha256:" + "0" * 64)

    assert not (store.root / "acme" / "report").exists() or not list((store.root / "acme" / "report").iterdir())


def test__put_version__refuses_symlinks(tmp_path: Path) -> None:
    store = PacksStore(tmp_path / "store")
    version_dir, digest = _version(tmp_path)
    (version_dir / "files" / "link").symlink_to("/etc/hosts")

    with pytest.raises(StoreIntegrityError):
        store.put_version(version_dir, "acme", "report", "2026.1.0", digest)


@pytest.mark.parametrize("name", ["..", ".hidden", "a/b", "catalog.json", "", "x" * 101])
def test__store_names__unsafe_names_are_refused(name: str) -> None:
    assert not is_store_name(name)


def test__version_store_path__refuses_unsafe_keys() -> None:
    with pytest.raises(ValueError, match="ключ"):
        version_store_path("..", "t", "1", "sha256:" + "a" * 64)
    with pytest.raises(ValueError, match="ключ"):
        version_store_path("p", "t", "1", "md5:x")


def test__catalog__round_trips_and_drops_broken_records(tmp_path: Path) -> None:
    store = PacksStore(tmp_path / "store")
    state = subscribe(store, write_pack(tmp_path / "src"))
    raw = json.loads(store.catalog_path.read_text(encoding="utf-8"))
    raw["packs"].append({"id": "../evil", "meta": "x", "source_id": "s"})
    raw["packs"][0]["templates"][0]["versions"].append({"version": "1", "digest": "d", "dir": "../../etc"})
    store.catalog_path.write_text(json.dumps(raw), encoding="utf-8")

    read = store.read()

    assert read == state
    assert read.stored_digest("acme", "report", "2026.1.0") is not None


def test__catalog__newer_format_or_garbage_reads_as_empty(tmp_path: Path) -> None:
    store = PacksStore(tmp_path / "store")
    store.root.mkdir()
    store.catalog_path.write_text('{"format": 99, "revision": 3, "packs": []}', encoding="utf-8")
    assert store.read() == CatalogState()
    store.catalog_path.write_text("{oops", encoding="utf-8")
    assert store.read() == CatalogState()


def test__resolve__stays_inside_the_store(tmp_path: Path) -> None:
    store = PacksStore(tmp_path / "store")
    (store.root / "acme").mkdir(parents=True)
    (store.root / "acme" / "link").symlink_to(tmp_path)

    assert store.resolve("acme") == store.root / "acme"
    assert store.resolve("../outside") is None
    assert store.resolve("/etc") is None
    assert store.resolve("acme/link") is None


def test__stamp__changes_with_each_write(tmp_path: Path) -> None:
    store = PacksStore(tmp_path / "store")
    assert store.stamp() is None
    store.write(CatalogState(revision=1))
    first = store.stamp()
    store.write(CatalogState(revision=2))

    assert first is not None
    assert store.stamp() != first


def test__file_lock__second_writer_waits_then_times_out_and_stale_lock_is_taken(tmp_path: Path) -> None:
    lock = tmp_path / ".lock"
    with file_lock(lock), pytest.raises(StoreLockTimeoutError), file_lock(lock, wait_s=0.1):
        pass
    assert not lock.exists()

    lock.write_text("dead", encoding="utf-8")
    old = time.time() - 3600
    os.utime(lock, (old, old))
    with file_lock(lock, wait_s=0.1):
        assert lock.read_text(encoding="utf-8") != "dead"
