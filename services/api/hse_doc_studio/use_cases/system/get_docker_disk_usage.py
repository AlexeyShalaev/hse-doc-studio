from __future__ import annotations

from dataclasses import dataclass, replace

from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.docker.system_manager import (
    DANGLING_CATEGORY,
    OTHER_CATEGORY,
    DockerDiskUsage,
    DockerSystemManager,
)
from hse_doc_studio.use_cases.system.old_versions import OldVersions, find_old_versions


@dataclass
class GetDockerDiskUsageOutput:
    usage: DockerDiskUsage
    # Bytes «Очистить всё» would free: build cache + dangling images + unused
    # app-category images + stopped managed containers. The startup banner
    # compares this against the disk_usage_warn_gb setting.
    cleanable_bytes: int
    old_versions: OldVersions


class GetDockerDiskUsageUC:
    def __init__(
        self,
        manager: DockerSystemManager,
        settings_repo: ISettingsRepository,
        default_images: dict[str, str],
        always_protected: frozenset[str],
        current_version: str = "",
        image_base: str = "",
    ) -> None:
        self._manager = manager
        self._settings_repo = settings_repo
        self._default_images = dict(default_images)
        self._always_protected = always_protected
        self._current_version = current_version
        self._image_base = image_base

    async def execute(self) -> GetDockerDiskUsageOutput:
        usage = ours_only(await self._manager.disk_usage(await self.protected_refs()))
        old = find_old_versions(usage, self._current_version, self._image_base)
        usage = _protect_rollback(usage, old)
        return GetDockerDiskUsageOutput(usage=usage, cleanable_bytes=cleanable_bytes(usage), old_versions=old)

    async def protected_refs(self) -> frozenset[str]:
        """Images that must survive cleanup: each category's configured/active ref."""
        stored = await self._settings_repo.get()
        refs = {str(stored.get(key) or default) for key, default in self._default_images.items()}
        return frozenset(refs) | self._always_protected


def _protect_rollback(usage: DockerDiskUsage, old: OldVersions) -> DockerDiskUsage:
    """Образ отката защищён от общих целей очистки: убрать его можно только осознанно."""
    if old.rollback is None:
        return usage
    images = [replace(i, protected=True) if i.reference == old.rollback.ref else i for i in usage.images]
    return replace(usage, images=images)


def ours_only(usage: DockerDiskUsage) -> DockerDiskUsage:
    """Drop everything that isn't the app's: foreign images, unmanaged containers/volumes.

    The section is «сколько занимает ПРОГРАММА», and the user's other docker
    workloads are none of our business — their names never even leave the
    backend. Dangling layers stay (untagged garbage is what cleanup handles);
    build cache stays (unattributable, and clearing it is the biggest win).
    Totals are recomputed over the kept entries — a naive per-image sum, so
    shared layers between kept images count twice; fine for a usage chart and
    consistent with the per-category breakdown built the same way.
    """
    if not usage.available:
        return usage
    images = [i for i in usage.images if i.category != OTHER_CATEGORY]
    containers = [c for c in usage.containers if c.managed]
    volumes = [v for v in usage.volumes if v.managed]
    return DockerDiskUsage(
        available=True,
        images=images,
        containers=containers,
        volumes=volumes,
        images_total_bytes=sum(i.size_bytes for i in images),
        containers_total_bytes=sum(c.size_bytes for c in containers),
        volumes_total_bytes=sum(v.size_bytes for v in volumes),
        build_cache_bytes=usage.build_cache_bytes,
        build_cache_reclaimable_bytes=usage.build_cache_reclaimable_bytes,
        build_cache_count=usage.build_cache_count,
    )


def cleanable_bytes(usage: DockerDiskUsage) -> int:
    if not usage.available:
        return 0
    freeable_images = sum(
        image.size_bytes for image in usage.images if not image.protected and image.category not in (OTHER_CATEGORY,)
    )
    stopped_managed = sum(c.size_bytes for c in usage.containers if c.managed and c.state != "running")
    return usage.build_cache_reclaimable_bytes + freeable_images + stopped_managed


def unused_app_image_refs(usage: DockerDiskUsage) -> list[str]:
    """Non-dangling app-category images safe to remove (dangling go via `image prune`)."""
    return [
        image.reference
        for image in usage.images
        if not image.protected and image.category not in (OTHER_CATEGORY, DANGLING_CATEGORY)
    ]
