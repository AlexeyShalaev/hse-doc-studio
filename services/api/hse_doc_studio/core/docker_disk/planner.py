"""`DockerDiskPlanner`: замер «Диска» и план очистки по свежему замеру.

Планировщик не знает, откуда взялась его конфигурация: локальная Студия собирает его из настроек
api и выбранных образов, раннер из своей (`tex_image`, версия раннера). План строится только из
того, что разрешает свежий замер, поэтому устаревший экран (или сервер, приславший цели раннеру)
не расширит удаление: явные ссылки сверяются с разрешённым, лишняя даёт ошибку
(docs/design/storage-cleanup.md, S1).
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Final, Literal, Protocol

from hse_doc_studio.core.docker_disk.old_versions import OldVersions, find_old_versions, previous_service_refs
from hse_doc_studio.core.docker_disk.rules import (
    cleanable_bytes,
    ours_only,
    protect_rollback,
    stopped_managed_container_names,
    unused_app_image_refs,
)
from hse_doc_studio.core.docker_disk.steps import CleanupStep
from hse_doc_studio.core.docker_disk.usage import DockerDiskUsage
from hse_doc_studio.core.i18n import localized_error

# Цели очистки Docker. Цели, которых здесь нет (у раннера `runner_cache`), планировщик пропускает:
# их шаги добавляет тот, кто их знает.
DockerCleanupTarget = Literal["build_cache", "dangling_images", "unused_images", "stopped_containers", "old_versions"]
DOCKER_CLEANUP_TARGETS: Final[tuple[DockerCleanupTarget, ...]] = (
    "build_cache",
    "dangling_images",
    "unused_images",
    "stopped_containers",
    "old_versions",
)


class DockerDiskProbe(Protocol):
    """Замер Docker; `protected_refs` помечаются в отчёте защищёнными (`DockerSystemManager`)."""

    async def disk_usage(self, protected_refs: frozenset[str]) -> DockerDiskUsage: ...


class DockerUnavailableError(ValueError):
    """Docker не ответил на замер: план не строится."""


@dataclass(frozen=True)
class DockerDiskSnapshot:
    # Только своё (`ours_only`), образ отката помечен защищённым.
    usage: DockerDiskUsage
    # Bytes «Очистить всё» would free: build cache + dangling images + unused
    # app-category images + stopped managed containers. The startup banner
    # compares this against the disk_usage_warn_gb setting.
    cleanable_bytes: int
    old_versions: OldVersions


@dataclass(frozen=True)
class CleanupPlanRequest:
    targets: Collection[str]
    # Explicit refs/names for the per-row «удалить» buttons; validated against
    # the same safety rules as the bulk targets, so a stale UI can never widen
    # the blast radius beyond what the current usage report allows.
    images: Sequence[str] = ()
    containers: Sequence[str] = ()
    # Для цели «old_versions»: убрать и образ отката (последней предыдущей версии).
    include_rollback: bool = False
    # Для цели «old_versions» в автоочистке: оставить и предыдущий тег каждого образа сервиса (TeX Live и т. п.).
    keep_previous_service_tags: bool = False


class DockerDiskPlanner:
    def __init__(
        self,
        probe: DockerDiskProbe,
        *,
        protected_refs: frozenset[str],
        current_version: str,
        image_base: str,
    ) -> None:
        """`protected_refs`: образы, которые не удаляются никогда (активные образы категорий, своя версия Студии)."""
        self._probe = probe
        self._protected_refs = protected_refs
        self._current_version = current_version
        self._image_base = image_base

    @property
    def protected_refs(self) -> frozenset[str]:
        return self._protected_refs

    async def measure(self) -> DockerDiskSnapshot:
        usage = ours_only(await self._probe.disk_usage(self._protected_refs))
        old = find_old_versions(usage, self._current_version, self._image_base)
        usage = protect_rollback(usage, old)
        return DockerDiskSnapshot(usage=usage, cleanable_bytes=cleanable_bytes(usage), old_versions=old)

    async def plan(self, request: CleanupPlanRequest) -> list[CleanupStep]:
        """Свежий замер и план по нему; `DockerUnavailableError`, если Docker не ответил."""
        return plan_steps(await self.measure(), request)


def plan_steps(snapshot: DockerDiskSnapshot, request: CleanupPlanRequest) -> list[CleanupStep]:
    """Шаги очистки по замеру; `ValueError` с переведённым текстом, если явная ссылка не разрешена."""
    usage = snapshot.usage
    if not usage.available:
        raise DockerUnavailableError(localized_error("Docker недоступен", "Docker is unavailable"))

    targets = set(request.targets)
    steps: list[CleanupStep] = []
    if "build_cache" in targets:
        steps.append(CleanupStep(kind="build_cache"))
    if "dangling_images" in targets:
        steps.append(CleanupStep(kind="dangling_images"))
    removable = unused_app_image_refs(usage)
    old_images: list[str] = []
    old_containers: list[str] = []
    if "old_versions" in targets:
        old = snapshot.old_versions
        kept = previous_service_refs(usage, old) if request.keep_previous_service_tags else frozenset()
        old_images = [i.ref for i in old.items if i.kind != "container" and i.ref not in kept]
        old_containers = [i.ref for i in old.items if i.kind == "container"]
        # Образ отката защищён от общих целей; в план он попадает только по явному флагу.
        if request.include_rollback and old.rollback is not None:
            removable = [*removable, old.rollback.ref]
            old_images.append(old.rollback.ref)
    steps.extend(
        CleanupStep(kind="image", ref=ref)
        for ref in _plan_refs(
            allowed=removable,
            take_all="unused_images" in targets,
            explicit=[*request.images, *old_images],
            error_ru="образ занят или защищён",
            error_en="image is in use or protected",
        )
    )
    steps.extend(
        CleanupStep(kind="container", ref=name)
        for name in _plan_refs(
            allowed=stopped_managed_container_names(usage),
            take_all="stopped_containers" in targets,
            explicit=[*request.containers, *old_containers],
            error_ru="контейнер запущен или не управляется приложением",
            error_en="container is running or not managed by the app",
        )
    )
    return steps


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
