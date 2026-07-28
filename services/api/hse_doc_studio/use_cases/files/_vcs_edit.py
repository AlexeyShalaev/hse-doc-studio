from __future__ import annotations

import asyncio

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import VcsCommitKind
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.core.vcs.protocols import (
    IVcsEditThrottle,
    IVcsFolderLocks,
    IVcsService,
)

logger = structlog.get_logger()


async def maybe_edit_commit(
    vcs: IVcsService,
    vcs_locks: IVcsFolderLocks,
    vcs_throttle: IVcsEditThrottle,
    project: Project,
    message: str,
) -> None:
    """Record an `edit` snapshot (detailed history) for a file mutation.

    Gated by the project's tracking_enabled setting and a per-folder throttle.
    Best-effort — a VCS failure must never affect the underlying file operation.
    Shared by put/delete/move use cases so they snapshot consistently.
    """
    try:
        if not vcs.is_available(project) or not vcs.is_initialized(project):
            return
        settings = VcsSettings.from_meta(project.meta)
        if not settings.tracking_enabled:
            return
        if not vcs_throttle.should_commit(project.folder):
            return
        async with vcs_locks.for_folder(project.folder):
            await asyncio.to_thread(
                lambda: vcs.commit(
                    project,
                    message=message,
                    kind=VcsCommitKind.edit,
                    include_pdf=settings.track_pdf,
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("vcs edit-commit failed", message=message, exc=str(exc))
