from __future__ import annotations

from pathlib import Path
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException

from hse_doc_studio.api.schemas.common import AuthorSchema, LockResponse, PersonSchema
from hse_doc_studio.api.schemas.project import (
    AuthorSuggestionResponse,
    ChecksOverrideSchema,
    ConnectProjectRequest,
    CreateProjectRequest,
    FolderRootResponse,
    MoveProjectRequest,
    NdaStatusResponse,
    ProjectDetailResponse,
    ProjectListItemResponse,
    ProjectSuggestionsResponse,
    UpdateProjectRequest,
    UpdateTeamSetRequest,
)
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import CheckSeverity, EngineType, Lang, PersonRole, ProjectKind, ProjectStaffing
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.core.value_objects import Author, ChecksOverride, Person
from hse_doc_studio.use_cases.projects.connect_project import (
    ConnectProjectInput,
    ConnectProjectUC,
)
from hse_doc_studio.use_cases.projects.create_project import (
    CreateProjectInput,
    CreateProjectUC,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.projects.get_project_suggestions import (
    GetProjectSuggestionsUC,
)
from hse_doc_studio.use_cases.projects.list_projects import ListProjectsUC
from hse_doc_studio.use_cases.projects.manage_nda import (
    DeleteNdaFilesUC,
    GetNdaStatusUC,
    InstantiateNdaUC,
    NdaInput,
    NdaStatusOutput,
)
from hse_doc_studio.use_cases.projects.move_project import MoveProjectInput, MoveProjectUC
from hse_doc_studio.use_cases.projects.unregister_project import (
    UnregisterProjectInput,
    UnregisterProjectUC,
)
from hse_doc_studio.use_cases.projects.update_project import (
    _MISSING,
    UpdateProjectInput,
    UpdateProjectUC,
)
from hse_doc_studio.use_cases.projects.update_team_set import (
    UpdateTeamSetInput,
    UpdateTeamSetUC,
)

router = APIRouter(route_class=DishkaRoute)


def _map_lock(project: Project) -> LockResponse:
    return LockResponse(
        pack_id=project.lock.pack_id,
        template_id=project.lock.template_id,
        version=project.lock.version,
        engine=str(project.lock.engine),
    )


def _map_author(author: Author) -> AuthorSchema:
    return AuthorSchema(
        name=author.name,
        group=author.group,
        email=author.email,
        slug=author.slug,
        topic=author.topic,
        managed=author.managed,
        meta=dict(author.meta),
    )


def _map_person(person: Person | None) -> PersonSchema | None:
    if person is None:
        return None
    return PersonSchema(
        name=person.name,
        role=str(person.role),
        title=person.title,
        degree=person.degree,
    )


def _map_project_list_item(project: Project, paths: PathMapping) -> ProjectListItemResponse:
    return ProjectListItemResponse(
        id=str(project.id),
        name=project.name,
        folder=paths.display(str(project.folder)),
        lock=_map_lock(project),
        kind=str(project.kind),
        staffing=str(project.staffing),
        updated_at=project.updated_at,
        pinned=project.pinned,
        archived=project.archived,
    )


def _map_checks_override(co: ChecksOverride) -> ChecksOverrideSchema:
    return ChecksOverrideSchema(
        disabled_categories=list(co.disabled_categories),
        disabled=list(co.disabled),
        enabled=list(co.enabled),
        severity_override={k: str(v) for k, v in co.severity_override.items()},
    )


def _parse_checks_override(schema: ChecksOverrideSchema) -> ChecksOverride:
    return ChecksOverride(
        disabled_categories=tuple(schema.disabled_categories),
        disabled=tuple(schema.disabled),
        enabled=tuple(schema.enabled),
        severity_override={k: CheckSeverity(v) for k, v in schema.severity_override.items()},
    )


def _map_project_detail(project: Project, paths: PathMapping) -> ProjectDetailResponse:
    return ProjectDetailResponse(
        id=str(project.id),
        name=project.name,
        folder=paths.display(str(project.folder)),
        lock=_map_lock(project),
        kind=str(project.kind),
        staffing=str(project.staffing),
        lang=str(project.lang),
        authors=[_map_author(a) for a in project.authors],
        supervisor=_map_person(project.supervisor),
        co_supervisor=_map_person(project.co_supervisor),
        academic_supervisor=_map_person(project.academic_supervisor),
        meta=project.meta,
        created_at=project.created_at,
        updated_at=project.updated_at,
        shared_enabled=project.shared_enabled,
        pinned=project.pinned,
        archived=project.archived,
        checks_override=_map_checks_override(project.checks_override),
    )


def _parse_author(schema: AuthorSchema) -> Author:
    return Author(
        name=schema.name,
        group=schema.group,
        email=schema.email,
        slug=schema.slug,
        topic=schema.topic,
        managed=schema.managed,
        meta=dict(schema.meta),
    )


def _parse_person(schema: PersonSchema | None) -> Person | None:
    if schema is None:
        return None
    return Person(
        name=schema.name,
        role=PersonRole(schema.role),
        title=schema.title,
        degree=schema.degree,
    )


@router.get("/projects", response_model=list[ProjectListItemResponse])
async def list_projects(
    uc: FromDishka[ListProjectsUC],
    paths: FromDishka[PathMapping],
) -> list[ProjectListItemResponse]:
    result = await uc.execute()
    return [_map_project_list_item(p, paths) for p in result.projects]


@router.get("/projects/suggestions", response_model=ProjectSuggestionsResponse)
async def project_suggestions(
    uc: FromDishka[GetProjectSuggestionsUC],
    paths: FromDishka[PathMapping],
) -> ProjectSuggestionsResponse:
    """Create-wizard hints from existing projects: parent folders (ranked by
    project count) + distinct authors (ranked by frequency). Static path — must
    stay ABOVE `/projects/{project_id}` so it isn't captured as an id."""
    result = await uc.execute()
    return ProjectSuggestionsResponse(
        folder_roots=[FolderRootResponse(path=paths.display(r.path), count=r.count) for r in result.folder_roots],
        authors=[AuthorSuggestionResponse(name=a.name, group=a.group) for a in result.authors],
    )


@router.post("/projects", response_model=ProjectDetailResponse, status_code=201)
async def create_project(
    body: CreateProjectRequest,
    uc: FromDishka[CreateProjectUC],
    paths: FromDishka[PathMapping],
) -> ProjectDetailResponse:
    try:
        inp = CreateProjectInput(
            folder=Path(paths.accept(body.folder)),
            pack_id=body.pack_id,
            template_id=body.template_id,
            version=body.version,
            name=body.name,
            kind=ProjectKind(body.kind),
            staffing=ProjectStaffing(body.staffing),
            lang=Lang(body.lang),
            engine=EngineType(body.engine),
            authors=[_parse_author(a) for a in body.authors],
            supervisor=_parse_person(body.supervisor),
            co_supervisor=_parse_person(body.co_supervisor),
            academic_supervisor=_parse_person(body.academic_supervisor),
            meta=body.meta,
            pres_variant=body.pres_variant,
            shared_enabled=body.shared_enabled,
        )
        result = await uc.execute(inp)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_project_detail(result.project, paths)


@router.post("/projects/connect", response_model=ProjectDetailResponse, status_code=201)
async def connect_project(
    body: ConnectProjectRequest,
    uc: FromDishka[ConnectProjectUC],
    paths: FromDishka[PathMapping],
) -> ProjectDetailResponse:
    try:
        result = await uc.execute(ConnectProjectInput(folder=Path(paths.accept(body.folder))))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_project_detail(result.project, paths)


@router.get("/projects/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: UUID,
    uc: FromDishka[GetProjectUC],
    paths: FromDishka[PathMapping],
) -> ProjectDetailResponse:
    try:
        result = await uc.execute(GetProjectInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_project_detail(result.project, paths)


@router.patch("/projects/{project_id}", response_model=ProjectDetailResponse)
async def update_project(
    project_id: UUID,
    body: UpdateProjectRequest,
    uc: FromDishka[UpdateProjectUC],
    paths: FromDishka[PathMapping],
) -> ProjectDetailResponse:
    # Use sentinel so that omitted person fields don't clear existing values
    supervisor = _parse_person(body.supervisor) if "supervisor" in body.model_fields_set else _MISSING
    co_supervisor = _parse_person(body.co_supervisor) if "co_supervisor" in body.model_fields_set else _MISSING
    academic_supervisor = (
        _parse_person(body.academic_supervisor) if "academic_supervisor" in body.model_fields_set else _MISSING
    )
    try:
        inp = UpdateProjectInput(
            project_id=project_id,
            name=body.name,
            lang=Lang(body.lang) if body.lang is not None else None,
            meta=body.meta,
            authors=[_parse_author(a) for a in body.authors] if body.authors is not None else None,
            supervisor=supervisor,  # type: ignore[arg-type]
            co_supervisor=co_supervisor,  # type: ignore[arg-type]
            academic_supervisor=academic_supervisor,  # type: ignore[arg-type]
            pinned=body.pinned,
            archived=body.archived,
            checks_override=_parse_checks_override(body.checks_override) if body.checks_override is not None else None,
        )
        result = await uc.execute(inp)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_project_detail(result.project, paths)


@router.post("/projects/{project_id}/move", response_model=ProjectDetailResponse)
async def move_project(
    project_id: UUID,
    body: MoveProjectRequest,
    uc: FromDishka[MoveProjectUC],
    paths: FromDishka[PathMapping],
) -> ProjectDetailResponse:
    try:
        result = await uc.execute(MoveProjectInput(project_id=project_id, new_folder=Path(paths.accept(body.folder))))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_project_detail(result.project, paths)


@router.delete("/projects/{project_id}", status_code=204, response_model=None)
async def unregister_project(
    project_id: UUID,
    uc: FromDishka[UnregisterProjectUC],
) -> None:
    try:
        await uc.execute(UnregisterProjectInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{project_id}/team/sets", response_model=ProjectDetailResponse)
async def update_team_set(
    project_id: UUID,
    body: UpdateTeamSetRequest,
    uc: FromDishka[UpdateTeamSetUC],
    paths: FromDishka[PathMapping],
) -> ProjectDetailResponse:
    """Довключить/выключить комплект (папку автора или shared) в team-проекте."""
    try:
        result = await uc.execute(
            UpdateTeamSetInput(project_id=project_id, author_slug=body.author_slug, enabled=body.enabled)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_project_detail(result.project, paths)


def _map_nda(out: NdaStatusOutput) -> NdaStatusResponse:
    return NdaStatusResponse(available=out.available, present=out.present, files=out.files)


@router.get("/projects/{project_id}/nda", response_model=NdaStatusResponse)
async def get_nda_status(
    project_id: UUID,
    uc: FromDishka[GetNdaStatusUC],
) -> NdaStatusResponse:
    try:
        out = await uc.execute(NdaInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_nda(out)


@router.post("/projects/{project_id}/nda/files", response_model=NdaStatusResponse)
async def instantiate_nda_files(
    project_id: UUID,
    uc: FromDishka[InstantiateNdaUC],
) -> NdaStatusResponse:
    """Materialise the template's NDA files into the project (after meta.nda is set)."""
    try:
        out = await uc.execute(NdaInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_nda(out)


@router.delete("/projects/{project_id}/nda/files", response_model=NdaStatusResponse)
async def delete_nda_files(
    project_id: UUID,
    uc: FromDishka[DeleteNdaFilesUC],
) -> NdaStatusResponse:
    """Delete the project's NDA folder (when the student opts to discard on disable)."""
    try:
        out = await uc.execute(NdaInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_nda(out)
