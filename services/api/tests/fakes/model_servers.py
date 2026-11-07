"""Подмена докера, движка и реестра провайдеров для серверов ИИ-моделей."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from hse_doc_studio.core.entities import HardwareInfo
from hse_doc_studio.core.enums import AIProviderType, GpuVendor
from hse_doc_studio.core.model_servers import (
    LABEL_SERVER,
    ContainerInfo,
    ContainerRunError,
    ContainerSpec,
    Engine,
    HostResources,
    PullProgress,
    RegisteredProvider,
)


def hardware(*, nvidia: bool = False, vram_mb: int | None = None, ram_mb: int = 32768) -> HardwareInfo:
    return HardwareInfo(
        gpu_vendor=GpuVendor.nvidia if nvidia else GpuVendor.none,
        gpu_name="RTX 4090" if nvidia else None,
        vram_mb=vram_mb,
        total_ram_mb=ram_mb,
        cpu_count=8,
        docker_gpu_supported=nvidia,
    )


class FakeProbe:
    def __init__(self, info: HardwareInfo) -> None:
        self.info = info

    async def detect(self) -> HardwareInfo:
        return self.info


class FakeResources:
    def __init__(self, free_mb: int | None = 500_000, arch: str = "x86_64") -> None:
        self.value = HostResources(arch, free_mb)

    async def read(self) -> HostResources:
        return self.value


class FakeRuntime:
    def __init__(self, *, docker: bool = True, run_error: str | None = None) -> None:
        self.docker = docker
        self.run_error = run_error
        self.specs: list[ContainerSpec] = []
        self.running: dict[str, bool] = {}
        self.removed: list[tuple[str, str | None]] = []
        self.log_text = "line one\nline two"

    async def available(self) -> bool:
        return self.docker

    async def run(self, spec: ContainerSpec) -> str:
        if self.run_error:
            raise ContainerRunError(self.run_error)
        self.specs.append(spec)
        self.running[spec.name] = True
        return "cid"

    def _info(self, spec: ContainerSpec) -> ContainerInfo:
        up = self.running.get(spec.name, False)
        return ContainerInfo(spec.name, up, "running" if up else "exited", spec.image, dict(spec.labels))

    async def inspect(self, name: str) -> ContainerInfo | None:
        return next((self._info(s) for s in self.specs if s.name == name), None)

    async def list_managed(self) -> list[ContainerInfo]:
        return [self._info(s) for s in self.specs if LABEL_SERVER in s.labels]

    async def start(self, name: str) -> bool:
        self.running[name] = True
        return True

    async def stop(self, name: str) -> bool:
        self.running[name] = False
        return True

    async def remove(self, name: str, *, volume: str | None = None) -> bool:
        self.removed.append((name, volume))
        self.specs = [s for s in self.specs if s.name != name]
        return True

    async def logs(self, name: str, tail: int) -> str:
        return self.log_text

    async def endpoint(self, name: str, port: int) -> str | None:
        return f"http://{name}:{port}"


class FakeEngineClient:
    def __init__(self, *, ping_ok: bool = True, pull_error: str | None = None) -> None:
        self.ping_ok = ping_ok
        self.pull_error = pull_error
        self.pinged: list[tuple[str, str, str]] = []

    async def healthy(self, base_url: str, health_path: str, api_key: str = "") -> bool:
        return True

    async def installed_models(self, engine: Engine, base_url: str, api_key: str = "") -> list[str]:
        return []

    async def pull(self, base_url: str, model: str) -> AsyncIterator[PullProgress]:
        if self.pull_error:
            yield PullProgress("", error=self.pull_error)
            return
        yield PullProgress("pulling", percent=40)
        yield PullProgress("success", percent=100, done=True)

    async def delete_model(self, base_url: str, model: str) -> bool:
        return True

    async def ping(self, base_url: str, model: str, api_key: str = "") -> bool:
        self.pinged.append((base_url, model, api_key))
        return self.ping_ok


class FakeRegistry:
    def __init__(self) -> None:
        self.registered: list[dict[str, object]] = []
        self.unregistered: list[UUID] = []

    async def register(
        self,
        admin_id: str,
        *,
        provider_id: UUID,
        name: str,
        type: AIProviderType,
        base_url: str,
        api_key: str,
        models: tuple[str, ...],
    ) -> RegisteredProvider:
        self.registered.append(
            {"id": provider_id, "name": name, "type": type, "base_url": base_url, "api_key": api_key, "models": models}
        )
        return RegisteredProvider(provider_id, name)

    async def unregister(self, admin_id: str, provider_id: UUID) -> None:
        self.unregistered.append(provider_id)


class InMemoryModelServerStore:
    def __init__(self) -> None:
        self.items: dict[str, object] = {}
        self.history: list[object] = []

    async def save(self, record) -> None:  # type: ignore[no-untyped-def]
        self.items[record.id] = record
        self.history.append(record)

    async def get(self, server_id: str):  # type: ignore[no-untyped-def]
        return self.items.get(server_id)

    async def list(self):  # type: ignore[no-untyped-def]
        return list(self.items.values())

    async def delete(self, server_id: str) -> None:
        self.items.pop(server_id, None)


class FakeRemote:
    """IRemoteRuntimes: отдаёт один и тот же FakeRuntime и считает открытия."""

    def __init__(self, runtime: FakeRuntime) -> None:
        self.runtime = runtime
        self.opened: list[tuple[str, str]] = []
        self.closed = 0

    async def open(self, actor, credential_id: str, public_host: str):  # type: ignore[no-untyped-def]
        from hse_doc_studio.core.model_servers import RemoteRuntime  # noqa: PLC0415

        self.opened.append((credential_id, public_host))

        async def close() -> None:
            self.closed += 1

        return RemoteRuntime(self.runtime, close)  # type: ignore[arg-type]
