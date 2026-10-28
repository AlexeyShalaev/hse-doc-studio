import asyncio
import json
import os
from contextlib import suppress

import structlog
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from hse_doc_studio.api.config import Settings, settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.logging_setup import configure_logging
from hse_doc_studio.api.observability.install import (
    install_background,
    install_health,
    install_server_observability,
)
from hse_doc_studio.api.rate_limit import install_rate_limiter
from hse_doc_studio.api.routers.v1 import api_router
from hse_doc_studio.api.security_install import install_server_security
from hse_doc_studio.api.server_setup import prepare_server_setup
from hse_doc_studio.core.ai_runtime import IOllamaRuntime
from hse_doc_studio.core.git_sync.protocols import IGitRemoteRegistry
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.readiness import (
    ReadinessZone,
    ServerReadinessCheck,
    ServerReadinessRegistry,
    server_readiness,
)
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.di.containers.api import create_container
from hse_doc_studio.infra.docker.cli import configure_docker_binary, image_present, run_docker
from hse_doc_studio.infra.git_sync.fetch_scheduler import GitFetchScheduler
from hse_doc_studio.infra.git_sync.ssh_command import sweep_stale_key_dirs
from hse_doc_studio.infra.languagetool.container_manager import LanguageToolContainerManager
from hse_doc_studio.infra.office.convert_manager import OfficeConvertManager
from hse_doc_studio.infra.office.editor_manager import OfficeEditorManager
from hse_doc_studio.infra.update.auto_update_scheduler import AutoUpdateScheduler
from hse_doc_studio.infra.update.deployment import docker_alive
from hse_doc_studio.use_cases.ai_runtime.sync_local_provider import SyncLocalOllamaProviderUC
from hse_doc_studio.use_cases.chat.recover_stale_chat_runs import RecoverStaleChatRunsUC
from hse_doc_studio.use_cases.compile.list_images import resolve_active_image
from hse_doc_studio.use_cases.compile.recover_stale_compiles import RecoverStaleCompilesUC
from hse_doc_studio.use_cases.fonts.adopt_host_fonts import AdoptHostFontsUC
from hse_doc_studio.use_cases.git_sync.fetch_all_remotes import FetchAllGitRemotesUC, FetchTickResult
from hse_doc_studio.use_cases.setup.inspect_setup import InspectSetupUC
from hse_doc_studio.use_cases.system.auto_update import AutoUpdateResult, AutoUpdateUC
from hse_doc_studio.use_cases.template_update.recover_template_updates import RecoverTemplateUpdatesUC

logger = structlog.get_logger(__name__)

# Образ TeX — несколько гигабайт; на медленном канале это десятки минут.
_TEX_PULL_TIMEOUT_S = 3600.0


_secrets_cfg_by_registry: dict[int, Settings] = {}


def _register_secrets_check(cfg: Settings, readiness: ServerReadinessRegistry) -> None:
    from hse_doc_studio.infra.secrets.server_keys import secrets_key_problem  # noqa: PLC0415

    # create_app зовут не один раз за процесс (тесты, перезапуск воркера): проверка одна, настройки берутся свежие
    _secrets_cfg_by_registry[id(readiness)] = cfg
    check = ServerReadinessCheck(
        ReadinessZone.persistence,
        "secrets_key",
        lambda: secrets_key_problem(_secrets_cfg_by_registry[id(readiness)]),
    )
    with suppress(ValueError):
        readiness.register(check)


def _register_per_user_routes_check(readiness: ServerReadinessRegistry) -> None:
    from hse_doc_studio.api.route_scopes import per_user_routes_problem  # noqa: PLC0415

    check = ServerReadinessCheck(ReadinessZone.per_user_routes, "global_user_routes", per_user_routes_problem)
    with suppress(ValueError):
        readiness.register(check)


def ensure_supported_mode(cfg: Settings, readiness: ServerReadinessRegistry = server_readiness) -> None:
    """Отказать на старте в режиме, которого пока нет (общий сервер — этап 2 совместной работы).

    Server пускают, только когда все зоны зарегистрировали проверки готовности и все они зелёные.
    """
    if cfg.mode is StudioMode.server:
        _register_secrets_check(cfg, readiness)
        _register_per_user_routes_check(readiness)
        problems = readiness.unmet()
        if problems:
            msg = (
                "HSE_STUDIO__MODE=server is not supported yet (stage 2 of collaboration); use local. "
                f"Not ready: {'; '.join(problems)}"
            )
            raise RuntimeError(msg)


def create_app() -> FastAPI:  # noqa: C901, PLR0915 — app-wiring factory: routers, DI, lifecycle hooks
    """Factory function for uvicorn to create the app instance."""
    ensure_supported_mode(settings)
    configure_logging()
    app = FastAPI(
        title="hse-doc-studio",
        version=settings.get_app_version(),
        openapi_url="/system/openapi.json",
        docs_url="/system/docs",
        redoc_url="/system/redoc",
        redirect_slashes=False,
    )

    app.add_middleware(GZipMiddleware, minimum_size=1000)
    if settings.mode is StudioMode.server:
        install_server_security(app, settings)
        install_rate_limiter(app, settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.allow_origins,
        allow_credentials=settings.cors.allow_credentials,
        allow_methods=settings.cors.allow_methods,
        allow_headers=settings.cors.allow_headers,
        # Имя файла выгрузки (bundle, PDF) приходит в Content-Disposition; без этой строки фронт на другом
        # origin его не видит и сохраняет файл под запасным именем.
        expose_headers=["Content-Disposition"],
    )

    @app.middleware("http")
    async def _interface_language_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        # Bind the UI language for this request (and any background task spawned
        # within it, e.g. an agent run, which inherits the context). Absent header
        # → None, so downstream code falls back to settings.interface_language.
        set_interface_language(request.headers.get("X-Interface-Language"))
        return await call_next(request)

    app.include_router(api_router)
    install_exception_handlers(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    health_checks = install_health(app, settings)

    configure_docker_binary(settings.docker_binary)

    container = create_container(settings.mode)
    setup_dishka(container, app)

    if settings.mode is StudioMode.server:
        server_metrics = install_server_observability(app, settings, health_checks)
        install_background(
            app,
            container,
            health_checks,
            server_metrics,
            shutdown_timeout_s=settings.server.timeout_graceful_shutdown,
        )

        @app.on_event("startup")
        async def _prepare_server_setup() -> None:
            await prepare_server_setup(app, container, settings, health_checks)

    @app.on_event("startup")
    async def _probe_docker() -> None:
        # Один короткий пинг демона ПЕРЕД усыновлением соседей. Без него на
        # машине, где докера ещё нет, старт занимал около сорока секунд: четыре
        # реконсиляции подряд, каждая со своим десятисекундным таймаутом. А
        # «докера ещё нет» — это ровно первый запуск, самый важный сценарий.
        app.state.docker_available = await docker_alive()
        if not app.state.docker_available:
            logger.info("docker is not available, skipping sibling container reconciliation")

    @app.on_event("startup")
    async def _adopt_host_fonts() -> None:
        # Один раз при первой установке: перенести к себе Times New Roman и
        # компанию, которые просят шаблоны. Пользователь этого не заказывает —
        # он и не знает, что до первой сборки надо куда-то сходить за шрифтами.
        #
        # В фоне: перебор каталогов ОС идёт одноразовыми контейнерами, это
        # десятки секунд, и держать на них старт приложения нечего.
        if not app.state.docker_available:
            return

        # Только в НАСТРОЕННОЙ установке. До выбора папки данных писать шрифты
        # некуда: `/data` не смонтирован, и каждый save_font падал бы с
        # «Permission denied» — ровно это и происходило, когда перенос запускался
        # в setup-режиме. Пропуск ничего не теряет: после мастера контейнер
        # пересоздаётся, и этот старт выполнится заново уже с папкой.
        try:
            async with container() as request_container:
                inspect_uc = await request_container.get(InspectSetupUC)
                if not (await inspect_uc.execute()).report.is_ready:
                    logger.info("host font adoption skipped: setup is not complete")
                    return
        except Exception:
            logger.exception("host font adoption pre-check failed")
            return

        async def _adopt() -> None:
            try:
                async with container() as request_container:
                    uc = await request_container.get(AdoptHostFontsUC)
                    result = await uc.execute()
                    if result.installed:
                        logger.info("host fonts adopted", count=len(result.installed))
            except Exception:
                logger.exception("host font adoption failed")

        app.state.adopt_fonts_task = asyncio.create_task(_adopt())

    @app.on_event("startup")
    async def _ensure_projects_dir() -> None:
        # `<data>/projects` — готовое место под работы: мастер создания проекта
        # предлагает его чипом, даже когда проектов ещё нет. В setup-режиме
        # каталог данных не смонтирован — молча пропускаем, после мастера
        # контейнер пересоздаётся и этот старт выполнится заново.
        try:
            (settings.data_dir.expanduser() / "projects").mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.info("projects dir not created", error=str(exc))

    @app.on_event("startup")
    async def _sync_local_ai_provider() -> None:
        # Нативная Ollama могла работать ещё ДО установки приложения — тогда ни
        # pull, ни «Запустить» в настройках не происходят, и авто-управляемый
        # провайдер не появлялся, пока пользователь не создаст его руками. Один
        # фоновый синк на старте закрывает ровно этот случай: use case сам
        # ничего не создаёт, если Ollama не отвечает. Только в настроенной
        # установке — до мастера data_dir не смонтирован и писать провайдера некуда.
        async def _sync() -> None:
            try:
                async with container() as request_container:
                    inspect_uc = await request_container.get(InspectSetupUC)
                    if not (await inspect_uc.execute()).report.is_ready:
                        return
                    uc = await request_container.get(SyncLocalOllamaProviderUC)
                    result = await uc.execute()
                    if result.provider_id is not None:
                        logger.info("local ollama provider synced", models=len(result.models))
            except Exception:
                logger.exception("local ollama provider sync failed")

        app.state.sync_ollama_provider_task = asyncio.create_task(_sync())

    @app.on_event("startup")
    async def _prefetch_tex_image() -> None:
        # Скачать движок LaTeX заранее, фоном. Иначе первый же «Собрать»
        # превращается в многоминутную загрузку нескольких гигабайт без
        # предупреждения — худший момент первого знакомства с продуктом.
        # Только в настроенной установке: до неё пользователь мог снять галочку
        # в мастере, и его выбор приедет переменной после пересоздания.
        if not app.state.docker_available or not settings.compile.prefetch_image:
            return
        try:
            async with container() as request_container:
                inspect_uc = await request_container.get(InspectSetupUC)
                if not (await inspect_uc.execute()).report.is_ready:
                    return
                settings_repo = await request_container.get(ISettingsRepository)
                image = resolve_active_image(settings_repo)
            if await image_present(image):
                return
        except Exception:
            logger.exception("tex prefetch pre-check failed")
            return

        async def _pull() -> None:
            logger.info("tex prefetch started", image=image)
            rc, _out, err = await run_docker(["pull", image], timeout=_TEX_PULL_TIMEOUT_S)
            if rc == 0:
                logger.info("tex prefetch finished", image=image)
            else:
                logger.warning("tex prefetch failed", image=image, err=err.strip()[-300:])

        app.state.tex_prefetch_task = asyncio.create_task(_pull())

    @app.on_event("shutdown")
    async def _prefetch_tex_shutdown() -> None:
        task = getattr(app.state, "tex_prefetch_task", None)
        if task is not None:
            task.cancel()

    @app.on_event("shutdown")
    async def _adopt_host_fonts_shutdown() -> None:
        task = getattr(app.state, "adopt_fonts_task", None)
        if task is not None:
            task.cancel()

    @app.on_event("startup")
    async def _recover_stale_compiles() -> None:
        # Mark any compile records left in `pending`/`running` from a previous
        # process as failed, so the project-wide build lock releases the next
        # time the UI loads. Runs once per process at startup.
        try:
            async with container() as request_container:
                uc = await request_container.get(RecoverStaleCompilesUC)
                result = await uc.execute()
                if result.recovered_compiles or result.unstuck_documents:
                    logger.info(
                        "startup recovery",
                        recovered_compiles=result.recovered_compiles,
                        unstuck_documents=result.unstuck_documents,
                    )
        except Exception:
            logger.exception("startup recovery failed")

    @app.on_event("startup")
    async def _recover_template_updates() -> None:
        # Обновления шаблона и слияния синхронизации, прерванные падением процесса: по журналу проект
        # возвращается в состояние до обновления (или обновление доводится,
        # если его коммит уже записан). Иначе проект остался бы «только чтение».
        try:
            async with container() as request_container:
                uc = await request_container.get(RecoverTemplateUpdatesUC)
                result = await uc.execute()
                for item in result.recovered:
                    logger.info(
                        "startup template update recovery",
                        folder=str(item.folder),
                        update_id=item.update_id,
                        kind=item.kind.value,
                        finalized=item.finalized,
                    )
        except Exception:
            logger.exception("startup template update recovery failed")

    @app.on_event("startup")
    async def _recover_stale_chat_runs() -> None:
        # Mark agent turns left pending/running by a previous process as
        # interrupted, so the per-session busy guard and the UI agree.
        try:
            async with container() as request_container:
                uc = await request_container.get(RecoverStaleChatRunsUC)
                result = await uc.execute()
                if result.recovered_runs:
                    logger.info("startup chat recovery", recovered_runs=result.recovered_runs)
        except Exception:
            logger.exception("startup chat recovery failed")

    @app.on_event("startup")
    async def _sweep_ssh_key_dirs() -> None:
        # Каталог временного ключа ssh удаляется в finally; остаться он может только после kill -9.
        sweep_stale_key_dirs()

    @app.on_event("startup")
    async def _auto_update_startup() -> None:
        # Фоновая проверка обновлений: сама решает, включена ли она (настройка
        # `auto_update`, по умолчанию да), умеет ли эта установка обновляться и
        # свободна ли система. Первый тик — с задержкой, см. AutoUpdateScheduler.
        async def _tick() -> AutoUpdateResult:
            # Свой request-скоуп на каждый тик — как в остальных фоновых задачах:
            # AutoUpdateUC живёт в REQUEST-скоупе, держать его на весь процесс нельзя.
            async with container() as request_container:
                uc = await request_container.get(AutoUpdateUC)
                return await uc.run_once()

        try:
            scheduler = AutoUpdateScheduler(
                _tick,
                interval_s=settings.auto_update_interval_s,
                startup_delay_s=settings.auto_update_startup_delay_s,
            )
            app.state.auto_update_task = asyncio.create_task(scheduler.loop())
        except Exception:
            logger.exception("auto-update startup failed")

    @app.on_event("shutdown")
    async def _auto_update_shutdown() -> None:
        task = getattr(app.state, "auto_update_task", None)
        if task is not None:
            task.cancel()

    @app.on_event("startup")
    async def _git_fetch_startup() -> None:
        # Фоновая выборка из удалённых репозиториев. Без подключённых проектов цикл спит и ничего не запускает;
        # подключение или клонирование будит его через реестр.
        if not settings.git.enabled:
            return

        async def _tick() -> FetchTickResult:
            # Свой request-скоуп на каждый тик, как у автообновления.
            async with container() as request_container:
                uc = await request_container.get(FetchAllGitRemotesUC)
                return await uc.run_once()

        try:
            scheduler = GitFetchScheduler(
                _tick,
                tick_s=settings.git.fetch_tick_s,
                startup_delay_s=settings.git.fetch_startup_delay_s,
            )
            registry = await container.get(IGitRemoteRegistry)
            registry.subscribe(scheduler.wake)
            app.state.git_fetch_task = asyncio.create_task(scheduler.loop())
        except Exception:
            logger.exception("git fetch startup failed")

    @app.on_event("shutdown")
    async def _git_fetch_shutdown() -> None:
        task = getattr(app.state, "git_fetch_task", None)
        if task is not None:
            task.cancel()

    @app.on_event("startup")
    async def _languagetool_startup() -> None:
        # Adopt an already-running managed container (after a backend restart)
        # and start the idle reaper that stops the auto-started container once
        # it's been unused for `idle_timeout_s`. The container is never
        # auto-started here — it comes up lazily on the first check that needs
        # it (see EmbeddedCompileRunner).
        if not app.state.docker_available:
            return
        try:
            manager = await container.get(LanguageToolContainerManager)
            await manager.reconcile()
            app.state.lt_reaper_task = asyncio.create_task(manager.idle_reaper_loop())
        except Exception:
            logger.exception("languagetool startup failed")

    @app.on_event("shutdown")
    async def _languagetool_shutdown() -> None:
        task = getattr(app.state, "lt_reaper_task", None)
        if task is not None:
            task.cancel()
        if not settings.languagetool.stop_on_shutdown:
            return
        try:
            manager = await container.get(LanguageToolContainerManager)
            await manager.stop()
        except Exception:
            logger.exception("languagetool shutdown stop failed")

    @app.on_event("startup")
    async def _office_convert_startup() -> None:
        # Same lifecycle as LanguageTool: adopt a running Gotenberg container
        # after a backend restart and start the idle reaper. Never auto-started
        # here — it comes up lazily on the first pptx build that needs a
        # PDF preview (see EmbeddedCompileRunner).
        if not app.state.docker_available:
            return
        try:
            manager = await container.get(OfficeConvertManager)
            await manager.reconcile()
            app.state.office_reaper_task = asyncio.create_task(manager.idle_reaper_loop())
        except Exception:
            logger.exception("office-convert startup failed")

    @app.on_event("shutdown")
    async def _detached_jobs_shutdown() -> None:
        # Фоновые задачи (обновление предпросмотра после сохранения из редактора)
        # доводим до остановки контейнеров конвертера, иначе они упадут на ровном месте.
        try:
            dispatcher = await container.get(IJobDispatcher)
            await dispatcher.drain_detached(timeout_s=5)
        except Exception:
            logger.exception("detached jobs drain failed")

    @app.on_event("shutdown")
    async def _office_convert_shutdown() -> None:
        task = getattr(app.state, "office_reaper_task", None)
        if task is not None:
            task.cancel()
        try:
            manager = await container.get(OfficeConvertManager)
            await manager.stop()
        except Exception:
            logger.exception("office-convert shutdown stop failed")

    @app.on_event("startup")
    async def _office_editor_startup() -> None:
        # Same lifecycle as Gotenberg: adopt a running Document Server container
        # after a backend restart and start the idle reaper. Never auto-started
        # here — it comes up lazily on the first «Редактировать» of a pptx
        # (see GetOfficeEditorConfigUC).
        if not app.state.docker_available:
            return
        try:
            manager = await container.get(OfficeEditorManager)
            await manager.reconcile()
            app.state.office_editor_reaper_task = asyncio.create_task(manager.idle_reaper_loop())
        except Exception:
            logger.exception("office-editor startup failed")

    @app.on_event("shutdown")
    async def _office_editor_shutdown() -> None:
        task = getattr(app.state, "office_editor_reaper_task", None)
        if task is not None:
            task.cancel()
        try:
            manager = await container.get(OfficeEditorManager)
            await manager.stop()
        except Exception:
            logger.exception("office-editor shutdown stop failed")

    @app.on_event("startup")
    async def _ollama_startup() -> None:
        # Adopt an already-running managed Ollama container (after a restart) and
        # start the idle reaper. Like LanguageTool, the container is never
        # auto-started here — it comes up lazily on an explicit user action.
        if not app.state.docker_available:
            return
        try:
            runtime = await container.get(IOllamaRuntime)
            await runtime.reconcile()
            app.state.ollama_reaper_task = asyncio.create_task(runtime.idle_reaper_loop())
        except Exception:
            logger.exception("ollama startup failed")

    @app.on_event("shutdown")
    async def _ollama_shutdown() -> None:
        task = getattr(app.state, "ollama_reaper_task", None)
        if task is not None:
            task.cancel()
        if not settings.ollama.stop_on_shutdown:
            return
        try:
            runtime = await container.get(IOllamaRuntime)
            await runtime.stop()
        except Exception:
            logger.exception("ollama shutdown stop failed")

    if settings.static_dir is not None:
        _mount_spa(app, settings)

    return app


def _mount_spa(app: FastAPI, settings: Settings) -> None:
    """Mount built frontend and add SPA fallback for client-side routing."""
    if settings.static_dir is None:
        raise ValueError("static_dir must be set before calling _mount_spa")
    static_dir = settings.static_dir
    index_html = static_dir / "index.html"

    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    # In all-in-one mode the frontend is served by this same server, so the
    # API base URL must be relative ("") — the browser resolves /api/v1/...
    # against the same host:port the user accessed the UI from.
    api_base_url = os.environ.get("HSE_STUDIO__API_BASE_URL", "")
    config_js_content = (
        f"window.__APP_CONFIG__ = {{\n"
        f"  API_BASE_URL: {json.dumps(api_base_url)},\n"
        f'  APP_ENV: "production",\n'
        f"  BUILD_TIME: new Date().toISOString(),\n"
        f"  VERSION: {json.dumps(settings.get_app_version())},\n"
        f"}};\n"
    )

    @app.get("/config.js", include_in_schema=False)
    async def serve_config_js() -> PlainTextResponse:
        return PlainTextResponse(config_js_content, media_type="application/javascript")

    # SPA fallback — all unmatched routes return index.html so the React
    # router can handle navigation on the client side
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str, request: Request) -> FileResponse:  # noqa: ARG001
        return FileResponse(index_html)


def main() -> None:
    """Run server."""
    ensure_supported_mode(settings)

    with suppress(ImportError):
        import uvloop  # noqa: PLC0415

        uvloop.install()

    import uvicorn  # noqa: PLC0415

    logger.info(
        "Starting server",
        service="hse-doc-studio",
        version=settings.get_app_version(),
        host=settings.server.host,
        port=settings.server.port,
        workers=settings.server.workers,
        cpu_count=os.cpu_count(),
    )

    uvicorn.run(
        "hse_doc_studio.api.entrypoint:create_app",
        factory=True,
        **settings.get_uvicorn_kwargs(),
    )


if __name__ == "__main__":
    main()
