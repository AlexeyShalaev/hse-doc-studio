from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.ai_runtime import IPullModelJobs
from hse_doc_studio.core.entities import PullJob


@dataclass
class ListPullsResult:
    jobs: list[PullJob]


class ListPullsUC:
    """List active/recent background download jobs (the UI polls this)."""

    def __init__(self, jobs: IPullModelJobs) -> None:
        self._jobs = jobs

    async def execute(self) -> ListPullsResult:
        return ListPullsResult(jobs=self._jobs.list_jobs())
