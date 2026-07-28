from __future__ import annotations

import pytest
from hse_doc_studio.core.ai_catalog import ModelCatalog, recommend
from hse_doc_studio.core.entities import CatalogModel, HardwareInfo
from hse_doc_studio.core.enums import GpuVendor


def _catalog() -> ModelCatalog:
    # Mirrors the real three-tier catalog shape (names/sizes) so the tests
    # exercise realistic VRAM/RAM thresholds.
    return ModelCatalog(
        models=[
            CatalogModel("qwen2.5:1.5b", "Qwen2.5 1.5B", "Qwen2.5", 1.5, 1.0, 2.0, 4.0, ["вычитка"], ""),
            CatalogModel("qwen2.5:3b", "Qwen2.5 3B", "Qwen2.5", 3.0, 2.0, 4.0, 8.0, ["вычитка"], ""),
            CatalogModel("qwen2.5:7b", "Qwen2.5 7B", "Qwen2.5", 7.0, 4.7, 6.0, 16.0, ["правки"], ""),
            CatalogModel("llama3.1:8b", "Llama 3.1 8B", "Llama 3.x", 8.0, 4.9, 6.0, 16.0, ["правки"], ""),
            CatalogModel("qwen2.5:14b", "Qwen2.5 14B", "Qwen2.5", 14.0, 9.0, 12.0, 32.0, ["разбор"], ""),
        ]
    )


def _hw(
    vendor: GpuVendor = GpuVendor.none,
    vram_mb: int | None = None,
    ram_mb: int | None = None,
) -> HardwareInfo:
    return HardwareInfo(
        gpu_vendor=vendor,
        gpu_name=None,
        vram_mb=vram_mb,
        total_ram_mb=ram_mb,
        cpu_count=8,
        docker_gpu_supported=False,
    )


def _by_name(fits: list, name: str):  # noqa: ANN001 — test helper
    return next(f for f in fits if f.model.name == name)


def _recommended(fits: list):  # noqa: ANN001 — test helper
    return [f.model.name for f in fits if f.recommended]


@pytest.mark.unit
def test__recommend__nvidia_8gb__fits_7_8b_on_gpu_recommends_largest() -> None:
    fits = recommend(_catalog(), _hw(GpuVendor.nvidia, vram_mb=8192, ram_mb=16384))

    assert _by_name(fits, "qwen2.5:7b").on_gpu is True
    assert _by_name(fits, "llama3.1:8b").on_gpu is True
    # 14B needs 12 GB VRAM and 32 GB RAM — fits nowhere on this host.
    big = _by_name(fits, "qwen2.5:14b")
    assert big.on_gpu is False
    assert big.runnable is False
    # Largest model that fits comfortably on the GPU is the default.
    assert _recommended(fits) == ["llama3.1:8b"]


@pytest.mark.unit
def test__recommend__cpu_only_16gb__no_gpu_capped_small_default() -> None:
    fits = recommend(_catalog(), _hw(GpuVendor.none, vram_mb=None, ram_mb=16384))

    assert all(not f.on_gpu for f in fits)
    # 7B/8B "run" on 16 GB RAM but are too big to be the CPU default (>4B).
    assert _by_name(fits, "qwen2.5:7b").runnable is True
    # The capped CPU default is the largest small model that fits comfortably.
    assert _recommended(fits) == ["qwen2.5:3b"]


@pytest.mark.unit
def test__recommend__tiny_4gb_ram__only_smallest_runnable_no_comfortable_default() -> None:
    fits = recommend(_catalog(), _hw(GpuVendor.none, vram_mb=None, ram_mb=4096))

    assert _by_name(fits, "qwen2.5:1.5b").runnable is True
    assert _by_name(fits, "qwen2.5:3b").runnable is False
    # 1.5B needs 4 GB and the host has exactly 4 GB — runnable, but not
    # comfortable enough (no headroom) to be auto-recommended.
    assert _recommended(fits) == []


@pytest.mark.unit
def test__recommend__unknown_hardware__nothing_runnable() -> None:
    fits = recommend(_catalog(), _hw(GpuVendor.none, vram_mb=None, ram_mb=None))

    assert all(not f.runnable for f in fits)
    assert _recommended(fits) == []
    assert "Не удалось оценить" in _by_name(fits, "qwen2.5:1.5b").note


@pytest.mark.unit
def test__recommend__apple_unified_memory__treated_as_gpu_budget() -> None:
    # 16 GB unified → ~9.6 GB usable for Metal → up to 8B comfortably on GPU.
    fits = recommend(_catalog(), _hw(GpuVendor.apple, vram_mb=None, ram_mb=16384))

    assert _by_name(fits, "llama3.1:8b").on_gpu is True
    assert _by_name(fits, "qwen2.5:14b").on_gpu is False
    assert _recommended(fits) == ["llama3.1:8b"]
