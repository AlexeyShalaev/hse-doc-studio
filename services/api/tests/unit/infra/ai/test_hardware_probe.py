from __future__ import annotations

import sys

import pytest
from hse_doc_studio.core.enums import GpuVendor
from hse_doc_studio.infra.ai.ollama.hardware_probe import SystemHardwareProbe


@pytest.mark.unit
async def test__probe__parses_nvidia_smi_output() -> None:
    probe = SystemHardwareProbe()

    async def fake_run(args: list[str]) -> tuple[int | None, str, str]:
        if args and args[0] == "nvidia-smi":
            return 0, "NVIDIA GeForce RTX 3060, 12288\n", ""
        return None, "", "not found"

    probe._run = fake_run  # type: ignore[method-assign]  # shadow the static probe

    hw = await probe.detect()

    assert hw.gpu_vendor == GpuVendor.nvidia
    assert hw.gpu_name == "NVIDIA GeForce RTX 3060"
    assert hw.vram_mb == 12288
    assert hw.docker_gpu_supported is (sys.platform in {"linux", "win32"})
    # RAM/CPU come from the real host but must always be populated as int|None.
    assert hw.cpu_count is None or isinstance(hw.cpu_count, int)


@pytest.mark.unit
async def test__probe__no_gpu_tools__degrades_to_none_without_raising() -> None:
    probe = SystemHardwareProbe()

    async def fake_run(_args: list[str]) -> tuple[int | None, str, str]:
        return None, "", "not found"

    probe._run = fake_run  # type: ignore[method-assign]

    hw = await probe.detect()

    # On Apple Silicon dev machines the platform check still classifies as apple;
    # everywhere else with no GPU tooling we must fall back to `none`, never raise.
    assert hw.gpu_vendor in {GpuVendor.none, GpuVendor.apple}
    assert hw.docker_gpu_supported is False
