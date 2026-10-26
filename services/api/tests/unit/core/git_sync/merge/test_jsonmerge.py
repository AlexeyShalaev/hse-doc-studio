"""Слияние JSON по полям: правила движка и свойства на случайных документах."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

import pytest
from hse_doc_studio.core.git_sync.merge.choices import FieldChoice
from hse_doc_studio.core.git_sync.merge.jsonmerge import (
    ABSENT,
    UNRESOLVED,
    Atomic,
    Custom,
    DocGroups,
    Extremum,
    FieldGroup,
    FieldType,
    InvalidFieldChoiceError,
    JsonMerge,
    JsonRules,
    Keyed,
    LocalOnly,
    MustEqual,
    PostResult,
    SetOf,
    canon,
    canonical_dumps,
    merge_json,
    pointer_of,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_PROFILE = settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def _merge(base: Any, ours: Any, theirs: Any, rules: JsonRules | None = None, **kwargs: Any) -> JsonMerge:
    return merge_json(base, ours, theirs, rules or JsonRules(), **kwargs)


def _by_pointer(merge: JsonMerge) -> dict[str, Any]:
    return {conflict.pointer: conflict for conflict in merge.conflicts}


# --- основа ------------------------------------------------------------------------------------


def test__merge_json__nothing_changed__is_the_same_document() -> None:
    doc = {"a": 1, "b": {"c": [1, 2]}}

    merge = _merge(doc, doc, doc)

    assert merge.value == doc
    assert merge.conflicts == ()
    assert merge.auto == ()


def test__merge_json__one_side_changed__takes_that_side() -> None:
    base = {"a": 1, "b": {"c": 2}}
    changed = {"a": 1, "b": {"c": 3}, "d": 4}

    assert _merge(base, changed, base).value == changed
    assert _merge(base, base, changed).value == changed


def test__merge_json__disjoint_fields__are_combined_without_conflicts() -> None:
    base = {"a": 1, "b": 1, "n": {"x": 1, "y": 1}}
    ours = {"a": 2, "b": 1, "n": {"x": 2, "y": 1}}
    theirs = {"a": 1, "b": 3, "n": {"x": 1, "y": 3}}

    merge = _merge(base, ours, theirs)

    assert merge.value == {"a": 2, "b": 3, "n": {"x": 2, "y": 3}}
    assert merge.conflicts == ()


def test__merge_json__same_change_on_both_sides__is_not_a_conflict() -> None:
    base = {"a": 1}

    assert _merge(base, {"a": 2}, {"a": 2}).value == {"a": 2}


def test__merge_json__scalar_changed_differently__is_a_conflict_with_ours_as_placeholder() -> None:
    merge = _merge({"a": {"b": 1}}, {"a": {"b": 2}}, {"a": {"b": 3}})

    (conflict,) = merge.conflicts
    assert (conflict.pointer, conflict.type) == ("/a/b", FieldType.scalar)
    assert (conflict.base, conflict.ours, conflict.theirs) == (1, 2, 3)
    assert conflict.allowed == (FieldChoice.mine, FieldChoice.theirs)
    assert merge.value == {"a": {"b": 2}}


def test__merge_json__true_and_one__are_different_values() -> None:
    merge = _merge({"a": 0}, {"a": True}, {"a": 1})

    assert [c.pointer for c in merge.conflicts] == ["/a"]


def test__merge_json__key_deleted_by_one_side__is_deleted_when_the_other_did_not_touch_it() -> None:
    assert _merge({"a": 1, "b": 2}, {"a": 1}, {"a": 1, "b": 2}).value == {"a": 1}
    assert _merge({"a": 1, "b": 2}, {"a": 1, "b": 2}, {"a": 1}).value == {"a": 1}


def test__merge_json__deleted_vs_modified__is_a_presence_conflict() -> None:
    merge = _merge({"a": 1, "b": 2}, {"a": 1}, {"a": 1, "b": 3})

    (conflict,) = merge.conflicts
    assert (conflict.pointer, conflict.type) == ("/b", FieldType.presence)
    assert (conflict.base, conflict.ours, conflict.theirs) == (2, None, 3)
    assert merge.value == {"a": 1}


def test__merge_json__key_added_on_both_sides_with_different_values__merges_against_empty_base() -> None:
    merge = _merge({}, {"n": {"x": 1}}, {"n": {"y": 2}})

    assert merge.value == {"n": {"x": 1, "y": 2}}
    assert merge.conflicts == ()


def test__merge_json__no_common_base__is_merged_as_empty_document() -> None:
    merge = _merge(ABSENT, {"a": 1, "b": 1}, {"a": 2, "c": 1})

    assert merge.value == {"a": 1, "b": 1, "c": 1}
    assert [c.pointer for c in merge.conflicts] == ["/a"]


def test__merge_json__list_without_rule__is_atomic_with_union_for_scalars() -> None:
    merge = _merge({"l": [1]}, {"l": [1, 2]}, {"l": [1, 3]})

    (conflict,) = merge.conflicts
    assert (conflict.pointer, conflict.type) == ("/l", FieldType.list)
    assert conflict.allowed == (FieldChoice.mine, FieldChoice.theirs, FieldChoice.union)
    assert _merge({"l": [1]}, {"l": [1, 2]}, {"l": [1, 3]}, choices={"/l": FieldChoice.union}).value == {"l": [1, 2, 3]}


def test__merge_json__list_of_records_without_rule__has_no_union() -> None:
    merge = _merge({"l": [{"a": 1}]}, {"l": [{"a": 2}]}, {"l": [{"a": 3}]})

    assert merge.conflicts[0].allowed == (FieldChoice.mine, FieldChoice.theirs)


def test__merge_json__type_changed__is_a_record_conflict() -> None:
    merge = _merge({"a": None}, {"a": {"x": 1}}, {"a": "text"})

    assert [(c.pointer, c.type) for c in merge.conflicts] == [("/a", FieldType.record)]


def test__merge_json__key_order__is_base_order_then_added_keys_sorted() -> None:
    base = {"z": 1, "a": 1}
    ours = {"z": 1, "a": 1, "m": 1, "b": 1}
    theirs = {"z": 2, "a": 1, "c": 1}

    assert list(_merge(base, ours, theirs).value) == ["z", "a", "b", "c", "m"]
    assert list(_merge(base, theirs, ours).value) == ["z", "a", "b", "c", "m"]


def test__canonical_dumps__matches_the_repositories_format() -> None:
    value = {"имя": "Анна", "n": [1, {"b": None}]}

    assert canonical_dumps(value) == '{\n  "имя": "Анна",\n  "n": [\n    1,\n    {\n      "b": null\n    }\n  ]\n}'


@pytest.mark.parametrize(
    ("path", "pointer"),
    [((), ""), (("a",), "/a"), (("a/b", "c~d"), "/a~1b/c~0d"), (("docs", "@x"), "/docs/@x")],
)
def test__pointer_of__escapes_per_rfc_6901(path: tuple[str, ...], pointer: str) -> None:
    assert pointer_of(path) == pointer


# --- правила -----------------------------------------------------------------------------------

_KEYED = JsonRules(rules=(Keyed(("docs",), lambda item: item.get("id")),))


def test__keyed__items_merge_pairwise_by_key_in_base_order() -> None:
    base = {"docs": [{"id": "b", "s": 1}, {"id": "a", "s": 1}]}
    ours = {"docs": [{"id": "b", "s": 2}, {"id": "a", "s": 1}, {"id": "z", "s": 1}]}
    theirs = {"docs": [{"id": "b", "s": 1}, {"id": "a", "s": 3}, {"id": "c", "s": 1}]}

    merge = _merge(base, ours, theirs, _KEYED)

    assert merge.conflicts == ()
    assert merge.value == {"docs": [{"id": "b", "s": 2}, {"id": "a", "s": 3}, {"id": "c", "s": 1}, {"id": "z", "s": 1}]}
    assert _merge(base, theirs, ours, _KEYED).value == merge.value


def test__keyed__same_field_changed_differently__conflicts_at_the_item_pointer() -> None:
    base = {"docs": [{"id": "a", "s": 1}]}

    merge = _merge(base, {"docs": [{"id": "a", "s": 2}]}, {"docs": [{"id": "a", "s": 3}]}, _KEYED)

    assert [c.pointer for c in merge.conflicts] == ["/docs/@a/s"]


def test__keyed__item_added_on_both_sides__is_merged_field_by_field() -> None:
    merge = _merge({"docs": []}, {"docs": [{"id": "a", "x": 1}]}, {"docs": [{"id": "a", "y": 2}]}, _KEYED)

    assert merge.value == {"docs": [{"id": "a", "x": 1, "y": 2}]}


def test__keyed__item_deleted_by_one_and_edited_by_other__is_a_presence_conflict() -> None:
    base = {"docs": [{"id": "a", "s": 1}, {"id": "b", "s": 1}]}
    ours = {"docs": [{"id": "b", "s": 1}]}
    theirs = {"docs": [{"id": "a", "s": 2}, {"id": "b", "s": 1}]}

    merge = _merge(base, ours, theirs, _KEYED)

    (conflict,) = merge.conflicts
    assert (conflict.pointer, conflict.type) == ("/docs/@a", FieldType.presence)
    assert merge.value == {"docs": [{"id": "b", "s": 1}]}


def test__keyed__item_deleted_by_one_and_untouched_by_other__is_deleted() -> None:
    base = {"docs": [{"id": "a"}, {"id": "b"}]}

    merge = _merge(base, {"docs": [{"id": "b"}]}, {"docs": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}, _KEYED)

    assert merge.value == {"docs": [{"id": "b"}, {"id": "c"}]}


def test__keyed__items_without_a_key_or_with_duplicates__make_the_list_atomic() -> None:
    base = {"docs": [{"id": "a"}]}

    merge = _merge(base, {"docs": [{"id": "a"}, {"x": 1}]}, {"docs": [{"id": "a"}, {"id": "a"}]}, _KEYED)

    assert [(c.pointer, c.type) for c in merge.conflicts] == [("/docs", FieldType.list)]


def test__keyed__order_rule__sorts_the_merged_items() -> None:
    rules = JsonRules(rules=(Keyed(("h",), lambda r: r["id"], order=lambda r: r["at"]),))
    base = {"h": [{"id": "1", "at": "1"}]}
    ours = {"h": [{"id": "1", "at": "1"}, {"id": "3", "at": "3"}]}
    theirs = {"h": [{"id": "1", "at": "1"}, {"id": "2", "at": "2"}]}

    assert [r["id"] for r in _merge(base, ours, theirs, rules).value["h"]] == ["1", "2", "3"]


def test__set__additions_and_removals_of_both_sides_are_applied() -> None:
    rules = JsonRules(rules=(SetOf(("s",)),))

    merge = _merge({"s": ["a", "b", "c"]}, {"s": ["a", "c", "x"]}, {"s": ["a", "b", "c", "y"]}, rules)

    assert merge.value == {"s": ["a", "c", "x", "y"]}
    assert merge.conflicts == ()
    swapped = _merge({"s": ["a", "b", "c"]}, {"s": ["a", "b", "c", "y"]}, {"s": ["a", "c", "x"]}, rules)
    assert swapped.value == merge.value


def test__set__sorted_variant__is_sorted() -> None:
    rules = JsonRules(rules=(SetOf(("s",), sort=True),))

    assert _merge({"s": ["b"]}, {"s": ["b", "z"]}, {"s": ["b", "a"]}, rules).value == {"s": ["a", "b", "z"]}


def test__set__not_a_list_of_scalars__falls_back_to_a_conflict() -> None:
    rules = JsonRules(rules=(SetOf(("s",)),))

    merge = _merge({"s": [{"a": 1}]}, {"s": [{"a": 2}]}, {"s": [{"a": 3}]}, rules)

    assert [c.pointer for c in merge.conflicts] == ["/s"]


def test__extremum__max_and_min_pick_by_key_not_by_text() -> None:
    rules = JsonRules(rules=(Extremum(("v",), "max", lambda x: x), Extremum(("w",), "min", lambda x: x)))

    merge = _merge({"v": 1, "w": 1}, {"v": 10, "w": 5}, {"v": 9, "w": 2}, rules)

    assert merge.value == {"v": 10, "w": 2}
    assert [a.pointer for a in merge.auto] == ["/v", "/w"]


def test__extremum__unparsable_value__is_a_conflict() -> None:
    rules = JsonRules(rules=(Extremum(("v",), "max", lambda x: x if isinstance(x, int) else None),))

    merge = _merge({"v": 1}, {"v": 2}, {"v": "?"}, rules)

    assert [c.pointer for c in merge.conflicts] == ["/v"]


def test__extremum__equal_keys__pick_the_same_value_whoever_is_ours() -> None:
    rules = JsonRules(rules=(Extremum(("t",), "max", lambda x: len(x)),))

    first = _merge({"t": ""}, {"t": "ab"}, {"t": "ba"}, rules).value
    second = _merge({"t": ""}, {"t": "ba"}, {"t": "ab"}, rules).value

    assert first == second


def test__atomic__record_changed_by_both__is_one_conflict_not_a_field_merge() -> None:
    rules = JsonRules(rules=(Atomic(("p", "*")),))
    base = {"p": {"a": {"x": 1, "y": 1}}}

    merge = _merge(base, {"p": {"a": {"x": 2, "y": 1}}}, {"p": {"a": {"x": 1, "y": 3}}}, rules)

    assert [(c.pointer, c.type) for c in merge.conflicts] == [("/p/a", FieldType.record)]


def test__must_equal__any_difference_is_a_conflict_even_if_one_side_changed() -> None:
    rules = JsonRules(rules=(MustEqual(("id",)),))

    merge = _merge({"id": "a"}, {"id": "a"}, {"id": "b"}, rules)

    assert [c.pointer for c in merge.conflicts] == ["/id"]
    assert _merge({"id": "a"}, {"id": "a"}, {"id": "a"}, rules).conflicts == ()


def test__custom__resolves_or_leaves_the_conflict() -> None:
    def pick_longer(_b: Any, ours: Any, theirs: Any) -> Any:
        return UNRESOLVED if len(ours) == len(theirs) else max(ours, theirs, key=len)

    rules = JsonRules(rules=(Custom(("s",), pick_longer),))

    assert _merge({"s": ""}, {"s": "ab"}, {"s": "c"}, rules).value == {"s": "ab"}
    assert [c.pointer for c in _merge({"s": ""}, {"s": "a"}, {"s": "b"}, rules).conflicts] == ["/s"]


_LOCAL = JsonRules(
    rules=(
        LocalOnly(("pinned",), False),
        LocalOnly(("meta", "vcs")),
        LocalOnly(("docs", "*", "compile"), None),
        Keyed(("docs",), lambda item: item.get("id")),
    )
)


def test__local_only__ours_is_kept_and_theirs_never_imported() -> None:
    base = {"pinned": False, "meta": {"vcs": {"a": 1}, "t": 1}}
    ours = {"pinned": True, "meta": {"vcs": {"a": 2}, "t": 1}}
    theirs = {"pinned": False, "meta": {"vcs": {"a": 3}, "t": 2}}

    merge = _merge(base, ours, theirs, _LOCAL)

    assert merge.value == {"pinned": True, "meta": {"vcs": {"a": 2}, "t": 2}}
    assert merge.conflicts == ()
    assert {a.pointer for a in merge.auto} == {"/pinned", "/meta/vcs"}


def test__local_only__theirs_only_change_of_a_local_field__does_not_come_over() -> None:
    base = {"pinned": False}

    assert _merge(base, base, {"pinned": True}, _LOCAL).value == {"pinned": False}


def test__local_only__added_foreign_record__gets_defaults_for_local_fields() -> None:
    base = {"docs": []}
    theirs = {"docs": [{"id": "n", "compile": "c-1", "status": "done"}]}

    merge = _merge(base, base, theirs, _LOCAL)

    assert merge.value == {"docs": [{"id": "n", "compile": None, "status": "done"}]}


def test__local_only__foreign_vcs_meta_is_dropped_when_i_have_none() -> None:
    base = {"meta": {}}

    assert _merge(base, base, {"meta": {"vcs": {"a": 1}, "t": 1}}, _LOCAL).value == {"meta": {"t": 1}}


def test__local_only__theirs_deleted_a_record_that_i_only_recompiled__is_deleted_without_conflict() -> None:
    base = {"docs": [{"id": "a", "s": 1, "compile": "c-1"}]}
    ours = {"docs": [{"id": "a", "s": 1, "compile": "c-2"}]}

    merge = _merge(base, ours, {"docs": []}, _LOCAL)

    assert merge.value == {"docs": []}
    assert merge.conflicts == ()


def test__local_only__theirs_deleted_a_record_that_i_edited__is_a_conflict() -> None:
    base = {"docs": [{"id": "a", "s": 1, "compile": "c-1"}]}
    ours = {"docs": [{"id": "a", "s": 2, "compile": "c-2"}]}

    merge = _merge(base, ours, {"docs": []}, _LOCAL)

    assert [c.pointer for c in merge.conflicts] == ["/docs/@a"]


def test__field_group__both_changed__follow_the_newest_side_together() -> None:
    rules = JsonRules(rules=(), field_groups=(FieldGroup(("slots", "*"), ("png", "w", "h")),))
    base = {"slots": {"s": {"png": "a", "w": 1, "h": 1, "note": "x"}}}
    ours = {"slots": {"s": {"png": "b", "w": 2, "h": 2, "note": "x"}}}
    theirs = {"slots": {"s": {"png": "c", "w": 3, "h": 3, "note": "y"}}}

    newer_theirs = _merge(base, ours, theirs, rules, newest_theirs=lambda _o, _t: True)
    newer_ours = _merge(base, ours, theirs, rules, newest_theirs=lambda _o, _t: False)

    assert newer_theirs.value == {"slots": {"s": {"png": "c", "w": 3, "h": 3, "note": "y"}}}
    assert newer_ours.value == {"slots": {"s": {"png": "b", "w": 2, "h": 2, "note": "y"}}}
    assert newer_theirs.conflicts == ()


def test__field_group__changed_by_one_side__is_not_decided_by_age() -> None:
    rules = JsonRules(field_groups=(FieldGroup(("s",), ("a", "b")),))

    merge = _merge({"s": {"a": 1, "b": 1}}, {"s": {"a": 2, "b": 1}}, {"s": {"a": 1, "b": 3}}, rules)

    # Правила группы: правили обе стороны, значит побеждает одна, поля не смешиваются.
    assert merge.value in ({"s": {"a": 2, "b": 1}}, {"s": {"a": 1, "b": 3}})


_GROUPS = JsonRules(rules=(), doc_groups=(DocGroups((), ("frozen", "detached"), "groups"),))


def test__doc_groups__changed_by_one_side__come_with_that_side() -> None:
    base = {"frozen": {"a": {"h": 1}}, "detached": {"a": {"s": {"h": 1}}}, "other": 1}
    ours = {"frozen": {"a": {"h": 2}}, "detached": {}, "other": 1}

    merge = _merge(base, ours, base, _GROUPS)

    assert merge.value == ours
    assert merge.conflicts == ()


def test__doc_groups__changed_by_both__is_one_conflict_for_the_whole_group() -> None:
    base = {"frozen": {"a": {"h": 1}}, "detached": {"a": {"s": {"h": 1}}}}
    ours = {"frozen": {"a": {"h": 2}}, "detached": {"a": {"s": {"h": 2}}}}
    theirs = {"frozen": {"a": {"h": 3}}, "detached": {}}

    merge = _merge(base, ours, theirs, _GROUPS)

    (conflict,) = merge.conflicts
    assert (conflict.pointer, conflict.type) == ("/groups/a", FieldType.record)
    assert conflict.ours == {"frozen": {"h": 2}, "detached": {"s": {"h": 2}}}
    assert conflict.theirs == {"frozen": {"h": 3}, "detached": None}
    assert merge.value == ours
    chosen = _merge(base, ours, theirs, _GROUPS, choices={"/groups/a": FieldChoice.theirs}).value
    assert chosen == {"frozen": {"a": {"h": 3}}, "detached": {}}


def test__doc_groups__different_documents__are_independent() -> None:
    base = {"frozen": {}, "detached": {}}
    ours = {"frozen": {"a": {"h": 1}}, "detached": {}}
    theirs = {"frozen": {"b": {"h": 1}}, "detached": {}}

    assert _merge(base, ours, theirs, _GROUPS).value == {"frozen": {"a": {"h": 1}, "b": {"h": 1}}, "detached": {}}


def test__post__runs_on_a_clean_result_and_collects_warnings() -> None:
    def mark(value: Any, _ours: Any, _theirs: Any) -> PostResult:
        return PostResult({**value, "checked": True})

    rules = JsonRules(post=(mark,))

    assert _merge({"a": 1}, {"a": 2}, {"a": 1}, rules).value == {"a": 2, "checked": True}
    assert "checked" not in _merge({"a": 1}, {"a": 2}, {"a": 3}, rules).value


# --- решения человека --------------------------------------------------------------------------


def test__choices__mine_theirs_and_union_are_applied_by_pointer() -> None:
    base = {"a": 1, "l": [1], "n": {"x": 1}}
    ours = {"a": 2, "l": [1, 2], "n": {"x": 2}}
    theirs = {"a": 3, "l": [1, 3], "n": {"x": 3}}
    choices = {"/a": FieldChoice.theirs, "/l": FieldChoice.union, "/n/x": FieldChoice.mine}

    merge = _merge(base, ours, theirs, choices=choices)

    assert merge.value == {"a": 3, "l": [1, 2, 3], "n": {"x": 2}}
    assert merge.conflicts == ()


def test__choices__partial__leaves_the_rest_open() -> None:
    merge = _merge({"a": 1, "b": 1}, {"a": 2, "b": 2}, {"a": 3, "b": 3}, choices={"/a": FieldChoice.theirs})

    assert [c.pointer for c in merge.conflicts] == ["/b"]
    assert merge.value == {"a": 3, "b": 2}


def test__choices__a_deleted_side_is_chosen__removes_the_key() -> None:
    merge = _merge({"a": 1, "b": 2}, {"a": 1}, {"a": 1, "b": 3}, choices={"/b": FieldChoice.mine})

    assert merge.value == {"a": 1}


def test__choices__unknown_pointer__is_rejected() -> None:
    with pytest.raises(InvalidFieldChoiceError) as error:
        _merge({"a": 1}, {"a": 2}, {"a": 3}, choices={"/a": FieldChoice.mine, "/zzz": FieldChoice.mine})

    assert error.value.pointers == ("/zzz",)


def test__choices__union_for_a_scalar__is_rejected() -> None:
    with pytest.raises(InvalidFieldChoiceError):
        _merge({"a": 1}, {"a": 2}, {"a": 3}, choices={"/a": FieldChoice.union})


def test__choices__an_automatic_field_can_be_overridden_with_ours_or_theirs() -> None:
    rules = JsonRules(rules=(Extremum(("v",), "max", lambda x: x),))

    merge = _merge({"v": 1}, {"v": 2}, {"v": 3}, rules, choices={"/v": FieldChoice.mine})

    assert merge.value == {"v": 2}


# --- свойства ----------------------------------------------------------------------------------

_LEAF = st.one_of(st.none(), st.integers(0, 2), st.sampled_from(["x", "y"]))
_KEYS = st.sampled_from(["a", "b", "c", "d"])
_INNER = st.dictionaries(st.sampled_from(["p", "q"]), _LEAF, max_size=2)
_VALUE = st.one_of(_LEAF, _INNER)
_DOC = st.dictionaries(_KEYS, _VALUE, max_size=4)
_EDIT = st.tuples(_KEYS, st.one_of(_VALUE, st.just(ABSENT)))


def _edit(doc: Mapping[str, Any], edits: list[tuple[str, Any]]) -> dict[str, Any]:
    result = copy.deepcopy(dict(doc))
    for key, value in edits:
        if value is ABSENT:
            result.pop(key, None)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _lookup(doc: Any, pointer: str) -> Any:
    for part in [p for p in pointer.split("/") if p]:
        doc = doc.get(part, ABSENT) if isinstance(doc, dict) else ABSENT
    return doc


@_PROFILE
@given(base=_DOC, first=st.lists(_EDIT, max_size=4), second=st.lists(_EDIT, max_size=4))
def test__property__merge_is_symmetric(base: dict, first: list, second: list) -> None:
    ours, theirs = _edit(base, first), _edit(base, second)

    forward, backward = _merge(base, ours, theirs), _merge(base, theirs, ours)

    assert {c.pointer for c in forward.conflicts} == {c.pointer for c in backward.conflicts}
    for conflict in forward.conflicts:
        swapped = _by_pointer(backward)[conflict.pointer]
        assert (conflict.ours, conflict.theirs, conflict.base) == (swapped.theirs, swapped.ours, swapped.base)
    if not forward.conflicts:
        assert canon(forward.value) == canon(backward.value)


@_PROFILE
@given(base=_DOC, first=st.lists(_EDIT, max_size=4), second=st.lists(_EDIT, max_size=4))
def test__property__merge_is_deterministic_and_has_identity(base: dict, first: list, second: list) -> None:
    ours, theirs = _edit(base, first), _edit(base, second)

    assert _merge(base, ours, theirs) == _merge(base, ours, theirs)
    assert canon(_merge(base, base, base).value) == canon(base)
    assert canon(_merge(base, ours, base).value) == canon(ours)
    assert canon(_merge(base, base, theirs).value) == canon(theirs)


@_PROFILE
@given(base=_DOC, first=st.lists(_EDIT, max_size=3), second=st.lists(_EDIT, max_size=3))
def test__property__disjoint_edits_compose_without_conflicts(base: dict, first: list, second: list) -> None:
    mine_keys = {key for key, _ in first}
    second = [edit for edit in second if edit[0] not in mine_keys]
    ours, theirs = _edit(base, first), _edit(base, second)

    merge = _merge(base, ours, theirs)

    assert merge.conflicts == ()
    assert canon(merge.value) == canon(_edit(ours, second))


@_PROFILE
@given(base=_DOC, first=st.lists(_EDIT, max_size=4), second=st.lists(_EDIT, max_size=4))
def test__property__every_conflict_is_a_real_disagreement(base: dict, first: list, second: list) -> None:
    ours, theirs = _edit(base, first), _edit(base, second)

    merge = _merge(base, ours, theirs)

    for conflict in merge.conflicts:
        mine, other, before = (_lookup(doc, conflict.pointer) for doc in (ours, theirs, base))
        assert canon(mine) != canon(other)
        assert canon(before) != canon(mine)
        assert canon(before) != canon(other)
    # Скалярные ключи верхнего уровня: если все три значения разные, конфликт обязан быть.
    for key in set(ours) | set(theirs) | set(base):
        values = [doc.get(key, ABSENT) for doc in (base, ours, theirs)]
        if any(isinstance(value, dict) for value in values):
            continue
        if len({canon(value) for value in values}) == 3:
            assert f"/{key}" in {c.pointer for c in merge.conflicts}


@_PROFILE
@given(
    base=_DOC,
    first=st.lists(_EDIT, max_size=4),
    second=st.lists(_EDIT, max_size=4),
    data=st.data(),
)
def test__property__any_allowed_choices_close_all_conflicts(
    base: dict, first: list, second: list, data: st.DataObject
) -> None:
    ours, theirs = _edit(base, first), _edit(base, second)
    merge = _merge(base, ours, theirs)
    choices = {c.pointer: data.draw(st.sampled_from(list(c.allowed))) for c in merge.conflicts}

    resolved = _merge(base, ours, theirs, choices=choices)

    assert resolved.conflicts == ()
    assert isinstance(resolved.value, dict)
    sides = {FieldChoice.mine: ours, FieldChoice.theirs: theirs}
    for conflict in merge.conflicts:
        choice = choices[conflict.pointer]
        if choice in sides:
            assert canon(_lookup(resolved.value, conflict.pointer)) == canon(_lookup(sides[choice], conflict.pointer))
