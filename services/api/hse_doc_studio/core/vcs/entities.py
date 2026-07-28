from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from hse_doc_studio.core.enums import VcsChange, VcsCommitKind, VcsTagKind


@dataclass(frozen=True)
class VcsCommitStats:
    files: int
    insertions: int
    deletions: int


@dataclass(frozen=True)
class VcsRef:
    name: str
    kind: str  # "branch" | "tag" | "head"


@dataclass(frozen=True)
class VcsCommit:
    id: str
    short_id: str
    kind: VcsCommitKind
    message: str
    author: str
    created_at: datetime
    parents: tuple[str, ...]
    refs: tuple[VcsRef, ...]
    doc_id: str | None = None
    stats: VcsCommitStats | None = None


@dataclass(frozen=True)
class VcsBranch:
    name: str
    head: str
    is_current: bool
    # The default/protected branch (e.g. master) — deletion is refused.
    is_protected: bool = False
    created_at: datetime | None = None


@dataclass(frozen=True)
class VcsTag:
    name: str
    commit_id: str
    kind: VcsTagKind
    message: str | None
    created_at: datetime | None


@dataclass(frozen=True)
class VcsFileChange:
    path: str
    change: VcsChange
    old_path: str | None = None


@dataclass(frozen=True)
class VcsCommitDetail:
    commit: VcsCommit
    files: tuple[VcsFileChange, ...]


@dataclass(frozen=True)
class VcsStatus:
    # `available` = the project folder is reachable by the backend (same condition
    # a build needs). `initialized` = a VCS store exists. When unavailable, all
    # other fields are zero/None and nothing is created.
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


@dataclass(frozen=True)
class VcsFileDiff:
    path: str
    change: VcsChange
    patch: str
    binary: bool


@dataclass(frozen=True)
class VcsDiff:
    from_id: str | None
    to_id: str | None
    files: tuple[VcsFileDiff, ...]
    truncated: bool


@dataclass(frozen=True)
class VcsRestoreResult:
    # `new_snapshot_id` is the restore commit (the Undo anchor). `pre_snapshot_id`
    # is the auto-snapshot of work-in-progress taken before the restore (None when
    # the tree was already clean).
    restored_from: str
    new_snapshot_id: str | None
    pre_snapshot_id: str | None
    files_changed: int


@dataclass
class VcsSettings:
    # Persisted in project.meta["vcs"] (NOT in git), so it round-trips with the
    # rest of project.json. `track_pdf` opt-in keeps compiled PDFs out of history
    # by default (avoids store bloat).
    tracking_enabled: bool = True
    auto_commit_on_compile: bool = True
    track_pdf: bool = False

    @classmethod
    def from_meta(cls, meta: dict[str, Any]) -> VcsSettings:
        raw = meta.get("vcs") or {}
        return cls(
            tracking_enabled=bool(raw.get("tracking_enabled", True)),
            auto_commit_on_compile=bool(raw.get("auto_commit_on_compile", True)),
            track_pdf=bool(raw.get("track_pdf", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tracking_enabled": self.tracking_enabled,
            "auto_commit_on_compile": self.auto_commit_on_compile,
            "track_pdf": self.track_pdf,
        }
