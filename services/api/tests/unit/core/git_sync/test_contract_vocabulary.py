"""Перечисления домена против эталонов контракта: ни одного значения ни без эталона, ни без перечисления."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.git_sync import entities as e
from hse_doc_studio.core.git_sync.providers import GitProvider
from hse_doc_studio.core.git_sync.url import RemoteKind

_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "git-sync" / "fixtures"


def _load(schema: str) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((_FIXTURES / schema).glob("*.json"))]


def _values(enum: type[StrEnum]) -> set[str]:
    return {member.value for member in enum}


def test__sync_ui_state__fixtures_show_every_state() -> None:
    assert {s["ui_state"] for s in _load("GitStatus")} == _values(e.SyncUiState)


def test__sync_relation_and_health__fixtures_stay_inside_the_enums() -> None:
    statuses = _load("GitStatus")

    assert {s["relation"] for s in statuses} <= _values(e.SyncRelation)
    assert {s["health"] for s in statuses} <= _values(e.SyncHealth)
    assert {s["blocked"]["reason"] for s in statuses if s["blocked"]} <= _values(e.SyncBlockReason)


def test__remote_kind_and_provider__fixtures_stay_inside_the_enums() -> None:
    remotes = [s["remote"] for s in _load("GitStatus") if s["remote"]]

    assert {r["kind"] for r in remotes} <= _values(RemoteKind)
    assert {r["provider"] for r in remotes} <= _values(GitProvider)


def test__operation_vocabulary__fixtures_show_every_value() -> None:
    operations = _load("Operation")

    assert {o["kind"] for o in operations} == _values(e.OperationKind)
    assert {o["status"] for o in operations} == _values(e.OperationStatus)
    assert {o["phase"] for o in operations} == _values(e.OperationPhase)


def test__probe_relation__fixtures_show_every_value() -> None:
    assert {p["relation"] for p in _load("Probe")} == _values(e.ProbeRelation)


def test__sync_outcome_and_auto_action__fixtures_stay_inside_the_enums() -> None:
    results = _load("SyncResult")

    assert {r["outcome"] for r in results} == _values(e.SyncOutcome)
    assert {a["action"] for r in results for a in r["auto"]} <= _values(e.AutoAction)
    assert {w["code"] for r in results for w in r["warnings"]} <= _values(e.SyncWarningCode)


@pytest.mark.parametrize(
    ("schema", "field", "enum"),
    [
        ("GitCredential", "kind", e.GitCredentialKind),
        ("GitCredential", "status", e.CredentialStatus),
    ],
)
def test__credential_vocabulary__fixtures_stay_inside_the_enums(schema: str, field: str, enum: type[StrEnum]) -> None:
    assert {c[field] for c in _load(schema)} <= _values(enum)
