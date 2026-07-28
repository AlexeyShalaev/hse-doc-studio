from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query

from hse_doc_studio.api.schemas.vcs import (
    CreateBranchRequest,
    CreateSnapshotRequest,
    CreateTagRequest,
    RestoreRequest,
    SwitchBranchRequest,
    UpdateVcsSettingsRequest,
    VcsBranchResponse,
    VcsCommitDetailResponse,
    VcsCommitResponse,
    VcsCommitStatsResponse,
    VcsDeleteResponse,
    VcsDiffResponse,
    VcsFileChangeResponse,
    VcsFileDiffResponse,
    VcsRefResponse,
    VcsRestoreResponse,
    VcsSettingsResponse,
    VcsStatusResponse,
    VcsTagResponse,
)
from hse_doc_studio.core.enums import VcsRestoreMode, VcsTagKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.vcs.entities import (
    VcsBranch,
    VcsCommit,
    VcsCommitDetail,
    VcsDiff,
    VcsRestoreResult,
    VcsSettings,
    VcsStatus,
    VcsTag,
)
from hse_doc_studio.core.vcs.errors import (
    VcsCommandError,
    VcsNotInitializedError,
    VcsUnavailableError,
)
from hse_doc_studio.use_cases.vcs.create_vcs_snapshot import (
    CreateVcsSnapshotInput,
    CreateVcsSnapshotUC,
)
from hse_doc_studio.use_cases.vcs.ensure_vcs import EnsureVcsInput, EnsureVcsUC
from hse_doc_studio.use_cases.vcs.get_vcs_commit import GetVcsCommitInput, GetVcsCommitUC
from hse_doc_studio.use_cases.vcs.get_vcs_diff import GetVcsDiffInput, GetVcsDiffUC
from hse_doc_studio.use_cases.vcs.get_vcs_settings import GetVcsSettingsInput, GetVcsSettingsUC
from hse_doc_studio.use_cases.vcs.get_vcs_status import GetVcsStatusInput, GetVcsStatusUC
from hse_doc_studio.use_cases.vcs.list_vcs_history import ListVcsHistoryInput, ListVcsHistoryUC
from hse_doc_studio.use_cases.vcs.restore_vcs import RestoreVcsInput, RestoreVcsUC
from hse_doc_studio.use_cases.vcs.update_vcs_settings import (
    UpdateVcsSettingsInput,
    UpdateVcsSettingsUC,
)
from hse_doc_studio.use_cases.vcs.vcs_branches import (
    CreateVcsBranchInput,
    CreateVcsBranchUC,
    DeleteVcsBranchInput,
    DeleteVcsBranchUC,
    ListVcsBranchesInput,
    ListVcsBranchesUC,
    SwitchVcsBranchInput,
    SwitchVcsBranchUC,
)
from hse_doc_studio.use_cases.vcs.vcs_tags import (
    CreateVcsTagInput,
    CreateVcsTagUC,
    DeleteVcsTagInput,
    DeleteVcsTagUC,
    ListVcsTagsInput,
    ListVcsTagsUC,
)

router = APIRouter(route_class=DishkaRoute)


# ── mappers ──────────────────────────────────────────────────────────────────
def _map_commit(commit: VcsCommit) -> VcsCommitResponse:
    return VcsCommitResponse(
        id=commit.id,
        short_id=commit.short_id,
        kind=commit.kind.value,
        message=commit.message,
        author=commit.author,
        created_at=commit.created_at,
        parents=list(commit.parents),
        refs=[VcsRefResponse(name=r.name, kind=r.kind) for r in commit.refs],
        doc_id=commit.doc_id,
        stats=(
            VcsCommitStatsResponse(
                files=commit.stats.files,
                insertions=commit.stats.insertions,
                deletions=commit.stats.deletions,
            )
            if commit.stats is not None
            else None
        ),
    )


def _map_detail(detail: VcsCommitDetail) -> VcsCommitDetailResponse:
    return VcsCommitDetailResponse(
        commit=_map_commit(detail.commit),
        files=[VcsFileChangeResponse(path=f.path, change=f.change.value, old_path=f.old_path) for f in detail.files],
    )


def _map_status(status: VcsStatus) -> VcsStatusResponse:
    return VcsStatusResponse(
        available=status.available,
        initialized=status.initialized,
        current_branch=status.current_branch,
        head=status.head,
        dirty=status.dirty,
        modified=status.modified,
        untracked=status.untracked,
        staged=status.staged,
        last_snapshot_at=status.last_snapshot_at,
        store_path=status.store_path,
        tracking_enabled=status.tracking_enabled,
    )


def _map_diff(diff: VcsDiff) -> VcsDiffResponse:
    return VcsDiffResponse(
        from_id=diff.from_id,
        to_id=diff.to_id,
        files=[
            VcsFileDiffResponse(path=f.path, change=f.change.value, patch=f.patch, binary=f.binary) for f in diff.files
        ],
        truncated=diff.truncated,
    )


def _map_restore(result: VcsRestoreResult) -> VcsRestoreResponse:
    return VcsRestoreResponse(
        restored_from=result.restored_from,
        new_snapshot_id=result.new_snapshot_id,
        pre_snapshot_id=result.pre_snapshot_id,
        files_changed=result.files_changed,
    )


def _map_settings(settings: VcsSettings) -> VcsSettingsResponse:
    return VcsSettingsResponse(
        tracking_enabled=settings.tracking_enabled,
        auto_commit_on_compile=settings.auto_commit_on_compile,
        track_pdf=settings.track_pdf,
    )


def _map_branch(branch: VcsBranch) -> VcsBranchResponse:
    return VcsBranchResponse(
        name=branch.name,
        head=branch.head,
        is_current=branch.is_current,
        is_protected=branch.is_protected,
        created_at=branch.created_at,
    )


def _map_tag(tag: VcsTag) -> VcsTagResponse:
    return VcsTagResponse(
        name=tag.name,
        commit_id=tag.commit_id,
        kind=tag.kind.value,
        message=tag.message,
        created_at=tag.created_at,
    )


# ── reads ────────────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/vcs/status", response_model=VcsStatusResponse)
async def get_vcs_status(project_id: UUID, uc: FromDishka[GetVcsStatusUC]) -> VcsStatusResponse:
    try:
        result = await uc.execute(GetVcsStatusInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_status(result.status)


@router.get("/projects/{project_id}/vcs/history", response_model=list[VcsCommitResponse])
async def list_vcs_history(
    project_id: UUID,
    uc: FromDishka[ListVcsHistoryUC],
    doc_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[VcsCommitResponse]:
    try:
        result = await uc.execute(ListVcsHistoryInput(project_id=project_id, doc_id=doc_id, limit=limit, offset=offset))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_map_commit(c) for c in result.commits]


@router.get("/projects/{project_id}/vcs/commits/{commit_id}", response_model=VcsCommitDetailResponse)
async def get_vcs_commit(project_id: UUID, commit_id: str, uc: FromDishka[GetVcsCommitUC]) -> VcsCommitDetailResponse:
    try:
        result = await uc.execute(GetVcsCommitInput(project_id=project_id, commit_id=commit_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VcsNotInitializedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except VcsCommandError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_detail(result.detail)


@router.get("/projects/{project_id}/vcs/diff", response_model=VcsDiffResponse)
async def get_vcs_diff(
    project_id: UUID,
    uc: FromDishka[GetVcsDiffUC],
    from_id: str | None = Query(default=None),
    to_id: str | None = Query(default=None),
    path: str | None = Query(default=None),
) -> VcsDiffResponse:
    try:
        result = await uc.execute(GetVcsDiffInput(project_id=project_id, from_id=from_id, to_id=to_id, path=path))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_diff(result.diff)


@router.get("/projects/{project_id}/vcs/settings", response_model=VcsSettingsResponse)
async def get_vcs_settings(project_id: UUID, uc: FromDishka[GetVcsSettingsUC]) -> VcsSettingsResponse:
    try:
        result = await uc.execute(GetVcsSettingsInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_settings(result.settings)


# ── writes ───────────────────────────────────────────────────────────────────
@router.post("/projects/{project_id}/vcs/init", response_model=VcsStatusResponse)
async def init_vcs(
    project_id: UUID,
    ensure_uc: FromDishka[EnsureVcsUC],
    status_uc: FromDishka[GetVcsStatusUC],
) -> VcsStatusResponse:
    try:
        await ensure_uc.execute(EnsureVcsInput(project_id=project_id))
        result = await status_uc.execute(GetVcsStatusInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VcsUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _map_status(result.status)


@router.post("/projects/{project_id}/vcs/snapshots", response_model=VcsCommitResponse | None)
async def create_vcs_snapshot(
    project_id: UUID, body: CreateSnapshotRequest, uc: FromDishka[CreateVcsSnapshotUC]
) -> VcsCommitResponse | None:
    try:
        result = await uc.execute(
            CreateVcsSnapshotInput(project_id=project_id, message=body.message, doc_id=body.doc_id)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VcsUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except VcsCommandError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_commit(result.commit) if result.commit is not None else None


@router.post("/projects/{project_id}/vcs/restore", response_model=VcsRestoreResponse)
async def restore_vcs(project_id: UUID, body: RestoreRequest, uc: FromDishka[RestoreVcsUC]) -> VcsRestoreResponse:
    try:
        mode = VcsRestoreMode(body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown restore mode: {body.mode}") from exc
    try:
        result = await uc.execute(
            RestoreVcsInput(
                project_id=project_id,
                commit_id=body.commit_id,
                paths=body.paths,
                mode=mode,
                confirm=body.confirm,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # e.g. "hard restore requires confirm" — a genuine client/validation error.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except VcsUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (VcsNotInitializedError, VcsCommandError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_restore(result.result)


@router.patch("/projects/{project_id}/vcs/settings", response_model=VcsSettingsResponse)
async def update_vcs_settings(
    project_id: UUID, body: UpdateVcsSettingsRequest, uc: FromDishka[UpdateVcsSettingsUC]
) -> VcsSettingsResponse:
    try:
        result = await uc.execute(
            UpdateVcsSettingsInput(
                project_id=project_id,
                tracking_enabled=body.tracking_enabled,
                auto_commit_on_compile=body.auto_commit_on_compile,
                track_pdf=body.track_pdf,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_settings(result.settings)


# ── branches ─────────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/vcs/branches", response_model=list[VcsBranchResponse])
async def list_vcs_branches(project_id: UUID, uc: FromDishka[ListVcsBranchesUC]) -> list[VcsBranchResponse]:
    try:
        result = await uc.execute(ListVcsBranchesInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_map_branch(b) for b in result.branches]


@router.post("/projects/{project_id}/vcs/branches", response_model=VcsBranchResponse)
async def create_vcs_branch(
    project_id: UUID, body: CreateBranchRequest, uc: FromDishka[CreateVcsBranchUC]
) -> VcsBranchResponse:
    try:
        result = await uc.execute(
            CreateVcsBranchInput(
                project_id=project_id,
                name=body.name,
                from_commit=body.from_commit,
                switch=body.switch,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VcsUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (VcsNotInitializedError, VcsCommandError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_branch(result.branch)


@router.post("/projects/{project_id}/vcs/branches/switch", response_model=VcsStatusResponse)
async def switch_vcs_branch(
    project_id: UUID, body: SwitchBranchRequest, uc: FromDishka[SwitchVcsBranchUC]
) -> VcsStatusResponse:
    try:
        result = await uc.execute(SwitchVcsBranchInput(project_id=project_id, name=body.name))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VcsUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (VcsNotInitializedError, VcsCommandError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_status(result.status)


@router.delete("/projects/{project_id}/vcs/branches", response_model=VcsDeleteResponse)
async def delete_vcs_branch(
    project_id: UUID, uc: FromDishka[DeleteVcsBranchUC], name: str = Query(...)
) -> VcsDeleteResponse:
    try:
        result = await uc.execute(DeleteVcsBranchInput(project_id=project_id, name=name))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # e.g. "current/main branch cannot be deleted" — a genuine validation error.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except VcsUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (VcsNotInitializedError, VcsCommandError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return VcsDeleteResponse(deleted=result.deleted)


# ── tags ─────────────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/vcs/tags", response_model=list[VcsTagResponse])
async def list_vcs_tags(project_id: UUID, uc: FromDishka[ListVcsTagsUC]) -> list[VcsTagResponse]:
    try:
        result = await uc.execute(ListVcsTagsInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_map_tag(t) for t in result.tags]


@router.post("/projects/{project_id}/vcs/tags", response_model=VcsTagResponse)
async def create_vcs_tag(project_id: UUID, body: CreateTagRequest, uc: FromDishka[CreateVcsTagUC]) -> VcsTagResponse:
    try:
        kind = VcsTagKind(body.kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown tag kind: {body.kind}") from exc
    try:
        result = await uc.execute(
            CreateVcsTagInput(
                project_id=project_id,
                name=body.name,
                commit_id=body.commit_id,
                message=body.message,
                kind=kind,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VcsUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (VcsNotInitializedError, VcsCommandError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_tag(result.tag)


@router.delete("/projects/{project_id}/vcs/tags", response_model=VcsDeleteResponse)
async def delete_vcs_tag(project_id: UUID, uc: FromDishka[DeleteVcsTagUC], name: str = Query(...)) -> VcsDeleteResponse:
    try:
        result = await uc.execute(DeleteVcsTagInput(project_id=project_id, name=name))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VcsUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (VcsNotInitializedError, VcsCommandError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return VcsDeleteResponse(deleted=result.deleted)
