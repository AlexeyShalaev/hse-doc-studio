"""Диск раннера: отчёт о занятом месте, цели очистки, команда раннеру и её ход.

Раннер сам меряет и сам чистит: сервер передаёт только цели (`DiskTarget`), никогда ссылки на образы, а план
раннер строит по свежему замеру своими правилами (`docs/design/storage-cleanup.md`, S1). Отчёт присылает
недоверенный раннер, поэтому длины строк, списков и чисел ограничены здесь же, а сервер показывает его как текст.

Формы кодируются `codec.encode` и разбираются `codec.decode`, как остальной протокол (`wire.py`); тела
`/disk` и `/control/*` описаны в `contracts/runner/openapi.yaml` и сверяются контрактным тестом.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final
from uuid import UUID

from hse_doc_studio.core.jobs.files import WIRE_OMIT_DEFAULT

# Закодированный отчёт больше этого сервер отвергает (413 `disk_report_too_large`); раннер обрезает списки.
MAX_DISK_REPORT_BYTES = 64 * 1024
# Списки образов и старых версий в отчёте: дальше обрезка (`unused_truncated`, итоги считаются по всем).
MAX_LISTED_ITEMS = 100
MAX_VOLUMES = 32
# Шагов очистки не больше, чем образов и контейнеров в двух списках, плюс шаги кэша.
MAX_STEPS = 512
MAX_REF = 384
MAX_VERSION = 64
MAX_VOLUME_NAME = 255
# Ошибка шага: одна строка, последняя строка stderr Docker.
MAX_STEP_ERROR = 300

# Сроки канала команд: не забрана за 10 минут значит `expired`, нет хода 3 минуты значит `lost`.
COMMAND_PICKUP_TIMEOUT_S = 600
COMMAND_SILENCE_TIMEOUT_S = 180
# Раннер шлёт отчёт сам раз в 6 часов; замер старше суток экран помечает устаревшим.
DISK_REPORT_EVERY_S = 6 * 3600
DISK_REPORT_STALE_S = 24 * 3600
# Кэш раннера чистится без остановки сборок: блобы, тронутые за это время, остаются (S9).
BLOB_MIN_IDLE_S = 600
# Первая версия раннера, которая сообщает о диске (срез B4): экран берёт её из ответа сервера, а не из своего кода.
DISK_MIN_RUNNER_VERSION = "0.22.0"
# Диалог «Диск» показывает незавершённую очистку или последнюю завершённую за это время.
RECENT_COMMAND_S = 24 * 3600

# Автоочистка по порогу места (storage-cleanup.md, раздел 14): раннер раз в 5 минут сообщает свободное место
# (`/control/disk-check`), сервер ставит очистку не чаще раза в час, если свободно меньше порога.
DISK_CHECK_EVERY_S = 300
DISK_AUTO_MIN_INTERVAL_S = 3600
DEFAULT_DISK_AUTO_MIN_FREE_PERCENT = 10
DISK_AUTO_PERCENT_RANGE = (1, 50)
# Первая версия раннера с автоочисткой (возможность `disk_auto`): экран берёт её из ответа сервера.
DISK_AUTO_MIN_RUNNER_VERSION = "0.28.0"


class DiskTarget(StrEnum):
    """Что раннер умеет очистить; порядок постоянный, им же идут блоки экрана."""

    old_versions = "old_versions"
    unused_images = "unused_images"
    build_cache = "build_cache"
    dangling_images = "dangling_images"
    stopped_containers = "stopped_containers"
    runner_cache = "runner_cache"

    @property
    def needs_docker(self) -> bool:
        return self is not DiskTarget.runner_cache


class DockerDiskReason(StrEnum):
    """Почему в отчёте нет Docker-части: раннер в Kubernetes или локальная Студия (её Docker в Настройках)."""

    kubernetes = "kubernetes"
    managed_locally = "managed_locally"


class DiskCategoryKey(StrEnum):
    """Полоса занятого места: категории образов Студии, кэш сборки и прочее Студии (висячие слои, контейнеры, тома)."""

    compile = "compile"
    languagetool = "languagetool"
    office = "office"
    ai = "ai"
    app = "app"
    cache = "cache"
    runtime = "runtime"


class StudioImageCategory(StrEnum):
    """Категории образов Студии; чужие (`other`) и висячие в списки отчёта не попадают."""

    compile = "compile"
    languagetool = "languagetool"
    office = "office"
    ai = "ai"
    app = "app"


class OldItemKind(StrEnum):
    studio_image = "studio_image"
    service_image = "service_image"
    container = "container"


def _check_bytes(*values: int) -> None:
    for value in values:
        if value < 0:
            raise ValueError("sizes and counts must not be negative")


def _check_text(value: str, limit: int, field: str) -> None:
    if not 1 <= len(value) <= limit:
        raise ValueError(f"{field} must be 1..{limit} characters")


def _check_len(items: tuple[object, ...], limit: int, field: str) -> None:
    if len(items) > limit:
        raise ValueError(f"{field} has more than {limit} items")


@dataclass(frozen=True)
class DiskCategory:
    key: DiskCategoryKey
    bytes: int

    def __post_init__(self) -> None:
        _check_bytes(self.bytes)


@dataclass(frozen=True)
class DiskBuildCache:
    bytes: int
    reclaimable_bytes: int
    count: int

    def __post_init__(self) -> None:
        _check_bytes(self.bytes, self.reclaimable_bytes, self.count)


@dataclass(frozen=True)
class DiskCount:
    """Размер и число: висячие образы, остановленные контейнеры Студии."""

    bytes: int
    count: int

    def __post_init__(self) -> None:
        _check_bytes(self.bytes, self.count)


@dataclass(frozen=True)
class UnusedImage:
    ref: str
    category: StudioImageCategory
    size_bytes: int

    def __post_init__(self) -> None:
        _check_text(self.ref, MAX_REF, "ref")
        _check_bytes(self.size_bytes)


@dataclass(frozen=True)
class OldItem:
    """Образ прежней версии или контейнер на нём; `version` пуста у образов сервисов."""

    kind: OldItemKind
    ref: str
    version: str
    size_bytes: int

    def __post_init__(self) -> None:
        _check_text(self.ref, MAX_REF, "ref")
        if len(self.version) > MAX_VERSION:
            raise ValueError(f"version is longer than {MAX_VERSION}")
        _check_bytes(self.size_bytes)


@dataclass(frozen=True)
class OldVersions:
    """Как «Старые версии» локального «Диска»: `items` до 100, итоги по всем; откат отдельно и не входит в `items`."""

    current_version: str
    rollback: OldItem | None
    items: tuple[OldItem, ...]
    reclaimable_bytes: int
    rollback_bytes: int

    def __post_init__(self) -> None:
        if len(self.current_version) > MAX_VERSION:
            raise ValueError(f"current_version is longer than {MAX_VERSION}")
        _check_len(self.items, MAX_LISTED_ITEMS, "old_versions.items")
        _check_bytes(self.reclaimable_bytes, self.rollback_bytes)


@dataclass(frozen=True)
class DockerVolume:
    """Том Студии (кэш TeX Live, модели): только размер, тома не удаляются."""

    name: str
    size_bytes: int

    def __post_init__(self) -> None:
        _check_text(self.name, MAX_VOLUME_NAME, "volume name")
        _check_bytes(self.size_bytes)


@dataclass(frozen=True)
class DockerDisk:
    """Docker-часть отчёта. `available=False`: Docker не ответил, списки пусты, числа нулевые."""

    available: bool
    categories: tuple[DiskCategory, ...]
    total_bytes: int
    cleanable_bytes: int
    build_cache: DiskBuildCache
    dangling: DiskCount
    stopped_containers: DiskCount
    unused_images: tuple[UnusedImage, ...]
    unused_truncated: bool
    old_versions: OldVersions
    volumes: tuple[DockerVolume, ...]

    def __post_init__(self) -> None:
        _check_bytes(self.total_bytes, self.cleanable_bytes)
        _check_len(self.unused_images, MAX_LISTED_ITEMS, "unused_images")
        _check_len(self.volumes, MAX_VOLUMES, "volumes")
        keys = [category.key for category in self.categories]
        if len(set(keys)) != len(keys):
            raise ValueError("disk categories must be unique")
        if not self.available and (self.categories or self.unused_images or self.volumes or self.total_bytes):
            raise ValueError("an unavailable docker reports nothing")


@dataclass(frozen=True)
class BlobCacheDisk:
    bytes: int
    count: int
    limit_bytes: int

    def __post_init__(self) -> None:
        _check_bytes(self.bytes, self.count, self.limit_bytes)


@dataclass(frozen=True)
class WorkspacesDisk:
    """Рабочие копии; `busy` сколько папок сейчас под замком задачи (их очистка пропускает)."""

    bytes: int
    count: int
    limit_bytes: int
    busy: int

    def __post_init__(self) -> None:
        _check_bytes(self.bytes, self.count, self.limit_bytes, self.busy)


@dataclass(frozen=True)
class RunnerCacheDisk:
    blobs: BlobCacheDisk
    workspaces: WorkspacesDisk


@dataclass(frozen=True)
class DataVolume:
    """Том `data_dir` раннера (`shutil.disk_usage`)."""

    total_bytes: int
    free_bytes: int

    def __post_init__(self) -> None:
        _check_bytes(self.total_bytes, self.free_bytes)
        if self.free_bytes > self.total_bytes:
            raise ValueError("free_bytes exceeds total_bytes")


def _check_targets(targets: Iterable[DiskTarget], *, at_least_one: bool) -> None:
    listed = list(targets)
    if len(set(listed)) != len(listed):
        raise ValueError("targets must be unique")
    if at_least_one and not listed:
        raise ValueError("at least one target is needed")


@dataclass(frozen=True)
class RunnerDiskReport:
    """Последний замер раннера (`POST /disk`). Путей, имён рабочих папок и чужих образов в нём нет.

    `docker` пуст ровно тогда, когда есть `docker_reason`. `targets` то, что раннер умеет чистить сейчас:
    без Docker-части или при недоступном Docker это только `runner_cache`.
    """

    measured_at: datetime
    targets: tuple[DiskTarget, ...]
    docker: DockerDisk | None
    docker_reason: DockerDiskReason | None
    cache: RunnerCacheDisk
    volume: DataVolume | None

    def __post_init__(self) -> None:
        _check_targets(self.targets, at_least_one=False)
        if (self.docker is None) == (self.docker_reason is None):
            raise ValueError("docker is null exactly when docker_reason is set")
        docker_usable = self.docker is not None and self.docker.available
        if not docker_usable and any(target.needs_docker for target in self.targets):
            raise ValueError("docker targets need a reachable docker")


def disk_cleanable_bytes(report: RunnerDiskReport) -> int:
    """«Можно освободить» по правилу 9.3: Docker `cleanable_bytes` (если Docker ответил) плюс весь кэш раннера.

    Откат сюда не входит: его `cleanable_bytes` раннера не считает. Тем же правилом считают сводка «Хранилища»,
    поле `disk` в списках раннеров, метрика и фронтенд (`runnerDiskTotals`).
    """
    docker = report.docker.cleanable_bytes if report.docker is not None and report.docker.available else 0
    return docker + report.cache.blobs.bytes + report.cache.workspaces.bytes


class RunnerCommandKind(StrEnum):
    """Вид команды канала; будущий вид объявляет свою возможность, канал остаётся тем же."""

    disk_measure = "disk.measure"
    disk_cleanup = "disk.cleanup"


class RunnerCommandState(StrEnum):
    queued = "queued"
    delivered = "delivered"
    running = "running"
    cancelling = "cancelling"
    done = "done"
    cancelled = "cancelled"
    error = "error"
    expired = "expired"
    lost = "lost"

    @property
    def finished(self) -> bool:
        return self in _FINISHED

    @property
    def reportable(self) -> bool:
        """Состояние, которое раннер может прислать в ходе (`/control/{id}/progress`)."""
        return self in _REPORTABLE


_FINISHED = frozenset(
    {
        RunnerCommandState.done,
        RunnerCommandState.cancelled,
        RunnerCommandState.error,
        RunnerCommandState.expired,
        RunnerCommandState.lost,
    }
)
_REPORTABLE = frozenset(
    {RunnerCommandState.running, RunnerCommandState.done, RunnerCommandState.cancelled, RunnerCommandState.error}
)
# Незавершённые состояния: при одной незавершённой `disk.cleanup` на раннер новая даёт 409 `runner_disk_busy`.
COMMAND_OPEN_STATES = frozenset(set(RunnerCommandState) - _FINISHED)

_S = RunnerCommandState
_AFTER_DELIVERY = frozenset({_S.running, _S.cancelling, _S.done, _S.cancelled, _S.error, _S.lost})
# Переходы раздела 5.3 дизайна. Из `delivered` сразу в итог: `disk.measure` и очистка без шагов не шлют
# промежуточного хода; остановка до первого хода тоже возможна.
COMMAND_TRANSITIONS: Mapping[RunnerCommandState, frozenset[RunnerCommandState]] = MappingProxyType(
    {
        _S.queued: frozenset({_S.delivered, _S.cancelled, _S.expired}),
        _S.delivered: _AFTER_DELIVERY,
        _S.running: _AFTER_DELIVERY,
        _S.cancelling: frozenset({_S.done, _S.cancelled, _S.error, _S.lost}),
        **{state: frozenset[RunnerCommandState]() for state in _FINISHED},
    }
)


def can_transition(current: RunnerCommandState, target: RunnerCommandState) -> bool:
    return target in COMMAND_TRANSITIONS[current]


@dataclass(frozen=True)
class DiskMeasurePayload:
    """`disk.measure`: раннер присылает свежий `/disk` и закрывает команду."""


@dataclass(frozen=True)
class DiskCleanupPayload:
    """`disk.cleanup`: только цели; что именно удалить, раннер решает по свежему замеру.

    `auto`: автоочистку поставил сервер по порогу места (14.3); раннер оставляет и предыдущий тег каждого образа
    сервиса. По проводу едет, только когда `true` (`WIRE_OMIT_DEFAULT`), а ставится только раннеру с `disk_auto`.
    """

    targets: tuple[DiskTarget, ...]
    include_rollback: bool = False
    auto: bool = field(default=False, metadata=WIRE_OMIT_DEFAULT)

    def __post_init__(self) -> None:
        _check_targets(self.targets, at_least_one=True)
        if self.include_rollback and DiskTarget.old_versions not in self.targets:
            raise ValueError("include_rollback needs the old_versions target")
        if self.auto and self.include_rollback:
            raise ValueError("an automatic cleanup never removes the rollback image")


# Цели автоочистки (A2): висячие слои, кэш сборки и старые версии без отката. Кэш раннера, неиспользуемые образы и
# остановленные контейнеры в неё не входят.
DISK_AUTO_TARGETS: Final[tuple[DiskTarget, ...]] = (
    DiskTarget.dangling_images,
    DiskTarget.build_cache,
    DiskTarget.old_versions,
)


RunnerCommandPayload = DiskCleanupPayload | DiskMeasurePayload

_PAYLOADS: Mapping[RunnerCommandKind, type[DiskCleanupPayload | DiskMeasurePayload]] = MappingProxyType(
    {RunnerCommandKind.disk_measure: DiskMeasurePayload, RunnerCommandKind.disk_cleanup: DiskCleanupPayload}
)


def check_payload(kind: RunnerCommandKind, payload: RunnerCommandPayload) -> None:
    if not isinstance(payload, _PAYLOADS[kind]):
        raise ValueError(f"{kind.value} does not take {type(payload).__name__}")  # noqa: TRY004 (ошибка формы сообщения, как остальные)


class CommandStepKind(StrEnum):
    """Шаг очистки; первые четыре это шаги локальной очистки Docker, два последних кэш раннера."""

    build_cache = "build_cache"
    dangling_images = "dangling_images"
    image = "image"
    container = "container"
    runner_blobs = "runner_blobs"
    runner_workspaces = "runner_workspaces"


class CommandStepStatus(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"
    skipped = "skipped"


_STEPS_WITH_REF = frozenset({CommandStepKind.image, CommandStepKind.container})


@dataclass(frozen=True)
class CommandStep:
    """`ref` у образа `repo:tag` или id висячего слоя, у контейнера имя, у остальных пусто."""

    kind: CommandStepKind
    ref: str | None
    status: CommandStepStatus
    freed_bytes: int
    error: str | None

    def __post_init__(self) -> None:
        _check_bytes(self.freed_bytes)
        if (self.ref is not None) != (self.kind in _STEPS_WITH_REF):
            raise ValueError(f"{self.kind.value} step ref mismatch")
        if self.ref is not None:
            _check_text(self.ref, MAX_REF, "ref")
        if self.error is not None:
            _check_text(self.error, MAX_STEP_ERROR, "error")


@dataclass(frozen=True)
class CommandProgress:
    """Ход команды: шаги плана и сколько освобождено; `error` общая причина, если план не построился."""

    steps: tuple[CommandStep, ...]
    freed_bytes: int
    error: str | None

    def __post_init__(self) -> None:
        _check_len(self.steps, MAX_STEPS, "steps")
        _check_bytes(self.freed_bytes)
        if self.error is not None:
            _check_text(self.error, MAX_STEP_ERROR, "error")


@dataclass(frozen=True)
class RunnerCommand:
    """Команда раннеру, как её хранит сервер (`runner_commands`)."""

    id: UUID
    runner_id: str
    kind: RunnerCommandKind
    payload: RunnerCommandPayload
    state: RunnerCommandState
    created_by: str
    created_at: datetime
    updated_at: datetime
    progress: CommandProgress | None = None
    delivered_at: datetime | None = None
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        check_payload(self.kind, self.payload)


@dataclass(frozen=True)
class DiskAutoPolicy:
    """Настройка автоочистки раннера (`runners.disk_auto_*`): включена ли и при каком проценте свободного места."""

    enabled: bool = True
    min_free_percent: int = DEFAULT_DISK_AUTO_MIN_FREE_PERCENT

    def __post_init__(self) -> None:
        low, high = DISK_AUTO_PERCENT_RANGE
        if not low <= self.min_free_percent <= high:
            raise ValueError(f"min_free_percent must be within {low}..{high}")

    def below(self, free_bytes: int, total_bytes: int) -> bool:
        """Свободно меньше порога; пустой том (`total_bytes = 0`) порога не задевает."""
        return total_bytes > 0 and free_bytes * 100 < total_bytes * self.min_free_percent


@dataclass(frozen=True)
class DiskAutoLast:
    """Последняя автоочистка раннера (`runners.disk_auto_last`): начало, итог и место на момент проверки."""

    command_id: UUID
    state: RunnerCommandState
    started_at: datetime
    finished_at: datetime | None
    freed_bytes: int
    free_bytes: int
    total_bytes: int

    def __post_init__(self) -> None:
        _check_bytes(self.freed_bytes, self.free_bytes, self.total_bytes)
