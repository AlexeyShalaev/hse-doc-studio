"""Слова слияния совпадают с контрактом (contracts/git-sync)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from hse_doc_studio.core.git_sync.entities import AutoAction
from hse_doc_studio.core.git_sync.merge.choices import FieldChoice, FileChoice, HunkChoice
from hse_doc_studio.core.git_sync.merge.entities import ConflictType, MergeAction
from hse_doc_studio.core.git_sync.merge.text import hunk_key

_FIXTURES = Path(__file__).resolve().parents[7] / "contracts" / "git-sync" / "fixtures"


def _load(schema: str) -> Iterator[Any]:
    for path in sorted((_FIXTURES / schema).glob("*.json")):
        yield json.loads(path.read_text(encoding="utf-8"))


def _resolutions() -> Iterator[dict[str, Any]]:
    for schema in ("ConflictSession", "SaveConflictDraftRequest", "ResolveConflictsRequest"):
        for body in _load(schema):
            if schema == "ConflictSession":
                yield from (f["resolution"] for f in body["files"] if f["resolution"])
            else:
                yield from (body.get("resolutions") or {}).values()


def test__merge_action__auto_actions_are_the_contract_ones() -> None:
    assert {a.value for a in MergeAction} - {"conflict"} == {a.value for a in AutoAction}


def test__choices__cover_every_choice_used_in_the_contract_fixtures() -> None:
    hunk, field, file = set(), set(), set()
    for resolution in _resolutions():
        if resolution["kind"] == "hunks":
            hunk |= {d["choice"] for d in resolution["hunks"].values()}
        elif resolution["kind"] == "fields":
            field |= {d["choice"] for d in resolution["fields"].values()}
        elif resolution["kind"] == "file":
            file.add(resolution["choice"])

    assert hunk <= {c.value for c in HunkChoice}
    assert field <= {c.value for c in FieldChoice}
    assert file <= {c.value for c in FileChoice}
    assert hunk
    assert field
    assert file


def test__conflict_types__used_by_the_planner_are_known_to_the_contract() -> None:
    contract = {"content", "fields", "deleted_by_us", "deleted_by_them", "add_add", "binary", "signature_group"}
    contract |= {"case_collision", "invalid_result", "rename_rename"}

    assert {t.value for t in ConflictType} <= contract


def test__hunk_key__has_the_contract_shape() -> None:
    keys = [
        segment["key"]
        for detail in _load("ConflictFileDetail")
        if detail["kind"] == "text"
        for segment in detail["segments"]
        if segment["type"] == "hunk"
    ]

    assert keys
    assert all(re.fullmatch(r"h:[0-9a-f]{8}", key) for key in keys)
    assert re.fullmatch(r"h:[0-9a-f]{8}", hunk_key(b"a\n", b"b\n"))
