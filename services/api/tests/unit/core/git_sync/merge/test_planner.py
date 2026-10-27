from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.git_sync.entities import SyncWarning, SyncWarningCode
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.merge.binary import conflict_copy_name
from hse_doc_studio.core.git_sync.merge.choices import (
    FieldChoice,
    FieldDecision,
    FieldsResolution,
    FileChoice,
    FileChoiceResolution,
    FileResolution,
    HunkChoice,
    HunkDecision,
    HunksResolution,
    TextResolution,
)
from hse_doc_studio.core.git_sync.merge.entities import ConflictType, ContentKind, MergeAction, MergeOp, MergeSide
from hse_doc_studio.core.git_sync.merge.planner import (
    MergeInput,
    ensure_tree_shape,
    plan_fingerprint,
    plan_merge,
    resolve_plan,
)
from hse_doc_studio.core.git_sync.protocols import MergeDecision, MergeMeta
from hse_doc_studio.core.template_update.entities import FileWrite, FileWriteKind
from hse_doc_studio.infra.template_update.merge_engine import GitMergeFileEngine

from .helpers import apply_writes

_B, _O, _T = b"base\n", b"ours\n", b"theirs\n"
_PNG_A = b"\x89PNG\r\n\x1a\nAAAA"
_PNG_B = b"\x89PNG\r\n\x1a\nBBBB"
_LINES = b"a\nb\nc\nd\ne\n"
_EARLY = datetime(2026, 10, 1, tzinfo=UTC)
_LATE = datetime(2026, 10, 2, tzinfo=UTC)


def _tree(path: str, content: bytes | None) -> dict[str, bytes]:
    return {} if content is None else {path: content}


def _plan(
    engine: GitMergeFileEngine,
    base: Mapping[str, bytes],
    ours: Mapping[str, bytes],
    theirs: Mapping[str, bytes],
    **kwargs: object,
):  # noqa: ANN202
    structured = kwargs.pop("structured", None)
    return plan_merge(MergeInput(base, ours, theirs, **kwargs), engine, structured)  # type: ignore[arg-type]


def _write(path: str, content: bytes) -> FileWrite:
    return FileWrite(path, FileWriteKind.write, content)


@pytest.mark.parametrize(
    ("base", "ours", "theirs", "action", "conflict"),
    [
        (None, None, None, None, None),
        (_B, _B, _B, None, None),
        (_B, _O, _B, None, None),
        (_B, _B, _T, MergeAction.take_theirs, None),
        (_B, _O, _O, None, None),
        (_B, None, None, None, None),
        (_B, None, _B, None, None),
        (_B, _B, None, MergeAction.delete, None),
        (_B, None, _T, MergeAction.conflict, ConflictType.deleted_by_us),
        (_B, _O, None, MergeAction.conflict, ConflictType.deleted_by_them),
        (None, _O, None, None, None),
        (None, None, _T, MergeAction.take_theirs, None),
        (None, _O, _O, None, None),
        (None, _O, _T, MergeAction.conflict, ConflictType.add_add),
        (_B, _O, _T, MergeAction.conflict, ConflictType.content),
    ],
)
def test__plan_merge__presence_matrix__text_file(
    engine: GitMergeFileEngine,
    base: bytes | None,
    ours: bytes | None,
    theirs: bytes | None,
    action: MergeAction | None,
    conflict: ConflictType | None,
) -> None:
    plan = _plan(engine, _tree("a.tex", base), _tree("a.tex", ours), _tree("a.tex", theirs))

    if action is None:
        assert plan.ops == ()
        return
    (op,) = plan.ops
    assert (op.action, op.conflict_type) == (action, conflict)
    assert (op.base, op.ours, op.theirs) == (base, ours, theirs)


def test__plan_merge__empty_input__is_a_clean_empty_plan(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, {}, {}, {})

    assert plan.ops == ()
    assert plan.is_clean
    assert plan.warnings == ()


def test__plan_merge__disjoint_text_edits__merge_into_one_file(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, {"a.tex": _LINES}, {"a.tex": b"A\nb\nc\nd\ne\n"}, {"a.tex": b"a\nb\nc\nd\nE\n"})

    (op,) = plan.ops
    assert (op.action, op.merged) == (MergeAction.merged, b"A\nb\nc\nd\nE\n")
    assert plan.is_clean


def test__plan_merge__merge_result_equal_to_ours__is_no_op(engine: GitMergeFileEngine) -> None:
    ours = b"A\nb\nc\nd\ne\n"
    plan = _plan(engine, {"a.tex": _LINES}, {"a.tex": ours}, {"a.tex": ours.replace(b"A", b"a")})

    assert plan.ops == ()


def test__plan_merge__merge_result_equal_to_theirs__is_take_theirs(engine: GitMergeFileEngine) -> None:
    theirs = b"A\nb\nc\nd\nE\n"
    plan = _plan(engine, {"a.tex": _LINES}, {"a.tex": b"A\nb\nc\nd\ne\n"}, {"a.tex": theirs})

    (op,) = plan.ops
    assert op.action is MergeAction.take_theirs


def test__plan_merge__crlf_edit_on_one_side_and_lf_edit_on_the_other__merge_without_phantom_conflict(
    engine: GitMergeFileEngine,
) -> None:
    ours = b"\xef\xbb\xbfA\r\nb\r\nc\r\nd\r\ne\r\n"
    plan = _plan(engine, {"a.tex": _LINES}, {"a.tex": ours}, {"a.tex": b"a\nb\nc\nd\nE\n"})

    (op,) = plan.ops
    assert op.action is MergeAction.merged
    assert op.merged == b"\xef\xbb\xbfA\r\nb\r\nc\r\nd\r\nE\r\n"


def test__plan_merge__only_line_endings_differ__changes_nothing(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, {"a.tex": _LINES}, {"a.tex": _LINES.replace(b"\n", b"\r\n")}, {"a.tex": _LINES})

    assert plan.ops == ()


def test__plan_merge__only_ours_changed_line_endings_and_theirs_edited__takes_theirs_with_ours_style(
    engine: GitMergeFileEngine,
) -> None:
    ours = _LINES.replace(b"\n", b"\r\n")
    plan = _plan(engine, {"a.tex": _LINES}, {"a.tex": ours}, {"a.tex": b"A\nb\nc\nd\ne\n"})

    (writes,) = [resolve_plan(plan, {})]
    assert writes == [_write("a.tex", b"A\r\nb\r\nc\r\nd\r\ne\r\n")]


def test__plan_merge__text_conflict__keeps_my_side_as_placeholder_and_exposes_hunks(
    engine: GitMergeFileEngine,
) -> None:
    plan = _plan(engine, {"a.tex": _LINES}, {"a.tex": b"a\nX\nc\nd\ne\n"}, {"a.tex": b"a\nY\nc\nd\ne\n"})

    (op,) = plan.ops
    assert op.needs_decision
    assert op.kind is ContentKind.text
    assert [(h.ours, h.theirs) for h in op.hunks] == [(b"X\n", b"Y\n")]
    assert op.merged == b"a\nX\nc\nd\ne\n"
    assert op.allowed_choices() == (FileChoice.mine, FileChoice.theirs)
    assert op.default_choice is None
    assert not plan.is_clean
    assert plan.conflicts == (op,)
    assert plan.op("a.tex") is op
    assert plan.op("other") is None


def test__plan_merge__both_added_binary__newest_wins_with_a_copy(engine: GitMergeFileEngine) -> None:
    meta = {"f.png": MergeMeta(ours_changed_at=_EARLY, theirs_changed_at=_LATE)}
    plan = _plan(engine, {}, {"f.png": _PNG_A}, {"f.png": _PNG_B}, meta=meta)

    (op,) = plan.ops
    assert (op.action, op.kind, op.winner) == (MergeAction.binary_newest, ContentKind.binary, MergeSide.theirs)
    assert op.copy_path == conflict_copy_name("f.png", _PNG_A)
    assert op.allowed_choices() == (FileChoice.newest, FileChoice.mine, FileChoice.theirs)
    assert op.default_choice is FileChoice.newest
    assert plan.is_clean


def test__plan_merge__pdf_is_binary_even_when_ascii(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, {"m.pdf": b"%PDF-0"}, {"m.pdf": b"%PDF-1"}, {"m.pdf": b"%PDF-2"})

    (op,) = plan.ops
    assert (op.action, op.copy_path) == (MergeAction.binary_newest, None)


def test__plan_merge__zip_repacked_only__is_no_change(engine: GitMergeFileEngine) -> None:
    import io
    import zipfile

    def pack(level: int) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=level) as archive:
            archive.writestr("ppt/slide1.xml", b"<a>" * 200)
        return buffer.getvalue()

    plan = _plan(engine, {"s.pptx": pack(1)}, {"s.pptx": pack(9)}, {"s.pptx": pack(1)})

    assert plan.ops == ()


def test__plan_merge__binary_deleted_on_one_side_and_changed_on_the_other__is_a_conflict(
    engine: GitMergeFileEngine,
) -> None:
    plan = _plan(engine, {"f.png": _PNG_A}, {"f.png": _PNG_B}, {})

    (op,) = plan.ops
    assert (op.action, op.conflict_type) == (MergeAction.conflict, ConflictType.deleted_by_them)


def test__plan_merge__unsafe_paths__are_skipped_with_a_warning(engine: GitMergeFileEngine) -> None:
    theirs = {"../escape.tex": b"x\n", ".git/config": b"x\n", ".hse-studio/git/HEAD": b"x\n", "ok.tex": b"x\n"}
    plan = _plan(engine, {}, {}, theirs, blocked=frozenset({"link.tex"}))

    assert [op.path for op in plan.ops] == ["ok.tex"]
    (warning,) = plan.warnings
    assert warning == SyncWarning(SyncWarningCode.unsafe_path, ("../escape.tex", ".git/config", ".hse-studio/git/HEAD"))


@pytest.mark.parametrize(
    ("ours", "theirs"),
    [
        ({"notes/x.txt": b"mine\n"}, {"notes": b"theirs\n"}),
        ({"notes": b"mine\n"}, {"notes/x.txt": b"theirs\n"}),
        ({"a/b/c.tex": b"mine\n"}, {"a/b": b"theirs\n"}),
    ],
    ids=["their_file_over_my_folder", "their_folder_over_my_file", "deeper"],
)
def test__plan_merge__file_and_folder_with_one_name__is_refused_before_anything_is_written(
    engine: GitMergeFileEngine, ours: dict[str, bytes], theirs: dict[str, bytes]
) -> None:
    plan = _plan(engine, {}, {}, theirs)

    with pytest.raises(GitSyncError) as info:
        ensure_tree_shape(plan, ours)

    assert info.value.code is GitErrorCode.git_error
    assert info.value.ctx["paths"]


def test__plan_merge__their_deletion_of_the_folder_makes_room_for_the_file(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, {"notes/x.txt": b"a\n"}, {"notes/x.txt": b"a\n"}, {"notes": b"theirs\n"})

    ensure_tree_shape(plan, ["notes/x.txt"])
    assert {(op.path, op.action) for op in plan.ops} == {
        ("notes", MergeAction.take_theirs),
        ("notes/x.txt", MergeAction.delete),
    }


def test__plan_merge__blocked_paths__are_never_planned(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, {}, {}, {"link.tex": b"x\n"}, blocked=frozenset({"link.tex"}))

    assert plan.ops == ()
    assert plan.warnings == (SyncWarning(SyncWarningCode.unsafe_path, ("link.tex",)),)


def test__plan_merge__added_file_differing_by_case_from_mine__lands_beside_it(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, {}, {"Chapter.tex": b"mine\n"}, {"chapter.tex": b"theirs\n"})

    (op,) = plan.ops
    assert op.path == conflict_copy_name("chapter.tex", b"theirs\n")
    assert op.action is MergeAction.take_theirs
    assert plan.warnings == (SyncWarning(SyncWarningCode.case_collision, ("chapter.tex",)),)


def test__plan_merge__nfd_name_colliding_with_nfc__lands_beside_it(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, {}, {"й.tex": b"mine\n"}, {"й.tex": b"theirs\n"})

    (op,) = plan.ops
    assert op.path != "й.tex"
    assert plan.warnings[0].code is SyncWarningCode.case_collision


def test__plan_merge__both_names_added_by_theirs__the_first_by_order_keeps_the_name(
    engine: GitMergeFileEngine,
) -> None:
    plan = _plan(engine, {}, {}, {"A.tex": b"1\n", "a.tex": b"2\n"})

    assert sorted(op.path for op in plan.ops) == sorted(["A.tex", conflict_copy_name("a.tex", b"2\n")])


def test__plan_merge__case_only_rename_by_theirs__is_not_a_collision(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, {"Chapter.tex": b"x\n"}, {"Chapter.tex": b"x\n"}, {"chapter.tex": b"x\n"})

    assert plan.warnings == ()
    assert {op.path: op.action for op in plan.ops} == {
        "Chapter.tex": MergeAction.delete,
        "chapter.tex": MergeAction.take_theirs,
    }


def test__plan_merge__ops_are_sorted_by_path(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, {}, {}, {"b.tex": b"1\n", "a.tex": b"1\n", "c/d.tex": b"1\n"})

    assert [op.path for op in plan.ops] == ["a.tex", "b.tex", "c/d.tex"]


class _FieldsStrategy:
    def __init__(self, decision: MergeDecision) -> None:
        self.decision = decision
        self.calls: list[str] = []

    def merge(
        self, path: str, base: bytes | None, ours: bytes | None, theirs: bytes | None, meta: MergeMeta
    ) -> MergeDecision:
        self.calls.append(path)
        return self.decision


def test__plan_merge__structured_strategy__handles_state_json_only(engine: GitMergeFileEngine) -> None:
    strategy = _FieldsStrategy(MergeDecision(b'{"merged": true}\n'))
    base = {".hse-studio/project.json": b'{"a": 1}\n', "data.json": b'{"a": 1}\n'}
    ours = {".hse-studio/project.json": b'{"a": 2}\n', "data.json": b'{"a": 2}\n'}
    theirs = {".hse-studio/project.json": b'{"a": 3}\n', "data.json": b'{"a": 3}\n'}

    plan = _plan(engine, base, ours, theirs, structured=strategy)

    assert strategy.calls == [".hse-studio/project.json"]
    by_path = {op.path: op for op in plan.ops}
    assert by_path[".hse-studio/project.json"].kind is ContentKind.json
    assert by_path[".hse-studio/project.json"].merged == b'{"merged": true}\n'
    assert by_path["data.json"].kind is ContentKind.text
    assert by_path["data.json"].action is MergeAction.conflict


def test__plan_merge__structured_conflict__is_decided_for_the_whole_file(engine: GitMergeFileEngine) -> None:
    strategy = _FieldsStrategy(MergeDecision(b'{"a": 2}\n', conflict=True))
    path = ".hse-studio/project.json"
    plan = _plan(engine, {path: b'{"a": 1}\n'}, {path: b'{"a": 2}\n'}, {path: b'{"a": 3}\n'}, structured=strategy)

    (op,) = plan.ops
    assert (op.action, op.conflict_type, op.merged) == (MergeAction.conflict, ConflictType.fields, b'{"a": 2}\n')
    assert resolve_plan(plan, {path: FileChoiceResolution(FileChoice.theirs)}) == [_write(path, b'{"a": 3}\n')]
    assert resolve_plan(plan, {path: FileChoiceResolution(FileChoice.mine)}) == []


def test__plan_merge__structured_deleted_decision__deletes_the_file(engine: GitMergeFileEngine) -> None:
    strategy = _FieldsStrategy(MergeDecision(None, deleted=True))
    path = ".hse-studio/forms/f.json"
    plan = _plan(engine, {path: b"{}\n"}, {path: b'{"a": 1}\n'}, {path: b'{"b": 1}\n'}, structured=strategy)

    (op,) = plan.ops
    assert op.action is MergeAction.delete


# --- fingerprint -------------------------------------------------------------------------------


def _conflicting(engine: GitMergeFileEngine, **changes: object):  # noqa: ANN202
    base = {"a.tex": _LINES, "keep.tex": b"k\n"}
    ours = {"a.tex": b"a\nX\nc\nd\ne\n", "keep.tex": b"k\n"}
    theirs = {"a.tex": b"a\nY\nc\nd\ne\n", "keep.tex": b"k\n", "new.tex": b"n\n"}
    args = {"base": base, "ours": ours, "theirs": theirs, "base_commit": "b" * 40, "theirs_commit": "c" * 40}
    args.update(changes)
    return plan_merge(MergeInput(**args), engine)  # type: ignore[arg-type]


def test__fingerprint__is_stable_for_identical_input(engine: GitMergeFileEngine) -> None:
    assert _conflicting(engine).fingerprint == _conflicting(engine).fingerprint


def test__fingerprint__ignores_unrelated_edits_and_new_clean_files(engine: GitMergeFileEngine) -> None:
    ours = {"a.tex": b"a\nX\nc\nd\ne\n", "keep.tex": b"edited\n", "mine.tex": b"added\n"}
    base = {"a.tex": _LINES, "keep.tex": b"k\n"}

    assert _conflicting(engine, ours=ours, base=base).fingerprint == _conflicting(engine).fingerprint


def test__fingerprint__ignores_the_theirs_blob_of_a_clean_path(engine: GitMergeFileEngine) -> None:
    theirs = {"a.tex": b"a\nY\nc\nd\ne\n", "keep.tex": b"k\n", "new.tex": b"other\n"}

    assert _conflicting(engine, theirs=theirs).fingerprint == _conflicting(engine).fingerprint


def test__fingerprint__changes_with_the_conflicted_ours_blob(engine: GitMergeFileEngine) -> None:
    ours = {"a.tex": b"a\nXX\nc\nd\ne\n", "keep.tex": b"k\n"}

    assert _conflicting(engine, ours=ours).fingerprint != _conflicting(engine).fingerprint


def test__fingerprint__changes_with_the_conflicted_theirs_blob(engine: GitMergeFileEngine) -> None:
    theirs = {"a.tex": b"a\nYY\nc\nd\ne\n", "keep.tex": b"k\n", "new.tex": b"n\n"}

    assert _conflicting(engine, theirs=theirs).fingerprint != _conflicting(engine).fingerprint


@pytest.mark.parametrize("field", ["base_commit", "theirs_commit"])
def test__fingerprint__changes_with_the_commits(engine: GitMergeFileEngine, field: str) -> None:
    assert _conflicting(engine, **{field: "f" * 40}).fingerprint != _conflicting(engine).fingerprint


def test__fingerprint__without_conflicts__depends_on_commits_only(engine: GitMergeFileEngine) -> None:
    one = plan_fingerprint((), base_commit="b", theirs_commit="c")

    assert one == plan_fingerprint((), base_commit="b", theirs_commit="c")
    assert one != plan_fingerprint((), base_commit="b", theirs_commit="d")
    assert plan_fingerprint((), base_commit=None, theirs_commit=None) != one


def test__fingerprint__does_not_depend_on_the_order_of_input_mappings(engine: GitMergeFileEngine) -> None:
    a = _conflicting(engine, theirs={"z.tex": b"1\n", "a.tex": b"a\nY\nc\nd\ne\n", "keep.tex": b"k\n"})
    b = _conflicting(engine, theirs={"keep.tex": b"k\n", "a.tex": b"a\nY\nc\nd\ne\n", "z.tex": b"1\n"})

    assert a.fingerprint == b.fingerprint
    assert a.ops == b.ops


# --- resolve_plan ------------------------------------------------------------------------------


def _text_plan(engine: GitMergeFileEngine):  # noqa: ANN202
    base = b"a\nb\nc\nd\ne\nf\ng\n"
    ours = b"a\nX\nc\nd\ne\nQ\ng\n"
    theirs = b"a\nY\nc\nd\ne\nR\ng\n"
    return _plan(engine, {"a.tex": base}, {"a.tex": ours}, {"a.tex": theirs})


def _decide(plan_op: MergeOp, choice: HunkChoice, text: str | None = None) -> HunksResolution:
    return HunksResolution({h.key: HunkDecision(choice, text) for h in plan_op.hunks})


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        (HunkChoice.theirs, b"a\nY\nc\nd\ne\nR\ng\n"),
        (HunkChoice.both, b"a\nX\nY\nc\nd\ne\nQ\nR\ng\n"),
        (HunkChoice.both_reverse, b"a\nY\nX\nc\nd\ne\nR\nQ\ng\n"),
        (HunkChoice.base, b"a\nb\nc\nd\ne\nf\ng\n"),
    ],
)
def test__resolve_plan__hunk_choice__writes_the_rendered_file(
    engine: GitMergeFileEngine, choice: HunkChoice, expected: bytes
) -> None:
    plan = _text_plan(engine)

    assert resolve_plan(plan, {"a.tex": _decide(plan.ops[0], choice)}) == [_write("a.tex", expected)]


def test__resolve_plan__all_hunks_mine__writes_nothing(engine: GitMergeFileEngine) -> None:
    plan = _text_plan(engine)

    assert resolve_plan(plan, {"a.tex": _decide(plan.ops[0], HunkChoice.mine)}) == []


def test__resolve_plan__mixed_hunk_choices_and_custom_text__restore_my_line_endings(
    engine: GitMergeFileEngine,
) -> None:
    base, ours, theirs = (b"a\nb\nc\nd\ne\nf\ng\n", b"a\nX\nc\nd\ne\nQ\ng\n", b"a\nY\nc\nd\ne\nR\ng\n")
    plan = _plan(engine, {"a.tex": base}, {"a.tex": ours.replace(b"\n", b"\r\n")}, {"a.tex": theirs})
    first, second = plan.ops[0].hunks
    resolution = HunksResolution(
        {first.key: HunkDecision(HunkChoice.custom, "Z1\nZ2"), second.key: HunkDecision(HunkChoice.theirs)}
    )

    assert resolve_plan(plan, {"a.tex": resolution}) == [_write("a.tex", b"a\r\nZ1\r\nZ2\r\nc\r\nd\r\ne\r\nR\r\ng\r\n")]


def test__resolve_plan__missing_hunk_decision__is_unresolved_with_the_path(engine: GitMergeFileEngine) -> None:
    plan = _text_plan(engine)
    first = plan.ops[0].hunks[0]

    with pytest.raises(GitSyncError) as error:
        resolve_plan(plan, {"a.tex": HunksResolution({first.key: HunkDecision(HunkChoice.mine)})})

    assert error.value.code is GitErrorCode.unresolved_conflicts
    assert error.value.ctx == {"paths": ["a.tex"]}


def test__resolve_plan__no_resolution_for_a_conflict__lists_every_unresolved_path(
    engine: GitMergeFileEngine,
) -> None:
    tree = {"a.tex": b"1\n", "b.tex": b"1\n", "c.tex": b"1\n"}
    plan = _plan(
        engine, tree, {"a.tex": b"2\n", "b.tex": b"2\n", "c.tex": b"1\n"}, {**tree, "a.tex": b"3\n", "b.tex": b"3\n"}
    )

    with pytest.raises(GitSyncError) as error:
        resolve_plan(plan, {"b.tex": FileChoiceResolution(FileChoice.mine)})

    assert error.value.ctx == {"paths": ["a.tex"]}


@pytest.mark.parametrize(
    "resolution",
    [FileChoiceResolution(FileChoice.newest), FieldsResolution({"/a": FieldDecision(FieldChoice.mine)})],
)
def test__resolve_plan__resolution_of_another_kind__is_invalid(
    engine: GitMergeFileEngine, resolution: FileResolution
) -> None:
    plan = _text_plan(engine)

    with pytest.raises(GitSyncError) as error:
        resolve_plan(plan, {"a.tex": resolution})

    assert error.value.code is GitErrorCode.invalid_resolution


def test__resolve_plan__unknown_hunk_key__is_invalid(engine: GitMergeFileEngine) -> None:
    plan = _text_plan(engine)
    decisions = {h.key: HunkDecision(HunkChoice.mine) for h in plan.ops[0].hunks}

    with pytest.raises(GitSyncError) as error:
        resolve_plan(plan, {"a.tex": HunksResolution({**decisions, "h:unknown": HunkDecision(HunkChoice.mine)})})

    assert error.value.code is GitErrorCode.invalid_resolution


def test__resolve_plan__empty_hunk_resolution__leaves_every_hunk_unresolved(engine: GitMergeFileEngine) -> None:
    plan = _text_plan(engine)

    with pytest.raises(GitSyncError) as error:
        resolve_plan(plan, {"a.tex": HunksResolution({})})

    assert error.value.code is GitErrorCode.unresolved_conflicts


def test__resolve_plan__custom_hunk_without_text__is_invalid(engine: GitMergeFileEngine) -> None:
    plan = _text_plan(engine)

    with pytest.raises(GitSyncError) as error:
        resolve_plan(plan, {"a.tex": _decide(plan.ops[0], HunkChoice.custom)})

    assert (error.value.code, error.value.ctx) == (GitErrorCode.invalid_resolution, {"path": "a.tex"})


def test__resolve_plan__whole_file_choices(engine: GitMergeFileEngine) -> None:
    plan = _text_plan(engine)
    theirs = b"a\nY\nc\nd\ne\nR\ng\n"

    assert resolve_plan(plan, {"a.tex": FileChoiceResolution(FileChoice.theirs)}) == [_write("a.tex", theirs)]
    assert resolve_plan(plan, {"a.tex": FileChoiceResolution(FileChoice.mine)}) == []


def test__resolve_plan__manual_text__is_written_with_my_style(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, {"a.tex": b"1\n"}, {"a.tex": b"2\r\n"}, {"a.tex": b"3\n"})

    writes = resolve_plan(plan, {"a.tex": TextResolution("final\nlines\n")})

    assert writes == [_write("a.tex", b"final\r\nlines\r\n")]


def test__resolve_plan__manual_text_equal_to_mine__writes_nothing(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, {"a.tex": b"1\n"}, {"a.tex": b"2\n"}, {"a.tex": b"3\n"})

    assert resolve_plan(plan, {"a.tex": TextResolution("2\n")}) == []


@pytest.mark.parametrize("marker", ["<<<<<<< hse:ours", "||||||| hse:base", ">>>>>>> hse:theirs"])
def test__resolve_plan__manual_text_with_markers__is_rejected(engine: GitMergeFileEngine, marker: str) -> None:
    plan = _plan(engine, {"a.tex": b"1\n"}, {"a.tex": b"2\n"}, {"a.tex": b"3\n"})

    with pytest.raises(GitSyncError) as error:
        resolve_plan(plan, {"a.tex": TextResolution(f"a\n{marker}\nb\n")})

    assert error.value.code is GitErrorCode.unresolved_markers


def test__resolve_plan__custom_hunk_with_markers__is_rejected(engine: GitMergeFileEngine) -> None:
    plan = _text_plan(engine)

    with pytest.raises(GitSyncError) as error:
        resolve_plan(plan, {"a.tex": _decide(plan.ops[0], HunkChoice.custom, "x\n<<<<<<< hse:ours\ny")})

    assert error.value.code is GitErrorCode.unresolved_markers


def test__resolve_plan__opaque_conflict__allows_whole_file_and_manual_text_but_not_hunks(
    engine: GitMergeFileEngine,
) -> None:
    base = b"a\n=======\nc\n"
    plan = _plan(engine, {"a.md": base}, {"a.md": b"a\n=======\nX\n"}, {"a.md": b"a\n=======\nY\n"})
    (op,) = plan.ops
    assert op.hunks == ()

    assert resolve_plan(plan, {"a.md": TextResolution("a\nz\n")}) == [_write("a.md", b"a\nz\n")]
    assert resolve_plan(plan, {"a.md": FileChoiceResolution(FileChoice.theirs)}) == [_write("a.md", b"a\n=======\nY\n")]
    with pytest.raises(GitSyncError) as error:
        resolve_plan(plan, {"a.md": HunksResolution({"h:00000000": HunkDecision(HunkChoice.mine)})})
    assert error.value.code is GitErrorCode.invalid_resolution


def test__resolve_plan__markers_already_in_the_input__are_not_rejected_in_manual_text(
    engine: GitMergeFileEngine,
) -> None:
    marked = b"doc about merges\n<<<<<<< hse:ours\n"
    plan = _plan(engine, {"a.md": b"1\n"}, {"a.md": marked + b"X\n"}, {"a.md": b"3\n"})

    assert resolve_plan(plan, {"a.md": TextResolution(marked.decode())}) == [_write("a.md", marked)]


def test__resolve_plan__add_add_text__resolves_with_both(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, {}, {"n.txt": b"mine\n"}, {"n.txt": b"theirs\n"})

    assert resolve_plan(plan, {"n.txt": _decide(plan.ops[0], HunkChoice.both)}) == [_write("n.txt", b"mine\ntheirs\n")]


@pytest.mark.parametrize(
    ("ours", "theirs", "kind", "choice", "expected"),
    [
        (None, _T, ConflictType.deleted_by_us, FileChoice.mine, []),
        (None, _T, ConflictType.deleted_by_us, FileChoice.theirs, [_write("a.tex", _T)]),
        (_O, None, ConflictType.deleted_by_them, FileChoice.mine, []),
        (_O, None, ConflictType.deleted_by_them, FileChoice.theirs, [FileWrite("a.tex", FileWriteKind.delete)]),
    ],
)
def test__resolve_plan__delete_versus_modify(
    engine: GitMergeFileEngine,
    ours: bytes | None,
    theirs: bytes | None,
    kind: ConflictType,
    choice: FileChoice,
    expected: list[FileWrite],
) -> None:
    plan = _plan(engine, {"a.tex": _B}, _tree("a.tex", ours), _tree("a.tex", theirs))

    assert plan.ops[0].conflict_type is kind
    assert resolve_plan(plan, {"a.tex": FileChoiceResolution(choice)}) == expected


def test__resolve_plan__clean_actions__write_without_any_resolution(engine: GitMergeFileEngine) -> None:
    base = {"gone.tex": b"g\n", "same.tex": _LINES, "up.tex": b"u\n"}
    ours = {"gone.tex": b"g\n", "same.tex": b"A\nb\nc\nd\ne\n", "up.tex": b"u\n"}
    theirs = {"same.tex": b"a\nb\nc\nd\nE\n", "up.tex": b"u2\n", "new.tex": b"n\n"}
    plan = _plan(engine, base, ours, theirs)

    writes = resolve_plan(plan, {"unrelated": FileChoiceResolution(FileChoice.theirs)})

    assert apply_writes(ours, writes) == {
        "same.tex": b"A\nb\nc\nd\nE\n",
        "up.tex": b"u2\n",
        "new.tex": b"n\n",
    }


def test__resolve_plan__binary_newest__writes_the_winner_and_the_copy(engine: GitMergeFileEngine) -> None:
    meta = {"f.png": MergeMeta(ours_changed_at=_EARLY, theirs_changed_at=_LATE)}
    plan = _plan(engine, {"f.png": b"\x89old"}, {"f.png": _PNG_A}, {"f.png": _PNG_B}, meta=meta)

    writes = resolve_plan(plan, {})

    assert writes == [_write("f.png", _PNG_B), _write(conflict_copy_name("f.png", _PNG_A), _PNG_A)]


def test__resolve_plan__binary_newest_when_ours_is_newer__only_the_copy_is_written(
    engine: GitMergeFileEngine,
) -> None:
    meta = {"f.png": MergeMeta(ours_changed_at=_LATE, theirs_changed_at=_EARLY)}
    plan = _plan(engine, {"f.png": b"\x89old"}, {"f.png": _PNG_A}, {"f.png": _PNG_B}, meta=meta)

    assert resolve_plan(plan, {}) == [_write(conflict_copy_name("f.png", _PNG_B), _PNG_B)]


@pytest.mark.parametrize(
    ("choice", "expected"),
    [(FileChoice.mine, []), (FileChoice.theirs, [_write("f.png", _PNG_B)])],
)
def test__resolve_plan__binary_override__writes_no_copy(
    engine: GitMergeFileEngine, choice: FileChoice, expected: list[FileWrite]
) -> None:
    plan = _plan(engine, {"f.png": b"\x89old"}, {"f.png": _PNG_A}, {"f.png": _PNG_B})

    assert resolve_plan(plan, {"f.png": FileChoiceResolution(choice)}) == expected


def test__resolve_plan__binary_with_a_text_resolution__is_invalid(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, {"f.png": b"\x89old"}, {"f.png": _PNG_A}, {"f.png": _PNG_B})

    with pytest.raises(GitSyncError) as error:
        resolve_plan(plan, {"f.png": TextResolution("x")})

    assert error.value.code is GitErrorCode.invalid_resolution


def test__resolve_plan__result_is_deterministic_for_swapped_sides(engine: GitMergeFileEngine) -> None:
    base = {"a.tex": _LINES, "f.png": b"\x89old"}
    ours = {"a.tex": b"A\nb\nc\nd\ne\n", "f.png": _PNG_A}
    theirs = {"a.tex": b"a\nb\nc\nd\nE\n", "f.png": _PNG_B}
    meta_ours = {"f.png": MergeMeta(ours_changed_at=_EARLY, theirs_changed_at=_LATE)}
    meta_theirs = {"f.png": MergeMeta(ours_changed_at=_LATE, theirs_changed_at=_EARLY)}

    mine_side = apply_writes(ours, resolve_plan(_plan(engine, base, ours, theirs, meta=meta_ours), {}))
    their_side = apply_writes(theirs, resolve_plan(_plan(engine, base, theirs, ours, meta=meta_theirs), {}))

    assert mine_side == their_side
