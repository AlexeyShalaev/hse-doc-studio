from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CleanupTargetName = Literal["build_cache", "dangling_images", "unused_images", "stopped_containers"]


class DockerImageUsageResponse(BaseModel):
    reference: str
    repository: str
    tag: str
    size_bytes: int
    created: str
    in_use: bool
    category: str
    dangling: bool
    # protected = активный/настроенный образ своей категории или занят контейнером;
    # такие образы UI не даёт удалять.
    protected: bool


class DockerContainerUsageResponse(BaseModel):
    name: str
    image: str
    state: str
    status: str
    size_bytes: int
    managed: bool


class DockerVolumeUsageResponse(BaseModel):
    name: str
    size_bytes: int
    links: int
    managed: bool


class DockerUsageResponse(BaseModel):
    available: bool
    images: list[DockerImageUsageResponse]
    containers: list[DockerContainerUsageResponse]
    volumes: list[DockerVolumeUsageResponse]
    # Сводные размеры по типам из `docker system df` (дедуплицированы по слоям).
    images_total_bytes: int
    containers_total_bytes: int
    volumes_total_bytes: int
    build_cache_bytes: int
    build_cache_reclaimable_bytes: int
    build_cache_count: int
    total_bytes: int
    # Сколько освободит «Очистить всё» — сигнал для стартового предупреждения.
    cleanable_bytes: int


class DockerCleanupRequest(BaseModel):
    targets: list[CleanupTargetName] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    containers: list[str] = Field(default_factory=list)


class CleanupStepResponse(BaseModel):
    kind: Literal["build_cache", "dangling_images", "image", "container"]
    ref: str | None
    status: Literal["pending", "running", "done", "error", "skipped"]
    freed_bytes: int
    error: str | None


class CleanupJobResponse(BaseModel):
    id: str
    status: Literal["running", "cancelling", "done", "cancelled", "error"]
    steps: list[CleanupStepResponse]
    freed_bytes: int


class CleanupJobStateResponse(BaseModel):
    # null until the first cleanup of this backend session starts.
    job: CleanupJobResponse | None
