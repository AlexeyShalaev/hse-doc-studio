from __future__ import annotations

import asyncio
from asyncio.subprocess import Process
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog

logger = structlog.get_logger()

_PROCESS_TERMINATE_TIMEOUT_S = 5.0


@dataclass
class _Slot:
    task: asyncio.Task[None]
    project_folder: Path
    doc_id: str
    process: Process | None = None


class CompileRunner:
    """In-memory registry of in-flight compile tasks.

    Lifecycle: the trigger use case registers the task before scheduling it
    and unregisters in `finally`. The docker executor reports the subprocess
    handle via `set_process` so a cancel can terminate it. Cancel issues
    SIGTERM/SIGKILL to the subprocess first, then cancels the asyncio task —
    that order matters because the task is blocked on `proc.stdout.readline()`
    and won't unwind until the process closes its stdout.
    """

    def __init__(self) -> None:
        self._slots: dict[UUID, _Slot] = {}

    def register(
        self,
        compile_id: UUID,
        task: asyncio.Task[None],
        project_folder: Path,
        doc_id: str,
    ) -> None:
        self._slots[compile_id] = _Slot(
            task=task,
            project_folder=project_folder,
            doc_id=doc_id,
        )

    def unregister(self, compile_id: UUID) -> None:
        self._slots.pop(compile_id, None)

    def set_process(self, compile_id: UUID, process: Process) -> None:
        slot = self._slots.get(compile_id)
        if slot is None:
            return
        slot.process = process

    def is_running(self, compile_id: UUID) -> bool:
        slot = self._slots.get(compile_id)
        return slot is not None and not slot.task.done()

    def has_any_active(self) -> bool:
        """True if any compile is in flight, in any project.

        Read by the self-update gateway: recreating the container mid-build kills
        the running docker task, so an automatic update waits for a quiet moment.
        """
        return any(not slot.task.done() for slot in self._slots.values())

    def has_active_for_folder(self, project_folder: Path) -> bool:
        """True if any in-flight compile belongs to this project folder.

        Used to block destructive folder operations (e.g. moving the project)
        while a build is running — the running docker container has the folder
        bind-mounted, so moving it out from under it would corrupt the build.
        """
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

    def get_meta(self, compile_id: UUID) -> tuple[Path, str] | None:
        slot = self._slots.get(compile_id)
        if slot is None:
            return None
        return slot.project_folder, slot.doc_id

    async def cancel(self, compile_id: UUID) -> bool:
        slot = self._slots.get(compile_id)
        if slot is None:
            return False

        proc = slot.process
        if proc is not None and proc.returncode is None:
            with suppress(ProcessLookupError):
                proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=_PROCESS_TERMINATE_TIMEOUT_S)
            except asyncio.TimeoutError:
                with suppress(ProcessLookupError):
                    proc.kill()

        if not slot.task.done():
            slot.task.cancel()

        logger.info("compile cancelled", compile_id=str(compile_id))
        return True
