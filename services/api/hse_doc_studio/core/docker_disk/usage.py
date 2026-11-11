"""Отчёт об использовании Docker: образы, контейнеры, тома и кэш сборки.

Его заполняет `DockerSystemManager` из `docker system df -v`, читают правила «Диска».
`protected` у образа ставит сам замер: образ занят контейнером или входит в защищённые ссылки.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DANGLING_CATEGORY = "dangling"
OTHER_CATEGORY = "other"


@dataclass(frozen=True)
class ImageUsage:
    reference: str
    repository: str
    tag: str
    id: str
    size_bytes: int
    created: str
    containers: int
    category: str
    dangling: bool
    protected: bool


@dataclass(frozen=True)
class ContainerUsage:
    name: str
    image: str
    state: str
    status: str
    size_bytes: int
    managed: bool


@dataclass(frozen=True)
class VolumeUsage:
    name: str
    size_bytes: int
    links: int
    managed: bool


@dataclass(frozen=True)
class DockerDiskUsage:
    available: bool
    images: list[ImageUsage] = field(default_factory=list)
    containers: list[ContainerUsage] = field(default_factory=list)
    volumes: list[VolumeUsage] = field(default_factory=list)
    # Totals from the `docker system df` summary — deduplicated across shared
    # layers, unlike a naive sum of per-image sizes.
    images_total_bytes: int = 0
    containers_total_bytes: int = 0
    volumes_total_bytes: int = 0
    build_cache_bytes: int = 0
    build_cache_reclaimable_bytes: int = 0
    build_cache_count: int = 0

    @property
    def total_bytes(self) -> int:
        return self.images_total_bytes + self.containers_total_bytes + self.volumes_total_bytes + self.build_cache_bytes


@dataclass(frozen=True)
class CleanupResult:
    target: str
    freed_bytes: int
    removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
