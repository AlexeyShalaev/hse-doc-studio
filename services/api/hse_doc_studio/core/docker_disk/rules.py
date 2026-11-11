"""Чистые правила «Диска» над отчётом Docker: что показывать, что можно освободить, что удалять."""

from __future__ import annotations

from dataclasses import replace

from hse_doc_studio.core.docker_disk.categories import (
    CATEGORY_AI,
    CATEGORY_APP,
    CATEGORY_COMPILE,
    CATEGORY_LANGUAGETOOL,
    CATEGORY_OFFICE,
)
from hse_doc_studio.core.docker_disk.old_versions import OldVersions
from hse_doc_studio.core.docker_disk.usage import DANGLING_CATEGORY, OTHER_CATEGORY, DockerDiskUsage

# Постоянный порядок полосы «Диска», как `SERVICE_CATEGORIES` во фронтенде (`widgets/settings/sections/disk/lib.ts`).
SERVICE_CATEGORIES: tuple[str, ...] = (
    CATEGORY_COMPILE,
    CATEGORY_LANGUAGETOOL,
    CATEGORY_OFFICE,
    CATEGORY_AI,
    CATEGORY_APP,
)


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


def protect_rollback(usage: DockerDiskUsage, old: OldVersions) -> DockerDiskUsage:
    """Образ отката защищён от общих целей очистки: убрать его можно только осознанно."""
    if old.rollback is None:
        return usage
    images = [replace(i, protected=True) if i.reference == old.rollback.ref else i for i in usage.images]
    return replace(usage, images=images)


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


def stopped_managed_container_names(usage: DockerDiskUsage) -> list[str]:
    """Остановленные контейнеры с меткой Студии: их можно удалить (метка проверяется ещё раз при удалении)."""
    return [c.name for c in usage.containers if c.managed and c.state != "running"]


def category_breakdown(usage: DockerDiskUsage) -> list[tuple[str, int]]:
    """Полоса «Диска» как во фронтенде (`buildSegments`): категории сервисов, `cache`, `runtime`, без пустых.

    `runtime` это то, что Docker не относит к одному образу: висячие слои, записываемые слои
    контейнеров и тома. Ждёт отчёт после `ours_only`.
    """
    by_category: dict[str, int] = {}
    for image in usage.images:
        by_category[image.category] = by_category.get(image.category, 0) + image.size_bytes
    rows = [(key, by_category.get(key, 0)) for key in SERVICE_CATEGORIES]
    rows.append(("cache", usage.build_cache_bytes))
    runtime = by_category.get(DANGLING_CATEGORY, 0) + usage.containers_total_bytes + usage.volumes_total_bytes
    rows.append(("runtime", runtime))
    return [(key, size) for key, size in rows if size > 0]
