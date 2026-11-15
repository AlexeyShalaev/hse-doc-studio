"""Контракт «Каталогов паков»: эталоны `contracts/pack-catalog` против моделей `api/schemas/pack_catalog.py`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.schemas import pack_catalog as s
from hse_doc_studio.core.pack_catalog.errors import CatalogErrorCode, status_of
from pydantic import BaseModel, ConfigDict, TypeAdapter

_REPO = Path(__file__).resolve().parents[5]
_CONTRACT = _REPO / "contracts" / "pack-catalog"
_FIXTURES = _CONTRACT / "fixtures"


class _ErrorBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    detail: str
    code: str


_SCHEMAS: dict[str, Any] = {
    "CatalogOverview": s.CatalogOverviewResponse,
    "CatalogSource": s.CatalogSourceResponse,
    "CatalogCheck": s.CatalogCheckResponse,
    "CatalogApply": s.CatalogApplyResponse,
    "CatalogEventList": list[s.CatalogEventResponse],
    "CreateGitSourceRequest": s.CreateGitSourceRequest,
    "UpdateSourceRequest": s.UpdateSourceRequest,
    "ApplySourceRequest": s.ApplySourceRequest,
    "WorkspaceCatalog": s.WorkspaceCatalogResponse,
    "WorkspaceCatalogCheckRequest": s.WorkspaceCatalogCheckRequest,
    "CatalogErrorBody": _ErrorBody,
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

    assert listed == [code.value for code in CatalogErrorCode]


def test__error_codes__each_has_an_http_status() -> None:
    assert all(400 <= status_of(code) < 600 for code in CatalogErrorCode)  # noqa: PLR2004


def test__error_bodies__codes_are_from_the_closed_list() -> None:
    known = {code.value for code in CatalogErrorCode}
    bodies = [json.loads(p.read_text(encoding="utf-8")) for p in (_FIXTURES / "CatalogErrorBody").glob("*.json")]

    assert bodies
    assert {body["code"] for body in bodies} <= known
