from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.ai_runtime import IPullModelJobs


@dataclass
class DismissPullInput:
    name: str


class DismissPullUC:
    """Drop a finished download job from the list (running jobs are kept)."""

    def __init__(self, jobs: IPullModelJobs) -> None:
        self._jobs = jobs

    async def execute(self, inp: DismissPullInput) -> None:
        self._jobs.dismiss(inp.name)
