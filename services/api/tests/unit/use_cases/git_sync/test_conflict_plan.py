from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from hse_doc_studio.core.git_sync.entities import PathStamp, TreeEntry
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.merge.rules import StateFileMerge
from hse_doc_studio.core.git_sync.merge.text import BASE_LABEL, OURS_LABEL, THEIRS_LABEL
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.infra.template_update.merge_engine import GitMergeFileEngine
from hse_doc_studio.use_cases.git_sync import conflict_plan
from hse_doc_studio.use_cases.git_sync.conflict_plan import ConflictPlanner

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def engine() -> GitMergeFileEngine:
    return GitMergeFileEngine(OURS_LABEL, BASE_LABEL, THEIRS_LABEL)


_FOLDER = Path("/projects/p")
_BASE, _OURS, _THEIRS = "b" * 40, "a" * 40, "c" * 40
_TREES: dict[str, dict[str, bytes]] = {
    _BASE: {"doc.tex": b"1\n2\n3\n"},
    _OURS: {"doc.tex": b"mine\n2\n3\n"},
    _THEIRS: {"doc.tex": b"theirs\n2\n3\n"},
}


class _Reader:
    """Хранилище из трёх деревьев в памяти; считает обращения, чтобы видеть, когда план строился заново."""

    def __init__(self, base: str | None = _BASE) -> None:
        self.base = base
        self.reads = 0

    def merge_base(self, _folder: Path, _a: str, _b: str) -> str | None:
        return self.base

    def tree_entries(self, _folder: Path, commit: str) -> list[TreeEntry]:
        return [TreeEntry(path, "100644", "blob", "0" * 40, len(data)) for path, data in _TREES[commit].items()]

    def changed_paths(self, _folder: Path, _a: str, _b: str) -> list[tuple[str, str]]:
        return [("M", "doc.tex")]

    def read_files(self, _folder: Path, commit: str, paths: Sequence[str]) -> Mapping[str, bytes | None]:
        self.reads += 1
        return {path: _TREES[commit].get(path) for path in paths}

    def path_stamp(self, *_args: object, **_kwargs: object) -> PathStamp | None:
        return None


def _planner(reader: _Reader, engine: GitMergeFileEngine) -> ConflictPlanner:
    return ConflictPlanner(reader=reader, engine=engine, structured=StateFileMerge(), policy=GitSyncPolicy())  # type: ignore[arg-type]


def test__plan__same_commits__are_read_once_and_the_plan_is_reused(engine: GitMergeFileEngine) -> None:
    reader = _Reader()
    planner = _planner(reader, engine)

    first = planner.plan(_FOLDER, _OURS, _THEIRS, adopted_unrelated=False)
    second = planner.plan(_FOLDER, _OURS, _THEIRS, adopted_unrelated=False)

    assert first is second
    assert reader.reads == 3
    assert [op.path for op in first.conflicts] == ["doc.tex"]


def test__plan__another_tip__is_built_again(engine: GitMergeFileEngine) -> None:
    reader = _Reader()
    planner = _planner(reader, engine)
    planner.plan(_FOLDER, _OURS, _THEIRS, adopted_unrelated=False)

    other = planner.plan(_FOLDER, _BASE, _THEIRS, adopted_unrelated=False)

    assert reader.reads == 6
    assert other.conflicts == ()


def test__plan__heavy_plans_are_not_kept(engine: GitMergeFileEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(conflict_plan, "_CACHE_BYTES", 1)
    reader = _Reader()
    planner = _planner(reader, engine)

    planner.plan(_FOLDER, _OURS, _THEIRS, adopted_unrelated=False)
    planner.plan(_FOLDER, _OURS, _THEIRS, adopted_unrelated=False)

    assert reader.reads == 6


def test__plan__oldest_plans_leave_the_cache(engine: GitMergeFileEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(conflict_plan, "_CACHE_PLANS", 1)
    reader = _Reader()
    planner = _planner(reader, engine)

    planner.plan(_FOLDER, _OURS, _THEIRS, adopted_unrelated=False)
    planner.plan(_FOLDER, _BASE, _THEIRS, adopted_unrelated=False)
    planner.plan(_FOLDER, _OURS, _THEIRS, adopted_unrelated=False)

    assert reader.reads == 9


def test__plan__no_common_history__needs_the_consent(engine: GitMergeFileEngine) -> None:
    planner = _planner(_Reader(base=None), engine)

    with pytest.raises(GitSyncError) as raised:
        planner.plan(_FOLDER, _OURS, _THEIRS, adopted_unrelated=False)

    assert raised.value.code is GitErrorCode.unrelated_histories
    assert raised.value.ctx == {"can_adopt": True}
    adopted = planner.plan(_FOLDER, _OURS, _THEIRS, adopted_unrelated=True)
    assert adopted.base_commit is None
