"""Хранилище предпросмотра: записи сборок, журнал из кэша у ответа по кэшу, уборка по возрасту и числу."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.pack_studio.preview import PreviewAuthor, PreviewBuild, PreviewError, PreviewStatus
from hse_doc_studio.infra.pack_studio.preview_store import FsPreviewStore


def _build(key: str, **kwargs: object) -> PreviewBuild:
    base = dict(
        id=uuid4(),
        owner_id="u1",
        workspace_id=uuid4(),
        pack="p",
        template="t",
        version="1.0.0",
        document="report",
        example="auto:normal",
        combination={"lang": "ru"},
        key=key,
        status=PreviewStatus.failed,
        cached=False,
        created_at=datetime(2026, 11, 15, tzinfo=UTC),
        error=PreviewError("build_failed", "! Undefined control sequence."),
    )
    base.update(kwargs)
    return PreviewBuild(**base)  # type: ignore[arg-type]


def _kept(store: FsPreviewStore, key: str) -> None:
    build_id = uuid4()
    work = store.work_dir(build_id)
    (work / "r").mkdir()
    (work / "r" / "r.pdf").write_bytes(b"%PDF")
    assert store.keep(key, build_id, "r/r.tex", "r", "built", 2) is not None


def test__save_load__round_trip(tmp_path: Path) -> None:
    store = FsPreviewStore(tmp_path, max_cache_entries=5, max_age_s=3600)
    build = _build("ab" * 32)

    store.save(build)

    assert store.load(build.id) == build


def test__save_load__keeps_the_author_and_the_team_and_reads_records_without_them(tmp_path: Path) -> None:
    store = FsPreviewStore(tmp_path, max_cache_entries=5, max_age_s=3600)
    team = (PreviewAuthor("ivanov", "Иванов Иван Иванович"), PreviewAuthor("petrova", "Петрова Мария Сергеевна"))
    build = _build("cd" * 32, author="petrova", authors=team)
    old = _build("ef" * 32)

    store.save(build)
    store.save(old)
    # Запись, сделанная до появления выбора автора: ключей нет.
    record = next(p for p in tmp_path.rglob("*.json") if str(old.id) in p.name)
    data = json.loads(record.read_text(encoding="utf-8"))
    del data["author"], data["authors"]
    record.write_text(json.dumps(data), encoding="utf-8")

    loaded = store.load(build.id)
    assert loaded is not None
    assert (loaded.author, loaded.authors) == ("petrova", team)
    legacy = store.load(old.id)
    assert legacy is not None
    assert (legacy.author, legacy.authors) == (None, ())


def test__read_log__cache_hit_reads_the_log_of_the_build_that_made_the_pdf(tmp_path: Path) -> None:
    store = FsPreviewStore(tmp_path, max_cache_entries=5, max_age_s=3600)
    _kept(store, "ab" * 32)
    hit = _build("ab" * 32, status=PreviewStatus.succeeded, cached=True, error=None)

    assert store.read_log(hit) == "built"
    assert store.cached("ab" * 32) is not None


def test__prune__old_records_and_folders_and_extra_cache_entries(tmp_path: Path) -> None:
    store = FsPreviewStore(tmp_path, max_cache_entries=2, max_age_s=60)
    old = _build("ab" * 32)
    store.save(old)
    store.save_log(old.id, "x")
    fresh = _build("ab" * 32)
    store.save(fresh)
    stale_work = store.work_dir(uuid4())
    for index, key in enumerate(("aa" * 32, "bb" * 32, "cc" * 32)):
        _kept(store, key)
        os.utime(tmp_path / "cache" / key, (time.time() - 10 + index, time.time() - 10 + index))
    past = time.time() - 120
    for path in (tmp_path / "builds" / f"{old.id}.json", tmp_path / "builds" / f"{old.id}.log", stale_work):
        os.utime(path, (past, past))

    store.prune()

    assert store.load(old.id) is None
    assert store.load(fresh.id) is not None
    assert not stale_work.exists()
    assert sorted(p.name for p in (tmp_path / "cache").iterdir()) == ["bb" * 32, "cc" * 32]


def test__cache__key_must_be_hex(tmp_path: Path) -> None:
    store = FsPreviewStore(tmp_path, max_cache_entries=2, max_age_s=60)

    with pytest.raises(ValueError, match="cache key"):
        store.pdf("../x")
