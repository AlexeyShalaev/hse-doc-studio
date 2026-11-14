"""Контракт Студии шаблонов: эталоны `contracts/pack-studio` против моделей `api/schemas/pack_studio.py`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.schemas import pack_studio as s
from hse_doc_studio.core.pack_studio.errors import PackStudioErrorCode, status_of
from pydantic import TypeAdapter

_REPO = Path(__file__).resolve().parents[5]
_CONTRACT = _REPO / "contracts" / "pack-studio"
_FIXTURES = _CONTRACT / "fixtures"

_SCHEMAS: dict[str, Any] = {
    "PackStudioSection": s.PackStudioSectionResponse,
    "UpdatePackStudioSectionRequest": s.UpdatePackStudioSectionRequest,
    "PackWorkspace": s.PackWorkspaceResponse,
    "PackWorkspaceList": list[s.PackWorkspaceResponse],
    "CreatePackWorkspaceRequest": s.CreatePackWorkspaceRequest,
    "PackTree": s.PackTreeResponse,
    "PackFileVersion": s.PackFileVersionResponse,
    "PackYamlPatchRequest": s.PackYamlPatchRequest,
    "PackYamlPatchResponse": s.PackYamlPatchResponse,
    "PackStudioErrorBody": s.PackStudioErrorBody,
    "PackStudioGrant": s.PackStudioGrantResponse,
    "PackStudioAdmin": s.PackStudioAdminResponse,
    "UpdatePackStudioAdminRequest": s.UpdatePackStudioAdminRequest,
    "CreatePackStudioGrantRequest": s.CreatePackStudioGrantRequest,
}


def _fixture_files() -> list[Path]:
    return sorted(_FIXTURES.glob("*/*.json"))


@pytest.mark.parametrize("path", _fixture_files(), ids=lambda p: f"{p.parent.name}/{p.stem}")
def test__fixture__parses_with_its_model_and_round_trips(path: Path) -> None:
    model = _SCHEMAS[path.parent.name]
    raw = json.loads(path.read_text(encoding="utf-8"))

    adapter: TypeAdapter[Any] = TypeAdapter(model)
    parsed = adapter.validate_python(raw)

    assert adapter.dump_python(parsed, mode="json", exclude_unset=True) == raw


def test__fixtures__every_folder_has_a_schema_and_every_schema_has_fixtures() -> None:
    folders = {path.name for path in _FIXTURES.iterdir() if path.is_dir()}

    assert folders == set(_SCHEMAS)


def test__error_codes__match_the_enum_in_order() -> None:
    listed = json.loads((_CONTRACT / "error_codes.json").read_text(encoding="utf-8"))

    assert listed == [code.value for code in PackStudioErrorCode]


def test__error_codes__each_has_an_http_status() -> None:
    assert all(400 <= status_of(code) < 500 for code in PackStudioErrorCode)  # noqa: PLR2004


def test__error_bodies__codes_are_from_the_closed_list() -> None:
    known = {code.value for code in PackStudioErrorCode}
    bodies = [json.loads(p.read_text(encoding="utf-8")) for p in (_FIXTURES / "PackStudioErrorBody").glob("*.json")]

    assert {body["code"] for body in bodies} <= known
