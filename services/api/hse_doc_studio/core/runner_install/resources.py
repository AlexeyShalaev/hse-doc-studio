"""Лимиты CPU и памяти раннера, поставленного из админки: разбор количеств Kubernetes и проверка границ."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_CPU_RE = re.compile(r"^(?P<n>\d+(?:\.\d+)?)(?P<u>m?)$")
_MEM_RE = re.compile(r"^(?P<n>\d+(?:\.\d+)?)(?P<u>Ki|Mi|Gi|Ti|k|K|M|G|T)?$")
_MEM_UNITS = {
    "": 1,
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
    "k": 1000,
    "K": 1000,
    "M": 1000**2,
    "G": 1000**3,
    "T": 1000**4,
}

# Нижние границы: ниже раннер не стартует, а TeX на обычном документе получает OOMKilled.
RUNNER_MIN_CPU_M = 100
RUNNER_MIN_MEMORY = 256 * 1024**2
BUILD_MIN_CPU_M = 500
BUILD_MIN_MEMORY = 1024**3


class InvalidResourcesError(ValueError):
    """Лимит не разобран или вне границ. `field` называет поле формы, `reason` одно из: format, min, max."""

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason


def parse_cpu_millicores(value: str) -> int:
    match = _CPU_RE.fullmatch(value.strip())
    if match is None:
        raise ValueError(value)
    number = Decimal(match["n"])
    return int(number if match["u"] else number * 1000)


def parse_memory_bytes(value: str) -> int:
    match = _MEM_RE.fullmatch(value.strip())
    if match is None:
        raise ValueError(value)
    try:
        return int(Decimal(match["n"]) * _MEM_UNITS[match["u"] or ""])
    except InvalidOperation as exc:
        raise ValueError(value) from exc


@dataclass(frozen=True, slots=True)
class PodResources:
    """requests и limits одного пода в строках Kubernetes."""

    cpu_request: str
    cpu_limit: str
    memory_request: str
    memory_limit: str

    def as_manifest(
        self, extra_requests: dict[str, str] | None = None, extra_limits: dict[str, str] | None = None
    ) -> dict[str, dict[str, str]]:
        return {
            "requests": {"cpu": self.cpu_request, "memory": self.memory_request, **(extra_requests or {})},
            "limits": {"cpu": self.cpu_limit, "memory": self.memory_limit, **(extra_limits or {})},
        }


@dataclass(frozen=True, slots=True)
class ResourceDefaults:
    """Умолчания и верхняя граница из настроек (значения Helm `runner.installFromUi`)."""

    runner: PodResources
    build: PodResources
    max_cpu: str = "8"
    max_memory: str = "16Gi"


@dataclass(frozen=True, slots=True)
class ResourceOverrides:
    """Лимиты из формы установки; `None` оставляет умолчание. Запросы подбираются под лимит, см. `resolve`."""

    runner_cpu: str | None = None
    runner_memory: str | None = None
    build_cpu: str | None = None
    build_memory: str | None = None

    def is_empty(self) -> bool:
        return not (self.runner_cpu or self.runner_memory or self.build_cpu or self.build_memory)


def _clamp_request(request: str, limit: str, parse: Callable[[str], int]) -> str:
    return request if parse(request) <= parse(limit) else limit


def _bounded(value: str | None, default: str, field: str, parse: Callable[[str], int], low: int, high: int) -> str:
    """Лимит из формы, если он задан и в границах; иначе умолчание."""
    if not value:
        return default
    try:
        number = parse(value)
    except ValueError as exc:
        raise InvalidResourcesError(field, "format") from exc
    if number < low:
        raise InvalidResourcesError(field, "min")
    if number > high:
        raise InvalidResourcesError(field, "max")
    return value.strip()


@dataclass(frozen=True, slots=True)
class _Bounds:
    min_cpu_m: int
    min_memory: int
    max_cpu_m: int
    max_memory: int


def _resolve_pod(base: PodResources, cpu: str | None, memory: str | None, field: str, bounds: _Bounds) -> PodResources:
    cpu_limit = _bounded(cpu, base.cpu_limit, f"{field}_cpu", parse_cpu_millicores, bounds.min_cpu_m, bounds.max_cpu_m)
    memory_limit = _bounded(
        memory, base.memory_limit, f"{field}_memory", parse_memory_bytes, bounds.min_memory, bounds.max_memory
    )
    return PodResources(
        cpu_request=_clamp_request(base.cpu_request, cpu_limit, parse_cpu_millicores),
        cpu_limit=cpu_limit,
        memory_request=_clamp_request(base.memory_request, memory_limit, parse_memory_bytes),
        memory_limit=memory_limit,
    )


def resolve(defaults: ResourceDefaults, overrides: ResourceOverrides | None) -> tuple[PodResources, PodResources]:
    """(раннер, поды сборки): умолчания с учётом формы; вне границ бросает `InvalidResourcesError`."""
    over = overrides or ResourceOverrides()
    max_cpu_m = parse_cpu_millicores(defaults.max_cpu)
    max_memory = parse_memory_bytes(defaults.max_memory)
    runner = _resolve_pod(
        defaults.runner,
        over.runner_cpu,
        over.runner_memory,
        "runner",
        _Bounds(RUNNER_MIN_CPU_M, RUNNER_MIN_MEMORY, max_cpu_m, max_memory),
    )
    build = _resolve_pod(
        defaults.build,
        over.build_cpu,
        over.build_memory,
        "build",
        _Bounds(BUILD_MIN_CPU_M, BUILD_MIN_MEMORY, max_cpu_m, max_memory),
    )
    return runner, build
