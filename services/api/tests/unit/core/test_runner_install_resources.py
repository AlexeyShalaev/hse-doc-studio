"""Лимиты раннера из формы установки: разбор количеств, границы, requests под лимит."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.runner_install import (
    InvalidResourcesError,
    PodResources,
    ResourceDefaults,
    ResourceOverrides,
    resolve,
)
from hse_doc_studio.core.runner_install.resources import parse_cpu_millicores, parse_memory_bytes

pytestmark = pytest.mark.unit

_DEFAULTS = ResourceDefaults(
    runner=PodResources("100m", "1", "256Mi", "2Gi"),
    build=PodResources("500m", "2", "1Gi", "4Gi"),
    max_cpu="8",
    max_memory="16Gi",
)


@pytest.mark.parametrize(("text", "expected"), [("250m", 250), ("2", 2000), ("0.5", 500), ("1.5", 1500)])
def test__parse_cpu__millicores(text: str, expected: int) -> None:
    assert parse_cpu_millicores(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("512Mi", 512 * 1024**2), ("2Gi", 2 * 1024**3), ("1G", 10**9), ("1024", 1024), ("1.5Gi", 1610612736)],
)
def test__parse_memory__bytes(text: str, expected: int) -> None:
    assert parse_memory_bytes(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "-1", "1e3", "1 Gi", "1gi"])
def test__parse__garbage_is_refused(text: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        parse_memory_bytes(text)
    with pytest.raises(ValueError):  # noqa: PT011
        parse_cpu_millicores(text)


def test__resolve__no_overrides__defaults() -> None:
    runner, build = resolve(_DEFAULTS, None)

    assert runner == _DEFAULTS.runner
    assert build == _DEFAULTS.build


def test__resolve__build_memory_override__limit_changes_request_kept_under_limit() -> None:
    _, build = resolve(_DEFAULTS, ResourceOverrides(build_memory="6Gi", build_cpu="4"))

    assert (build.memory_limit, build.memory_request) == ("6Gi", "1Gi")
    assert build.cpu_limit == "4"


def test__resolve__request_is_lowered_to_a_small_limit() -> None:
    runner, _ = resolve(_DEFAULTS, ResourceOverrides(runner_memory="256Mi", runner_cpu="100m"))

    assert runner.memory_request == runner.memory_limit == "256Mi"
    assert runner.cpu_request == runner.cpu_limit == "100m"


@pytest.mark.parametrize(
    ("overrides", "field", "reason"),
    [
        (ResourceOverrides(build_memory="512Mi"), "build_memory", "min"),
        (ResourceOverrides(build_cpu="100m"), "build_cpu", "min"),
        (ResourceOverrides(runner_memory="64Mi"), "runner_memory", "min"),
        (ResourceOverrides(build_memory="64Gi"), "build_memory", "max"),
        (ResourceOverrides(runner_cpu="16"), "runner_cpu", "max"),
        (ResourceOverrides(build_memory="lots"), "build_memory", "format"),
        (ResourceOverrides(build_cpu="two"), "build_cpu", "format"),
    ],
)
def test__resolve__out_of_bounds__refused_with_field(overrides: ResourceOverrides, field: str, reason: str) -> None:
    with pytest.raises(InvalidResourcesError) as caught:
        resolve(_DEFAULTS, overrides)

    assert (caught.value.field, caught.value.reason) == (field, reason)
