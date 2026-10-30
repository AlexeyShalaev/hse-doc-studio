from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from hse_doc_studio.api.schemas.common import AuthorSchema, LockResponse, PersonSchema
from hse_doc_studio.api.schemas.session import ProjectOwner, ProjectRoleName


class ProjectListItemResponse(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    id: str
    name: str
    folder: str
    lock: LockResponse
    kind: str
    staffing: str
    updated_at: datetime
    pinned: bool
    archived: bool


class FolderRootResponse(BaseModel):
    path: str
    count: int


class AuthorSuggestionResponse(BaseModel):
    name: str
    group: str


class ProjectSuggestionsResponse(BaseModel):
    # Create-wizard hints aggregated from existing projects: parent folders
    # (ranked by project count) + distinct authors (ranked by frequency).
    folder_roots: list[FolderRootResponse]
    authors: list[AuthorSuggestionResponse]


class ChecksOverrideSchema(BaseModel):
    disabled_categories: list[str] = []
    disabled: list[str] = []
    enabled: list[str] = []
    severity_override: dict[str, str] = {}


class ProjectAccessResponse(BaseModel):
    # Режим: full, read_only или files_only (core.project_access).
    mode: str = "full"
    reasons: list[str] = []
    required_studio: str | None = None


class ProjectStorageResponse(BaseModel):
    # Только на сервере: занятое место проекта и предупреждение с доли предела (по умолчанию 80%).
    used_bytes: int
    limit_bytes: int
    warning: bool
    exceeded: bool
    measured_at: datetime


class ProjectDetailResponse(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    id: str
    name: str
    folder: str
    lock: LockResponse
    kind: str
    staffing: str
    lang: str
    authors: list[AuthorSchema]
    supervisor: PersonSchema | None
    co_supervisor: PersonSchema | None
    academic_supervisor: PersonSchema | None
    meta: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    shared_enabled: bool = True
    pinned: bool
    archived: bool
    checks_override: ChecksOverrideSchema
    # Что эта Студия может делать с проектом; заполняется в GET /projects/{id}.
    access: ProjectAccessResponse = ProjectAccessResponse()
    # Заполняется в GET /projects/{id} на сервере; в локальном режиме None.
    storage: ProjectStorageResponse | None = None
    # Только на сервере (GET /projects/{id}): чей проект и роль смотрящего, как в списке проектов.
    owner: ProjectOwner | None = None
    my_role: ProjectRoleName | None = None


class NdaStatusResponse(BaseModel):
    # available: the template declares an NDA file group at all.
    # present:   the project currently has NDA files on disk.
    # files:     their paths relative to the NDA dir (for display).
    available: bool
    present: bool
    files: list[str] = []


class CreateProjectRequest(BaseModel):
    name: str
    # В локальном режиме обязательна; на общем сервере папку выбирает сервер, и поле отклоняется.
    folder: str | None = None
    # Из контракта серверного режима (CreateServerProjectRequest): организаций пока нет, непустое значение отклоняется.
    owner_org_slug: str | None = None
    pack_id: str
    template_id: str
    version: str
    engine: str = "xelatex"
    kind: str = "research"
    staffing: str = "solo"
    lang: str = "ru"
    authors: list[AuthorSchema] = []
    supervisor: PersonSchema | None = None
    co_supervisor: PersonSchema | None = None
    academic_supervisor: PersonSchema | None = None
    meta: dict[str, Any] = {}
    pres_variant: str | None = None
    # Team mode: вести ли общие (shared) документы в этом проекте.
    shared_enabled: bool = True


class ConnectProjectRequest(BaseModel):
    folder: str


class UpdateTeamSetRequest(BaseModel):
    """Довключение/выключение комплекта в командном проекте.

    `author_slug` — чей комплект; None — общие (shared) документы. Выключение
    не удаляет файлы: комплект лишь дерегистрируется (восстановимо + VCS).
    """

    author_slug: str | None = None
    enabled: bool


class MoveProjectRequest(BaseModel):
    # Destination folder for the project (must be empty or not yet exist).
    folder: str


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    lang: str | None = None
    meta: dict[str, Any] | None = None
    authors: list[AuthorSchema] | None = None
    supervisor: PersonSchema | None = None
    co_supervisor: PersonSchema | None = None
    academic_supervisor: PersonSchema | None = None
    # Team mode: включение/выключение общих документов идёт через отдельный
    # эндпоинт наборов (см. team router) — здесь флаг только читается.
    pinned: bool | None = None
    archived: bool | None = None
    checks_override: ChecksOverrideSchema | None = None
