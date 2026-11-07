"""Установка сервера ИИ-модели на другой машине по SSH поверх общего слоя установки (`SshInstallService`).

Свой SSH здесь не пишется: сеанс, отпечаток хоста, SSRF-политика, учётные данные и ход по шагам приходят из слоя
установки раннеров. Этот модуль задаёт только «что запускать» (`SshPayload`): проверка видеокарты, контейнер движка,
модель, регистрация провайдера, проверка «модель отвечает».

Эндпоинт на удалённой машине по умолчанию слушает только loopback хоста. Открыть наружу (`public`) можно лишь для
движков с ключом API (vLLM, SGLang), с явным подтверждением; провайдер регистрируется только для открытого сервера,
иначе Студии до него не достучаться.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.model_servers import (
    CONTAINER_PREFIX,
    ENGINES,
    MAX_NAME,
    Engine,
    Exposure,
    IContainerRuntime,
    IModelProviderRegistry,
    IModelServerClient,
    IModelServerStore,
    ModelServerError,
    ModelServerErrorCode,
    ServerRecord,
    ServerStatus,
    StepState,
    Target,
    build_container_spec,
    valid_model_ref,
)
from hse_doc_studio.core.runner_install import InstallError, InstallStepState, ISshSession
from hse_doc_studio.use_cases.admin.model_servers import HfTokenVault, require_admin_actor
from hse_doc_studio.use_cases.runner_install.ssh_service import SshStepContext

# (сеанс, sudo, stdin sudo, внешний адрес, имя контейнера, порт) -> docker и клиент движка на удалённой машине
RemoteBuilder = Callable[[ISshSession, str, str, str, str, int], tuple[IContainerRuntime, IModelServerClient]]

SSH_STEPS = ("connect", "docker", "gpu", "container", "model", "provider", "verify")
_STATE = {
    InstallStepState.pending: StepState.pending,
    InstallStepState.running: StepState.running,
    InstallStepState.done: StepState.done,
    InstallStepState.failed: StepState.failed,
    InstallStepState.skipped: StepState.skipped,
}


class ModelServerSshPayload:
    steps: tuple[str, ...] = SSH_STEPS

    def __init__(  # noqa: PLR0913
        self,
        *,
        engine: Engine,
        model: str,
        name: str,
        exposure: Exposure,
        force: bool,
        image: str,
        store: IModelServerStore,
        registry: IModelProviderRegistry,
        vault: HfTokenVault | None,
        build: RemoteBuilder,
        ready_timeout_s: float,
        poll_s: float = 3.0,
    ) -> None:
        self.engine = engine
        self.model = model
        self.name = name
        self.exposure = exposure
        self.force = force
        self._image = image
        self._store = store
        self._registry = registry
        self._vault = vault
        self._build = build
        self._ready_timeout_s = ready_timeout_s
        self._poll_s = poll_s

    def secrets(self, ctx: SshStepContext) -> list[str]:
        return [ctx.state.get("api_key", ""), ctx.state.get("hf_token", "")]

    def _record(self, ctx: SshStepContext, status: ServerStatus) -> ServerRecord:
        job = ctx.job
        target = ctx.session.target
        return ServerRecord(
            id=job.id,
            engine=self.engine,
            model=self.model,
            name=self.name,
            target=Target.ssh,
            credential_id=ctx.session.credential_id,
            host=target.host,
            container=f"{CONTAINER_PREFIX}{job.id[:8]}",
            status=status,
            exposure=self.exposure,
            endpoint=ctx.state.get("endpoint"),
            provider_id=ctx.state.get("provider_id"),
            image=self._image,
            steps={s.key: _STATE[s.state] for s in job.steps},
            percent=ctx.state.get("percent"),
            text=job.steps[-1].detail if job.steps else "",
            error=job.error_code,
            created_by=job.created_by,
            created_at=job.created_at,
            updated_at=datetime.now(UTC),
        )

    async def _save(self, ctx: SshStepContext, status: ServerStatus = ServerStatus.installing) -> None:
        await self._store.save(self._record(ctx, status))

    async def run(self, ctx: SshStepContext) -> None:  # noqa: C901, PLR0915
        spec_engine = ENGINES[self.engine]
        await self._save(ctx)
        await ctx.ensure_docker()
        await self._save(ctx)

        ctx.step("gpu", InstallStepState.running)
        gpu = (await ctx.conn.run("nvidia-smi -L", timeout=30)).code == 0
        if spec_engine.needs_gpu and not gpu and not self.force:
            raise InstallError("engine_requires_gpu")
        ctx.step("gpu", InstallStepState.done, "nvidia" if gpu else "none")

        api_key = "" if self.engine is Engine.ollama else secrets.token_urlsafe(32)
        hf_token = await self._vault.reveal() if self._vault else ""
        ctx.state["api_key"], ctx.state["hf_token"] = api_key, hf_token
        provider_id = uuid4()
        spec = build_container_spec(
            self.engine,
            server_id=ctx.job.id[:8],
            model=self.model,
            name=self.name,
            image=self._image,
            api_key=api_key,
            hf_token=hf_token,
            gpu=gpu,
            provider_id=provider_id,
            bind="0.0.0.0" if self.exposure is Exposure.public else "127.0.0.1",  # noqa: S104 — только по подтверждению
        )
        public_host = ctx.session.target.host if self.exposure is Exposure.public else ""
        runtime, client = self._build(ctx.conn, ctx.sudo, ctx.sudo_stdin, public_host, spec.name, spec_engine.port)

        ctx.step("container", InstallStepState.running, spec.image)
        await self._save(ctx)
        await runtime.run(spec)
        ctx.step("container", InstallStepState.done)
        await self._save(ctx)

        ctx.step("model", InstallStepState.running)
        await self._wait_ready(ctx, client, spec_engine.health_path)
        if not spec_engine.model_at_start:
            async for event in client.pull("", self.model):
                if event.error:
                    raise InstallError("model_pull_failed", event.error)
        ctx.step("model", InstallStepState.done)
        ctx.state["percent"] = 100
        await self._save(ctx)

        base = (await runtime.endpoint(spec.name, spec_engine.port)) or ""
        ctx.state["endpoint"] = base if self.exposure is Exposure.public else None
        if self.exposure is Exposure.public:
            ctx.step("provider", InstallStepState.running)
            registered = await self._registry.register(
                ctx.actor.id or "",
                provider_id=provider_id,
                name=self.name,
                type=spec_engine.provider_type,
                base_url=f"{base}/v1",
                api_key=api_key,
                models=(self.model,),
            )
            ctx.state["provider_id"] = str(registered.id)
            ctx.step("provider", InstallStepState.done)
        else:
            # Студия не достучится до loopback чужой машины: провайдер не регистрируется, сервер доступен на ней самой.
            ctx.step("provider", InstallStepState.skipped, "localhost")

        ctx.step("verify", InstallStepState.running)
        ok = await client.ping("", self.model, api_key)
        ctx.step("verify", InstallStepState.done if ok else InstallStepState.failed)
        await self._save(ctx, ServerStatus.running)

    async def _wait_ready(self, ctx: SshStepContext, client: IModelServerClient, health_path: str) -> None:
        limit = self._ready_timeout_s if ENGINES[self.engine].model_at_start else 120.0
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            if await client.healthy("", health_path):
                return
            await asyncio.sleep(self._poll_s)
        raise InstallError("not_ready")

    async def on_failure(self, ctx: SshStepContext) -> None:
        await self._save(ctx, ServerStatus.failed)


class ModelServerSshInstaller:
    """Проверяет запрос админа и собирает `SshPayload` для общего слоя установки по SSH."""

    def __init__(  # noqa: PLR0913
        self,
        store: IModelServerStore,
        registry: IModelProviderRegistry,
        vault: HfTokenVault | None,
        build: RemoteBuilder,
        *,
        images: dict[Engine, str],
        ready_timeout_s: float,
    ) -> None:
        self._store = store
        self._registry = registry
        self._vault = vault
        self._build = build
        self._images = images
        self._ready_timeout_s = ready_timeout_s

    def payload(
        self,
        actor: Actor,
        *,
        engine: Engine,
        model: str,
        name: str,
        exposure: Exposure,
        acknowledge_public: bool,
        force: bool,
    ) -> ModelServerSshPayload:
        require_admin_actor(actor)
        model = model.strip()
        if not valid_model_ref(model):
            raise ModelServerError(
                ModelServerErrorCode.invalid_input,
                localized_error("Название модели задано неверно.", "The model name is not valid."),
            )
        label = name.strip() or f"{engine.value} {model}"
        if len(label) > MAX_NAME:
            raise ModelServerError(
                ModelServerErrorCode.invalid_input,
                localized_error("Слишком длинное название.", "The name is too long."),
            )
        if exposure is Exposure.internal:
            exposure = Exposure.localhost
        if exposure is Exposure.public:
            if engine is Engine.ollama:
                raise ModelServerError(
                    ModelServerErrorCode.public_needs_key,
                    localized_error(
                        "Ollama не умеет ключ API: открыть её наружу нельзя, оставьте доступ только с самой машины.",
                        "Ollama has no API key: it cannot be exposed. Keep it reachable from the machine itself.",
                    ),
                )
            if not acknowledge_public:
                raise ModelServerError(
                    ModelServerErrorCode.public_unconfirmed,
                    localized_error(
                        "Подтвердите, что сервер будет доступен из сети.",
                        "Confirm that the server will be reachable from the network.",
                    ),
                )
        return ModelServerSshPayload(
            engine=engine,
            model=model,
            name=label,
            exposure=exposure,
            force=force,
            image=self._images.get(engine) or ENGINES[engine].image,
            store=self._store,
            registry=self._registry,
            vault=self._vault,
            build=self._build,
            ready_timeout_s=self._ready_timeout_s,
        )
