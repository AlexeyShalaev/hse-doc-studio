"""Разбор чужого JSON: мусор и глубокая вложенность дают ValueError, а не RecursionError."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.git_sync.merge.rules import StateFileMerge
from hse_doc_studio.core.git_sync.merge.signature_groups import _referenced
from hse_doc_studio.core.git_sync.protocols import MergeMeta
from hse_doc_studio.core.git_sync.untrusted_json import MAX_JSON_DEPTH, loads_untrusted

pytestmark = pytest.mark.unit


def test__loads_untrusted__bom_and_ordinary_document__parsed() -> None:
    assert loads_untrusted('﻿{"a": [1, {"b": null}]}'.encode()) == {"a": [1, {"b": None}]}


@pytest.mark.parametrize("raw", [b"{", b"\xff\xfe", b""])
def test__loads_untrusted__not_json__value_error(raw: bytes) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        loads_untrusted(raw)


@pytest.mark.parametrize("depth", [MAX_JSON_DEPTH + 1, 5_000, 200_000])
def test__loads_untrusted__too_deep__value_error(depth: int) -> None:
    with pytest.raises(ValueError, match="deeply"):
        loads_untrusted(("[" * depth + "]" * depth).encode())


def test__loads_untrusted__depth_at_the_limit__parsed() -> None:
    assert loads_untrusted(("[" * MAX_JSON_DEPTH + "]" * MAX_JSON_DEPTH).encode()) is not None


def test__signature_references__too_deep_document__is_empty() -> None:
    raw = ("[" * 200_000 + "]" * 200_000).encode()

    assert _referenced(raw, "doc") == frozenset()


def test__state_file_merge__too_deep_side__is_merged_as_text_instead_of_raising() -> None:
    deep = ("[" * 200_000 + "]" * 200_000).encode()

    decision = StateFileMerge().merge(".hse-studio/project.json", b"{}", b"{}", deep, MergeMeta())

    assert decision.as_text
