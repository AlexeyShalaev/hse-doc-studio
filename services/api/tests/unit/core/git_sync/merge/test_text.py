from __future__ import annotations

import re

import pytest
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.merge.choices import HunkChoice, HunkDecision
from hse_doc_studio.core.git_sync.merge.text import (
    CleanText,
    TextHunk,
    TextMerge,
    has_hse_markers,
    hunk_key,
    merge_text,
    parse_diff3,
    render,
    result_starts,
    single_hunk,
    split_lines,
    swap_sides,
    to_text_lines,
)
from hse_doc_studio.infra.template_update.merge_engine import GitMergeFileEngine
from hypothesis import given, settings
from hypothesis import strategies as st

from .helpers import git_merge_file

_MINE = HunkChoice.mine
_BASE = b"a\nb\nc\nd\ne\n"


def _hunks(merge: TextMerge) -> list[TextHunk]:
    return list(merge.hunks)


def test__merge_text__disjoint_edits__merge_cleanly(engine: GitMergeFileEngine) -> None:
    merge = merge_text(engine, b"A\nb\nc\nd\ne\n", _BASE, b"a\nb\nc\nd\nE\n")

    assert not merge.conflicted
    assert merge.clean_content == b"A\nb\nc\nd\nE\n"


def test__merge_text__same_line_edited_on_both_sides__makes_a_keyed_hunk(engine: GitMergeFileEngine) -> None:
    merge = merge_text(engine, b"a\nX\nc\nd\ne\n", _BASE, b"a\nY\nc\nd\ne\n")

    (hunk,) = _hunks(merge)
    assert (hunk.ours, hunk.base, hunk.theirs) == (b"X\n", b"b\n", b"Y\n")
    assert (hunk.ours_start, hunk.theirs_start) == (2, 2)
    assert hunk.key == hunk_key(b"X\n", b"Y\n")
    assert re.fullmatch(r"h:[0-9a-f]{8}", hunk.key)
    assert merge.segments[0] == CleanText(b"a\n")


def test__merge_text__two_hunks__keep_document_order_and_line_starts(engine: GitMergeFileEngine) -> None:
    merge = merge_text(engine, b"a\nX\nc\nQ\ne\n", _BASE, b"a\nY\nc\nR\ne\n")

    first, second = _hunks(merge)
    assert (first.ours_start, second.ours_start) == (2, 4)
    assert first.key != second.key


def test__merge_text__identical_hunks__get_distinct_keys(engine: GitMergeFileEngine) -> None:
    base = b"a\nb\nc\nb\ne\n"
    merge = merge_text(engine, b"a\nX\nc\nX\ne\n", base, b"a\nY\nc\nY\ne\n")

    first, second = _hunks(merge)
    assert second.key == f"{first.key}.2"


def test__hunk_key__ignores_line_endings_and_bom() -> None:
    assert hunk_key(b"\xef\xbb\xbfX\r\n", b"Y\r\n") == hunk_key(b"X\n", b"Y\n")


def test__merge_text__swapped_sides__give_the_same_hunks_with_sides_swapped(engine: GitMergeFileEngine) -> None:
    ours, theirs = b"a\nX\nc\nQ\ne\n", b"a\nY\nc\nR\ne\n"

    forward = merge_text(engine, ours, _BASE, theirs)
    backward = merge_text(engine, theirs, _BASE, ours)

    assert swap_sides(backward) == forward


def test__merge_text__crlf_and_bom_inputs__are_normalized(engine: GitMergeFileEngine) -> None:
    merge = merge_text(engine, b"\xef\xbb\xbfa\r\nX\r\nc\r\nd\r\n", b"a\nb\nc\nd\n", b"a\nb\nc\nD\n")

    assert merge.clean_content == b"a\nX\nc\nD\n"


def test__merge_text__input_with_marker_lines__is_opaque_not_parsed(engine: GitMergeFileEngine) -> None:
    base = b"a\n=======\nc\n"
    merge = merge_text(engine, b"a\n=======\nX\n", base, b"a\n=======\nY\n")

    assert merge.opaque
    assert merge.conflicted
    assert merge.hunks == ()


def test__merge_text__input_with_hse_marker_line__is_opaque(engine: GitMergeFileEngine) -> None:
    merge = merge_text(engine, b"<<<<<<< hse:ours\nX\n", b"a\n", b"Y\n")

    assert merge.opaque


def test__parse_diff3__unterminated_marker__is_none() -> None:
    assert parse_diff3(b"a\n<<<<<<< hse:ours\nX\n") is None


def test__parse_diff3__text_without_conflicts__is_one_clean_segment() -> None:
    assert parse_diff3(b"a\nb\n") == (CleanText(b"a\nb\n"),)


def test__render__every_choice__builds_the_expected_text(engine: GitMergeFileEngine) -> None:
    merge = merge_text(engine, b"a\nX\nc\nd\ne\n", _BASE, b"a\nY\nc\nd\ne\n")
    key = merge.hunks[0].key

    def choose(choice: HunkChoice, text: str | None = None) -> bytes:
        return render(merge, {key: HunkDecision(choice, text)})

    assert choose(HunkChoice.mine) == b"a\nX\nc\nd\ne\n"
    assert choose(HunkChoice.theirs) == b"a\nY\nc\nd\ne\n"
    assert choose(HunkChoice.both) == b"a\nX\nY\nc\nd\ne\n"
    assert choose(HunkChoice.both_reverse) == b"a\nY\nX\nc\nd\ne\n"
    assert choose(HunkChoice.base) == _BASE
    assert choose(HunkChoice.custom, "Z1\nZ2") == b"a\nZ1\nZ2\nc\nd\ne\n"
    assert choose(HunkChoice.custom, "") == b"a\nc\nd\ne\n"


def test__render__missing_choice_without_default__is_unresolved(engine: GitMergeFileEngine) -> None:
    merge = merge_text(engine, b"a\nX\nc\nd\ne\n", _BASE, b"a\nY\nc\nd\ne\n")

    with pytest.raises(GitSyncError) as error:
        render(merge, {})

    assert error.value.code is GitErrorCode.unresolved_conflicts
    assert error.value.ctx == {"hunks": [merge.hunks[0].key]}


def test__render__custom_without_text__is_invalid(engine: GitMergeFileEngine) -> None:
    merge = merge_text(engine, b"a\nX\nc\nd\ne\n", _BASE, b"a\nY\nc\nd\ne\n")

    with pytest.raises(GitSyncError) as error:
        render(merge, {merge.hunks[0].key: HunkDecision(HunkChoice.custom)})

    assert error.value.code is GitErrorCode.invalid_resolution


def test__result_starts__follow_the_chosen_text(engine: GitMergeFileEngine) -> None:
    merge = merge_text(engine, b"a\nX\nc\nQ\ne\n", _BASE, b"a\nY\nc\nR\ne\n")
    first, second = _hunks(merge)

    starts = result_starts(merge, {first.key: HunkDecision(HunkChoice.both)}, HunkChoice.mine)

    assert starts == {first.key: 2, second.key: 5}


def test__single_hunk__add_add__has_empty_base() -> None:
    merge = single_hunk(b"mine\r\n", b"theirs\n")

    (hunk,) = _hunks(merge)
    assert (hunk.ours, hunk.base, hunk.theirs) == (b"mine\n", b"", b"theirs\n")
    assert render(merge, {}, HunkChoice.both) == b"mine\ntheirs\n"


def test__has_hse_markers__labelled_lines_only() -> None:
    assert has_hse_markers(b"a\n<<<<<<< hse:ours\nb\n")
    assert has_hse_markers(b"a\r\n>>>>>>> hse:theirs\r\n")
    assert not has_hse_markers(b"<<<<<<< HEAD\n=======\n>>>>>>> main\n")
    assert not has_hse_markers(b"x <<<<<<< hse:ours\n")


def test__split_lines__keeps_terminators_and_unterminated_tail() -> None:
    assert split_lines(b"a\nb\nc") == [b"a\n", b"b\n", b"c"]
    assert split_lines(b"") == []
    assert to_text_lines("а\nб\n".encode()) == ["а", "б"]


@pytest.mark.parametrize(("ours_tail", "theirs_tail"), [(b"", b"\n"), (b"\n", b""), (b"", b"")])
@pytest.mark.parametrize("mode", ["--ours", "--theirs", "--union"])
def test__render__last_hunk_without_final_newline__matches_git(
    engine: GitMergeFileEngine, ours_tail: bytes, theirs_tail: bytes, mode: str
) -> None:
    ours, base, theirs = b"a\nX" + ours_tail, b"a\nb\n", b"a\nY" + theirs_tail
    merge = merge_text(engine, ours, base, theirs)

    assert render(merge, {}, _MODES[mode]) == git_merge_file(ours, base, theirs, mode)


_MODES = {"--ours": HunkChoice.mine, "--theirs": HunkChoice.theirs, "--union": HunkChoice.both}

_LINES = st.lists(st.sampled_from(["a", "b", "c", "d", "e", ""]), max_size=7)


def _text(lines: list[str], *, final_newline: bool) -> bytes:
    body = "\n".join(lines).encode()
    return body + b"\n" if lines and final_newline else body


_TEXTS = st.builds(_text, _LINES, final_newline=st.booleans())


@pytest.mark.parametrize("mode", sorted(_MODES))
@settings(max_examples=50, deadline=None)
@given(ours=_TEXTS, base=_TEXTS, theirs=_TEXTS)
def test__render__uniform_choice__equals_git_merge_file(ours: bytes, base: bytes, theirs: bytes, mode: str) -> None:
    engine = GitMergeFileEngine("hse:ours", "hse:base", "hse:theirs")
    expected = git_merge_file(ours, base, theirs, mode)

    merge = merge_text(engine, ours, base, theirs)

    assert render(merge, {}, _MODES[mode]) == expected
