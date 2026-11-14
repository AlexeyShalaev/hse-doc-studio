"""Отчёт об использовании Docker: образы, контейнеры, тома и кэш сборки.

Его заполняет `DockerSystemManager` из `docker system df -v`, читают правила «Диска».
`protected` у образа ставит сам замер: образ занят контейнером или входит в защищённые ссылки.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

DANGLING_CATEGORY = "dangling"
OTHER_CATEGORY = "other"

# `CreatedAt` образа в выводе docker: `2024-05-01 12:34:56 +0000 UTC` (бывает и ISO с `T` и долями секунды).
_CREATED_AT = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.\d+)?\s*(Z|[+-]\d{2}:?\d{2})?")


def parse_created_at(text: str) -> datetime | None:
    """Время сборки образа из `CreatedAt`; без пояса считается UTC, мусор даёт None."""
    match = _CREATED_AT.match(text.strip())
    if match is None:
        return None
    day, clock, zone = match.groups()
    offset = "+0000" if zone in (None, "Z") else zone.replace(":", "")
    try:
        return datetime.strptime(f"{day} {clock} {offset}", "%Y-%m-%d %H:%M:%S %z").astimezone(UTC)
    except ValueError:
        return None


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
    # Когда образ собран (`CreatedAt` замера); None, если Docker не сообщил или время не разобралось.
    created_at: datetime | None = None


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
