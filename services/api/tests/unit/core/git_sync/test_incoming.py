"""Предел на размер файлов чужой ветки проверяется по дереву, до чтения содержимого."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.git_sync.entities import TreeEntry
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.incoming import ensure_incoming_fits
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy

pytestmark = pytest.mark.unit

_POLICY = GitSyncPolicy(max_incoming_blob_bytes=1_000_000, max_incoming_total_bytes=2_500_000)


def _entry(path: str, size: int | None) -> TreeEntry:
    return TreeEntry(path=path, mode="100644", kind="blob", sha="a" * 40, size=size)


def test__ensure_incoming_fits__files_within_limits__passes() -> None:
    ensure_incoming_fits([_entry("a.bin", 1_000_000), _entry("b.bin", 1_000_000), _entry("link", None)], _POLICY)


def test__ensure_incoming_fits__one_blob_over_the_limit__refused_with_its_path() -> None:
    with pytest.raises(GitSyncError) as info:
        ensure_incoming_fits([_entry("ok.txt", 10), _entry("big.bin", 1_000_001)], _POLICY)

    assert info.value.code is GitErrorCode.git_error
    assert "big.bin" in info.value.detail


def test__ensure_incoming_fits__total_over_the_limit__refused() -> None:
    entries = [_entry(f"f{i}.bin", 900_000) for i in range(3)]

    with pytest.raises(GitSyncError) as info:
        ensure_incoming_fits(entries, _POLICY)

    assert info.value.code is GitErrorCode.git_error
