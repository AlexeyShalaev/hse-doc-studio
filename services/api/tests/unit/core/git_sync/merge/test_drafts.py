from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.git_sync.merge.choices import (
    FieldChoice,
    FieldDecision,
    FieldsResolution,
    FileChoice,
    FileChoiceResolution,
    HunkChoice,
    HunkDecision,
    HunksResolution,
    TextResolution,
)
from hse_doc_studio.core.git_sync.merge.drafts import (
    is_empty,
    progress,
    prune,
    prune_all,
    resolution_from_json,
    resolution_to_json,
)
from hse_doc_studio.core.git_sync.merge.entities import MergeAction, MergePlan, MergeSide
from hse_doc_studio.core.git_sync.merge.planner import MergeInput, plan_merge
from hse_doc_studio.core.git_sync.merge.preview import preview_result
from hse_doc_studio.core.git_sync.merge.rules import StateFileMerge
from hse_doc_studio.core.git_sync.merge.signature_groups import conflicting_groups, group_paths, pointer_for
from hse_doc_studio.core.git_sync.protocols import MergeMeta
from hse_doc_studio.infra.template_update.merge_engine import GitMergeFileEngine

pytestmark = pytest.mark.unit

_BASE = b"1\n2\n3\n4\n5\n6\n7\n8\n9\n"
_MINE = b"mine\n2\n3\n4\n5\n6\n7\n8\nmine end\n"
_THEIRS = b"theirs\n2\n3\n4\n5\n6\n7\n8\ntheirs end\n"
_PATH = "doc.tex"


def _plan(engine: GitMergeFileEngine, base: bytes, ours: bytes, theirs: bytes, path: str = _PATH) -> MergePlan:
    inp = MergeInput(
        base={path: base}, ours={path: ours}, theirs={path: theirs}, base_commit="b" * 40, theirs_commit="c" * 40
    )
    return plan_merge(inp, engine, StateFileMerge())


def _text_plan(engine: GitMergeFileEngine) -> tuple[MergePlan, list[str]]:
    plan = _plan(engine, _BASE, _MINE, _THEIRS)
    return plan, [hunk.key for hunk in plan.conflicts[0].hunks]


# --- запись в JSON -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "resolution",
    [
        FileChoiceResolution(FileChoice.newest),
        HunksResolution({"h:1": HunkDecision(HunkChoice.mine), "h:2": HunkDecision(HunkChoice.custom, "a\nb")}),
        FieldsResolution({"/name": FieldDecision(FieldChoice.union)}),
        TextResolution("whole\n"),
    ],
)
def test__json__round_trips_every_kind_through_text(resolution: object) -> None:
    raw = json.loads(json.dumps(resolution_to_json(resolution)))  # type: ignore[arg-type]
    assert resolution_from_json(raw) == resolution


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "mine",
        {},
        {"kind": "file"},
        {"kind": "file", "choice": "sideways"},
        {"kind": "hunks", "hunks": {"h:1": {"choice": "mine"}, "h:2": 5}},
        {"kind": "fields", "fields": []},
        {"kind": "mystery"},
    ],
)
def test__json__damaged_record__is_dropped(raw: object) -> None:
    assert resolution_from_json(raw) is None


def test__is_empty__only_for_hunks_and_fields_without_choices() -> None:
    assert is_empty(HunksResolution({}))
    assert is_empty(FieldsResolution({}))
    assert not is_empty(TextResolution(""))
    assert not is_empty(FileChoiceResolution(FileChoice.mine))


# --- пересчёт под план -------------------------------------------------------------------------------------------


def test__prune__keeps_known_hunks_and_drops_the_rest(engine: GitMergeFileEngine) -> None:
    plan, keys = _text_plan(engine)
    op = plan.conflicts[0]
    draft = HunksResolution(
        {
            keys[0]: HunkDecision(HunkChoice.both),
            "h:gone": HunkDecision(HunkChoice.mine),
            keys[1]: HunkDecision(HunkChoice.custom),
        }
    )

    assert prune(op, draft) == HunksResolution({keys[0]: HunkDecision(HunkChoice.both)})
    assert prune(op, HunksResolution({"h:gone": HunkDecision(HunkChoice.mine)})) is None


def test__prune__file_choices_follow_what_the_file_allows(engine: GitMergeFileEngine) -> None:
    op = _text_plan(engine)[0].conflicts[0]

    assert prune(op, FileChoiceResolution(FileChoice.theirs)) == FileChoiceResolution(FileChoice.theirs)
    assert prune(op, FileChoiceResolution(FileChoice.newest)) is None
    assert prune(op, TextResolution("x")) == TextResolution("x")
    assert prune(op, FieldsResolution({"/a": FieldDecision(FieldChoice.mine)})) is None


def test__prune__nothing_to_decide_in_a_clean_file(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, b"a\nb\n", b"a\nb\n", b"a\nc\n")
    assert plan.conflicts == ()
    assert prune(plan.ops[0], FileChoiceResolution(FileChoice.mine)) is None


def test__prune_all__drops_paths_the_plan_no_longer_has(engine: GitMergeFileEngine) -> None:
    plan, keys = _text_plan(engine)
    drafts = {
        _PATH: HunksResolution({keys[0]: HunkDecision(HunkChoice.mine)}),
        "removed.tex": FileChoiceResolution(FileChoice.mine),
    }

    assert set(prune_all({op.path: op for op in plan.ops}, drafts)) == {_PATH}


# --- что осталось решить -----------------------------------------------------------------------------------------


def test__progress__counts_open_hunks_and_closes_when_every_hunk_is_decided(engine: GitMergeFileEngine) -> None:
    op = _text_plan(engine)[0].conflicts[0]
    keys = [hunk.key for hunk in op.hunks]

    assert progress(op, None).open_hunks == 2
    half = progress(op, HunksResolution({keys[0]: HunkDecision(HunkChoice.mine)}))
    assert (half.open_hunks, half.resolved) == (1, False)
    full = progress(op, HunksResolution({key: HunkDecision(HunkChoice.theirs) for key in keys}))
    assert (full.open_hunks, full.resolved) == (0, True)
    assert progress(op, FileChoiceResolution(FileChoice.mine)).resolved
    assert progress(op, TextResolution("x")).resolved


def test__progress__a_clean_file_is_always_resolved(engine: GitMergeFileEngine) -> None:
    plan = _plan(engine, b"a\nb\n", b"a\nb\n", b"a\nc\n")
    assert progress(plan.ops[0], None).resolved


# --- предпросмотр ------------------------------------------------------------------------------------------------


def test__preview__undecided_hunks_show_mine_and_decided_ones_follow_the_draft(engine: GitMergeFileEngine) -> None:
    op = _text_plan(engine)[0].conflicts[0]
    first = op.hunks[0].key

    assert preview_result(op, None, None) == _MINE
    assert preview_result(op, HunksResolution({first: HunkDecision(HunkChoice.theirs)}), None) == (
        b"theirs\n2\n3\n4\n5\n6\n7\n8\nmine end\n"
    )
    assert preview_result(op, FileChoiceResolution(FileChoice.theirs), None) == _THEIRS
    assert preview_result(op, TextResolution("typed\n"), None) == b"typed\n"


def test__preview__binary_follows_the_winner_unless_a_side_is_chosen(engine: GitMergeFileEngine) -> None:
    ours, theirs = b"\x89PNG\r\n\x00mine", b"\x89PNG\r\n\x00theirs"
    meta = MergeMeta(datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 2, tzinfo=UTC), "a" * 40, "b" * 40)
    inp = MergeInput(
        base={"a.png": b"\x89PNG\r\n\x00base"},
        ours={"a.png": ours},
        theirs={"a.png": theirs},
        meta={"a.png": meta},
        base_commit="b" * 40,
        theirs_commit="c" * 40,
    )
    op = plan_merge(inp, engine).ops[0]

    assert (op.action, op.winner) == (MergeAction.binary_newest, MergeSide.theirs)
    assert preview_result(op, None, None) == theirs
    assert preview_result(op, FileChoiceResolution(FileChoice.mine), None) == ours


# --- группы подписей ---------------------------------------------------------------------------------------------


def _signatures(sha: str, pdf: str, detached: dict[str, str] | None = None) -> bytes:
    frozen = {"main": {"path": pdf, "sha256": sha, "source_sha256": "s", "size": 1, "frozen_at": "t"}}
    files = {slot: {"file": file} for slot, file in (detached or {}).items()}
    return json.dumps({"slots": {}, "placements": {}, "frozen": frozen, "detached": {"main": files}}).encode()


def test__signature_groups__collects_files_of_both_sides_and_their_copies(engine: GitMergeFileEngine) -> None:
    path = ".hse-studio/signatures.json"
    pdf_ours, pdf_theirs = ".hse-studio/frozen/main.pdf", ".hse-studio/frozen/main-2.pdf"
    inp = MergeInput(
        base={path: _signatures("0", pdf_ours)},
        ours={path: _signatures("1", pdf_ours, {"a": ".hse-studio/detached/main/a.sig"}), pdf_ours: b"%PDF-mine"},
        theirs={path: _signatures("2", pdf_theirs), pdf_theirs: b"%PDF-theirs", pdf_ours: b"%PDF-theirs-old"},
        base_commit="b" * 40,
        theirs_commit="c" * 40,
    )
    plan = plan_merge(inp, engine, StateFileMerge())

    [group] = conflicting_groups(plan)

    assert group.doc_id == "main"
    assert group.ours == {pdf_ours, ".hse-studio/detached/main/a.sig"}
    assert group.theirs == {pdf_theirs}
    assert pointer_for("main") == "/signature_groups/main"
    assert {pdf_ours, pdf_theirs, ".hse-studio/detached/main/a.sig"} <= group_paths(plan)


def test__signature_groups__no_signatures_file__no_groups(engine: GitMergeFileEngine) -> None:
    plan, _ = _text_plan(engine)
    assert conflicting_groups(plan) == []
    assert group_paths(plan) == frozenset()
