from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.events import IJobLogStream
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import (
    ICompileRepository,
)

logger = structlog.get_logger()


@dataclass
class GetCompileStreamInput:
    project_id: UUID
    doc_id: str
    compile_id: UUID


class GetCompileStreamUC:
    """Returns an AsyncGenerator that yields log lines.

    If the build is still running (tracked by the in-memory log bus), the
    generator delivers lines as they arrive. Once the bus closes or if the
    build was already finished before subscription, we fall back to the
    persisted record's log.
    """

    def __init__(
        self,
        locator: IProjectLocator,
        compile_repo: ICompileRepository,
        log_stream: IJobLogStream,
    ) -> None:
        self._locator = locator
        self._compile_repo = compile_repo
        self._log_stream = log_stream

    async def execute(self, inp: GetCompileStreamInput) -> AsyncGenerator[str, None]:  # noqa: C901
        project_folder = await self._locator.folder_of(inp.project_id)
        if project_folder is None:

            async def _not_found() -> AsyncGenerator[str, None]:
                yield f"[error] project not found: {inp.project_id}"

            return _not_found()

        compile_id = inp.compile_id
        bus = self._log_stream
        compile_repo = self._compile_repo

        async def _stream() -> AsyncGenerator[str, None]:
            seen: set[str] = set()
            # Live tail while the build is active.
            if bus.has(compile_id):
                async for line in bus.subscribe(compile_id):
                    seen.add(line)
                    yield line

            # After the bus closes (or if it was never active), backfill any
            # lines we didn't already emit from the persisted record. This
            # covers two cases:
            #   - Subscriber arrived after build finished — replay everything.
            #   - Subscriber raced producer at very start — gap was tiny but
            #     we still want a deterministic final state.
            record = compile_repo.get_for_project(project_folder, compile_id)
            if record is None:
                if not seen:
                    yield f"[error] compile record not found: {compile_id}"
                return

            for line in (record.log or "").splitlines():
                if line in seen:
                    continue
                yield line

            yield f"__STATUS__:{record.status}"

        return _stream()
