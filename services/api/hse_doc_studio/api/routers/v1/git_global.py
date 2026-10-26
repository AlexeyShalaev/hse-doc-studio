from __future__ import annotations

from pathlib import Path

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query

from hse_doc_studio.api.schemas.git_sync import CloneDefaultsResponse, SharedFolderResponse
from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.use_cases.git_sync.clone_defaults import CloneDefaultsInput, GetCloneDefaultsUC
from hse_doc_studio.use_cases.git_sync.shared_folder import DetectSharedFolderInput, DetectSharedFolderUC

router = APIRouter(route_class=DishkaRoute)


@router.get("/git/shared-folder", response_model=SharedFolderResponse)
async def get_shared_folder(
    uc: FromDishka[DetectSharedFolderUC],
    paths: FromDishka[PathMapping],
    folder: str = Query(..., min_length=1, max_length=4096),
) -> SharedFolderResponse:
    """Лежит ли папка в каталоге, который синхронизирует служба: только предупреждение."""
    if "\0" in folder:
        raise HTTPException(status_code=400, detail="invalid folder")
    info = await uc.execute(DetectSharedFolderInput(folder=Path(paths.accept(folder))))
    if info is None:
        return SharedFolderResponse(detected=False, provider=None, root=None, evidence=[])
    return SharedFolderResponse(
        detected=True, provider=info.provider.value, root=info.root, evidence=list(info.evidence)
    )


@router.get("/git/clone/defaults", response_model=CloneDefaultsResponse)
async def get_clone_defaults(
    uc: FromDishka[GetCloneDefaultsUC],
    paths: FromDishka[PathMapping],
    name: str | None = Query(default=None, max_length=256),
) -> CloneDefaultsResponse:
    folder = await uc.execute(CloneDefaultsInput(name=name))
    return CloneDefaultsResponse(folder=paths.display(str(folder)))
