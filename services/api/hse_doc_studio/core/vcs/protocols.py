from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import VcsCommitKind, VcsRestoreMode, VcsTagKind
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


class IVcsService(Protocol):
    """ProjectVCS over an isolated git store at <project>/.hse-studio/git/.

    The store is keyed by the project's on-disk folder (work-tree = project root),
    so it travels with a copied/moved folder and never collides with the user's
    own git. Methods take the domain `Project`; path resolution is an infra detail.
    """

    def is_available(self, project: Project) -> bool: ...
    def is_initialized(self, project: Project) -> bool: ...
    def init(self, project: Project, ignore: Sequence[str]) -> None: ...
    def write_ignore(self, project: Project, ignore: Sequence[str]) -> None: ...
    def status(self, project: Project, settings: VcsSettings) -> VcsStatus: ...
    def commit(
        self,
        project: Project,
        *,
        message: str,
        kind: VcsCommitKind,
        paths: Sequence[str] | None = None,
        include_pdf: bool = False,
        allow_empty: bool = False,
    ) -> VcsCommit | None: ...
    def log(
        self,
        project: Project,
        *,
        doc_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[VcsCommit]: ...
    def commit_detail(self, project: Project, commit_id: str) -> VcsCommitDetail: ...
    def diff(
        self,
        project: Project,
        *,
        from_id: str | None = None,
        to_id: str | None = None,
        path: str | None = None,
        max_bytes: int | None = None,
    ) -> VcsDiff: ...
    def restore(
        self,
        project: Project,
        *,
        commit_id: str,
        paths: Sequence[str] | None = None,
        mode: VcsRestoreMode = VcsRestoreMode.snapshot,
        include_pdf: bool = False,
    ) -> VcsRestoreResult: ...
    def list_branches(self, project: Project) -> list[VcsBranch]: ...
    def create_branch(
        self,
        project: Project,
        settings: VcsSettings,
        *,
        name: str,
        from_commit: str | None = None,
        switch: bool = True,
    ) -> VcsBranch: ...
    def switch_branch(
        self,
        project: Project,
        settings: VcsSettings,
        *,
        name: str,
        autosnapshot: bool = True,
    ) -> VcsStatus: ...
    def delete_branch(self, project: Project, *, name: str) -> None: ...
    def list_tags(self, project: Project) -> list[VcsTag]: ...
    def create_tag(
        self,
        project: Project,
        *,
        name: str,
        commit_id: str | None = None,
        message: str | None = None,
        kind: VcsTagKind = VcsTagKind.tag,
    ) -> VcsTag: ...
    def delete_tag(self, project: Project, *, name: str) -> None: ...
    def destroy(self, project: Project) -> None: ...


class IVcsFolderLocks(Protocol):
    """Hands out a per-project-folder lock that serializes VCS write operations
    (and the compile-success auto-commit) so concurrent git writes can't corrupt
    the index. Read-only operations never lock."""

    def for_folder(self, folder: Path) -> asyncio.Lock: ...


class IVcsEditThrottle(Protocol):
    """Per-folder throttle for edit-commits: returns True at most once per
    interval per folder. Edits inside the window are folded into the next commit
    (files on disk are never lost), keeping the timeline from spamming on every
    keystroke-save."""

    def should_commit(self, folder: Path) -> bool: ...
