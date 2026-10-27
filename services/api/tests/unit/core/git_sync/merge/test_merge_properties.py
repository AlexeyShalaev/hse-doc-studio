"""Свойства планировщика слияния на случайных текстах, бинарниках и путях."""

from __future__ import annotations

import random
from collections.abc import Mapping
from pathlib import PurePosixPath

import pytest
from hse_doc_studio.core.git_sync.merge.binary import conflict_copy_name
from hse_doc_studio.core.git_sync.merge.choices import (
    FileChoice,
    FileChoiceResolution,
    FileResolution,
    HunkChoice,
    HunkDecision,
    HunksResolution,
)
from hse_doc_studio.core.git_sync.merge.entities import MergeAction, MergePlan
from hse_doc_studio.core.git_sync.merge.paths import is_safe_path
from hse_doc_studio.core.git_sync.merge.planner import MergeInput, plan_merge, resolve_plan
from hse_doc_studio.core.git_sync.merge.text import has_hse_markers
from hse_doc_studio.core.git_sync.protocols import MergeMeta
from hse_doc_studio.infra.template_update.merge_engine import GitMergeFileEngine
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from .helpers import apply_writes

_PROFILE = settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])

_LINES = st.lists(st.sampled_from(["a", "b", "c", "d", "e", ""]), max_size=7)
_TEXT = _LINES.map(lambda lines: "".join(f"{line}\n" for line in lines).encode())
_NAMES = st.sampled_from(["a.tex", "b.tex", "dir/c.tex", "d.md", "e.bib"])


def _plan(
    engine: GitMergeFileEngine, base: Mapping[str, bytes], ours: Mapping[str, bytes], theirs: Mapping[str, bytes]
):  # noqa: ANN202
    return plan_merge(MergeInput(base, ours, theirs), engine)


def _everywhere(plan: MergePlan, choice: HunkChoice) -> dict[str, FileResolution]:
    """Одно и то же решение везде: по участкам, а у файлов без участков (удаление) — по файлу."""
    file_choice = FileChoice.theirs if choice is HunkChoice.theirs else FileChoice.mine
    return {
        op.path: HunksResolution({h.key: HunkDecision(choice) for h in op.hunks})
        if op.hunks
        else FileChoiceResolution(file_choice)
        for op in plan.conflicts
    }


def _final(
    engine: GitMergeFileEngine,
    base: Mapping[str, bytes],
    ours: Mapping[str, bytes],
    theirs: Mapping[str, bytes],
    choice: HunkChoice = HunkChoice.mine,
) -> dict[str, bytes]:
    plan = _plan(engine, base, ours, theirs)
    return apply_writes(ours, resolve_plan(plan, _everywhere(plan, choice)))


def _tree(name: str, content: bytes) -> dict[str, bytes]:
    return {name: content} if content else {}


@_PROFILE
@given(name=_NAMES, base=_TEXT, ours=_TEXT, theirs=_TEXT)
def test__plan_merge__identity_and_idempotence(
    engine: GitMergeFileEngine, name: str, base: bytes, ours: bytes, theirs: bytes
) -> None:
    b, o, t = _tree(name, base), _tree(name, ours), _tree(name, theirs)

    assert _plan(engine, b, b, b).ops == ()
    assert _plan(engine, b, o, b).ops == ()
    assert _plan(engine, b, o, o).ops == ()
    assert _final(engine, b, b, t) == t


@_PROFILE
@given(name=_NAMES, base=_TEXT, ours=_TEXT, theirs=_TEXT, choice=st.sampled_from([HunkChoice.mine, HunkChoice.theirs]))
def test__plan_merge__swapping_the_sides_gives_the_same_clean_result_and_mirrored_conflicts(
    engine: GitMergeFileEngine, name: str, base: bytes, ours: bytes, theirs: bytes, choice: HunkChoice
) -> None:
    b, o, t = _tree(name, base), _tree(name, ours), _tree(name, theirs)
    forward, backward = _plan(engine, b, o, t), _plan(engine, b, t, o)

    assert [op.path for op in forward.conflicts] == [op.path for op in backward.conflicts]
    for mine, theirs_side in zip(forward.conflicts, backward.conflicts, strict=True):
        assert [(h.ours, h.base, h.theirs) for h in mine.hunks] == [
            (h.theirs, h.base, h.ours) for h in theirs_side.hunks
        ]
    if forward.is_clean:
        assert apply_writes(o, resolve_plan(forward, {})) == apply_writes(t, resolve_plan(backward, {}))
    mirrored = HunkChoice.theirs if choice is HunkChoice.mine else HunkChoice.mine
    assert _final(engine, b, o, t, choice) == _final(engine, b, t, o, mirrored)


@_PROFILE
@given(
    data=st.dictionaries(_NAMES, st.tuples(_TEXT, _TEXT, _TEXT), min_size=1, max_size=4),
    seed=st.integers(0, 1000),
)
def test__plan_merge__is_deterministic_and_independent_of_mapping_order(
    engine: GitMergeFileEngine, data: dict[str, tuple[bytes, bytes, bytes]], seed: int
) -> None:
    def trees(order: list[str]) -> tuple[dict[str, bytes], dict[str, bytes], dict[str, bytes]]:
        return tuple({n: data[n][i] for n in order if data[n][i]} for i in range(3))  # type: ignore[return-value]

    names = sorted(data)
    shuffled = names[:]
    random.Random(seed).shuffle(shuffled)

    first = _plan(engine, *trees(names))
    second = _plan(engine, *trees(shuffled))

    assert first == second
    assert first == _plan(engine, *trees(names))
    assert [op.path for op in first.ops] == sorted(op.path for op in first.ops)


@_PROFILE
@given(name=_NAMES, base=_TEXT, ours=_TEXT, theirs=_TEXT, data=st.data())
def test__resolve_plan__any_choices__never_leave_markers_and_resolve_every_hunk(
    engine: GitMergeFileEngine, name: str, base: bytes, ours: bytes, theirs: bytes, data: st.DataObject
) -> None:
    b, o, t = _tree(name, base), _tree(name, ours), _tree(name, theirs)
    plan = _plan(engine, b, o, t)
    resolutions = {}
    for op in plan.conflicts:
        if op.hunks:
            choices = {h.key: HunkDecision(data.draw(st.sampled_from(list(HunkChoice)[:5]))) for h in op.hunks}
            resolutions[op.path] = HunksResolution(choices)
        else:
            resolutions[op.path] = FileChoiceResolution(data.draw(st.sampled_from(list(op.allowed_choices()))))

    result = apply_writes(o, resolve_plan(plan, resolutions))

    assert not any(has_hse_markers(content) or b"<<<<<<<" in content for content in result.values())


@_PROFILE
@given(name=_NAMES, base=_TEXT, ours=_TEXT, theirs=_TEXT)
def test__resolve_plan__keeping_both_sides_loses_no_line_of_either(
    engine: GitMergeFileEngine, name: str, base: bytes, ours: bytes, theirs: bytes
) -> None:
    b, o, t = _tree(name, base), _tree(name, ours), _tree(name, theirs)
    plan = _plan(engine, b, o, t)
    if not plan.conflicts or any(op.hunks == () for op in plan.conflicts):
        return

    merged = _final(engine, b, o, t, HunkChoice.both).get(name, b"")

    # Каждая строка каждой стороны, которой нет в базе (то есть добавленная правкой), осталась в итоге.
    added = (set(ours.split(b"\n")) | set(theirs.split(b"\n"))) - set(base.split(b"\n"))
    assert added <= set(merged.split(b"\n"))


_STYLES = {
    "lf": lambda text: text,
    "crlf": lambda text: text.replace(b"\n", b"\r\n"),
    "bom": lambda text: b"\xef\xbb\xbf" + text.replace(b"\n", b"\r\n"),
}


@_PROFILE
@given(
    name=_NAMES,
    base=_TEXT,
    ours=_TEXT,
    theirs=_TEXT,
    base_style=st.sampled_from(sorted(_STYLES)),
    ours_style=st.sampled_from(sorted(_STYLES)),
    theirs_style=st.sampled_from(sorted(_STYLES)),
)
def test__plan_merge__line_endings_and_bom_never_create_conflicts(
    engine: GitMergeFileEngine,
    name: str,
    base: bytes,
    ours: bytes,
    theirs: bytes,
    base_style: str,
    ours_style: str,
    theirs_style: str,
) -> None:

    def styled_tree(content: bytes, style: str) -> dict[str, bytes]:
        return _tree(name, _STYLES[style](content) if content else b"")

    plain = _plan(engine, _tree(name, base), _tree(name, ours), _tree(name, theirs))
    styled = _plan(
        engine, styled_tree(base, base_style), styled_tree(ours, ours_style), styled_tree(theirs, theirs_style)
    )

    assert [(op.path, op.action, op.conflict_type) for op in styled.ops] == [
        (op.path, op.action, op.conflict_type) for op in plain.ops
    ]
    assert [h.key for op in styled.ops for h in op.hunks] == [h.key for op in plain.ops for h in op.hunks]


_BLOB = st.binary(min_size=1, max_size=6).map(lambda raw: b"\x89\x00" + raw)


@_PROFILE
@given(base=st.none() | _BLOB, ours=_BLOB, theirs=_BLOB, newer=st.sampled_from(["ours", "theirs"]))
def test__resolve_plan__binary_merge_keeps_both_versions_and_picks_the_same_winner_from_either_side(
    engine: GitMergeFileEngine, base: bytes | None, ours: bytes, theirs: bytes, newer: str
) -> None:
    from datetime import UTC, datetime

    early, late = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 2, tzinfo=UTC)
    stamps = (late, early) if newer == "ours" else (early, late)
    b = {} if base is None else {"f.png": base}
    forward = plan_merge(MergeInput(b, {"f.png": ours}, {"f.png": theirs}, meta={"f.png": MergeMeta(*stamps)}), engine)
    backward = plan_merge(
        MergeInput(b, {"f.png": theirs}, {"f.png": ours}, meta={"f.png": MergeMeta(stamps[1], stamps[0])}), engine
    )

    from_ours = apply_writes({"f.png": ours}, resolve_plan(forward, {}))
    from_theirs = apply_writes({"f.png": theirs}, resolve_plan(backward, {}))

    if base in {ours, theirs} or ours == theirs:
        return
    assert from_ours == from_theirs
    assert {ours, theirs} <= set(from_ours.values())
    assert set(from_ours) <= {"f.png", conflict_copy_name("f.png", ours), conflict_copy_name("f.png", theirs)}


_PARTS = st.sampled_from(["..", ".", ".git", ".GIT", "a", "b.tex", ".hse-studio", "git", "update", "C:", "", "x\\y"])


@_PROFILE
@given(parts=st.lists(st.lists(_PARTS, min_size=1, max_size=4).map("/".join), min_size=1, max_size=6, unique=True))
def test__plan_merge__no_operation_ever_targets_an_unsafe_path(engine: GitMergeFileEngine, parts: list[str]) -> None:
    theirs = dict.fromkeys(parts, b"x\n")

    plan = _plan(engine, {}, {}, theirs)

    for op in plan.ops:
        assert is_safe_path(op.path)
        posix = PurePosixPath(op.path)
        assert not posix.is_absolute()
        assert ".." not in posix.parts
        assert ".git" not in {part.casefold() for part in posix.parts}
    skipped = {path for path in parts if not is_safe_path(path)}
    warned = {path for warning in plan.warnings if warning.code.value == "unsafe_path" for path in warning.paths}
    assert warned == skipped
    assert len(plan.ops) == len(parts) - len(skipped)
    assert all(op.action is MergeAction.take_theirs for op in plan.ops)


@_PROFILE
@given(name=_NAMES, base=_TEXT, ours=_TEXT, theirs=_TEXT, edit=_TEXT)
def test__plan_merge__fingerprint_ignores_edits_of_files_outside_the_conflicts(
    engine: GitMergeFileEngine, name: str, base: bytes, ours: bytes, theirs: bytes, edit: bytes
) -> None:
    b, o, t = _tree(name, base), _tree(name, ours), _tree(name, theirs)
    unrelated_base = {"unrelated.tex": b"u\n"}

    before = plan_merge(
        MergeInput({**b, **unrelated_base}, {**o, "unrelated.tex": b"u\n"}, {**t, "unrelated.tex": b"u\n"}), engine
    )
    after = plan_merge(
        MergeInput({**b, **unrelated_base}, {**o, "unrelated.tex": b"edited\n" + edit}, {**t, "unrelated.tex": b"u\n"}),
        engine,
    )

    assert before.fingerprint == after.fingerprint


@pytest.mark.parametrize("name", ["a.tex"])
def test__plan_merge__real_world_latex_paragraph_edits_on_one_line__conflict_as_a_whole_line(
    engine: GitMergeFileEngine, name: str
) -> None:
    base = b"Intro\nOne long paragraph about sync and merge.\nOutro\n"
    ours = b"Intro\nOne long paragraph about sync and MERGE.\nOutro\n"
    theirs = b"Intro\nOne LONG paragraph about sync and merge.\nOutro\n"

    plan = _plan(engine, {name: base}, {name: ours}, {name: theirs})

    (op,) = plan.ops
    assert [(h.ours, h.theirs) for h in op.hunks] == [(ours.split(b"\n")[1] + b"\n", theirs.split(b"\n")[1] + b"\n")]
