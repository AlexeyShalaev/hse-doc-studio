from __future__ import annotations

import time
from collections.abc import Callable

import httpx
import pytest
from hse_doc_studio.infra.docker.siblings import SiblingNetwork
from hse_doc_studio.infra.languagetool.container_manager import (
    ContainerState,
    LanguageToolContainerManager,
)

_HEALTHY = lambda _req: httpx.Response(200, json={"languages": []})  # noqa: E731
_UNHEALTHY = lambda _req: httpx.Response(503)  # noqa: E731


def _manager(handler: Callable[[httpx.Request], httpx.Response]) -> LanguageToolContainerManager:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return LanguageToolContainerManager(
        container_name="hse-languagetool-test",
        container_port=8010,
        health_path="/v2/languages",
        model_volume_name="lt-cache-test",
        health_timeout_s=2.0,
        startup_timeout_s=5.0,
        idle_timeout_s=600.0,
        client=client,
        siblings=SiblingNetwork.disabled(),
    )


_RUNNING = ContainerState(
    present=True,
    running=True,
    status_text="Up",
    container_id="abc123",
    image="erikvl87/languagetool:latest",
)


# ── ensure_running ─────────────────────────────────────────────────────────


@pytest.mark.unit
async def test__ensure_running__docker_unavailable__returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = _manager(_HEALTHY)

    async def no_docker() -> bool:
        return False

    monkeypatch.setattr(mgr, "_docker_available", no_docker)
    assert await mgr.ensure_running("erikvl87/languagetool:latest") is None
    assert mgr.current_base_url is None


@pytest.mark.unit
async def test__ensure_running__image_missing__returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = _manager(_HEALTHY)

    async def yes() -> bool:
        return True

    async def no_image(_image: str) -> bool:
        return False

    monkeypatch.setattr(mgr, "_docker_available", yes)
    monkeypatch.setattr(mgr, "_image_present", no_image)
    assert await mgr.ensure_running("erikvl87/languagetool:latest") is None


@pytest.mark.unit
async def test__ensure_running__fresh_start__publishes_free_port(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = _manager(_HEALTHY)
    calls: list[list[str]] = []

    async def yes() -> bool:
        return True

    async def yes_image(_image: str) -> bool:
        return True

    async def absent() -> ContainerState:
        return ContainerState.absent()

    async def fake_run(args: list[str], timeout: float) -> tuple[int, str, str]:
        calls.append(args)
        return 0, "", ""

    monkeypatch.setattr(mgr, "_docker_available", yes)
    monkeypatch.setattr(mgr, "_image_present", yes_image)
    monkeypatch.setattr(mgr, "inspect_container", absent)
    monkeypatch.setattr(mgr, "_run_docker_raw", fake_run)

    url = await mgr.ensure_running("erikvl87/languagetool:latest")

    assert url is not None
    assert url.startswith("http://127.0.0.1:")
    assert mgr.current_base_url == url
    # the run command published the container port to a host port
    run_args = calls[0]
    assert run_args[0] == "run"
    assert "-d" in run_args
    assert any(a.endswith(":8010") and a.startswith("127.0.0.1:") for a in run_args)


@pytest.mark.unit
async def test__ensure_running__already_healthy__skips_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = _manager(_HEALTHY)
    mgr._base_url = "http://127.0.0.1:50000"  # noqa: SLF001 — simulate a warm container

    async def fail(args: list[str], timeout: float) -> tuple[int, str, str]:
        raise AssertionError(f"docker must not be invoked when already healthy: {args}")

    monkeypatch.setattr(mgr, "_run_docker_raw", fail)
    assert await mgr.ensure_running("erikvl87/languagetool:latest") == "http://127.0.0.1:50000"


# ── is_healthy ─────────────────────────────────────────────────────────────


@pytest.mark.unit
async def test__is_healthy__running_and_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = _manager(_HEALTHY)

    async def running() -> ContainerState:
        return _RUNNING

    async def url() -> str:
        return "http://127.0.0.1:50001"

    monkeypatch.setattr(mgr, "inspect_container", running)
    monkeypatch.setattr(mgr, "_published_base_url", url)
    assert await mgr.is_healthy() is True


@pytest.mark.unit
async def test__is_healthy__not_running__false(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = _manager(_HEALTHY)

    async def absent() -> ContainerState:
        return ContainerState.absent()

    monkeypatch.setattr(mgr, "inspect_container", absent)
    assert await mgr.is_healthy() is False


# ── inspect_container parsing ──────────────────────────────────────────────


@pytest.mark.unit
async def test__inspect_container__running(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = _manager(_HEALTHY)

    async def fake(args: list[str], timeout: float) -> tuple[int, str, str]:
        return 0, "running|Up 3 minutes|abc123|erikvl87/languagetool:latest\n", ""

    monkeypatch.setattr(mgr, "_run_docker_raw", fake)
    state = await mgr.inspect_container()

    assert state.present is True
    assert state.running is True
    assert state.image == "erikvl87/languagetool:latest"


@pytest.mark.unit
async def test__inspect_container__absent(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = _manager(_HEALTHY)

    async def fake(args: list[str], timeout: float) -> tuple[int, str, str]:
        return 0, "\n", ""

    monkeypatch.setattr(mgr, "_run_docker_raw", fake)
    assert await mgr.inspect_container() == ContainerState.absent()


# ── stop / idle reaper ──────────────────────────────────────────────────────


@pytest.mark.unit
async def test__stop__clears_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = _manager(_HEALTHY)
    mgr._base_url = "http://127.0.0.1:50002"  # noqa: SLF001

    async def running() -> ContainerState:
        return _RUNNING

    async def fake_run(args: list[str], timeout: float) -> tuple[int, str, str]:
        return 0, "", ""

    monkeypatch.setattr(mgr, "inspect_container", running)
    monkeypatch.setattr(mgr, "_run_docker_raw", fake_run)

    ok, err = await mgr.stop()
    assert ok is True
    assert err is None
    assert mgr.current_base_url is None


@pytest.mark.unit
async def test__maybe_reap__stops_when_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = _manager(_HEALTHY)
    mgr._base_url = "http://127.0.0.1:50003"  # noqa: SLF001
    mgr._last_used = time.monotonic() - 100_000  # noqa: SLF001 — long idle
    calls: list[list[str]] = []

    async def running() -> ContainerState:
        return _RUNNING

    async def fake_run(args: list[str], timeout: float) -> tuple[int, str, str]:
        calls.append(args)
        return 0, "", ""

    monkeypatch.setattr(mgr, "inspect_container", running)
    monkeypatch.setattr(mgr, "_run_docker_raw", fake_run)

    await mgr._maybe_reap()  # noqa: SLF001
    assert calls
    assert calls[0][0] == "stop"
    assert mgr.current_base_url is None


@pytest.mark.unit
async def test__maybe_reap__skips_when_recent(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = _manager(_HEALTHY)
    mgr._last_used = time.monotonic()  # noqa: SLF001 — just used

    async def fail(args: list[str], timeout: float) -> tuple[int, str, str]:
        raise AssertionError("must not stop a recently-used container")

    monkeypatch.setattr(mgr, "_run_docker_raw", fail)
    await mgr._maybe_reap()  # noqa: SLF001 — should be a no-op
