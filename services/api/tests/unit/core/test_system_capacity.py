from __future__ import annotations

import pytest
from hse_doc_studio.core.system_capacity import (
    FALLBACK_CONCURRENT_COMPILES,
    FALLBACK_DISK_WARN_GB,
    MAX_CONCURRENT_COMPILES_CEILING,
    MAX_DISK_WARN_GB,
    MIN_DISK_WARN_GB,
    SystemCapacity,
    capacity_scaled_defaults,
    default_disk_usage_warn_gb,
    default_max_concurrent_compiles,
)

_GB = 1024**3


@pytest.mark.unit
@pytest.mark.parametrize(
    ("cpu_count", "total_ram_mb", "expected"),
    [
        pytest.param(4, 8 * 1024, 2, id="4_cores_8gb_keeps_the_old_default"),
        pytest.param(8, 16 * 1024, 4, id="8_cores_16gb"),
        pytest.param(24, 32 * 1024, MAX_CONCURRENT_COMPILES_CEILING, id="workstation_hits_the_ceiling"),
        pytest.param(16, 4 * 1024, 2, id="ram_is_the_bottleneck"),
        pytest.param(2, 64 * 1024, 1, id="cores_are_the_bottleneck"),
        pytest.param(10, 32 * 1024, 4, id="off_step_value_snaps_down_to_a_ui_step"),
        pytest.param(1, 1024, 1, id="tiny_machine_never_goes_below_one"),
    ],
)
def test__default_max_concurrent_compiles__known_machine__scales_with_the_scarcer_resource(
    cpu_count: int, total_ram_mb: int, expected: int
) -> None:
    capacity = SystemCapacity(cpu_count=cpu_count, total_ram_mb=total_ram_mb)

    assert default_max_concurrent_compiles(capacity) == expected


@pytest.mark.unit
def test__default_max_concurrent_compiles__nothing_detected__returns_conservative_fallback() -> None:
    assert default_max_concurrent_compiles(SystemCapacity()) == FALLBACK_CONCURRENT_COMPILES


@pytest.mark.unit
def test__default_max_concurrent_compiles__only_cpu_detected__uses_cpu_alone() -> None:
    assert default_max_concurrent_compiles(SystemCapacity(cpu_count=8)) == 4


@pytest.mark.unit
@pytest.mark.parametrize(
    ("disk_total_bytes", "expected"),
    [
        pytest.param(1024 * _GB, 50, id="1tb_disk_five_percent_snaps_to_50"),
        pytest.param(500 * _GB, 20, id="500gb_disk_snaps_down_to_20"),
        pytest.param(64 * _GB, MIN_DISK_WARN_GB, id="small_disk_gets_the_lowest_step"),
        pytest.param(8 * 1024 * _GB, MAX_DISK_WARN_GB, id="huge_disk_capped_at_the_top_step"),
    ],
)
def test__default_disk_usage_warn_gb__known_disk__is_a_share_of_it_snapped_to_a_ui_step(
    disk_total_bytes: int, expected: int
) -> None:
    assert default_disk_usage_warn_gb(SystemCapacity(disk_total_bytes=disk_total_bytes)) == expected


@pytest.mark.unit
def test__default_disk_usage_warn_gb__disk_unknown__returns_fallback() -> None:
    assert default_disk_usage_warn_gb(SystemCapacity()) == FALLBACK_DISK_WARN_GB


@pytest.mark.unit
def test__capacity_scaled_defaults__returns_exactly_the_machine_dependent_setting_keys() -> None:
    defaults = capacity_scaled_defaults(SystemCapacity(cpu_count=8, total_ram_mb=16 * 1024))

    assert set(defaults) == {"max_concurrent_compiles", "disk_usage_warn_gb"}
