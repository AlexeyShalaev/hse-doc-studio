"""Серверы ИИ-моделей, поставленные из админки: установка рядом со Студией, запуск, остановка, журнал, удаление.

Состояние установки (шаги, ход загрузки, журнал) живёт в памяти процесса и теряется при перезапуске. Сами серверы
находятся по меткам контейнеров, поэтому после перезапуска они на месте, а статус берётся у докера.
Секреты (ключ API сервера, токен Hugging Face) в ответы, аудит и журнал не попадают.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from collections import deque
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.ai_runtime import IHardwareProbe
from hse_doc_studio.core.entities import HardwareInfo
from hse_doc_studio.core.enums import GpuVendor
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.model_servers import (
    ENGINES,
    LABEL_ENGINE,
    LABEL_MODEL,
    LABEL_NAME,
    LABEL_PROVIDER,
    LABEL_SERVER,
    MAX_NAME,
    CatalogModel,
    ContainerInfo,
    ContainerRunError,
    Engine,
    Estimate,
    Fit,
    HostResources,
    IContainerRuntime,
    IHostResources,
    IModelProviderRegistry,
    IModelServerClient,
    ModelServerError,
    ModelServerErrorCode,
    ServerStatus,
    StepState,
    build_container_spec,
    catalog_for,
    estimate_requirements,
    valid_model_ref,
)
from hse_doc_studio.use_cases.admin.users import require_admin

logger = structlog.get_logger()

STEPS = ("container", "engine", "model", "provider", "verify")
_LOG_LIMIT = 200
_POLL_S = 2.0


@dataclass(frozen=True)
class ModelServerSettings:
    local_enabled: bool = True
    images: Mapping[Engine, str] = field(default_factory=dict)
    max_concurrent_installs: int = 1
    startup_timeout_s: float = 120.0
    ready_timeout_s: float = 3600.0


@dataclass
class Job:
    id: str
    engine: Engine
    model: str
    name: str
    steps: dict[str, StepState] = field(default_factory=lambda: dict.fromkeys(STEPS, StepState.pending))
    percent: int | None = None
    text: str = ""
    error: str | None = None
    finished: bool = False
    provider_id: UUID | None = None
    log: deque[str] = field(default_factory=lambda: deque(maxlen=_LOG_LIMIT))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    task: asyncio.Task[None] | None = None

    def note(self, line: str) -> None:
        self.log.append(line)
        self.text = line


@dataclass(frozen=True)
class EngineAvailability:
    engine: Engine
    image: str
    available: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Capabilities:
    local_enabled: bool
    docker_available: bool
    hardware: HardwareInfo
    resources: HostResources
    engines: tuple[EngineAvailability, ...]


@dataclass(frozen=True)
class ServerView:
    id: str
    engine: Engine
    model: str
    name: str
    status: ServerStatus
    endpoint: str | None
    provider_id: UUID | None
    image: str
    steps: Mapping[str, StepState]
    percent: int | None
    text: str
    error: str | None


@dataclass(frozen=True)
class InstallRequest:
    engine: Engine
    model: str
    name: str = ""
    force: bool = False


def _invalid(ru: str, en: str) -> ModelServerError:
    return ModelServerError(ModelServerErrorCode.invalid_input, localized_error(ru, en))


def _not_found() -> ModelServerError:
    return ModelServerError(ModelServerErrorCode.not_found, localized_error("Сервер не найден.", "Server not found."))


def engine_availability(engine: Engine, hardware: HardwareInfo, image: str) -> EngineAvailability:
    reasons: list[str] = []
    if ENGINES[engine].needs_gpu:
        if hardware.gpu_vendor is not GpuVendor.nvidia:
            reasons.append("engine_requires_gpu")
        elif not hardware.docker_gpu_supported:
            reasons.append("docker_gpu_unsupported")
    return EngineAvailability(engine, image, not reasons, tuple(reasons))


class ModelServerService:
    """Состояние и работа с серверами. Живёт в APP-скоупе: фоновые установки переживают запрос."""

    def __init__(  # noqa: PLR0913 — порты
        self,
        runtime: IContainerRuntime,
        client: IModelServerClient,
        hardware: IHardwareProbe,
        resources: IHostResources,
        registry: IModelProviderRegistry,
        settings: ModelServerSettings,
    ) -> None:
        self._runtime = runtime
        self._client = client
        self._hardware = hardware
        self._resources = resources
        self._registry = registry
        self._settings = settings
        self._jobs: dict[str, Job] = {}

    def _image(self, engine: Engine) -> str:
        return self._settings.images.get(engine) or ENGINES[engine].image

    # ── сведения до установки ──────────────────────────────────────────────

    async def capabilities(self) -> Capabilities:
        hardware = await self._hardware.detect()
        return Capabilities(
            local_enabled=self._settings.local_enabled,
            docker_available=await self._runtime.available() if self._settings.local_enabled else False,
            hardware=hardware,
            resources=await self._resources.read(),
            engines=tuple(engine_availability(e, hardware, self._image(e)) for e in Engine),
        )

    async def estimate(self, engine: Engine, model: str, params_b: float | None) -> Estimate:
        if not valid_model_ref(model):
            raise _invalid("Название модели задано неверно.", "The model name is not valid.")
        return estimate_requirements(
            engine, model, await self._hardware.detect(), await self._resources.read(), params_b=params_b
        )

    @staticmethod
    def catalog(engine: Engine, query: str) -> list[CatalogModel]:
        return catalog_for(engine, query)

    # ── установка ──────────────────────────────────────────────────────────

    async def start_install(self, admin_id: str, request: InstallRequest) -> ServerView:
        self._require_local()
        model = request.model.strip()
        if not valid_model_ref(model):
            raise _invalid("Название модели задано неверно.", "The model name is not valid.")
        name = request.name.strip() or f"{request.engine.value} {model}"
        if len(name) > MAX_NAME:
            raise _invalid("Слишком длинное название.", "The name is too long.")
        if sum(1 for j in self._jobs.values() if not j.finished) >= self._settings.max_concurrent_installs:
            raise ModelServerError(
                ModelServerErrorCode.busy,
                localized_error("Уже идёт другая установка. Дождитесь её окончания.", "Another install is running."),
            )
        if not await self._runtime.available():
            raise ModelServerError(
                ModelServerErrorCode.docker_unavailable,
                localized_error("Docker недоступен Студии.", "Docker is not available to the Studio."),
            )
        hardware = await self._hardware.detect()
        availability = engine_availability(request.engine, hardware, self._image(request.engine))
        if not availability.available and not request.force:
            raise ModelServerError(
                ModelServerErrorCode.engine_requires_gpu,
                localized_error(
                    "Этому движку нужна видеокарта NVIDIA, доступная Docker.",
                    "This engine needs an NVIDIA GPU that Docker can use.",
                ),
            )
        estimate = estimate_requirements(request.engine, model, hardware, await self._resources.read())
        if estimate.fit is Fit.too_large and not request.force:
            raise ModelServerError(
                ModelServerErrorCode.too_large,
                localized_error("Модель не поместится в память этой машины.", "The model will not fit into memory."),
            )
        job = Job(id=uuid4().hex[:8], engine=request.engine, model=model, name=name)
        self._jobs[job.id] = job
        gpu = hardware.gpu_vendor is GpuVendor.nvidia and hardware.docker_gpu_supported
        job.task = asyncio.create_task(self._run(admin_id, job, gpu))
        return self._job_view(job)

    def _require_local(self) -> None:
        if not self._settings.local_enabled:
            raise ModelServerError(
                ModelServerErrorCode.local_install_disabled,
                localized_error(
                    "Установка на машине со Студией выключена администратором кластера.",
                    "Installing next to the Studio is turned off by the cluster administrator.",
                ),
            )

    async def _run(self, admin_id: str, job: Job, gpu: bool) -> None:
        try:
            await self._install(admin_id, job, gpu)
        except ModelServerError as exc:
            self._fail(job, exc.message)
        except ContainerRunError as exc:
            self._fail(job, str(exc))
        except Exception:
            logger.exception("model server install crashed", server=job.id)
            self._fail(job, localized_error("Установка прервалась из-за внутренней ошибки.", "The install crashed."))
        finally:
            job.finished = True

    def _fail(self, job: Job, message: str) -> None:
        job.error = message
        job.note(message)
        for key, state in job.steps.items():
            if state is StepState.running:
                job.steps[key] = StepState.failed

    async def _install(self, admin_id: str, job: Job, gpu: bool) -> None:
        spec_engine = ENGINES[job.engine]
        api_key = "" if job.engine is Engine.ollama else secrets.token_urlsafe(32)
        provider_id = uuid4()
        spec = build_container_spec(
            job.engine,
            server_id=job.id,
            model=job.model,
            name=job.name,
            image=self._image(job.engine),
            api_key=api_key,
            gpu=gpu,
            provider_id=provider_id,
        )
        job.steps["container"] = StepState.running
        job.note(f"docker run {spec.image}")
        await self._runtime.run(spec)
        job.steps["container"] = StepState.done

        job.steps["engine"] = StepState.running
        base = await self._wait_endpoint(spec.name, spec_engine.port)
        if spec_engine.model_at_start:
            job.steps["engine"] = StepState.done
            job.steps["model"] = StepState.running
            await self._wait_ready(job, spec.name, base, spec_engine.health_path, api_key)
        else:
            await self._wait_ready(job, spec.name, base, spec_engine.health_path, api_key)
            job.steps["engine"] = StepState.done
            job.steps["model"] = StepState.running
            await self._pull(job, base)
        job.steps["model"] = StepState.done
        job.percent = 100

        job.steps["provider"] = StepState.running
        v1 = f"{base}/v1"
        registered = await self._registry.register(
            admin_id,
            provider_id=provider_id,
            name=job.name,
            type=spec_engine.provider_type,
            base_url=v1,
            api_key=api_key,
            models=(job.model,),
        )
        job.provider_id = registered.id
        job.steps["provider"] = StepState.done

        job.steps["verify"] = StepState.running
        if await self._client.ping(base, job.model, api_key):
            job.steps["verify"] = StepState.done
            job.note(localized_error("Модель отвечает.", "The model responds."))
        else:
            # Сервер и провайдер уже есть и могут заработать позже (первая генерация грузит веса): это предупреждение.
            job.steps["verify"] = StepState.failed
            job.note(localized_error("Модель пока не отвечает.", "The model does not respond yet."))

    async def _wait_endpoint(self, name: str, port: int) -> str:
        deadline = time.monotonic() + self._settings.startup_timeout_s
        while time.monotonic() < deadline:
            url = await self._runtime.endpoint(name, port)
            if url:
                return url.rstrip("/")
            await asyncio.sleep(_POLL_S)
        raise ModelServerError(
            ModelServerErrorCode.start_failed,
            localized_error("Контейнер запущен, но адрес не определился.", "The container started but has no address."),
        )

    async def _wait_ready(self, job: Job, name: str, base: str, health_path: str, api_key: str) -> None:
        limit = (
            self._settings.ready_timeout_s if ENGINES[job.engine].model_at_start else self._settings.startup_timeout_s
        )
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            if await self._client.healthy(base, health_path, api_key):
                return
            info = await self._runtime.inspect(name)
            if info is None or not info.running:
                tail = (await self._runtime.logs(name, 20)).strip().splitlines()
                raise ModelServerError(
                    ModelServerErrorCode.start_failed,
                    localized_error("Контейнер остановился при запуске.", "The container stopped while starting.")
                    + (f" {tail[-1][:200]}" if tail else ""),
                )
            tail = (await self._runtime.logs(name, 1)).strip().splitlines()
            if tail:
                job.text = tail[-1][:200]
            await asyncio.sleep(_POLL_S)
        raise ModelServerError(
            ModelServerErrorCode.start_failed,
            localized_error("Сервер не стал готов вовремя.", "The server did not become ready in time."),
        )

    async def _pull(self, job: Job, base: str) -> None:
        async for event in self._client.pull(base, job.model):
            if event.error:
                raise ModelServerError(
                    ModelServerErrorCode.start_failed,
                    localized_error("Не удалось скачать модель: ", "Could not download the model: ") + event.error,
                )
            if event.percent is not None:
                job.percent = event.percent
            if event.text:
                job.note(event.text)
            if event.done:
                return
        raise ModelServerError(
            ModelServerErrorCode.start_failed,
            localized_error("Загрузка модели оборвалась.", "The model download was interrupted."),
        )

    # ── просмотр и управление ──────────────────────────────────────────────

    def _job_view(self, job: Job) -> ServerView:
        status = (
            ServerStatus.failed if job.error else ServerStatus.installing if not job.finished else ServerStatus.running
        )
        return ServerView(
            id=job.id,
            engine=job.engine,
            model=job.model,
            name=job.name,
            status=status,
            endpoint=None,
            provider_id=job.provider_id,
            image=self._image(job.engine),
            steps=dict(job.steps),
            percent=job.percent,
            text=job.text,
            error=job.error,
        )

    async def _view(self, info: ContainerInfo | None, job: Job | None) -> ServerView | None:
        if info is None and job is None:
            return None
        if info is None:
            assert job is not None  # noqa: S101
            return self._job_view(job)
        labels = info.labels
        engine = Engine(labels.get(LABEL_ENGINE, Engine.ollama.value))
        endpoint = await self._runtime.endpoint(info.name, ENGINES[engine].port) if info.running else None
        raw_provider = labels.get(LABEL_PROVIDER)
        status = ServerStatus.running if info.running else ServerStatus.stopped
        if job is not None and not job.finished:
            status = ServerStatus.installing
        elif job is not None and job.error:
            status = ServerStatus.failed
        return ServerView(
            id=labels.get(LABEL_SERVER, ""),
            engine=engine,
            model=labels.get(LABEL_MODEL, ""),
            name=labels.get(LABEL_NAME, info.name),
            status=status,
            endpoint=endpoint,
            provider_id=UUID(raw_provider) if raw_provider else None,
            image=info.image,
            steps=dict(job.steps) if job else dict.fromkeys(STEPS, StepState.done),
            percent=job.percent if job else None,
            text=job.text if job else "",
            error=job.error if job else None,
        )

    async def list(self) -> list[ServerView]:
        infos = {i.labels.get(LABEL_SERVER, ""): i for i in await self._runtime.list_managed()}
        views: list[ServerView] = []
        for server_id in dict.fromkeys([*infos, *self._jobs]):
            view = await self._view(infos.get(server_id), self._jobs.get(server_id))
            if view is not None:
                views.append(view)
        return views

    async def get(self, server_id: str) -> ServerView:
        infos = {i.labels.get(LABEL_SERVER, ""): i for i in await self._runtime.list_managed()}
        view = await self._view(infos.get(server_id), self._jobs.get(server_id))
        if view is None:
            raise _not_found()
        return view

    async def logs(self, server_id: str, tail: int) -> str:
        view = await self.get(server_id)
        job = self._jobs.get(server_id)
        text = await self._runtime.logs(f"hse-ms-{view.id}", tail)
        if not text and job is not None:
            return "\n".join(job.log)
        return text

    async def start(self, server_id: str) -> ServerView:
        view = await self.get(server_id)
        if not await self._runtime.start(f"hse-ms-{view.id}"):
            raise ModelServerError(
                ModelServerErrorCode.start_failed,
                localized_error("Не удалось запустить сервер.", "Could not start the server."),
            )
        return await self.get(server_id)

    async def stop(self, server_id: str) -> ServerView:
        view = await self.get(server_id)
        await self._runtime.stop(f"hse-ms-{view.id}")
        return await self.get(server_id)

    async def remove(self, admin_id: str, server_id: str, *, purge_models: bool = False) -> ServerView:
        view = await self.get(server_id)
        job = self._jobs.get(server_id)
        if job is not None and not job.finished:
            raise ModelServerError(
                ModelServerErrorCode.busy,
                localized_error("Установка ещё идёт.", "The install is still running."),
            )
        volume: str | None = None
        if purge_models:
            siblings = [v for v in await self.list() if v.engine is view.engine and v.id != view.id]
            if siblings:
                raise ModelServerError(
                    ModelServerErrorCode.busy,
                    localized_error(
                        "Тома с моделями делят другие серверы этого движка.",
                        "Other servers of this engine share the models volume.",
                    ),
                )
            volume = build_container_spec(view.engine, server_id=view.id, model=view.model).volume[0]
        await self._runtime.remove(f"hse-ms-{view.id}", volume=volume)
        if view.provider_id is not None:
            with suppress(Exception):
                await self._registry.unregister(admin_id, view.provider_id)
        self._jobs.pop(server_id, None)
        return view

    async def wait_idle(self) -> None:
        """Для тестов: дождаться фоновых установок."""
        tasks = [j.task for j in self._jobs.values() if j.task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


class ModelServersUC:
    """Запросный фасад: проверка админа и аудит поверх `ModelServerService`. Секретов в аудите нет."""

    def __init__(self, service: ModelServerService, audit: IAuditLog) -> None:
        self._service = service
        self._audit = audit

    async def capabilities(self, actor: Actor) -> Capabilities:
        require_admin(actor)
        return await self._service.capabilities()

    async def catalog(self, actor: Actor, engine: Engine, query: str) -> list[CatalogModel]:
        require_admin(actor)
        return self._service.catalog(engine, query)

    async def estimate(self, actor: Actor, engine: Engine, model: str, params_b: float | None) -> Estimate:
        require_admin(actor)
        return await self._service.estimate(engine, model, params_b)

    async def install(self, actor: Actor, request: InstallRequest) -> ServerView:
        admin_id = require_admin(actor)
        view = await self._service.start_install(admin_id, request)
        await self._audit.record(
            "model_server.install",
            actor_id=admin_id,
            target=view.id,
            details={"engine": request.engine.value, "model": view.model, "target": "local", "force": request.force},
        )
        return view

    async def list(self, actor: Actor) -> list[ServerView]:
        require_admin(actor)
        return await self._service.list()

    async def get(self, actor: Actor, server_id: str) -> ServerView:
        require_admin(actor)
        return await self._service.get(server_id)

    async def logs(self, actor: Actor, server_id: str, tail: int) -> str:
        require_admin(actor)
        return await self._service.logs(server_id, tail)

    async def start(self, actor: Actor, server_id: str) -> ServerView:
        admin_id = require_admin(actor)
        view = await self._service.start(server_id)
        await self._audit.record("model_server.start", actor_id=admin_id, target=server_id)
        return view

    async def stop(self, actor: Actor, server_id: str) -> ServerView:
        admin_id = require_admin(actor)
        view = await self._service.stop(server_id)
        await self._audit.record("model_server.stop", actor_id=admin_id, target=server_id)
        return view

    async def remove(self, actor: Actor, server_id: str, *, purge_models: bool) -> None:
        admin_id = require_admin(actor)
        view = await self._service.remove(admin_id, server_id, purge_models=purge_models)
        await self._audit.record(
            "model_server.remove",
            actor_id=admin_id,
            target=server_id,
            details={"engine": view.engine.value, "model": view.model, "purge_models": purge_models},
        )
