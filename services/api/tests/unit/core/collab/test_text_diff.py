"""Правки между версиями текста и трёхстороннее слияние: основа согласования комнаты с диском и git."""

from __future__ import annotations

import random

import pytest
from hse_doc_studio.core.collab.awareness import (
    AwarenessEntry,
    AwarenessFormatError,
    decode_awareness,
    encode_awareness,
)
from hse_doc_studio.core.collab.text_diff import apply_edits, diff_edits, merge3


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("", ""),
        ("", "новый текст"),
        ("старый текст", ""),
        ("a\nb\nc\n", "a\nB\nc\n"),
        ("a\nb\nc\n", "a\nc\n"),
        ("a\nc\n", "a\nb\nc\n"),
        ("Привет, мир 😀\nвторая строка\n", "Привет, мир 😀!\nвторая строка с правкой\nтретья\n"),
        ("no newline at end", "no newline at the end"),
    ],
)
def test__diff_edits__applied_edits_give_new_text(old: str, new: str) -> None:
    assert apply_edits(old, diff_edits(old, new)) == new


def test__diff_edits__identical_texts_give_no_edits() -> None:
    assert diff_edits("одно и то же\n", "одно и то же\n") == []


def test__diff_edits__small_change_in_long_line_is_char_level() -> None:
    old = "очень длинная строка " * 20 + "\n"
    new = old.replace("длинная", "длиннющая", 1)

    edits = diff_edits(old, new)

    assert apply_edits(old, edits) == new
    assert sum(e.end - e.start for e in edits) < 20


def test__diff_edits__random_roundtrip() -> None:
    rng = random.Random(7)
    alphabet = ["аб ", "cd\n", "😀", "\n", "x"]
    for _ in range(200):
        old = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        new = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        assert apply_edits(old, diff_edits(old, new)) == new


def test__merge3__disjoint_edits_of_both_sides_are_kept() -> None:
    base = "1\n2\n3\n4\n5\n"
    ours = "1\nдва\n3\n4\n5\n"
    theirs = "1\n2\n3\n4\nпять\n"

    merged = merge3(base, ours, theirs)

    assert merged.text == "1\nдва\n3\n4\nпять\n"
    assert merged.conflicts == 0


def test__merge3__same_change_on_both_sides_is_not_a_conflict() -> None:
    base = "a\nb\nc\n"
    both = "a\nB\nc\n"

    assert merge3(base, both, both).conflicts == 0


def test__merge3__conflicting_edits_keep_ours_and_count() -> None:
    base = "a\nb\nc\n"

    merged = merge3(base, "a\nмоё\nc\n", "a\nчужое\nc\n")

    assert merged.text == "a\nмоё\nc\n"
    assert merged.conflicts == 1


def test__merge3__only_one_side_changed() -> None:
    base = "a\nb\n"

    assert merge3(base, base, "a\nb\nc\n").text == "a\nb\nc\n"
    assert merge3(base, "a\nb\nc\n", base).text == "a\nb\nc\n"


def test__merge3__insertions_at_different_places() -> None:
    base = "a\nb\nc\n"

    merged = merge3(base, "x\na\nb\nc\n", "a\nb\nc\ny\n")

    assert merged.text == "x\na\nb\nc\ny\n"
    assert merged.conflicts == 0


def test__awareness__roundtrip_and_null_state() -> None:
    entries = [
        AwarenessEntry(4_000_000_000_123, 5, {"user": {"name": "Анна"}, "cursor": None}),
        AwarenessEntry(7, 300, None),
    ]

    assert decode_awareness(encode_awareness(entries)) == entries


@pytest.mark.parametrize(
    "data", [b"", b"\x02\x01", b"\x01\x01\x01\x05ab", b"\x01\x01\x01\x02[]", b"\x01\x01\x01\x04nope"]
)
def test__awareness__garbage_is_rejected(data: bytes) -> None:
    with pytest.raises(AwarenessFormatError):
        decode_awareness(data)


def test__awareness__too_many_entries_is_rejected() -> None:
    many = encode_awareness([AwarenessEntry(i, 1, {}) for i in range(10)])

    with pytest.raises(AwarenessFormatError):
        decode_awareness(many, max_entries=5)
