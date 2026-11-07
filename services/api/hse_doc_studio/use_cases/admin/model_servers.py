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
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.ai_runtime import IHardwareProbe
from hse_doc_studio.core.entities import HardwareInfo
from hse_doc_studio.core.enums import GpuVendor
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.model_servers import (
    CONTAINER_PREFIX,
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
    Exposure,
    Fit,
    HostResources,
    IContainerRuntime,
    IHostResources,
    IModelProviderRegistry,
    IModelServerClient,
    IModelServerStore,
    IRemoteRuntimes,
    ModelServerError,
    ModelServerErrorCode,
    ServerRecord,
    ServerStatus,
    StepState,
    Target,
    build_container_spec,
    catalog_for,
    estimate_requirements,
    valid_model_ref,
)
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.core.uow import IUnitOfWork
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
    created_by: str = ""
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
    target: Target = Target.local
    host: str = ""
    exposure: Exposure = Exposure.internal
    manageable: bool = True


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


HF_TOKEN_KEY = "model_servers.hf_token"  # noqa: S105 — имя ключа настроек, не токен
_SECRET_TABLE = "instance_settings"  # noqa: S105
_SECRET_COLUMN = "secret_enc"  # noqa: S105
_MAX_TOKEN_LEN = 512


def require_admin_actor(actor: Actor) -> str:
    return require_admin(actor)


class HfTokenVault:
    """Токен Hugging Face: только шифртекст под ключом секретов. Значение наружу не отдаётся, в журналы не пишется."""

    def __init__(self, repo: IInstanceSettingsRepository, cipher: ISecretCipher) -> None:
        self._repo = repo
        self._cipher = cipher

    def _aad(self) -> str:
        return column_aad(_SECRET_TABLE, _SECRET_COLUMN, HF_TOKEN_KEY)

    async def is_set(self) -> bool:
        return await self._repo.get_secret(HF_TOKEN_KEY) is not None

    async def reveal(self) -> str:
        """Пустая строка, если токена нет или ключ шифрования недоступен: установка идёт без токена."""
        token = await self._repo.get_secret(HF_TOKEN_KEY)
        if token is None:
            return ""
        try:
            return self._cipher.decrypt(token, aad=self._aad()).reveal()
        except GitSyncError:
            return ""

    async def save(self, value: str) -> None:
        sealed = self._cipher.encrypt(Secret(value), aad=self._aad())
        await self._repo.set_secret(HF_TOKEN_KEY, sealed, source="admin")

    async def clear(self) -> None:
        await self._repo.delete(HF_TOKEN_KEY)


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
        vault: HfTokenVault | None = None,
        store: IModelServerStore | None = None,
        remote: IRemoteRuntimes | None = None,
    ) -> None:
        self._store = store
        self._remote = remote
        self._vault = vault
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
        job = Job(id=uuid4().hex[:8], engine=request.engine, model=model, name=name, created_by=admin_id)
        self._jobs[job.id] = job
        await self._persist(job)
        gpu = hardware.gpu_vendor is GpuVendor.nvidia and hardware.docker_gpu_supported
        job.task = asyncio.create_task(self._run(admin_id, job, gpu))
        return self._job_view(job)

    # ── состояние в базе ───────────────────────────────────────────────────

    def _record(self, job: Job, status: ServerStatus | None = None) -> ServerRecord:
        if status is None:
            status = (
                ServerStatus.failed
                if job.error
                else ServerStatus.installing
                if not job.finished
                else ServerStatus.running
            )
        return ServerRecord(
            id=job.id,
            engine=job.engine,
            model=job.model,
            name=job.name,
            target=Target.local,
            credential_id=None,
            host="",
            container=f"{CONTAINER_PREFIX}{job.id}",
            status=status,
            exposure=Exposure.internal,
            endpoint=None,
            provider_id=str(job.provider_id) if job.provider_id else None,
            image=self._image(job.engine),
            steps=dict(job.steps),
            percent=job.percent,
            text=job.text,
            error=job.error,
            created_by=job.created_by,
            created_at=job.created_at,
            updated_at=datetime.now(UTC),
        )

    async def _persist(self, job: Job) -> None:
        if self._store is None:
            return
        try:
            await self._store.save(self._record(job))
        except Exception:
            logger.exception("model server state was not saved", server=job.id)

    async def _set(self, job: Job, key: str, state: StepState) -> None:
        job.steps[key] = state
        await self._persist(job)

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
            await self._persist(job)

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
            hf_token=await self._vault.reveal() if self._vault else "",
            gpu=gpu,
            provider_id=provider_id,
        )
        await self._set(job, "container", StepState.running)
        job.note(f"docker run {spec.image}")
        await self._runtime.run(spec)
        await self._set(job, "container", StepState.done)

        await self._set(job, "engine", StepState.running)
        base = await self._wait_endpoint(spec.name, spec_engine.port)
        if spec_engine.model_at_start:
            await self._set(job, "engine", StepState.done)
            await self._set(job, "model", StepState.running)
            await self._wait_ready(job, spec.name, base, spec_engine.health_path, api_key)
        else:
            await self._wait_ready(job, spec.name, base, spec_engine.health_path, api_key)
            await self._set(job, "engine", StepState.done)
            await self._set(job, "model", StepState.running)
            await self._pull(job, base)
        await self._set(job, "model", StepState.done)
        job.percent = 100

        await self._set(job, "provider", StepState.running)
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
        await self._set(job, "provider", StepState.done)

        await self._set(job, "verify", StepState.running)
        if await self._client.ping(base, job.model, api_key):
            await self._set(job, "verify", StepState.done)
            job.note(localized_error("Модель отвечает.", "The model responds."))
        else:
            # Сервер и провайдер уже есть и могут заработать позже (первая генерация грузит веса): это предупреждение.
            await self._set(job, "verify", StepState.failed)
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
        rec = self._record(job)
        return self._record_view(rec, None)

    def _record_view(self, rec: ServerRecord, endpoint: str | None) -> ServerView:
        return ServerView(
            id=rec.id,
            engine=rec.engine,
            model=rec.model,
            name=rec.name,
            status=rec.status,
            endpoint=endpoint if endpoint is not None else rec.endpoint,
            provider_id=UUID(rec.provider_id) if rec.provider_id else None,
            image=rec.image,
            steps=dict(rec.steps),
            percent=rec.percent,
            text=rec.text,
            error=rec.error,
            target=rec.target,
            host=rec.host,
            exposure=rec.exposure,
            manageable=rec.target is Target.local or rec.credential_id is not None,
        )

    def _missing_container(self, rec: ServerRecord | None, job: Job | None) -> ServerView | None:
        if job is not None:
            return self._job_view(job)
        if rec is None:
            return None
        # Запись есть, контейнера нет: перезапуск оборвал установку либо контейнер удалили вручную.
        if rec.status is ServerStatus.installing:
            error = localized_error("Установка прервана перезапуском Студии.", "The install was interrupted.")
            return self._record_view(replace(rec, status=ServerStatus.failed, error=error), None)
        return self._record_view(replace(rec, status=ServerStatus.stopped), None)

    @staticmethod
    def _adopt(info: ContainerInfo, status: ServerStatus) -> ServerRecord:
        """Контейнер без записи (поставлен до появления базы): показываем по меткам."""
        labels = info.labels
        return ServerRecord(
            id=labels.get(LABEL_SERVER, ""),
            engine=Engine(labels.get(LABEL_ENGINE, Engine.ollama.value)),
            model=labels.get(LABEL_MODEL, ""),
            name=labels.get(LABEL_NAME, info.name),
            target=Target.local,
            credential_id=None,
            host="",
            container=info.name,
            status=status,
            exposure=Exposure.internal,
            endpoint=None,
            provider_id=labels.get(LABEL_PROVIDER),
            image=info.image,
            steps=dict.fromkeys(STEPS, StepState.done),
            percent=None,
            text="",
            error=None,
            created_by="",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    async def _view(self, rec: ServerRecord | None, info: ContainerInfo | None, job: Job | None) -> ServerView | None:
        if job is not None and not job.finished:
            return self._job_view(job)
        if rec is not None and rec.target is Target.ssh:
            return self._record_view(rec, None)
        if info is None:
            return self._missing_container(rec, job)
        status = ServerStatus.running if info.running else ServerStatus.stopped
        if (job is not None and job.error) or (rec is not None and rec.status is ServerStatus.failed):
            status = ServerStatus.failed
        base = self._record(job) if job is not None else (rec or self._adopt(info, status))
        endpoint = await self._runtime.endpoint(info.name, ENGINES[base.engine].port) if info.running else None
        return self._record_view(replace(base, status=status, image=info.image), endpoint)

    async def _all(self) -> list[tuple[ServerRecord | None, ContainerInfo | None, Job | None]]:
        infos = {i.labels.get(LABEL_SERVER, ""): i for i in await self._runtime.list_managed()}
        records = {r.id: r for r in await self._store.list()} if self._store is not None else {}
        ids = dict.fromkeys([*records, *infos, *self._jobs])
        return [(records.get(i), infos.get(i), self._jobs.get(i)) for i in ids]

    async def list(self) -> list[ServerView]:
        views = [await self._view(*row) for row in await self._all()]
        return [v for v in views if v is not None]

    async def _entry(self, server_id: str) -> tuple[ServerRecord | None, ContainerInfo | None, Job | None]:
        for rec, info, job in await self._all():
            if (
                (rec and rec.id == server_id)
                or (info and info.labels.get(LABEL_SERVER) == server_id)
                or (job and job.id == server_id)
            ):
                return rec, info, job
        raise _not_found()

    async def get(self, server_id: str) -> ServerView:
        view = await self._view(*await self._entry(server_id))
        if view is None:
            raise _not_found()
        return view

    @staticmethod
    def _not_manageable() -> ModelServerError:
        return ModelServerError(
            ModelServerErrorCode.not_manageable,
            localized_error(
                "Для этого сервера не сохранён SSH-доступ: управлять им отсюда нельзя.",
                "No SSH access is saved for this server, so it cannot be managed from here.",
            ),
        )

    async def _runtime_for(
        self, actor: Actor | None, rec: ServerRecord | None
    ) -> tuple[IContainerRuntime, Callable[[], Awaitable[None]]]:
        async def nothing() -> None:
            return None

        if rec is None or rec.target is Target.local:
            return self._runtime, nothing
        if not rec.credential_id or self._remote is None or actor is None:
            raise self._not_manageable()
        try:
            opened = await self._remote.open(
                actor, rec.credential_id, rec.host if rec.exposure is Exposure.public else ""
            )
        except Exception as exc:
            raise ModelServerError(
                ModelServerErrorCode.start_failed,
                localized_error("Не удалось подключиться по SSH.", "Could not connect over SSH."),
            ) from exc
        return opened.runtime, opened.close

    async def logs(self, server_id: str, tail: int, actor: Actor | None = None) -> str:
        rec, info, job = await self._entry(server_id)
        runtime, close = await self._runtime_for(actor, rec)
        try:
            name = rec.container if rec else f"{CONTAINER_PREFIX}{server_id}"
            text = await runtime.logs(name, tail)
        finally:
            await close()
        if not text and job is not None:
            return "\n".join(job.log)
        return text

    async def _set_status(self, rec: ServerRecord | None, status: ServerStatus) -> None:
        if rec is not None and self._store is not None:
            await self._store.save(replace(rec, status=status, updated_at=datetime.now(UTC)))

    async def start(self, server_id: str, actor: Actor | None = None) -> ServerView:
        rec, _info, _job = await self._entry(server_id)
        runtime, close = await self._runtime_for(actor, rec)
        try:
            ok = await runtime.start(rec.container if rec else f"{CONTAINER_PREFIX}{server_id}")
        finally:
            await close()
        if not ok:
            raise ModelServerError(
                ModelServerErrorCode.start_failed,
                localized_error("Не удалось запустить сервер.", "Could not start the server."),
            )
        await self._set_status(rec, ServerStatus.running)
        return await self.get(server_id)

    async def stop(self, server_id: str, actor: Actor | None = None) -> ServerView:
        rec, _info, _job = await self._entry(server_id)
        runtime, close = await self._runtime_for(actor, rec)
        try:
            await runtime.stop(rec.container if rec else f"{CONTAINER_PREFIX}{server_id}")
        finally:
            await close()
        await self._set_status(rec, ServerStatus.stopped)
        return await self.get(server_id)

    async def remove(
        self, admin_id: str, server_id: str, *, purge_models: bool = False, actor: Actor | None = None
    ) -> ServerView:
        rec, _info, job = await self._entry(server_id)
        view = await self.get(server_id)
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
        name = rec.container if rec else f"{CONTAINER_PREFIX}{server_id}"
        if rec is not None and rec.target is Target.ssh and not rec.credential_id:
            # Доступа нет: удаляем только запись и провайдера, контейнер на хосте остаётся (админ уберёт его сам).
            pass
        else:
            runtime, close = await self._runtime_for(actor, rec)
            try:
                await runtime.remove(name, volume=volume)
            finally:
                await close()
        if view.provider_id is not None:
            with suppress(Exception):
                await self._registry.unregister(admin_id, view.provider_id)
        if self._store is not None:
            await self._store.delete(server_id)
        self._jobs.pop(server_id, None)
        return view

    async def wait_idle(self) -> None:
        """Для тестов: дождаться фоновых установок."""
        tasks = [j.task for j in self._jobs.values() if j.task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


class ModelServersUC:
    """Запросный фасад: проверка админа и аудит поверх `ModelServerService`. Секретов в аудите нет."""

    def __init__(
        self,
        service: ModelServerService,
        audit: IAuditLog,
        vault: HfTokenVault | None = None,
        uow: IUnitOfWork | None = None,
    ) -> None:
        self._service = service
        self._audit = audit
        self._vault = vault
        self._uow = uow

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
        return await self._service.logs(server_id, tail, actor)

    async def start(self, actor: Actor, server_id: str) -> ServerView:
        admin_id = require_admin(actor)
        view = await self._service.start(server_id, actor)
        await self._audit.record("model_server.start", actor_id=admin_id, target=server_id)
        return view

    async def stop(self, actor: Actor, server_id: str) -> ServerView:
        admin_id = require_admin(actor)
        view = await self._service.stop(server_id, actor)
        await self._audit.record("model_server.stop", actor_id=admin_id, target=server_id)
        return view

    async def remove(self, actor: Actor, server_id: str, *, purge_models: bool) -> None:
        admin_id = require_admin(actor)
        view = await self._service.remove(admin_id, server_id, purge_models=purge_models, actor=actor)
        await self._audit.record(
            "model_server.remove",
            actor_id=admin_id,
            target=server_id,
            details={"engine": view.engine.value, "model": view.model, "purge_models": purge_models},
        )

    async def hf_token_set(self, actor: Actor) -> bool:
        require_admin(actor)
        assert self._vault is not None  # noqa: S101
        return await self._vault.is_set()

    async def save_hf_token(self, actor: Actor, value: str) -> None:
        admin_id = require_admin(actor)
        token = value.strip()
        if not token or len(token) > _MAX_TOKEN_LEN or any(c.isspace() for c in token):
            raise _invalid("Токен задан неверно.", "The token is not valid.")
        assert self._vault is not None  # noqa: S101
        assert self._uow is not None  # noqa: S101
        async with self._uow.begin():
            await self._vault.save(token)
            await self._audit.record("model_server.hf_token_set", actor_id=admin_id)

    async def clear_hf_token(self, actor: Actor) -> None:
        admin_id = require_admin(actor)
        assert self._vault is not None  # noqa: S101
        assert self._uow is not None  # noqa: S101
        async with self._uow.begin():
            await self._vault.clear()
            await self._audit.record("model_server.hf_token_clear", actor_id=admin_id)
