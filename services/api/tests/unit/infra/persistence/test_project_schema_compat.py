"""Совместимость данных проекта между версиями Студии (core.project_schema)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.enums import DocumentStatus, ProjectAccessMode, SignMode
from hse_doc_studio.core.errors import ProjectReadOnlyError
from hse_doc_studio.core.project_schema import (
    LEGACY_PROJECT_SCHEMA,
    PROJECT_SCHEMA_VERSION,
    schema_access,
    schema_to_write,
)
from hse_doc_studio.core.value_objects import FormState, ProjectSchema, SignatureSlot, SignaturesState
from hse_doc_studio.infra.persistence.forms import JsonFormStateRepository
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.persistence.project_migrations import ProjectStateBundle, migrate_project_state
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from hse_doc_studio.infra.persistence.unknown_fields import (
    PROJECT_SHAPE,
    ListOf,
    MapOf,
    Struct,
    preserve_unknown,
)

from tests.factories import make_document, make_project

pytestmark = pytest.mark.unit

repo = JsonProjectRepository(app_version="0.2.0")


def _project_json(folder: Path) -> dict[str, Any]:
    return json.loads((folder / ".hse-studio" / "project.json").read_text(encoding="utf-8"))


def _write_project_json(folder: Path, data: dict[str, Any]) -> None:
    (folder / ".hse-studio" / "project.json").write_text(json.dumps(data), encoding="utf-8")


# ── схема ────────────────────────────────────────────────────────────────────


def test__save__writes_schema_block(tmp_path: Path) -> None:
    repo.save(make_project(folder=tmp_path))

    assert _project_json(tmp_path)["schema"] == {
        "version": PROJECT_SCHEMA_VERSION,
        "read_compat": 1,
        "write_compat": 1,
        "written_by": "0.2.0",
    }


def test__legacy_project_without_schema__reads_as_schema_1(tmp_path: Path) -> None:
    repo.save(make_project(folder=tmp_path))
    data = _project_json(tmp_path)
    del data["schema"]
    _write_project_json(tmp_path, data)

    project = repo.get(tmp_path)

    assert project is not None
    assert project.schema == LEGACY_PROJECT_SCHEMA


@pytest.mark.parametrize(
    ("schema", "expected"),
    [
        (ProjectSchema(1, 1, 1), ProjectAccessMode.full),
        (ProjectSchema(5, 1, 1), ProjectAccessMode.full),  # аддитивная схема новее — пишем
        (ProjectSchema(5, 1, 5), ProjectAccessMode.read_only),
        (ProjectSchema(5, 5, 5), ProjectAccessMode.files_only),
    ],
)
def test__schema_access(schema: ProjectSchema, expected: ProjectAccessMode) -> None:
    assert schema_access(schema) == expected


def test__schema_to_write__keeps_newer_requirements() -> None:
    written = schema_to_write(ProjectSchema(5, 2, 1, "0.9.0"), "0.2.0")
    assert (written.version, written.read_compat, written.write_compat) == (5, 2, 1)
    assert written.written_by == "0.2.0"


def test__save__refuses_data_only_a_newer_studio_may_write(tmp_path: Path) -> None:
    repo.save(make_project(folder=tmp_path, name="Новое"))
    data = _project_json(tmp_path)
    data["schema"] = {"version": 9, "read_compat": 1, "write_compat": 9, "written_by": "9.0.0"}
    _write_project_json(tmp_path, data)

    project = repo.get(tmp_path)
    assert project is not None
    project.name = "Старая Студия переписала"

    with pytest.raises(ProjectReadOnlyError):
        repo.save(project)
    assert _project_json(tmp_path)["name"] == "Новое"


def test__signature_and_form_saves__respect_project_schema(tmp_path: Path) -> None:
    repo.save(make_project(folder=tmp_path))
    data = _project_json(tmp_path)
    data["schema"] = {"version": 9, "read_compat": 1, "write_compat": 9}
    _write_project_json(tmp_path, data)

    with pytest.raises(ProjectReadOnlyError):
        JsonSignatureRepository().save_state(tmp_path, SignaturesState.empty())
    with pytest.raises(ProjectReadOnlyError):
        JsonFormStateRepository().save_state(tmp_path, "f", FormState.empty())


# ── неизвестные поля ─────────────────────────────────────────────────────────


def test__save__preserves_fields_written_by_a_newer_studio(tmp_path: Path) -> None:
    repo.save(make_project(folder=tmp_path, documents=[make_document("vkr"), make_document("pres")]))
    data = _project_json(tmp_path)
    data["future_top"] = {"x": 1}
    data["lock"]["future_lock"] = "L"
    data["documents"][1]["future_doc"] = [1, 2]
    data["authors"][0]["future_author"] = True
    _write_project_json(tmp_path, data)

    project = repo.get(tmp_path)
    assert project is not None
    project.name = "Переименован"
    project.documents.reverse()
    repo.save(project)

    saved = _project_json(tmp_path)
    assert saved["name"] == "Переименован"
    assert saved["future_top"] == {"x": 1}
    assert saved["lock"]["future_lock"] == "L"
    by_id = {d["id"]: d for d in saved["documents"]}
    assert by_id["pres"]["future_doc"] == [1, 2]
    assert "future_doc" not in by_id["vkr"]
    assert saved["authors"][0]["future_author"] is True


def test__save__removed_meta_key_stays_removed(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path)
    project.meta = {"keep": 1, "drop": 2}
    repo.save(project)

    project.meta = {"keep": 1}
    repo.save(project)

    assert _project_json(tmp_path)["meta"] == {"keep": 1}


def test__unknown_enum_values__project_still_opens(tmp_path: Path) -> None:
    repo.save(make_project(folder=tmp_path, documents=[make_document("vkr")]))
    data = _project_json(tmp_path)
    data["documents"][0]["status"] = "hologram"
    data["lock"]["engine"] = "tectonic"
    _write_project_json(tmp_path, data)

    project = repo.get(tmp_path)

    assert project is not None
    assert project.documents[0].status == DocumentStatus.draft


def test__preserve_unknown__map_values_merge_by_shape() -> None:
    shape = Struct({"slots": MapOf(Struct())})
    old = {"slots": {"a": {"png": "a.png", "future": 1}, "gone": {"png": "g.png"}}}
    new = {"slots": {"a": {"png": "b.png"}}}

    assert preserve_unknown(new, old, shape) == {"slots": {"a": {"png": "b.png", "future": 1}}}


def test__preserve_unknown__list_items_matched_by_key() -> None:
    shape = ListOf(Struct(), key=lambda item: item.get("id"))
    old = [{"id": "x", "extra": 1}, {"id": "y", "extra": 2}]
    new = [{"id": "y"}, {"id": "z"}]

    assert preserve_unknown(new, old, shape) == [{"id": "y", "extra": 2}, {"id": "z"}]


def test__preserve_unknown__no_old_file_returns_new() -> None:
    new = {"name": "x"}
    assert preserve_unknown(new, None, PROJECT_SHAPE) is new


def test__signatures_and_forms__unknown_fields_survive_rewrite(tmp_path: Path) -> None:
    repo.save(make_project(folder=tmp_path))
    signatures = JsonSignatureRepository()
    state = SignaturesState(slots={"sup": SignatureSlot("sup.png", 10, 10, sign_mode=SignMode.image)}, placements={})
    signatures.save_state(tmp_path, state)
    sig_path = tmp_path / ".hse-studio" / "signatures.json"
    raw = json.loads(sig_path.read_text(encoding="utf-8"))
    raw["slots"]["sup"]["future_slot"] = "f"
    raw["future_block"] = {}
    sig_path.write_text(json.dumps(raw), encoding="utf-8")

    signatures.save_state(tmp_path, signatures.get_state(tmp_path))

    rewritten = json.loads(sig_path.read_text(encoding="utf-8"))
    assert rewritten["slots"]["sup"]["future_slot"] == "f"
    assert rewritten["future_block"] == {}

    forms = JsonFormStateRepository()
    forms.save_state(tmp_path, "decl", FormState(schema_version=1, completed=False, answers={"a": 1}))
    form_path = tmp_path / ".hse-studio" / "forms" / "decl.json"
    raw_form = json.loads(form_path.read_text(encoding="utf-8"))
    raw_form["reviewed_at"] = "2027-01-01"
    form_path.write_text(json.dumps(raw_form), encoding="utf-8")

    forms.save_state(tmp_path, "decl", FormState(schema_version=1, completed=True, answers={}))

    rewritten_form = json.loads(form_path.read_text(encoding="utf-8"))
    assert rewritten_form["reviewed_at"] == "2027-01-01"
    assert rewritten_form["answers"] == {}


# ── миграции ─────────────────────────────────────────────────────────────────


def test__migrations__run_in_order_back_up_and_persist(tmp_path: Path) -> None:
    repo.save(make_project(folder=tmp_path))
    studio = tmp_path / ".hse-studio"
    (studio / "signatures.json").write_text(json.dumps({"slots": {"old": {}}}), encoding="utf-8")
    original = _project_json(tmp_path)

    def to_2(bundle: ProjectStateBundle) -> None:
        bundle.project["renamed"] = bundle.project.pop("name")

    def to_3(bundle: ProjectStateBundle) -> None:
        signatures = bundle.get("signatures.json")
        signatures["slots"]["new"] = signatures["slots"].pop("old")
        bundle.set("signatures.json", signatures)

    migrated = migrate_project_state(
        tmp_path, original, steps={1: to_2, 2: to_3}, target_version=3, write_compat=2, app_version="0.3.0"
    )

    assert migrated["renamed"] == original["name"]
    assert migrated["schema"] == {"version": 3, "read_compat": 1, "write_compat": 2, "written_by": "0.3.0"}
    assert _project_json(tmp_path) == migrated
    assert json.loads((studio / "signatures.json").read_text(encoding="utf-8")) == {"slots": {"new": {}}}
    backup = studio / "backup" / "schema-1"
    assert json.loads((backup / "project.json").read_text(encoding="utf-8")) == original
    assert json.loads((backup / "signatures.json").read_text(encoding="utf-8")) == {"slots": {"old": {}}}


def test__migrations__current_schema_is_left_alone(tmp_path: Path) -> None:
    repo.save(make_project(folder=tmp_path))
    data = _project_json(tmp_path)

    assert migrate_project_state(tmp_path, data, steps={}, target_version=PROJECT_SCHEMA_VERSION) is data
    assert not (tmp_path / ".hse-studio" / "backup").exists()
