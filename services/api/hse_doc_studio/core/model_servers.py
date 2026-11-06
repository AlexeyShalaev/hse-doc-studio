"""Серверы ИИ-моделей: движки, оценка требований, описание контейнера и порты. Без ввода-вывода.

Правила здесь чистые: что запускать, с какими аргументами, влезет ли модель в железо. Docker, сеть и база
подключаются портами ниже и живут в infra.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.entities import HardwareInfo
from hse_doc_studio.core.enums import AIProviderType, GpuVendor

# Метки контейнера: по ним сервер находит свои установки после перезапуска Студии (своей таблицы нет).
LABEL_SERVER = "com.hse-studio.model-server"
LABEL_ENGINE = "com.hse-studio.model-server.engine"
LABEL_MODEL = "com.hse-studio.model-server.model"
LABEL_PROVIDER = "com.hse-studio.model-server.provider"
LABEL_TARGET = "com.hse-studio.model-server.target"
LABEL_NAME = "com.hse-studio.model-server.name"

CONTAINER_PREFIX = "hse-ms-"
MAX_MODEL_LEN = 200
MAX_NAME = 64

_MODEL_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}$")
_SIZE_IN_NAME = re.compile(r"(?<![0-9.])(\d+(?:\.\d+)?)\s*([bm])(?![a-z0-9])", re.IGNORECASE)
_MB = 1024 * 1024


class Engine(StrEnum):
    ollama = "ollama"
    vllm = "vllm"
    sglang = "sglang"


class Target(StrEnum):
    local = "local"
    ssh = "ssh"


class ServerStatus(StrEnum):
    installing = "installing"
    running = "running"
    stopped = "stopped"
    failed = "failed"


class StepState(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class Fit(StrEnum):
    fits = "fits"
    tight = "tight"
    too_large = "too_large"
    unknown = "unknown"


@dataclass(frozen=True)
class EngineSpec:
    engine: Engine
    image: str
    port: int
    needs_gpu: bool
    # Тип провайдера в Студии. Ollama держит свой тип, остальные идут как OpenAI-совместимые.
    provider_type: AIProviderType
    # Движок принимает модель при старте (vLLM, SGLang) или скачивает её после (Ollama).
    model_at_start: bool
    models_mount: str
    health_path: str


ENGINES: Mapping[Engine, EngineSpec] = {
    Engine.ollama: EngineSpec(
        Engine.ollama,
        "ollama/ollama:latest",
        11434,
        False,
        AIProviderType.ollama,
        False,
        "/root/.ollama",
        "/api/version",
    ),
    Engine.vllm: EngineSpec(
        Engine.vllm,
        "vllm/vllm-openai:latest",
        8000,
        True,
        AIProviderType.openai_compat,
        True,
        "/root/.cache/huggingface",
        "/health",
    ),
    Engine.sglang: EngineSpec(
        Engine.sglang,
        "lmsysorg/sglang:latest",
        30000,
        True,
        AIProviderType.openai_compat,
        True,
        "/root/.cache/huggingface",
        "/health",
    ),
}


@dataclass(frozen=True)
class CatalogModel:
    ref: str
    title: str
    params_b: float
    # Для Ollama это тег библиотеки, для vLLM и SGLang идентификатор на Hugging Face.
    engines: tuple[Engine, ...]
    quant: str = "q4"


CATALOG: tuple[CatalogModel, ...] = (
    CatalogModel("qwen3:4b", "Qwen3 4B", 4.0, (Engine.ollama,)),
    CatalogModel("qwen3:8b", "Qwen3 8B", 8.0, (Engine.ollama,)),
    CatalogModel("llama3.2:3b", "Llama 3.2 3B", 3.0, (Engine.ollama,)),
    CatalogModel("llama3.1:8b", "Llama 3.1 8B", 8.0, (Engine.ollama,)),
    CatalogModel("gemma3:12b", "Gemma 3 12B", 12.0, (Engine.ollama,)),
    CatalogModel("qwen3:32b", "Qwen3 32B", 32.0, (Engine.ollama,)),
    CatalogModel("Qwen/Qwen3-4B", "Qwen3 4B", 4.0, (Engine.vllm, Engine.sglang), "bf16"),
    CatalogModel("Qwen/Qwen3-8B", "Qwen3 8B", 8.0, (Engine.vllm, Engine.sglang), "bf16"),
    CatalogModel(
        "meta-llama/Llama-3.1-8B-Instruct", "Llama 3.1 8B Instruct", 8.0, (Engine.vllm, Engine.sglang), "bf16"
    ),
    CatalogModel("google/gemma-3-12b-it", "Gemma 3 12B", 12.0, (Engine.vllm, Engine.sglang), "bf16"),
)

_BYTES_PER_PARAM = {"q4": 0.6, "q8": 1.1, "fp16": 2.0, "bf16": 2.0}


def catalog_for(engine: Engine, query: str = "") -> list[CatalogModel]:
    needle = query.strip().lower()
    return [
        m
        for m in CATALOG
        if engine in m.engines and (not needle or needle in m.ref.lower() or needle in m.title.lower())
    ]


def valid_model_ref(ref: str) -> bool:
    return bool(_MODEL_REF.match(ref)) and ".." not in ref


def guess_params_b(ref: str) -> float | None:
    """Размер из каталога, а если модели там нет, из имени (`7b`, `70B`, `500m`)."""
    known = next((m.params_b for m in CATALOG if m.ref == ref), None)
    if known is not None:
        return known
    found = _SIZE_IN_NAME.search(ref)
    if found is None:
        return None
    value = float(found.group(1))
    return value / 1000 if found.group(2).lower() == "m" else value


@dataclass(frozen=True)
class HostResources:
    arch: str | None
    disk_free_mb: int | None


@dataclass(frozen=True)
class Estimate:
    fit: Fit
    params_b: float | None
    weights_mb: int | None
    needed_mb: int | None
    available_mb: int | None
    # "vram" или "ram": против чего считали.
    memory_kind: str
    disk_ok: bool | None
    reasons: tuple[str, ...] = ()


_OVERHEAD = 1.25
_TIGHT_RATIO = 0.85
_DISK_MARGIN = 1.1
_SUPPORTED_ARCH = frozenset({"x86_64", "amd64", "aarch64", "arm64"})


def _fit(needed_mb: int, available: int) -> tuple[Fit, str]:
    if needed_mb > available:
        return Fit.too_large, "memory_low"
    if needed_mb > available * _TIGHT_RATIO:
        return Fit.tight, "memory_tight"
    return Fit.fits, ""


def _engine_reasons(engine: Engine, hardware: HardwareInfo, resources: HostResources) -> list[str]:
    reasons: list[str] = []
    if ENGINES[engine].needs_gpu and hardware.gpu_vendor is not GpuVendor.nvidia:
        reasons.append("engine_requires_gpu")
    if resources.arch is not None and resources.arch.lower() not in _SUPPORTED_ARCH:
        reasons.append("arch_unsupported")
    return reasons


def estimate_requirements(
    engine: Engine, model: str, hardware: HardwareInfo, resources: HostResources, *, params_b: float | None = None
) -> Estimate:
    """Грубая оценка до скачивания: вес по числу параметров и квантованию плюс запас на KV-кэш.

    Это порядок величины, а не обещание: реальное потребление зависит от длины контекста и числа запросов.
    """
    size = params_b if params_b is not None else guess_params_b(model)
    on_gpu = hardware.gpu_vendor is GpuVendor.nvidia and hardware.vram_mb is not None
    available = hardware.vram_mb if on_gpu else hardware.total_ram_mb
    kind = "vram" if on_gpu else "ram"
    reasons = _engine_reasons(engine, hardware, resources)
    if size is None:
        return Estimate(Fit.unknown, None, None, None, available, kind, None, (*reasons, "size_unknown"))
    quant = next((m.quant for m in CATALOG if m.ref == model), "q4" if engine is Engine.ollama else "bf16")
    weights_mb = int(size * 1e9 * _BYTES_PER_PARAM[quant] / _MB)
    needed_mb = int(weights_mb * _OVERHEAD)
    disk_ok = None if resources.disk_free_mb is None else resources.disk_free_mb >= weights_mb * _DISK_MARGIN
    if disk_ok is False:
        reasons.append("disk_low")
    if available is None:
        return Estimate(Fit.unknown, size, weights_mb, needed_mb, None, kind, disk_ok, (*reasons, "memory_unknown"))
    fit, reason = _fit(needed_mb, available)
    if reason:
        reasons.append(reason)
    if not on_gpu and engine is not Engine.ollama:
        reasons.append("cpu_only")
    return Estimate(fit, size, weights_mb, needed_mb, available, kind, disk_ok, tuple(reasons))


@dataclass(frozen=True)
class ContainerSpec:
    """Что запустить. Секреты отдельно: рантайм кладёт их не в аргументы процесса, а в файл с правами 0600."""

    name: str
    image: str
    command: tuple[str, ...]
    port: int
    labels: Mapping[str, str]
    volume: tuple[str, str]
    env: Mapping[str, str] = field(default_factory=dict)
    secret_env: Mapping[str, str] = field(default_factory=dict)
    gpu: bool = False
    # Можно ли при отказе `--gpus` запуститься на процессоре (Ollama да, vLLM и SGLang нет).
    gpu_optional: bool = True
    shm_size: str | None = None


def build_container_spec(
    engine: Engine,
    *,
    server_id: str,
    model: str,
    name: str = "",
    image: str | None = None,
    api_key: str = "",
    hf_token: str = "",
    gpu: bool = False,
    provider_id: UUID | None = None,
) -> ContainerSpec:
    spec = ENGINES[engine]
    labels = {
        LABEL_SERVER: server_id,
        LABEL_ENGINE: engine.value,
        LABEL_MODEL: model,
        LABEL_TARGET: Target.local.value,
        LABEL_NAME: name or f"{engine.value} {model}",
    }
    if provider_id is not None:
        labels[LABEL_PROVIDER] = str(provider_id)
    secret_env = {"HF_TOKEN": hf_token} if hf_token else {}
    env: dict[str, str] = {}
    command: tuple[str, ...] = ()
    shm = None
    if engine is Engine.ollama:
        env["OLLAMA_KEEP_ALIVE"] = "30m"
    elif engine is Engine.vllm:
        command = ("--model", model, "--host", "0.0.0.0", "--port", str(spec.port))  # noqa: S104 — внутри контейнера
        shm = "8g"
        if api_key:
            secret_env["VLLM_API_KEY"] = api_key
    else:
        launch = (
            f"exec python3 -m sglang.launch_server --model-path {shlex.quote(model)} --host 0.0.0.0 --port {spec.port}"  # noqa: S104 — внутри контейнера
        )
        if api_key:
            # Ключ у SGLang только флагом: раскрываем его из окружения внутри контейнера, в аргументах запуска его нет.
            launch += ' --api-key "$SGLANG_API_KEY"'
            secret_env["SGLANG_API_KEY"] = api_key
        command = ("sh", "-c", launch)
        shm = "8g"
    return ContainerSpec(
        name=f"{CONTAINER_PREFIX}{server_id}",
        image=image or spec.image,
        command=command,
        port=spec.port,
        labels=labels,
        volume=(f"{CONTAINER_PREFIX}{engine.value}-models", spec.models_mount),
        env=env,
        secret_env=secret_env,
        gpu=gpu,
        gpu_optional=not spec.needs_gpu,
        shm_size=shm,
    )


@dataclass(frozen=True)
class ContainerInfo:
    name: str
    running: bool
    status_text: str
    image: str
    labels: Mapping[str, str]


class IContainerRuntime(Protocol):
    """Контейнеры на целевой машине. Локально это docker CLI, по SSH те же команды через сеанс."""

    async def available(self) -> bool: ...

    async def run(self, spec: ContainerSpec) -> str:
        """Запустить; при сбое поднимает `ContainerRunError` с безопасным текстом (без секретов)."""
        ...

    async def inspect(self, name: str) -> ContainerInfo | None: ...

    async def list_managed(self) -> list[ContainerInfo]: ...

    async def start(self, name: str) -> bool: ...

    async def stop(self, name: str) -> bool: ...

    async def remove(self, name: str, *, volume: str | None = None) -> bool: ...

    async def logs(self, name: str, tail: int) -> str: ...

    async def endpoint(self, name: str, port: int) -> str | None:
        """Адрес, по которому Студия достучится до контейнера (имя в общей сети либо loopback хоста)."""
        ...


class ContainerRunError(Exception):
    pass


class IModelServerClient(Protocol):
    """Разговор с самим движком по HTTP."""

    async def healthy(self, base_url: str, health_path: str, api_key: str = "") -> bool: ...

    async def installed_models(self, engine: Engine, base_url: str, api_key: str = "") -> list[str]: ...

    def pull(self, base_url: str, model: str) -> AsyncIterator[PullProgress]: ...

    async def delete_model(self, base_url: str, model: str) -> bool: ...

    async def ping(self, base_url: str, model: str, api_key: str = "") -> bool:
        """Модель отвечает: короткий запрос на дополнение."""
        ...


@dataclass(frozen=True)
class PullProgress:
    text: str
    percent: int | None = None
    done: bool = False
    error: str | None = None


class IHostResources(Protocol):
    async def read(self) -> HostResources: ...


@dataclass(frozen=True)
class RegisteredProvider:
    id: UUID
    name: str


class IModelProviderRegistry(Protocol):
    """Общий ИИ-провайдер установки, который заводится вместе с сервером и уходит вместе с ним."""

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
    ) -> RegisteredProvider: ...

    async def unregister(self, admin_id: str, provider_id: UUID) -> None: ...


class ModelServerErrorCode(StrEnum):
    local_install_disabled = "model_server_local_install_disabled"
    docker_unavailable = "model_server_docker_unavailable"
    engine_requires_gpu = "model_server_engine_requires_gpu"
    too_large = "model_server_too_large"
    invalid_input = "model_server_invalid_input"
    busy = "model_server_busy"
    not_found = "model_server_not_found"
    start_failed = "model_server_start_failed"


class ModelServerError(Exception):
    def __init__(self, code: ModelServerErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
