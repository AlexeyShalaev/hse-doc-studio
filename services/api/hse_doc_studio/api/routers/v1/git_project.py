from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException

from hse_doc_studio.api.schemas.git_sync import GitContentsResponse, GitLargestFile, GitOverLimitFile
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.git_sync.contents import GetGitContentsInput, GetGitContentsUC

router = APIRouter(route_class=DishkaRoute)


@router.get("/projects/{project_id}/git/contents", response_model=GitContentsResponse)
async def get_git_contents(project_id: UUID, uc: FromDishka[GetGitContentsUC]) -> GitContentsResponse:
    """Что уйдёт в удалённый репозиторий: по локальной истории, без сети."""
    try:
        contents = await uc.execute(GetGitContentsInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return GitContentsResponse(
        files=contents.files,
        bytes=contents.bytes,
        commits=contents.commits,
        bot_authored_commits=contents.bot_authored_commits,
        signatures=contents.signatures,
        nda_files=contents.nda_files,
        pdf_tracked=contents.pdf_tracked,
        largest=[GitLargestFile(path=f.path, bytes=f.bytes) for f in contents.largest],
        over_limit=[
            GitOverLimitFile(path=f.path, bytes=f.bytes, limit=contents.limit_bytes) for f in contents.over_limit
        ],
        lfs_pointers=contents.lfs_pointers,
    )
