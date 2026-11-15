"""Схемы «Каталогов паков» (`/api/admin/pack-catalog*`) и подключения папки локально
(`/api/v1/pack-studio/workspaces/{id}/catalog*`), docs/design/template-studio.md, 10.3, срез T17.

Эталоны лежат в `contracts/pack-catalog/fixtures`, тест `tests/unit/contract/test_pack_catalog_contract.py` сверяет
их с этими моделями, клиент разбирает те же эталоны.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel

SourceKindName = Literal["git", "archive", "folder"]
AccessName = Literal["none", "personal", "service"]
VerdictName = Literal["new", "present", "changed", "incompatible", "invalid", "unreleased"]
ConflictName = Literal["builtin", "other_source", "invalid"]
BlockerName = Literal["pack_conflict", "version_changed", "version_invalid", "no_packs"]
EventActionName = Literal["add", "update", "check", "apply", "enable", "disable", "remove", "track"]
OriginName = Literal["builtin", "subscribed"]


class CatalogSourceErrorResponse(StrictModel):
    code: str
    detail: str


class CatalogVersionResponse(StrictModel):
    template: str
    version: str
    # False: версия есть для существующих проектов, но мастер её не предлагает.
    listed: bool


class CatalogPackResponse(StrictModel):
    id: str
    name: dict[str, str]
    origin: OriginName
    source_id: str | None
    listed: bool
    replaces_builtin: bool
    versions: list[CatalogVersionResponse]


class CatalogSourceResponse(StrictModel):
    id: str
    kind: SourceKindName
    label: str
    enabled: bool
    replace_builtin: bool
    track: bool
    packs_path: str
    url: str | None
    ref: str | None
    access: AccessName
    credential_id: str | None
    service_access_id: str | None
    insecure_http: bool
    archive_name: str | None
    archive_digest: str | None
    folder: str | None
    workspace_id: str | None
    applied_revision: str | None
    applied_at: datetime | None
    checked_revision: str | None
    checked_at: datetime | None
    check_ok: bool | None
    pending_versions: int
    error: CatalogSourceErrorResponse | None
    busy: bool
    created_at: datetime
    updated_at: datetime
    created_by: str | None
    packs: list[CatalogPackResponse]


class CatalogLimitsResponse(StrictModel):
    max_archive_bytes: int
    max_files: int
    max_bytes: int


class CatalogOverviewResponse(StrictModel):
    revision: int
    sources: list[CatalogSourceResponse]
    # Паки каталога помимо подключённых источников: вшитые и оставшиеся от удалённых источников.
    packs: list[CatalogPackResponse]
    limits: CatalogLimitsResponse


class PlannedVersionResponse(StrictModel):
    template: str
    version: str
    verdict: VerdictName
    digest: str | None
    kind: str | None
    min_studio: str | None
    errors: list[str]
    warnings: list[str]


class PlannedPackResponse(StrictModel):
    id: str
    name: dict[str, str]
    conflict: ConflictName | None
    conflict_with: str | None
    replaces_builtin: bool
    problems: list[str]
    versions: list[PlannedVersionResponse]


class CatalogCheckResponse(StrictModel):
    source: CatalogSourceResponse
    revision: str
    ok: bool
    blockers: list[BlockerName]
    new_count: int
    problems: list[str]
    packs: list[PlannedPackResponse]


class CatalogApplyResponse(StrictModel):
    source: CatalogSourceResponse
    revision: str
    added: list[str]
    catalog_revision: int


class CatalogEventResponse(StrictModel):
    id: str
    action: EventActionName
    at: datetime
    ok: bool
    actor_id: str | None
    revision: str | None
    summary: dict[str, Any]


class CreateGitSourceRequest(StrictModel):
    url: str = Field(min_length=1, max_length=2048)
    label: str | None = Field(default=None, max_length=200)
    packs_path: str | None = Field(default=None, max_length=512)
    ref: str | None = Field(default=None, max_length=200)
    credential_id: UUID | None = None
    service_access_id: UUID | None = None
    insecure_http: bool = False
    replace_builtin: bool = False
    track: bool = False


class UpdateSourceRequest(StrictModel):
    label: str | None = Field(default=None, max_length=200)
    packs_path: str | None = Field(default=None, max_length=512)
    ref: str | None = Field(default=None, max_length=200)
    credential_id: UUID | None = None
    service_access_id: UUID | None = None
    clear_access: bool = False
    replace_builtin: bool | None = None
    track: bool | None = None
    enabled: bool | None = None


class ApplySourceRequest(StrictModel):
    revision: str = Field(min_length=1, max_length=128)


class WorkspaceCatalogResponse(StrictModel):
    """Папка рабочего пространства в каталоге этой Студии: источник или null, если не подключена."""

    source: CatalogSourceResponse | None


class WorkspaceCatalogCheckRequest(StrictModel):
    replace_builtin: bool = False
