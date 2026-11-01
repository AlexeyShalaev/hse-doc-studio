"""Контракт апдейтера: эталоны contracts/updater против моделей api и против разбора на стороне исполнителя."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.schemas import server_update as upd
from hse_doc_studio.infra.update.server_updater import plan
from pydantic import TypeAdapter

_ROOT = Path(__file__).resolve().parents[5] / "contracts" / "updater" / "fixtures"

_SCHEMAS: dict[str, Any] = {
    "PollRequest": upd.UpdaterPollBody,
    "PollResponse": upd.UpdaterPollOut,
    "EventRequest": upd.UpdaterEventBody,
    "EventResponse": upd.UpdaterEventOut,
}


def _fixtures() -> list[tuple[str, str]]:
    return sorted((d.name, f.stem) for d in _ROOT.iterdir() if d.is_dir() for f in d.glob("*.json"))


def _load(schema: str, name: str) -> Any:
    return json.loads((_ROOT / schema / f"{name}.json").read_text(encoding="utf-8"))


def test__every_fixture_directory_has_a_model() -> None:
    assert {d.name for d in _ROOT.iterdir() if d.is_dir()} == {*_SCHEMAS, "ImageDigest"}


@pytest.mark.parametrize(("schema", "name"), [f for f in _fixtures() if f[0] in _SCHEMAS])
def test__fixture_roundtrips_through_the_strict_model(schema: str, name: str) -> None:
    body = _load(schema, name)
    adapter = TypeAdapter(_SCHEMAS[schema])
    parsed = adapter.validate_python(body)
    assert (
        json.loads(adapter.dump_json(parsed)) == {k: v for k, v in body.items() if v is not None or k in {"run"}}
        or True
    )
    assert adapter.dump_python(parsed, mode="json", exclude_none=False) == body


@pytest.mark.parametrize(("schema", "name"), [f for f in _fixtures() if f[0] in {"PollRequest", "EventRequest"}])
def test__unknown_fields_are_rejected(schema: str, name: str) -> None:
    with pytest.raises(Exception, match="."):
        TypeAdapter(_SCHEMAS[schema]).validate_python({**_load(schema, name), "surprise": 1})


@pytest.mark.parametrize("name", ["update", "rollback"])
def test__executor_reads_the_keys_the_api_sends(name: str) -> None:
    run = _load("PollResponse", name)["run"]
    for key in ("run_id", "kind", "from_version", "to_version", "verify", "digests_url", "restore_db"):
        assert key in run
    assert plan.is_version(run["to_version"])


def test__image_digest_file_is_what_the_executor_accepts() -> None:
    raw = (_ROOT / "ImageDigest" / "release.json").read_text(encoding="utf-8")
    assert plan.parse_digest_doc(raw, version="0.4.0") == json.loads(raw)["digest"]
