from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VcsCommitStatsResponse(BaseModel):
    files: int
    insertions: int
    deletions: int


class VcsRefResponse(BaseModel):
    name: str
    kind: str


class VcsCommitResponse(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    id: str
    short_id: str
    kind: str
    message: str
    author: str
    created_at: datetime
    parents: list[str]
    refs: list[VcsRefResponse]
    doc_id: str | None = None
    stats: VcsCommitStatsResponse | None = None


class VcsFileChangeResponse(BaseModel):
    path: str
    change: str
    old_path: str | None = None


class VcsCommitDetailResponse(BaseModel):
    commit: VcsCommitResponse
    files: list[VcsFileChangeResponse]


class VcsStatusResponse(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    available: bool
    initialized: bool
    current_branch: str | None
    head: str | None
    dirty: bool
    modified: int
    untracked: int
    staged: int
    last_snapshot_at: datetime | None
    store_path: str
    tracking_enabled: bool


class VcsFileDiffResponse(BaseModel):
    path: str
    change: str
    patch: str
    binary: bool


class VcsDiffResponse(BaseModel):
    from_id: str | None
    to_id: str | None
    files: list[VcsFileDiffResponse]
    truncated: bool


class VcsRestoreResponse(BaseModel):
    restored_from: str
    new_snapshot_id: str | None
    pre_snapshot_id: str | None
    files_changed: int


class VcsSettingsResponse(BaseModel):
    tracking_enabled: bool
    auto_commit_on_compile: bool
    track_pdf: bool


class VcsBranchResponse(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    name: str
    head: str
    is_current: bool
    is_protected: bool = False
    created_at: datetime | None = None


class VcsTagResponse(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    name: str
    commit_id: str
    kind: str
    message: str | None = None
    created_at: datetime | None = None


class VcsDeleteResponse(BaseModel):
    deleted: bool


class CreateBranchRequest(BaseModel):
    name: str
    from_commit: str | None = None
    switch: bool = True


class SwitchBranchRequest(BaseModel):
    name: str


class CreateTagRequest(BaseModel):
    name: str
    commit_id: str | None = None
    message: str | None = None
    kind: str = "tag"


class CreateSnapshotRequest(BaseModel):
    message: str
    doc_id: str | None = None


class RestoreRequest(BaseModel):
    commit_id: str
    paths: list[str] | None = None
    mode: str = "snapshot"
    confirm: bool = False


class UpdateVcsSettingsRequest(BaseModel):
    tracking_enabled: bool | None = None
    auto_commit_on_compile: bool | None = None
    track_pdf: bool | None = None
