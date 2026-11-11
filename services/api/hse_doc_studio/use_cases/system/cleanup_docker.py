from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from hse_doc_studio.core.docker_disk.planner import CleanupPlanRequest, DockerCleanupTarget, DockerDiskProbe
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.docker.cleanup_jobs import (
    CleanupBusyError,
    CleanupJob,
    DockerCleanupJobManager,
)
from hse_doc_studio.use_cases.system.get_docker_disk_usage import GetDockerDiskUsageUC

logger = structlog.get_logger()

CleanupTarget = DockerCleanupTarget


@dataclass
class StartDockerCleanupInput:
    targets: list[CleanupTarget]
    # Explicit refs/names for the per-row «удалить» buttons; validated against
    # the same safety rules as the bulk targets, so a stale UI can never widen
    # the blast radius beyond what the current usage report allows.
    images: list[str] = field(default_factory=list)
    containers: list[str] = field(default_factory=list)
    # Для цели «old_versions»: убрать и образ отката (последней предыдущей версии).
    include_rollback: bool = False


class StartDockerCleanupUC:
    """Expand the request into a validated step plan and start the background job."""

    def __init__(
        self,
        manager: DockerDiskProbe,
        jobs: DockerCleanupJobManager,
        settings_repo: ISettingsRepository,
        default_images: dict[str, str],
        always_protected: frozenset[str],
        current_version: str = "",
        image_base: str = "",
    ) -> None:
        self._jobs = jobs
        self._usage_uc = GetDockerDiskUsageUC(
            manager=manager,
            settings_repo=settings_repo,
            default_images=default_images,
            always_protected=always_protected,
            current_version=current_version,
            image_base=image_base,
        )

    async def execute(self, inp: StartDockerCleanupInput) -> CleanupJob:
        planner = await self._usage_uc.planner()
        steps = await planner.plan(
            CleanupPlanRequest(
                targets=inp.targets,
                images=inp.images,
                containers=inp.containers,
                include_rollback=inp.include_rollback,
            )
        )
        try:
            job = await self._jobs.start(steps)
        except CleanupBusyError as exc:
            raise ValueError(localized_error("Очистка уже выполняется", "a cleanup is already running")) from exc
        logger.info("docker cleanup started", job_id=job.id, steps=len(steps))
        return job


class GetDockerCleanupJobUC:
    def __init__(self, jobs: DockerCleanupJobManager) -> None:
        self._jobs = jobs

    async def execute(self) -> CleanupJob | None:
        return self._jobs.current()


class CancelDockerCleanupUC:
    def __init__(self, jobs: DockerCleanupJobManager) -> None:
        self._jobs = jobs

    async def execute(self) -> CleanupJob | None:
        return self._jobs.cancel()
