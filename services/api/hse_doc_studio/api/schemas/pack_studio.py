"""Схемы `/api/v1/pack-studio/*` и `/api/admin/pack-studio*` (docs/design/template-studio.md, раздел 12).

Эталоны лежат в `contracts/pack-studio/fixtures`, тест `tests/unit/contract/test_pack_studio_contract.py` сверяет их
с этими моделями. Форму меняют так: сначала эталоны, затем модели и клиент в одном коммите.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from hse_doc_studio.api.schemas.common import StrictModel

WorkspaceKindName = Literal["git", "folder"]
WorkspaceStateName = Literal["cloning", "ready", "failed"]
ReadOnlyReason = Literal["version_released", "releases_read_only"]
YamlOpName = Literal["set", "insert", "delete", "move"]
GrantSubjectName = Literal["user", "group"]


class PackStudioErrorBody(BaseModel):
    """`{detail, code}` и поля по коду: `etag` и `content` у `stale_file`, `path` у `version_released`, `op` и
    `reason` у `yaml_patch_conflict`, `limit` у `file_too_large` и `workspace_limit`."""

    model_config = ConfigDict(extra="allow")

    detail: str
    code: str


class PackStudioSectionResponse(StrictModel):
    enabled: bool
    # Включение задано окружением или профилем standalone: переключатель только для чтения.
    locked: bool
    # Раздел открыт этому человеку: включён и есть право «Автор шаблонов».
    allowed: bool
    has_right: bool
    standalone: bool


class UpdatePackStudioSectionRequest(StrictModel):
    enabled: bool


class PackWorkspaceErrorBody(StrictModel):
    # Код из contracts/pack-studio/error_codes.json или contracts/git-sync/error_codes.json.
    code: str
    detail: str


class PackWorkspaceResponse(StrictModel):
    id: str
    kind: WorkspaceKindName
    label: str
    state: WorkspaceStateName
    # Идёт фоновая операция: клон или выборка базовой ветки.
    busy: bool
    packs_path: str
    url: str | None
    credential_id: str | None
    insecure_http: bool
    # Папка для показа (путь хоста); только у `folder`.
    folder: str | None
    base_branch: str | None
    base_sha: str | None
    fetched_at: datetime | None
    # Срез T6: рабочая ветка, запрос на слияние и статус проверок; до него всегда null.
    work_branch: str | None
    pr_url: str | None
    pr_number: int | None
    ci_status: str | None
    error: PackWorkspaceErrorBody | None
    created_at: datetime
    updated_at: datetime


class CreatePackWorkspaceRequest(StrictModel):
    kind: WorkspaceKindName
    label: str | None = Field(default=None, max_length=120)
    url: str | None = Field(default=None, max_length=2048)
    credential_id: UUID | None = None
    insecure_http: bool = False
    base_branch: str | None = Field(default=None, max_length=255)
    folder: str | None = Field(default=None, max_length=4096)
    packs_path: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def _source(self) -> CreatePackWorkspaceRequest:
        if self.kind == "git" and not (self.url or "").strip():
            raise ValueError("url is required for a git workspace")
        if self.kind == "folder" and not (self.folder or "").strip():
            raise ValueError("folder is required for a folder workspace")
        return self


class PackTreeVersion(StrictModel):
    version: str
    path: str
    status: str | None
    released: bool
    # Каталог выпущенной версии отличается от дайджеста в реестре: его правили мимо Студии.
    modified: bool


class PackTreeTemplate(StrictModel):
    id: str
    path: str
    name: dict[str, str] | None
    default_version: str | None
    versions: list[PackTreeVersion]


class PackTreePack(StrictModel):
    id: str
    path: str
    name: dict[str, str] | None
    templates: list[PackTreeTemplate]


class PackTreeFile(StrictModel):
    path: str
    is_dir: bool
    size: int
    read_only: ReadOnlyReason | None


class PackTreeResponse(StrictModel):
    workspace_id: str
    # Вершина базовой ветки, по реестрам которой отмечены выпущенные версии; у папки null.
    base_sha: str | None
    packs: list[PackTreePack]
    files: list[PackTreeFile]
    truncated: bool


class PackFileVersionResponse(StrictModel):
    path: str
    etag: str
    size: int


class PackYamlOp(StrictModel):
    """Точечная правка YAML: путь это ключи словарей (строки) и индексы списков (целые)."""

    op: YamlOpName
    path: list[StrictStr | StrictInt] = Field(max_length=64)
    value: Any = None
    # insert: место нового элемента; move: откуда.
    index: int | None = Field(default=None, ge=0)
    # move: куда (индекс в итоговом списке).
    to: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _fields(self) -> PackYamlOp:
        if self.op in {"insert", "move"} and self.index is None:
            raise ValueError(f"{self.op} needs index")
        if self.op == "move" and self.to is None:
            raise ValueError("move needs to")
        if self.op == "delete" and not self.path:
            raise ValueError("delete needs a path")
        return self


class PackYamlPatchRequest(StrictModel):
    ops: list[PackYamlOp] = Field(min_length=1, max_length=200)


class PackYamlPatchResponse(StrictModel):
    path: str
    etag: str
    size: int
    # Текст файла после правок: вкладка «Исходник» обновляется без второго запроса.
    content: str


class PackStudioGrantResponse(StrictModel):
    id: str
    subject: GrantSubjectName
    subject_id: str
    # Человек: имя и почта; группа: название и её организация.
    name: str | None
    email: str | None
    org_slug: str | None
    org_name: str | None
    granted_by: str | None
    created_at: datetime


class PackStudioAdminResponse(StrictModel):
    enabled: bool
    locked: bool
    grants: list[PackStudioGrantResponse]


class UpdatePackStudioAdminRequest(StrictModel):
    enabled: bool


class CreatePackStudioGrantRequest(StrictModel):
    user_id: str | None = Field(default=None, min_length=1, max_length=64)
    group_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _one(self) -> CreatePackStudioGrantRequest:
        if (self.user_id is None) == (self.group_id is None):
            raise ValueError("exactly one of user_id and group_id")
        return self
