from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.git_sync.merge.binary import (
    blob_sha,
    conflict_copy_name,
    is_derived_pdf,
    merge_binary,
    newest_side,
)
from hse_doc_studio.core.git_sync.merge.entities import MergeSide
from hse_doc_studio.core.git_sync.protocols import MergeMeta
from hypothesis import given
from hypothesis import strategies as st

_T1 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
_T2 = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
_PNG_A = b"\x89PNG\r\n\x1a\nAAAA"
_PNG_B = b"\x89PNG\r\n\x1a\nBBBB"


def test__blob_sha__matches_git_hash_object() -> None:
    assert blob_sha(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"
    assert blob_sha(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("figure.png", "figure.conflict-{sha}.png"),
        ("figures/scheme.png", "figures/scheme.conflict-{sha}.png"),
        ("archive.tar.gz", "archive.tar.conflict-{sha}.gz"),
        ("Makefile", "Makefile.conflict-{sha}"),
        ("рисунок.png", "рисунок.conflict-{sha}.png"),
    ],
)
def test__conflict_copy_name__keeps_directory_stem_and_suffix(path: str, expected: str) -> None:
    sha = blob_sha(_PNG_B)[:7]

    assert conflict_copy_name(path, _PNG_B) == expected.format(sha=sha)


@pytest.mark.parametrize(
    ("path", "derived"),
    [
        ("main.pdf", True),
        ("build/Main.PDF", True),
        (".hse-studio/frozen/main.pdf", False),
        (".hse-studio/detached/main/slot.pdf", False),
        ("figure.png", False),
    ],
)
def test__is_derived_pdf__only_rebuildable_pdfs(path: str, derived: bool) -> None:
    assert is_derived_pdf(path) is derived


def test__merge_binary__newer_theirs__wins_and_ours_is_kept_as_a_copy() -> None:
    meta = MergeMeta(ours_changed_at=_T1, theirs_changed_at=_T2, ours_commit="a" * 40, theirs_commit="b" * 40)

    outcome = merge_binary("figures/scheme.png", _PNG_A, _PNG_B, meta)

    assert outcome.winner is MergeSide.theirs
    assert outcome.copy_path == conflict_copy_name("figures/scheme.png", _PNG_A)
    assert outcome.copy_content == _PNG_A


def test__merge_binary__newer_ours__wins_and_theirs_is_kept_as_a_copy() -> None:
    meta = MergeMeta(ours_changed_at=_T2, theirs_changed_at=_T1)

    outcome = merge_binary("scheme.png", _PNG_A, _PNG_B, meta)

    assert outcome.winner is MergeSide.ours
    assert outcome.copy_content == _PNG_B


def test__merge_binary__derived_pdf__has_no_copy() -> None:
    outcome = merge_binary("main.pdf", b"%PDF-1", b"%PDF-2", MergeMeta(ours_changed_at=_T1, theirs_changed_at=_T2))

    assert outcome.winner is MergeSide.theirs
    assert (outcome.copy_path, outcome.copy_content) == (None, None)


def test__merge_binary__signed_pdf__keeps_a_copy() -> None:
    outcome = merge_binary(".hse-studio/frozen/main.pdf", b"%PDF-1", b"%PDF-2", MergeMeta())

    assert outcome.copy_path is not None


def test__newest_side__same_time__commit_hash_breaks_the_tie() -> None:
    meta = MergeMeta(ours_changed_at=_T1, theirs_changed_at=_T1, ours_commit="a" * 40, theirs_commit="b" * 40)

    assert newest_side(_PNG_A, _PNG_B, meta) is MergeSide.theirs


def test__newest_side__no_stamps__content_hash_breaks_the_tie() -> None:
    forward = newest_side(_PNG_A, _PNG_B, MergeMeta())
    backward = newest_side(_PNG_B, _PNG_A, MergeMeta())

    assert {forward, backward} == {MergeSide.ours, MergeSide.theirs}


def test__newest_side__missing_stamp_loses_to_a_known_one() -> None:
    assert newest_side(_PNG_A, _PNG_B, MergeMeta(theirs_changed_at=_T1)) is MergeSide.theirs
    assert newest_side(_PNG_A, _PNG_B, MergeMeta(ours_changed_at=_T1)) is MergeSide.ours


def test__newest_side__naive_datetime__is_read_as_utc() -> None:
    naive = MergeMeta(ours_changed_at=datetime(2026, 10, 2, 12, 0), theirs_changed_at=_T1)  # noqa: DTZ001

    assert newest_side(_PNG_A, _PNG_B, naive) is MergeSide.ours


_STAMPS = st.one_of(st.none(), st.integers(0, 3).map(lambda n: datetime(2026, 10, 1 + n, tzinfo=UTC)))
_COMMITS = st.one_of(st.none(), st.sampled_from(["a" * 40, "b" * 40]))


@given(
    ours=st.binary(min_size=1, max_size=8),
    theirs=st.binary(min_size=1, max_size=8),
    ours_at=_STAMPS,
    theirs_at=_STAMPS,
    ours_commit=_COMMITS,
    theirs_commit=_COMMITS,
)
def test__merge_binary__swapped_sides__pick_the_same_physical_version(
    ours: bytes,
    theirs: bytes,
    ours_at: datetime | None,
    theirs_at: datetime | None,
    ours_commit: str | None,
    theirs_commit: str | None,
) -> None:
    if ours == theirs:
        return
    forward = merge_binary("a.png", ours, theirs, MergeMeta(ours_at, theirs_at, ours_commit, theirs_commit))
    backward = merge_binary("a.png", theirs, ours, MergeMeta(theirs_at, ours_at, theirs_commit, ours_commit))

    kept_forward = ours if forward.winner is MergeSide.ours else theirs
    kept_backward = theirs if backward.winner is MergeSide.ours else ours
    assert kept_forward == kept_backward
    assert (forward.copy_path, forward.copy_content) == (backward.copy_path, backward.copy_content)
    assert {kept_forward, forward.copy_content} == {ours, theirs}
