from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from hse_doc_studio.core.entities import HardwareInfo
from hse_doc_studio.core.enums import GpuVendor, OllamaRuntimeMode
from hse_doc_studio.infra.ai.ollama import runtime_manager as rm
from hse_doc_studio.infra.ai.ollama.runtime_manager import OllamaRuntimeManager, _installed_matches
from hse_doc_studio.infra.docker.cli import ContainerState
from hse_doc_studio.infra.docker.siblings import SiblingNetwork


@pytest.mark.unit
def test__installed_matches__tagged_and_bare() -> None:
    installed = ["qwen2.5:7b", "qwen3.5:latest"]
    assert _installed_matches("qwen2.5:7b", installed) is True  # exact tag
    assert _installed_matches("qwen3.5", installed) is True  # bare → :latest variant
    assert _installed_matches("mistral:7b", installed) is False


class _FakeProbe:
    async def detect(self) -> HardwareInfo:
        return HardwareInfo(GpuVendor.none, None, None, 16000, 8, docker_gpu_supported=False)


def _const(value: Any) -> Callable[..., Awaitable[Any]]:  # noqa: ANN401 — test helper
    async def _f(*_args: Any, **_kwargs: Any) -> Any:  # noqa: ANN401
        return value

    return _f


def _mgr() -> OllamaRuntimeManager:
    return OllamaRuntimeManager(
        image="ollama/ollama:latest",
        container_name="hse-ollama",
        container_port=11434,
        host_port=11434,
        local_base_url="http://127.0.0.1:11434",
        health_path="/api/tags",
        model_volume_name="vol",
        health_timeout_s=1.0,
        request_timeout_s=1.0,
        startup_timeout_s=1.0,
        idle_timeout_s=1.0,
        keep_alive="5m",
        hardware_probe=_FakeProbe(),
        siblings=SiblingNetwork.disabled(),
    )


@pytest.mark.unit
async def test__status__native_when_local_url_serves_and_no_container(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _mgr()
    monkeypatch.setattr(rm, "docker_available", _const(True))
    monkeypatch.setattr(rm, "image_present", _const(True))
    monkeypatch.setattr(rm, "inspect_container", _const(ContainerState.absent()))

    async def probe(_self: OllamaRuntimeManager, base: str) -> bool:
        return base == "http://127.0.0.1:11434"

    monkeypatch.setattr(OllamaRuntimeManager, "_probe", probe)
    monkeypatch.setattr(OllamaRuntimeManager, "_list_models", _const(["qwen2.5:3b"]))
    monkeypatch.setattr(OllamaRuntimeManager, "_version", _const("0.5.0"))

    st = await m.status()

    assert st.mode == OllamaRuntimeMode.native
    assert st.base_url == "http://127.0.0.1:11434"
    assert st.installed_models == ["qwen2.5:3b"]
    assert st.engine_image_installed is True


@pytest.mark.unit
async def test__status__docker_when_managed_container_running(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _mgr()
    monkeypatch.setattr(rm, "docker_available", _const(True))
    monkeypatch.setattr(rm, "image_present", _const(True))
    monkeypatch.setattr(
        rm,
        "inspect_container",
        _const(
            ContainerState(
                present=True, running=True, status_text="Up", container_id="abc", image="ollama/ollama:latest"
            )
        ),
    )
    monkeypatch.setattr(rm, "published_host_port", _const(11500))
    monkeypatch.setattr(OllamaRuntimeManager, "_probe", _const(True))
    monkeypatch.setattr(OllamaRuntimeManager, "_list_models", _const(["llama3.1:8b"]))
    monkeypatch.setattr(OllamaRuntimeManager, "_version", _const("0.5.0"))

    st = await m.status()

    assert st.mode == OllamaRuntimeMode.docker
    assert st.base_url == "http://127.0.0.1:11500"
    assert st.installed_models == ["llama3.1:8b"]


@pytest.mark.unit
async def test__status__none_when_nothing_serves(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _mgr()
    monkeypatch.setattr(rm, "docker_available", _const(True))
    monkeypatch.setattr(rm, "image_present", _const(False))
    monkeypatch.setattr(rm, "inspect_container", _const(ContainerState.absent()))
    monkeypatch.setattr(OllamaRuntimeManager, "_probe", _const(False))

    st = await m.status()

    assert st.mode == OllamaRuntimeMode.none
    assert st.base_url is None
    assert st.installed_models == []
    assert st.engine_image_installed is False


@pytest.mark.unit
async def test__run_new__passes_keep_alive_env(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _mgr()
    captured: list[list[str]] = []

    async def fake_run(args: list[str], timeout: float = 30.0) -> tuple[int | None, str, str]:
        captured.append(args)
        return 0, "", ""

    monkeypatch.setattr(rm, "is_port_free", lambda _port: True)
    monkeypatch.setattr(rm, "run_docker", fake_run)
    monkeypatch.setattr(OllamaRuntimeManager, "_gpu_run_args", _const([]))

    base = await m._run_new()

    assert base == "http://127.0.0.1:11434"
    assert "OLLAMA_KEEP_ALIVE=5m" in captured[0]


@pytest.mark.unit
async def test__list_loaded_models__parses_ps(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _mgr()
    monkeypatch.setattr(OllamaRuntimeManager, "_resolve_base", _const("http://127.0.0.1:11434"))
    monkeypatch.setattr(
        OllamaRuntimeManager,
        "_get_json",
        _const(
            {
                "models": [
                    {
                        "name": "phi3.5:latest",
                        "size": 3999079936,
                        "size_vram": 3999079936,
                        "expires_at": "2026-06-03T13:14:50+04:00",
                    }
                ]
            }
        ),
    )

    [loaded] = await m.list_loaded_models()

    assert loaded.name == "phi3.5:latest"
    assert loaded.size_bytes == 3999079936
    assert loaded.vram_bytes == 3999079936
    assert loaded.expires_at == "2026-06-03T13:14:50+04:00"


@pytest.mark.unit
async def test__stop__native_runtime_is_never_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _mgr()
    m._mode = OllamaRuntimeMode.native  # adopted a user-run native server
    stop_calls: list[list[str]] = []

    async def fake_run(args: list[str], timeout: float = 30.0) -> tuple[int | None, str, str]:
        stop_calls.append(args)
        return 0, "", ""

    monkeypatch.setattr(rm, "run_docker", fake_run)
    monkeypatch.setattr(rm, "inspect_container", _const(ContainerState.absent()))

    ok, detail = await m.stop()

    assert ok is True
    assert detail is None
    assert stop_calls == []  # never shelled out to `docker stop`
