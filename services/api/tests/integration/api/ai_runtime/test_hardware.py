from __future__ import annotations

import pytest
import pytest_asyncio
from hse_doc_studio.core.entities import HardwareInfo
from hse_doc_studio.core.enums import GpuVendor
from httpx import AsyncClient
from pytest_lazy_fixtures import lf

from tests.integration.api.ai_runtime.conftest import FakeHardwareProbe


@pytest_asyncio.fixture
async def nvidia_gpu_hardware() -> HardwareInfo:
    return HardwareInfo(
        gpu_vendor=GpuVendor.nvidia,
        gpu_name="NVIDIA GeForce RTX 4090",
        vram_mb=24576,
        total_ram_mb=65536,
        cpu_count=16,
        docker_gpu_supported=True,
    )


@pytest_asyncio.fixture
async def no_gpu_hardware() -> HardwareInfo:
    return HardwareInfo(
        gpu_vendor=GpuVendor.none,
        gpu_name=None,
        vram_mb=None,
        total_ram_mb=8192,
        cpu_count=4,
        docker_gpu_supported=False,
    )


@pytest.mark.parametrize(
    ("hardware", "expected"),
    [
        pytest.param(
            lf("nvidia_gpu_hardware"),
            {
                "gpu_vendor": "nvidia",
                "gpu_name": "NVIDIA GeForce RTX 4090",
                "vram_mb": 24576,
                "total_ram_mb": 65536,
                "cpu_count": 16,
                "docker_gpu_supported": True,
            },
            id="nvidia-gpu",
        ),
        pytest.param(
            lf("no_gpu_hardware"),
            {
                "gpu_vendor": "none",
                "gpu_name": None,
                "vram_mb": None,
                "total_ram_mb": 8192,
                "cpu_count": 4,
                "docker_gpu_supported": False,
            },
            id="no-gpu",
        ),
    ],
)
async def test__api__get_hardware__reflects_probe_reading(
    test_app: AsyncClient,
    hardware_probe: FakeHardwareProbe,
    hardware: HardwareInfo,
    expected: dict[str, object],
) -> None:
    # `test_app` and `hardware_probe` resolve to the SAME fixture instance
    # within one test (pytest caches fixtures per test), so mutating it here
    # before the request changes what the DI-wired use case sees.
    hardware_probe.hardware = hardware

    resp = await test_app.get("/api/v1/ai-runtime/hardware")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    for key, value in expected.items():
        assert data[key] == value
