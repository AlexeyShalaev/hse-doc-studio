from __future__ import annotations

import json
from uuid import UUID

import pytest
from hse_doc_studio.core.git_sync.entities import SchemaAccess
from hse_doc_studio.core.git_sync.remote_project import (
    parse_remote_project,
    remote_required_studio,
    remote_schema_access,
    schema_blocks_merge,
)
from hse_doc_studio.core.value_objects import ProjectSchema

pytestmark = pytest.mark.unit

_ID = "5f0c2b7e-3b1a-4d6e-9a54-0a1b2c3d4e5f"


def _project(**changes: object) -> bytes:
    data: dict[str, object] = {
        "schema": {"version": 1, "read_compat": 1, "write_compat": 1, "written_by": "0.3.0"},
        "id": _ID,
        "name": "Курсовая работа",
        "lock": {"pack_id": "hse-cs-sse", "template_id": "course-paper", "version": "1.2.0", "min_studio": "0.3.0"},
        "kind": "course_paper",
        "staffing": "team",
        "authors": [{"name": "A"}, {"name": "B"}],
    }
    return json.dumps({**data, **changes}, ensure_ascii=False).encode()


def test__parse__reads_identity_template_and_team() -> None:
    project = parse_remote_project(_project())

    assert project is not None
    assert project.id == UUID(_ID)
    assert (project.name, project.pack_id, project.template_id, project.template_version) == (
        "Курсовая работа",
        "hse-cs-sse",
        "course-paper",
        "1.2.0",
    )
    assert (project.kind, project.staffing, project.authors_count, project.min_studio) == (
        "course_paper",
        "team",
        2,
        "0.3.0",
    )


def test__parse__utf8_bom_and_missing_schema_block_mean_schema_one() -> None:
    raw = b"\xef\xbb\xbf" + _project(schema=None)

    project = parse_remote_project(raw)

    assert project is not None
    assert project.schema == ProjectSchema(version=1, read_compat=1, write_compat=1, written_by="")
    assert remote_schema_access(project.schema) is SchemaAccess.full


@pytest.mark.parametrize(
    "raw",
    [b"", b"not json", b"[]", b"{}", json.dumps({"id": "nope", "lock": {}}).encode(), json.dumps({"id": _ID}).encode()],
)
def test__parse__garbage__returns_none(raw: bytes) -> None:
    assert parse_remote_project(raw) is None


@pytest.mark.parametrize(
    ("schema", "access", "blocks"),
    [
        (ProjectSchema(1, 1, 1), SchemaAccess.full, False),
        (ProjectSchema(2, 1, 2), SchemaAccess.read_only, True),
        (ProjectSchema(2, 2, 2), SchemaAccess.files_only, True),
    ],
)
def test__schema_access__follows_read_and_write_compat(
    schema: ProjectSchema, access: SchemaAccess, blocks: bool
) -> None:
    assert remote_schema_access(schema) is access
    assert schema_blocks_merge(schema) is blocks


def test__required_studio__prefers_the_template_requirement_when_the_template_is_missing() -> None:
    newer = parse_remote_project(
        _project(schema={"version": 9, "read_compat": 9, "write_compat": 9, "written_by": "9.0.0"})
    )
    assert newer is not None

    assert remote_required_studio(newer, template_available=True) == "9.0.0"
    assert remote_required_studio(newer, template_available=False) == "0.3.0"


def test__required_studio__nothing_is_required_when_everything_is_available() -> None:
    project = parse_remote_project(_project())
    assert project is not None

    assert remote_required_studio(project, template_available=True) is None


@pytest.mark.parametrize("depth", [100, 20_000])
def test__parse__deeply_nested_document__is_not_a_project_and_does_not_raise(depth: int) -> None:
    nested = "[" * depth + "]" * depth
    raw = f'{{"id": "{_ID}", "lock": {{}}, "x": {nested}}}'.encode()

    assert parse_remote_project(raw) is None
