from __future__ import annotations

import pytest
from hse_doc_studio.core.enums import GpuVendor
from hse_doc_studio.infra.ai.ollama import hardware_probe as probe_module
from hse_doc_studio.infra.ai.ollama.hardware_probe import SystemHardwareProbe

_SMI_OUTPUT = "NVIDIA GeForce RTX 2060, 6144\n"


@pytest.fixture
def probe() -> SystemHardwareProbe:
    return SystemHardwareProbe()


@pytest.mark.unit
async def test__detect_nvidia__local_nvidia_smi_works__no_docker_needed(
    probe: SystemHardwareProbe, monkeypatch
) -> None:
    calls: list[list[str]] = []

    async def fake_run(args: list[str], timeout: float = 0) -> tuple[int, str, str]:
        calls.append(args)
        return 0, _SMI_OUTPUT, ""

    monkeypatch.setattr(probe, "_run", fake_run)

    assert await probe._detect_nvidia() == (GpuVendor.nvidia, "NVIDIA GeForce RTX 2060", 6144)
    assert [c[0] for c in calls] == ["nvidia-smi"]


@pytest.mark.unit
async def test__detect_nvidia__no_local_nvidia_smi__asks_the_host_docker(
    probe: SystemHardwareProbe, monkeypatch
) -> None:
    # Регрессия: в контейнере nvidia-smi нет, и карта хоста была не видна вовсе.
    monkeypatch.setattr(probe_module, "self_container_ref", lambda: "abc123")

    async def fake_run(args: list[str], timeout: float = 0) -> tuple[int, str, str]:
        if args[0] == "nvidia-smi":
            return 127, "", "not found"
        if args[:2] == ["docker", "inspect"]:
            return 0, "ghcr.io/alexeyshalaev/hse-doc-studio:latest\n", ""
        return 0, _SMI_OUTPUT, ""

    monkeypatch.setattr(probe, "_run", fake_run)

    assert await probe._detect_nvidia() == (GpuVendor.nvidia, "NVIDIA GeForce RTX 2060", 6144)


@pytest.mark.unit
async def test__detect_nvidia__docker_probe_repeated__runs_the_container_once(
    probe: SystemHardwareProbe, monkeypatch
) -> None:
    monkeypatch.setattr(probe_module, "self_container_ref", lambda: "abc123")
    runs: list[list[str]] = []

    async def fake_run(args: list[str], timeout: float = 0) -> tuple[int, str, str]:
        runs.append(args)
        if args[0] == "nvidia-smi":
            return 127, "", "not found"
        if args[:2] == ["docker", "inspect"]:
            return 0, "image:tag\n", ""
        return 0, _SMI_OUTPUT, ""

    monkeypatch.setattr(probe, "_run", fake_run)

    await probe._detect_nvidia()
    await probe._detect_nvidia()

    assert sum(1 for r in runs if r[:2] == ["docker", "run"]) == 1


@pytest.mark.unit
async def test__detect_nvidia__native_run_without_gpu__reports_no_card(probe: SystemHardwareProbe, monkeypatch) -> None:
    monkeypatch.setattr(probe_module, "self_container_ref", lambda: None)

    async def fake_run(args: list[str], timeout: float = 0) -> tuple[int, str, str]:
        return 127, "", "not found"

    monkeypatch.setattr(probe, "_run", fake_run)

    assert await probe._detect_nvidia() is None
