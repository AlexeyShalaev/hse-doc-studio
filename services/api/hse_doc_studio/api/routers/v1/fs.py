from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query

from hse_doc_studio.api.schemas.fs import (
    BrowseEntryResponse,
    BrowseResponse,
    InspectedProjectResponse,
    InspectResponse,
)
from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.use_cases.fs.browse_filesystem import (
    BrowseFilesystemInput,
    BrowseFilesystemUC,
)
from hse_doc_studio.use_cases.fs.inspect_folder import (
    InspectFolderInput,
    InspectFolderUC,
)

router = APIRouter(route_class=DishkaRoute)


@router.get("/fs/browse", response_model=BrowseResponse)
async def browse_filesystem(
    uc: FromDishka[BrowseFilesystemUC],
    paths: FromDishka[PathMapping],
    path: str | None = Query(default=None),
) -> BrowseResponse:
    # Пользователь мыслит своими путями, а процесс живёт в контейнере: наружу
    # отдаём хостовые имена, внутрь принимаем и хостовые, и контейнерные.
    try:
        result = await uc.execute(BrowseFilesystemInput(path=paths.accept(path) if path else path))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return BrowseResponse(
        path=paths.display(str(result.path)),
        parent=paths.display(str(result.parent)) if result.parent is not None else None,
        is_root=result.is_root,
        entries=[
            BrowseEntryResponse(
                name=e.name,
                path=paths.display(str(e.path)),
                is_dir=e.is_dir,
                is_hidden=e.is_hidden,
            )
            for e in result.entries
        ],
    )


@router.get("/fs/inspect", response_model=InspectResponse)
async def inspect_folder(
    uc: FromDishka[InspectFolderUC],
    paths: FromDishka[PathMapping],
    path: str = Query(...),
) -> InspectResponse:
    try:
        result = await uc.execute(InspectFolderInput(path=paths.accept(path)))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    project_resp: InspectedProjectResponse | None = None
    if result.project is not None:
        p = result.project
        project_resp = InspectedProjectResponse(
            id=str(p.id),
            name=p.name,
            pack_id=p.lock.pack_id,
            template_id=p.lock.template_id,
            version=p.lock.version,
            engine=str(p.lock.engine),
        )

    return InspectResponse(
        path=paths.display(str(result.resolved_path)),
        exists=result.exists,
        is_dir=result.is_dir,
        has_project=result.has_project,
        project=project_resp,
    )
