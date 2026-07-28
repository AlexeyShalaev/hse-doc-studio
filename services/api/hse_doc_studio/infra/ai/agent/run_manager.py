from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog

logger = structlog.get_logger()


@dataclass
class _Slot:
    task: asyncio.Task[None]
    session_id: UUID
    project_folder: Path


class AgentRunManager:
    """In-memory registry of in-flight agent-turn tasks (twin of CompileRunner).

    A turn runs as a background task that must outlive the request that started
    it, so this is an app-scoped singleton. It also enforces one in-flight turn
    per session (a per-session lock + an active-run lookup), which keeps the
    append-only transcript single-writer and the replayed model history coherent.
    Cancellation is a plain task.cancel() — unlike compile there is no subprocess.
    """

    def __init__(self) -> None:
        self._slots: dict[UUID, _Slot] = {}
        self._session_locks: dict[UUID, asyncio.Lock] = {}

    def session_lock(self, session_id: UUID) -> asyncio.Lock:
        return self._session_locks.setdefault(session_id, asyncio.Lock())

    def register(self, run_id: UUID, task: asyncio.Task[None], session_id: UUID, project_folder: Path) -> None:
        self._slots[run_id] = _Slot(task=task, session_id=session_id, project_folder=project_folder)

    def unregister(self, run_id: UUID) -> None:
        self._slots.pop(run_id, None)

    def is_running(self, run_id: UUID) -> bool:
        slot = self._slots.get(run_id)
        return slot is not None and not slot.task.done()

    def active_run_for_session(self, session_id: UUID) -> UUID | None:
        for run_id, slot in self._slots.items():
            if slot.session_id == session_id and not slot.task.done():
                return run_id
        return None

    def has_any_active(self) -> bool:
        """True if any agent turn is in flight (twin of CompileRunner.has_any_active).

        An automatic update would kill the turn mid-answer and leave the transcript
        truncated, so the self-update gateway waits it out.
        """
        return any(not slot.task.done() for slot in self._slots.values())

    def has_active_for_folder(self, project_folder: Path) -> bool:
        try:
            target = project_folder.resolve()
        except OSError:
            target = project_folder
        for slot in self._slots.values():
            if slot.task.done():
                continue
            try:
                if slot.project_folder.resolve() == target:
                    return True
            except OSError:
                if slot.project_folder == target:
                    return True
        return False

    async def cancel(self, run_id: UUID) -> bool:
        slot = self._slots.get(run_id)
        if slot is None:
            return False
        if not slot.task.done():
            slot.task.cancel()
        logger.info("agent run cancelled", run_id=str(run_id))
        return True
