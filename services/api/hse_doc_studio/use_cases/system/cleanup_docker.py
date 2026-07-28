from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import structlog

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.docker.cleanup_jobs import (
    CleanupBusyError,
    CleanupJob,
    CleanupStep,
    DockerCleanupJobManager,
)
from hse_doc_studio.infra.docker.system_manager import DockerSystemManager
from hse_doc_studio.use_cases.system.get_docker_disk_usage import (
    GetDockerDiskUsageUC,
    unused_app_image_refs,
)

logger = structlog.get_logger()

CleanupTarget = Literal["build_cache", "dangling_images", "unused_images", "stopped_containers"]

ALL_TARGETS: tuple[CleanupTarget, ...] = (
    "build_cache",
    "dangling_images",
    "unused_images",
    "stopped_containers",
)


@dataclass
class StartDockerCleanupInput:
    targets: list[CleanupTarget]
    # Explicit refs/names for the per-row «удалить» buttons; validated against
    # the same safety rules as the bulk targets, so a stale UI can never widen
    # the blast radius beyond what the current usage report allows.
    images: list[str] = field(default_factory=list)
    containers: list[str] = field(default_factory=list)


class StartDockerCleanupUC:
    """Expand the request into a validated step plan and start the background job."""

    def __init__(
        self,
        manager: DockerSystemManager,
        jobs: DockerCleanupJobManager,
        settings_repo: ISettingsRepository,
        default_images: dict[str, str],
        always_protected: frozenset[str],
    ) -> None:
        self._jobs = jobs
        self._usage_uc = GetDockerDiskUsageUC(
            manager=manager,
            settings_repo=settings_repo,
            default_images=default_images,
            always_protected=always_protected,
        )

    async def execute(self, inp: StartDockerCleanupInput) -> CleanupJob:
        output = await self._usage_uc.execute()
        if not output.usage.available:
            raise ValueError(localized_error("Docker недоступен", "Docker is unavailable"))

        steps: list[CleanupStep] = []
        if "build_cache" in inp.targets:
            steps.append(CleanupStep(kind="build_cache"))
        if "dangling_images" in inp.targets:
            steps.append(CleanupStep(kind="dangling_images"))
        removable = unused_app_image_refs(output.usage)
        stopped_managed = [c.name for c in output.usage.containers if c.managed and c.state != "running"]
        steps.extend(
            CleanupStep(kind="image", ref=ref)
            for ref in _plan_refs(
                allowed=removable,
                take_all="unused_images" in inp.targets,
                explicit=inp.images,
                error_ru="образ занят или защищён",
                error_en="image is in use or protected",
            )
        )
        steps.extend(
            CleanupStep(kind="container", ref=name)
            for name in _plan_refs(
                allowed=stopped_managed,
                take_all="stopped_containers" in inp.targets,
                explicit=inp.containers,
                error_ru="контейнер запущен или не управляется приложением",
                error_en="container is running or not managed by the app",
            )
        )

        try:
            job = await self._jobs.start(steps)
        except CleanupBusyError as exc:
            raise ValueError(localized_error("Очистка уже выполняется", "a cleanup is already running")) from exc
        logger.info("docker cleanup started", job_id=job.id, steps=len(steps))
        return job


def _plan_refs(
    allowed: list[str],
    take_all: bool,
    explicit: list[str],
    error_ru: str,
    error_en: str,
) -> list[str]:
    """Bulk target + explicit per-row picks → ordered dedup, validated against `allowed`."""
    refs = list(allowed) if take_all else []
    for ref in explicit:
        if ref not in allowed:
            raise ValueError(localized_error(f"{ref}: {error_ru}", f"{ref}: {error_en}"))
        if ref not in refs:
            refs.append(ref)
    return refs


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
