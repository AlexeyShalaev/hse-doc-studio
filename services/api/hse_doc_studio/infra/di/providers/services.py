from __future__ import annotations

import httpx
import structlog
from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.agent.protocols import IAgentProvider, IApprovalGate
from hse_doc_studio.core.ai import IAIModelLister, IChatSummarizer
from hse_doc_studio.core.ai_catalog import ModelCatalog
from hse_doc_studio.core.ai_runtime import (
    IHardwareProbe,
    IOllamaRegistry,
    IOllamaRuntime,
    IPullModelJobs,
)
from hse_doc_studio.core.entities import CatalogModel
from hse_doc_studio.core.fonts.entities import FontCatalog, FontCatalogFile, FontCatalogItem
from hse_doc_studio.core.fonts.repositories import (
    IFontDownloader,
    IFontMarketplace,
    IFontStore,
    ISystemFontProvider,
)
from hse_doc_studio.core.hse_persons.repositories import IHsePersonsGateway
from hse_doc_studio.core.paths import Mount, PathMapping, looks_absolute
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.core.services import (
    ChatContextService,
    CheckResolutionService,
    FormValidationService,
    ProjectTemplateService,
    RequirementMatchingService,
    SubmissionProfileService,
)
from hse_doc_studio.core.system_capacity import ISystemCapacityProbe
from hse_doc_studio.core.vcs.protocols import (
    IVcsEditThrottle,
    IVcsFolderLocks,
    IVcsService,
)
from hse_doc_studio.infra.ai.agent.approval import ConfigApprovalGate
from hse_doc_studio.infra.ai.agent.chat_summarizer import SdkChatSummarizer
from hse_doc_studio.infra.ai.agent.edit_applier import FuzzySearchReplaceApplier
from hse_doc_studio.infra.ai.agent.run_bus import AgentRunBus
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager
from hse_doc_studio.infra.ai.agent.sdk_agent_provider import SdkAgentProvider
from hse_doc_studio.infra.ai.ollama.hardware_probe import SystemHardwareProbe
from hse_doc_studio.infra.ai.ollama.pull_jobs import PullModelJobManager
from hse_doc_studio.infra.ai.ollama.registry import OllamaRegistryClient
from hse_doc_studio.infra.ai.ollama.runtime_manager import OllamaRuntimeManager
from hse_doc_studio.infra.ai.sdk_model_lister import SdkAIModelLister
from hse_doc_studio.infra.checks.runner import CheckRunner
from hse_doc_studio.infra.compile.compile_runner import CompileRunner
from hse_doc_studio.infra.compile.concurrency import CompileConcurrencyLimiter
from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager
from hse_doc_studio.infra.compile.host_path_resolver import HostPathResolver
from hse_doc_studio.infra.compile.log_bus import CompileLogBus
from hse_doc_studio.infra.docker.cleanup_jobs import DockerCleanupJobManager
from hse_doc_studio.infra.docker.siblings import Reachability, SiblingNetwork
from hse_doc_studio.infra.docker.system_manager import DockerSystemManager
from hse_doc_studio.infra.fonts.font_downloader import HttpxFontDownloader
from hse_doc_studio.infra.fonts.font_store import LocalFontStore
from hse_doc_studio.infra.fonts.gfonts_marketplace import GoogleFontsMarketplace
from hse_doc_studio.infra.fonts.host_font_provider import DockerHostFontProvider
from hse_doc_studio.infra.fonts.system_fonts import OsSystemFontProvider
from hse_doc_studio.infra.forms.form_renderer import FormOutputRenderer
from hse_doc_studio.infra.hse_persons.client import HseHttpPersonsGateway
from hse_doc_studio.infra.languagetool.container_manager import LanguageToolContainerManager
from hse_doc_studio.infra.office.convert_manager import OfficeConvertManager
from hse_doc_studio.infra.office.editor_manager import OfficeEditorManager
from hse_doc_studio.infra.project_init.template_renderer import TemplateRenderer
from hse_doc_studio.infra.runtime.environment import in_container
from hse_doc_studio.infra.signatures.pdf_stamper import PdfStamper
from hse_doc_studio.infra.signatures.pyhanko_signer import PyHankoPdfSigner
from hse_doc_studio.infra.submission.assembler import SubmissionAssembler
from hse_doc_studio.infra.system.capacity_probe import SystemCapacityProbe
from hse_doc_studio.infra.vcs.edit_throttle import VcsEditThrottle
from hse_doc_studio.infra.vcs.folder_locks import VcsFolderLocks
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService

logger = structlog.get_logger()


class DomainServiceProvider(Provider):
    scope = Scope.APP

    @provide
    def get_check_resolution_service(self) -> CheckResolutionService:
        return CheckResolutionService()

    @provide
    def get_project_template_service(self) -> ProjectTemplateService:
        return ProjectTemplateService()

    @provide
    def get_submission_profile_service(self) -> SubmissionProfileService:
        return SubmissionProfileService()

    @provide
    def get_form_validation_service(self) -> FormValidationService:
        return FormValidationService()

    @provide
    def get_form_output_renderer(self) -> FormOutputRenderer:
        return FormOutputRenderer()

    @provide
    def get_ai_model_lister(self) -> IAIModelLister:
        # Stateless: SDK clients are built per request from each provider's key.
        return SdkAIModelLister()

    @provide
    def get_agent_provider(self) -> IAgentProvider:
        # Stateless dispatcher over the OpenAI-/Anthropic-shaped adapters; a fresh
        # SDK client is built per turn from the provider's own key/base_url.
        return SdkAgentProvider()

    @provide
    def get_agent_run_bus(self) -> AgentRunBus:
        # Single long-lived pub/sub for live run events (mirror get_compile_log_bus).
        return AgentRunBus()

    @provide
    def get_agent_run_manager(self) -> AgentRunManager:
        # App-scoped: agent turns run as background tasks that must outlive the
        # request that started them (mirror get_compile_runner / pull jobs).
        return AgentRunManager()

    @provide
    def get_approval_gate(self, settings_repo: ISettingsRepository) -> IApprovalGate:
        # read tools auto-run; write/exec gated unless the user opts into auto-approve.
        # The flag is read live from runtime settings (env default as fallback).
        return ConfigApprovalGate(settings.agent.auto_approve_writes, settings_repo=settings_repo)

    @provide
    def get_edit_applier(self) -> FuzzySearchReplaceApplier:
        # Stateless fuzzy search/replace applier used by the edit_tex tool.
        return FuzzySearchReplaceApplier()

    @provide
    def get_chat_context_service(self) -> ChatContextService:
        # Pure compaction policy (when to compact + what to keep); no I/O.
        return ChatContextService()

    @provide
    def get_chat_summarizer(self, agent_provider: IAgentProvider) -> IChatSummarizer:
        # Rolling-summary generator; one tool-free model call via the agent provider.
        return SdkChatSummarizer(agent_provider)

    @provide
    def get_hardware_probe(self) -> IHardwareProbe:
        # Stateless, best-effort host detection (nvidia-smi / psutil / os).
        return SystemHardwareProbe()

    @provide
    def get_ollama_runtime(self, hardware_probe: IHardwareProbe, siblings: SiblingNetwork) -> IOllamaRuntime:
        # Single long-lived manager (holds the warm endpoint + idle timer), like
        # the LanguageTool container manager.
        cfg = settings.ollama
        return OllamaRuntimeManager(
            image=cfg.image,
            container_name=cfg.container_name,
            container_port=cfg.container_port,
            host_port=cfg.host_port,
            local_base_url=cfg.local_base_url,
            health_path=cfg.health_path,
            model_volume_name=cfg.model_volume_name,
            health_timeout_s=cfg.health_timeout_s,
            request_timeout_s=cfg.request_timeout_s,
            startup_timeout_s=cfg.startup_timeout_s,
            idle_timeout_s=cfg.idle_timeout_s,
            keep_alive=cfg.keep_alive,
            hardware_probe=hardware_probe,
            siblings=siblings,
        )

    @provide
    def get_pull_model_jobs(self, runtime: IOllamaRuntime) -> IPullModelJobs:
        # App-scoped: background pull tasks must outlive the request that starts
        # them, so the manager (and its task dict) is a single long-lived instance.
        return PullModelJobManager(runtime=runtime, max_concurrent=settings.ollama.max_concurrent_pulls)

    @provide
    def get_ollama_registry(self) -> IOllamaRegistry:
        # Best-effort registry search (ollama.com); degrades to [] on any error.
        return OllamaRegistryClient(
            search_url=settings.ollama.registry_search_url,
            timeout_s=settings.ollama.registry_timeout_s,
        )

    @provide
    def get_ollama_catalog(self) -> ModelCatalog:
        # Build the curated local-model catalog (the install allowlist) from the
        # deployment config so a fork can repoint it via env without code edits.
        return ModelCatalog(
            models=[
                CatalogModel(
                    name=entry.name,
                    label=entry.label,
                    family=entry.family,
                    params_b=entry.params_b,
                    size_gb=entry.size_gb,
                    min_vram_gb=entry.min_vram_gb,
                    min_ram_gb=entry.min_ram_gb,
                    tasks=list(entry.tasks),
                    description=entry.description,
                )
                for entry in settings.ollama.catalog
            ]
        )

    @provide
    def get_hse_persons_gateway(self) -> IHsePersonsGateway:
        # APP-scoped so the polite min-interval gate (Crawl-delay: 3) + the three
        # TTL caches are shared across requests. Best-effort scrape of
        # hse.ru/org/persons; degrades to empty results / None on any failure.
        cfg = settings.hse_persons
        return HseHttpPersonsGateway(
            base_url=cfg.base_url,
            list_path=cfg.list_path,
            campus_udept=dict(cfg.campus_udept),
            user_agent=cfg.user_agent,
            request_timeout_s=cfg.request_timeout_s,
            min_request_interval_s=cfg.min_request_interval_s,
            max_concurrency=cfg.max_concurrency,
            retries=cfg.retries,
            list_cache_ttl_s=cfg.list_cache_ttl_s,
            detail_cache_ttl_s=cfg.detail_cache_ttl_s,
            facets_cache_ttl_s=cfg.facets_cache_ttl_s,
        )

    @provide
    def get_requirement_matching_service(self) -> RequirementMatchingService:
        return RequirementMatchingService()

    @provide
    def get_template_renderer(self) -> TemplateRenderer:
        return TemplateRenderer()

    @provide
    def get_languagetool_http_client(self) -> httpx.Client:
        # Reused, long-lived client for LanguageTool requests + health probes.
        # The blocking call is offloaded to a worker thread by the callers, so
        # the event loop is never blocked while LanguageTool processes a request.
        return httpx.Client(timeout=settings.languagetool.request_timeout_s)

    @provide
    def get_languagetool_container_manager(
        self,
        lt_client: httpx.Client,
        siblings: SiblingNetwork,
    ) -> LanguageToolContainerManager:
        cfg = settings.languagetool
        return LanguageToolContainerManager(
            container_name=cfg.container_name,
            container_port=cfg.container_port,
            health_path=cfg.health_path,
            model_volume_name=cfg.model_volume_name,
            health_timeout_s=cfg.health_timeout_s,
            startup_timeout_s=cfg.startup_timeout_s,
            idle_timeout_s=cfg.idle_timeout_s,
            client=lt_client,
            siblings=siblings,
        )

    @provide
    def get_check_runner(
        self,
        lt_manager: LanguageToolContainerManager,
        lt_client: httpx.Client,
    ) -> CheckRunner:
        return CheckRunner(lt_manager=lt_manager, lt_client=lt_client)

    @provide
    def get_office_convert_manager(
        self,
        lt_client: httpx.Client,
        siblings: SiblingNetwork,
    ) -> OfficeConvertManager:
        # Gotenberg для pptx→PDF-предпросмотра. HTTP-клиент общий с LanguageTool
        # (обычный пул httpx, ничего LT-специфичного); таймаут конвертации
        # передаётся пер-запросно. Маппинг путей проекта не нужен — файл уходит
        # multipart'ом; хосто-путь нужен только fonts-mount'у (как у texlive).
        cfg = settings.office_convert
        data_dir = settings.data_dir.expanduser()
        host_data = settings.host_data_dir or str(data_dir)
        return OfficeConvertManager(
            image=cfg.image,
            container_name=cfg.container_name,
            container_port=cfg.container_port,
            health_path=cfg.health_path,
            convert_timeout_s=cfg.convert_timeout_s,
            health_timeout_s=cfg.health_timeout_s,
            startup_timeout_s=cfg.startup_timeout_s,
            idle_timeout_s=cfg.idle_timeout_s,
            fonts_dir=data_dir / settings.fonts.dir_name,
            fonts_host_dir=host_data.replace("\\", "/").rstrip("/") + "/" + settings.fonts.dir_name,
            client=lt_client,
            siblings=siblings,
        )

    @provide
    def get_office_editor_manager(
        self,
        lt_client: httpx.Client,
        siblings: SiblingNetwork,
    ) -> OfficeEditorManager:
        # ONLYOFFICE Document Server для in-app редактирования pptx. HTTP-клиент
        # общий (health-пробы + скачивание сохранённого документа); JWT-секрет
        # живёт в data_dir и переживает рестарты (усыновлённый контейнер обязан
        # валидировать те же токены). Шрифты — та же механика, что у Gotenberg.
        cfg = settings.office_editor
        data_dir = settings.data_dir.expanduser()
        host_data = settings.host_data_dir or str(data_dir)
        return OfficeEditorManager(
            image=cfg.image,
            container_name=cfg.container_name,
            container_port=cfg.container_port,
            health_path=cfg.health_path,
            health_timeout_s=cfg.health_timeout_s,
            startup_timeout_s=cfg.startup_timeout_s,
            idle_timeout_s=cfg.idle_timeout_s,
            secret_path=data_dir / "office-editor-jwt.secret",
            fonts_dir=data_dir / settings.fonts.dir_name,
            fonts_host_dir=host_data.replace("\\", "/").rstrip("/") + "/" + settings.fonts.dir_name,
            client=lt_client,
            siblings=siblings,
        )

    @provide
    def get_sibling_network(self) -> SiblingNetwork:
        # Один на процесс: подключённость себя к сети — процессный факт.
        return SiblingNetwork()

    @provide
    def get_reachability(self, siblings: SiblingNetwork) -> Reachability:
        # Наш адрес глазами соседнего контейнера — тоже процессный факт, поэтому
        # APP-скоуп: выясняется один раз и кэшируется.
        return Reachability(
            siblings,
            gateway_host=settings.office_editor.backend_host_for_container,
            listen_port=settings.server.port,
        )

    @provide
    def get_system_capacity_probe(self) -> ISystemCapacityProbe:
        return SystemCapacityProbe(data_dir=settings.data_dir.expanduser())

    @provide
    def get_path_mapping(self) -> PathMapping:
        """Соответствие «путь в контейнере ↔ путь на машине пользователя».

        Один источник правды и для монтирования каталога проекта в TeX-контейнер,
        и для показа путей в интерфейсе.
        """
        cfg = settings.compile
        if bool(cfg.projects_container_path) != bool(cfg.projects_host_path):
            raise ValueError(
                "compile.projects_container_path и compile.projects_host_path задаются только вместе",
            )
        mounts: list[Mount] = []
        # Отдельный бинд-маунт проектов (оверлей compose.projects.yml) — он специфичнее,
        # поэтому идёт первым.
        if cfg.projects_container_path and cfg.projects_host_path:
            mounts.append(Mount(container=cfg.projects_container_path, host=cfg.projects_host_path))
        # Дефолтная топология: проекты лежат внутри каталога данных, а его хостовый путь
        # compose уже сообщает через HOST_DATA_DIR (он же нужен для монтирования шрифтов).
        # Относительный путь (DATA_DIR=./data) в `docker -v` непригоден — демон примет
        # его за имя тома, поэтому такой маппинг не регистрируем.
        host_data = settings.host_data_dir
        if host_data and looks_absolute(host_data):
            mounts.append(Mount(container=str(settings.data_dir.expanduser()), host=host_data))
        elif host_data:
            logger.warning(
                "host_data_dir is not an absolute path — compiles of projects inside the data dir "
                "will fail; set DATA_DIR to an absolute host path",
                host_data_dir=host_data,
            )
        return PathMapping(mounts)

    @provide
    def get_host_path_resolver(self, mapping: PathMapping) -> HostPathResolver:
        return HostPathResolver(mapping)

    @provide
    def get_docker_compile_executor(
        self,
        host_path_resolver: HostPathResolver,
    ) -> DockerCompileExecutor:
        data_dir = settings.data_dir.expanduser()
        fonts_dir = data_dir / settings.fonts.dir_name
        # Host path of the fonts folder for the sibling `-v` mount: host_data_dir
        # when containerized, else data_dir itself (already a host path natively).
        host_data = settings.host_data_dir or str(data_dir)
        fonts_host_dir = host_data.replace("\\", "/").rstrip("/") + "/" + settings.fonts.dir_name
        return DockerCompileExecutor(
            host_path_resolver=host_path_resolver,
            image=settings.compile.image,
            cache_volume_name=settings.compile.cache_volume_name,
            cache_volume_target=settings.compile.cache_volume_target,
            idle_timeout_s=settings.compile.idle_timeout_s,
            fonts_dir=fonts_dir,
            fonts_host_dir=fonts_host_dir,
            fonts_mount_target=settings.fonts.container_mount,
        )

    @provide
    def get_font_store(self) -> IFontStore:
        fonts_dir = settings.data_dir.expanduser() / settings.fonts.dir_name
        return LocalFontStore(fonts_dir, frozenset(settings.fonts.allowed_extensions))

    @provide
    def get_font_downloader(self) -> IFontDownloader:
        return HttpxFontDownloader(timeout_s=settings.fonts.download_timeout_s)

    @provide
    def get_system_font_provider(self) -> ISystemFontProvider:
        """Откуда брать шрифты, установленные у ПОЛЬЗОВАТЕЛЯ.

        В контейнере каталоги ОС принадлежат образу, а не человеку, поэтому
        читать их напрямую бессмысленно — там лежит DejaVu, а не его Times New
        Roman. Смотрим на хост через докер: каталог шрифтов у каждой ОС ровно
        один и известен заранее, спрашивать нечего.

        Явно заданные `system_dirs` (оверлей `compose.system-fonts.yml` из
        прежней раскладки) остаются главнее: если человек уже смонтировал каталог
        руками, отбирать у него это управление незачем.
        """
        if settings.fonts.system_dirs:
            return OsSystemFontProvider(extra_roots=settings.fonts.system_dirs)
        if in_container():
            return DockerHostFontProvider(root_override=settings.fonts.host_dir)
        return OsSystemFontProvider()

    @provide
    def get_font_marketplace(self, font_catalog: FontCatalog) -> IFontMarketplace:
        # APP-scoped so the fetched Google Fonts index is cached across requests.
        cfg = settings.fonts
        return GoogleFontsMarketplace(
            metadata_url=cfg.marketplace_metadata_url,
            tree_url=cfg.marketplace_tree_url,
            ttl_s=cfg.marketplace_index_ttl_s,
            request_timeout_s=cfg.marketplace_fetch_timeout_s,
            fallback=font_catalog,
        )

    @provide
    def get_font_catalog(self) -> FontCatalog:
        return FontCatalog(
            items=tuple(
                FontCatalogItem(
                    id=e.id,
                    label=e.label,
                    family=e.family,
                    description=e.description,
                    license=e.license,
                    files=tuple(FontCatalogFile(filename=f.filename, url=f.url) for f in e.files),
                )
                for e in settings.fonts.catalog
            )
        )

    @provide
    def get_docker_image_manager(self) -> DockerImageManager:
        return DockerImageManager()

    @provide
    def get_docker_system_manager(self) -> DockerSystemManager:
        # Классификация docker-обитателей по «нашим» категориям для страницы
        # «Диск»: allowlist-репозитории каждой подсистемы + собственный образ
        # приложения (GHCR). Всё вне карты — «other» и очистке не подлежит.
        category_by_repo: dict[str, str] = {}
        for repo in settings.compile.allowed_repos:
            category_by_repo[repo] = "compile"
        for repo in settings.languagetool.allowed_repos:
            category_by_repo[repo] = "languagetool"
        for repo in settings.office_convert.allowed_repos:
            category_by_repo[repo] = "office"
        for repo in settings.office_editor.allowed_repos:
            category_by_repo[repo] = "office"
        category_by_repo[settings.ollama.image.rsplit(":", 1)[0]] = "ai"
        return DockerSystemManager(
            category_by_repo=category_by_repo,
            app_repo_prefix=settings.image_base,
            managed_volume_names=frozenset(
                {
                    settings.compile.cache_volume_name,
                    settings.languagetool.model_volume_name,
                    settings.ollama.model_volume_name,
                }
            ),
        )

    @provide
    def get_docker_cleanup_jobs(self, docker_system_manager: DockerSystemManager) -> DockerCleanupJobManager:
        # App-scoped: the cleanup task must outlive the request that started it,
        # and the UI polls the same singleton for progress (mirror pull jobs).
        return DockerCleanupJobManager(docker_system_manager)

    @provide
    def get_compile_log_bus(self) -> CompileLogBus:
        return CompileLogBus()

    @provide
    def get_compile_runner(self) -> CompileRunner:
        return CompileRunner()

    @provide
    def get_compile_limiter(self) -> CompileConcurrencyLimiter:
        # App-scoped: очередь docker-сборок общая для всех проектов и запросов.
        return CompileConcurrencyLimiter()

    @provide
    def get_pdf_stamper(self) -> PdfStamper:
        return PdfStamper()

    @provide
    def get_pyhanko_signer(self) -> PyHankoPdfSigner:
        return PyHankoPdfSigner()

    @provide
    def get_submission_assembler(
        self, pdf_stamper: PdfStamper, office_manager: OfficeConvertManager
    ) -> SubmissionAssembler:
        return SubmissionAssembler(pdf_stamper=pdf_stamper, office_manager=office_manager)

    @provide
    def get_vcs_service(self) -> IVcsService:
        cfg = settings.vcs
        return GitVcsService(
            author_name=cfg.author_name,
            author_email=cfg.author_email,
            diff_max_bytes=cfg.diff_max_bytes,
            default_branch=cfg.default_branch,
        )

    @provide
    def get_vcs_folder_locks(self) -> IVcsFolderLocks:
        # App-scoped: the lock map must be shared across requests AND the compile
        # task so the compile-success auto-commit serializes against snapshots.
        return VcsFolderLocks()

    @provide
    def get_vcs_edit_throttle(self) -> IVcsEditThrottle:
        # App-scoped: the per-folder last-commit timestamps must persist across
        # the requests that save files.
        return VcsEditThrottle(min_interval_seconds=settings.vcs.edit_min_interval_seconds)
