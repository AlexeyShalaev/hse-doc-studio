"""Что известно о проекте Студии по его `.hse-studio/project.json` в удалённом репозитории.

Файл читается как есть, без создания `Project`: удалённый проект может быть записан более новой Студией,
и здесь важно лишь понять, чей он, какого шаблона и открывает ли его эта Студия.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.git_sync.entities import SchemaAccess
from hse_doc_studio.core.project_schema import PROJECT_SCHEMA_VERSION
from hse_doc_studio.core.value_objects import ProjectSchema

PROJECT_FILE = ".hse-studio/project.json"


@dataclass(frozen=True)
class RemoteProject:
    id: UUID
    name: str
    pack_id: str
    template_id: str
    template_version: str
    kind: str
    staffing: str
    authors_count: int
    schema: ProjectSchema
    min_studio: str | None


def _int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def parse_remote_project(raw: bytes) -> RemoteProject | None:
    """None, если файл не разбирается как проект Студии."""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
        lock = data["lock"]
        project_id = UUID(data["id"])
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    if not isinstance(lock, dict):
        return None
    block = data.get("schema")
    block = block if isinstance(block, dict) else {}
    version = _int(block.get("version"), 1)
    authors = data.get("authors")
    min_studio = lock.get("min_studio")
    return RemoteProject(
        id=project_id,
        name=_text(data.get("name")),
        pack_id=_text(lock.get("pack_id")),
        template_id=_text(lock.get("template_id")),
        template_version=_text(lock.get("version")),
        kind=_text(data.get("kind")),
        staffing=_text(data.get("staffing")),
        authors_count=len(authors) if isinstance(authors, list) else 0,
        schema=ProjectSchema(
            version=version,
            read_compat=_int(block.get("read_compat"), version),
            write_compat=_int(block.get("write_compat"), version),
            written_by=_text(block.get("written_by")),
        ),
        min_studio=min_studio if isinstance(min_studio, str) and min_studio else None,
    )


def remote_schema_access(schema: ProjectSchema) -> SchemaAccess:
    """Что эта Студия делает с данными такой схемы; повторяет core.project_schema.schema_access."""
    if schema.read_compat > PROJECT_SCHEMA_VERSION:
        return SchemaAccess.files_only
    if schema.write_compat > PROJECT_SCHEMA_VERSION:
        return SchemaAccess.read_only
    return SchemaAccess.full


def remote_required_studio(project: RemoteProject, *, template_available: bool) -> str | None:
    """Версия Студии, которая откроет удалённый проект полностью; None, если и эта Студия справится."""
    required: str | None = None
    if remote_schema_access(project.schema) is not SchemaAccess.full:
        required = project.schema.written_by or None
    if not template_available:
        required = project.min_studio or required
    return required


def schema_blocks_merge(schema: ProjectSchema) -> bool:
    """Данные удалённого проекта эта Студия не вправе ни читать, ни писать: слияние с ними невозможно."""
    return remote_schema_access(schema) is not SchemaAccess.full
