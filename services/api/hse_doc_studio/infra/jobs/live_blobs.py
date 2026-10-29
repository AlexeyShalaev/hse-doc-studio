"""Блобы незавершённых задач очереди: сборка мусора хранилища их не трогает."""

from __future__ import annotations

from hse_doc_studio.core.jobs.enums import JobState
from hse_doc_studio.core.jobs.queue import IJobQueue


class QueueLiveBlobs:
    def __init__(self, queue: IJobQueue) -> None:
        self._queue = queue

    async def live_blobs(self) -> set[str]:
        live: set[str] = set()
        for state in (JobState.queued, JobState.running):
            for job in await self._queue.list(state=state):
                live.update(str(entry["sha256"]) for entry in job.payload.get("manifest", ()) if entry.get("sha256"))
        return live
