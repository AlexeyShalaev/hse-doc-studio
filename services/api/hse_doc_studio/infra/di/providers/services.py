from __future__ import annotations

from pathlib import Path

import httpx
import structlog
from dishka import AnyOf, Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.agent.protocols import IAgentProvider, IAgentRunBus, IApprovalGate
from hse_doc_studio.core.ai import IAIModelLister, IChatSummarizer
from hse_doc_studio.core.ai_catalog import ModelCatalog
from hse_doc_studio.core.ai_runtime import (
    IHardwareProbe,
    IOllamaRegistry,
    IOllamaRuntime,
    IPullModelJobs,
)
from hse_doc_studio.core.checks.protocols import ICheckRunner
from hse_doc_studio.core.egress import IEgressPolicy
from hse_doc_studio.core.entities import CatalogModel
from hse_doc_studio.core.events import IJobLogStream
from hse_doc_studio.core.fonts.entities import FontCatalog, FontCatalogFile, FontCatalogItem
from hse_doc_studio.core.fonts.repositories import (
    IFontDownloader,
    IFontMarketplace,
    IFontStore,
    ISystemFontProvider,
)
from hse_doc_studio.core.git_sync.fetch_schedule import FetchBook
from hse_doc_studio.core.git_sync.merge.rules import StateFileMerge
from hse_doc_studio.core.git_sync.merge.text import BASE_LABEL, OURS_LABEL, THEIRS_LABEL
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import (
    ICertificateService,
    ICiRenderer,
    IGitBundleService,
    IGitCloneStore,
    IGitCredentialRepository,
    IGitCredentialUsage,
    IGitHostSettingsRepository,
    IGitMergeCommitter,
    IGitMergeEngine,
    IGitOperationRegistry,
    IGitRemoteRegistry,
    IGitRemoteRunner,
    IGitRepoReader,
    IGitStoreGuard,
    IGitStoreRemotes,
    IGitSyncStateRepository,
    IGitTransport,
    IHostKeyScanner,
    IKnownHostsStore,
    ILocalAuthorProfile,
    IProviderDetector,
    IRemoteProjectCheck,
    ISecretCipher,
    ISharedFolderDetector,
    ISshKeyGenerator,
    ITokenIntrospector,
)
from hse_doc_studio.core.git_sync.status import RefStatusMemo
from hse_doc_studio.core.hse_persons.repositories import IHsePersonsGateway
from hse_doc_studio.core.jobs.artifacts import IArtifactStore
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.files import IProjectFileProbeFactory
from hse_doc_studio.core.jobs.outputs import IJobOutputs
from hse_doc_studio.core.jobs.protocols import ICompileJobRunner, IJobDispatcher
from hse_doc_studio.core.language_check import ILanguageCheckService
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.office import IBackendReachability, IOfficeConvertService, IOfficeEditorService
from hse_doc_studio.core.paths import Mount, PathMapping, looks_absolute
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import (
    IProjectRepository,
    ISettingsRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import (
    ChatContextService,
    CheckResolutionService,
    FormValidationService,
    ProjectTemplateService,
    RequirementMatchingService,
    SubmissionProfileService,
)
from hse_doc_studio.core.signatures.ports import (
    IChainFetcher,
    IOpenPgpKeyImporter,
    IPublicKeyExporter,
    ITrustMaterialProvider,
)
from hse_doc_studio.core.system_capacity import ISystemCapacityProbe
from hse_doc_studio.core.template_materializer import ITemplateMaterializer
from hse_doc_studio.core.template_update.protocols import (
    IMergeEngine,
    ITemplateBaseStore,
    ITemplateTrackingRepository,
    ITemplateTreeRenderer,
    IUpdateJournalRepository,
)
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.core.vcs.protocols import (
    ICommitAuthorProvider,
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
from hse_doc_studio.infra.egress.policy import AllowAllEgressPolicy, ResolvingEgressPolicy
from hse_doc_studio.infra.fonts.font_downloader import HttpxFontDownloader
from hse_doc_studio.infra.fonts.font_store import LocalFontStore
from hse_doc_studio.infra.fonts.gfonts_marketplace import GoogleFontsMarketplace
from hse_doc_studio.infra.fonts.host_font_provider import DockerHostFontProvider
from hse_doc_studio.infra.fonts.system_fonts import OsSystemFontProvider
from hse_doc_studio.infra.forms.form_renderer import FormOutputRenderer
from hse_doc_studio.infra.git_sync.bundle import GitBundleService
from hse_doc_studio.infra.git_sync.ci_renderer import JinjaCiRenderer
from hse_doc_studio.infra.git_sync.clone_store import GitCloneStore
from hse_doc_studio.infra.git_sync.credential_repository import JsonGitCredentialRepository
from hse_doc_studio.infra.git_sync.credential_usage import StoreConfigCredentialUsage
from hse_doc_studio.infra.git_sync.git_remote_runner import GitRemoteRunner
from hse_doc_studio.infra.git_sync.git_transport import GitTransport
from hse_doc_studio.infra.git_sync.host_key_scanner import SshKeyscanScanner
from hse_doc_studio.infra.git_sync.host_settings_repository import JsonGitHostSettingsRepository
from hse_doc_studio.infra.git_sync.known_hosts import FileKnownHostsStore
from hse_doc_studio.infra.git_sync.merge_committer import GitMergeCommitter
from hse_doc_studio.infra.git_sync.operation_registry import InMemoryGitOperationRegistry
from hse_doc_studio.infra.git_sync.provider_api import HttpProviderDetector, HttpTokenIntrospector
from hse_doc_studio.infra.git_sync.remote_project_check import ProjectDocumentCheck
from hse_doc_studio.infra.git_sync.remote_registry import ConfigScanRemoteRegistry
from hse_doc_studio.infra.git_sync.repo_reader import GitRepoReader
from hse_doc_studio.infra.git_sync.shared_folder import SharedFolderDetector
from hse_doc_studio.infra.git_sync.ssh_keys import Ed25519KeyGenerator
from hse_doc_studio.infra.git_sync.store_git import StoreGit
from hse_doc_studio.infra.git_sync.store_hardening import GitStoreGuard
from hse_doc_studio.infra.git_sync.store_remotes import GitStoreRemotes
from hse_doc_studio.infra.git_sync.sync_state import JsonGitSyncStateRepository
from hse_doc_studio.infra.git_sync.tls_certificates import TlsCertificateService
from hse_doc_studio.infra.hse_persons.client import HseHttpPersonsGateway
from hse_doc_studio.infra.jobs.artifact_store import LocalDiskArtifactStore
from hse_doc_studio.infra.jobs.embedded_runner import EmbeddedCompileRunner
from hse_doc_studio.infra.jobs.fs_file_probe import FsProjectFileProbeFactory
from hse_doc_studio.infra.jobs.handler_registry import JobHandlerRegistry
from hse_doc_studio.infra.jobs.local_dispatcher import LocalJobDispatcher
from hse_doc_studio.infra.jobs.office_convert import OfficeConvertHandler
from hse_doc_studio.infra.jobs.outputs import LocalJobOutputs
from hse_doc_studio.infra.jobs.pack_handler import PackHandler
from hse_doc_studio.infra.jobs.verify_detached import VerifyDetachedHandler
from hse_doc_studio.infra.languagetool.container_manager import LanguageToolContainerManager
from hse_doc_studio.infra.office.convert_manager import OfficeConvertManager
from hse_doc_studio.infra.office.editor_manager import OfficeEditorManager
from hse_doc_studio.infra.persistence.serializers import (
    deserialize_form_state,
    deserialize_project,
    deserialize_signatures_state,
)
from hse_doc_studio.infra.project_init.materializer import TemplateMaterializer
from hse_doc_studio.infra.project_init.template_renderer import TemplateRenderer
from hse_doc_studio.infra.runtime.environment import in_container
from hse_doc_studio.infra.secrets.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from hse_doc_studio.infra.signatures.chain_fetcher import ChainFetcher
from hse_doc_studio.infra.signatures.detached_verifier import DetachedSignatureVerifier
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring
from hse_doc_studio.infra.signatures.pdf_stamper import PdfStamper
from hse_doc_studio.infra.signatures.pyhanko_signer import PyHankoPdfSigner
from hse_doc_studio.infra.signatures.trust_material import LocalTrustMaterialProvider
from hse_doc_studio.infra.signatures.trusted_roots import TrustedRootStore
from hse_doc_studio.infra.submission.pack_executor import PackExecutor
from hse_doc_studio.infra.system.capacity_probe import SystemCapacityProbe
from hse_doc_studio.infra.template_update.merge_engine import GitMergeFileEngine
from hse_doc_studio.infra.template_update.state import JsonTemplateTrackingRepository, JsonUpdateJournalRepository
from hse_doc_studio.infra.template_update.tree_renderer import TemplateTreeRenderer
from hse_doc_studio.infra.vcs.commit_author import ActorCommitAuthorProvider
from hse_doc_studio.infra.vcs.edit_throttle import VcsEditThrottle
from hse_doc_studio.infra.vcs.folder_locks import VcsFolderLocks
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService
from hse_doc_studio.infra.vcs.profile_source import ConfigAuthorProfile
from hse_doc_studio.infra.vcs.template_base_store import GitTemplateBaseStore
from hse_doc_studio.use_cases.compile.list_images import resolve_active_image
from hse_doc_studio.use_cases.git_sync.conflict_plan import ConflictPlanner
from hse_doc_studio.use_cases.languagetool.list_languagetool_images import resolve_active_languagetool_image
from hse_doc_studio.use_cases.office_services.list_office_service_images import resolve_active_office_image
from hse_doc_studio.use_cases.projects.get_project_access import ProjectAccessService
from hse_doc_studio.use_cases.submission.pack_planner import PackPlanner
from hse_doc_studio.use_cases.template_update.base_service import TemplateBaseService
from hse_doc_studio.use_cases.template_update.planning import TemplateUpdatePlanner

logger = structlog.get_logger()


def _server_egress(egress: IEgressPolicy) -> IEgressPolicy | None:
    """Политика egress нужна только общему серверу: в режиме local клиенты и git работают как прежде."""
    return None if settings.mode is StudioMode.local else egress


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
    def get_agent_run_bus(self) -> AnyOf[AgentRunBus, IAgentRunBus]:
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
    ) -> AnyOf[LanguageToolContainerManager, ILanguageCheckService]:
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
        lt_manager: ILanguageCheckService,
        lt_client: httpx.Client,
    ) -> AnyOf[CheckRunner, ICheckRunner]:
        return CheckRunner(lt_manager=lt_manager, lt_client=lt_client)

    @provide
    def get_office_convert_manager(
        self,
        lt_client: httpx.Client,
        siblings: SiblingNetwork,
    ) -> AnyOf[OfficeConvertManager, IOfficeConvertService]:
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
    ) -> AnyOf[OfficeEditorManager, IOfficeEditorService]:
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
    def get_reachability(self, siblings: SiblingNetwork) -> AnyOf[Reachability, IBackendReachability]:
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
    def get_artifact_store(self) -> IArtifactStore:
        return LocalDiskArtifactStore()

    @provide
    def get_job_outputs(self) -> IJobOutputs:
        return LocalJobOutputs()

    @provide
    def get_docker_compile_executor(
        self,
        host_path_resolver: HostPathResolver,
        artifacts: IArtifactStore,
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
            artifacts=artifacts,
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
    def get_compile_log_bus(self) -> AnyOf[CompileLogBus, IJobLogStream]:
        return CompileLogBus()

    @provide
    def get_compile_runner(self) -> CompileRunner:
        return CompileRunner()

    @provide
    def get_compile_limiter(self) -> CompileConcurrencyLimiter:
        # App-scoped: очередь docker-сборок общая для всех проектов и запросов.
        return CompileConcurrencyLimiter()

    @provide
    def get_template_materializer(self, template_repo: ITemplateRepository) -> ITemplateMaterializer:
        return TemplateMaterializer(template_repo)

    @provide
    def get_embedded_compile_runner(  # noqa: PLR0913
        self,
        executor: DockerCompileExecutor,
        image_manager: DockerImageManager,
        office_convert: IOfficeConvertService,
        check_runner: ICheckRunner,
        lt_manager: ILanguageCheckService,
        settings_repo: ISettingsRepository,
        capacity_probe: ISystemCapacityProbe,
        limiter: CompileConcurrencyLimiter,
        outputs: IJobOutputs,
    ) -> AnyOf[EmbeddedCompileRunner, ICompileJobRunner]:
        # Образы читаются из настроек в момент вызова: сборка выбирает образ заново после ожидания слота.
        return EmbeddedCompileRunner(
            executor=executor,
            image_manager=image_manager,
            office_convert=office_convert,
            check_runner=check_runner,
            lt_manager=lt_manager,
            settings_repo=settings_repo,
            capacity_probe=capacity_probe,
            limiter=limiter,
            outputs=outputs,
            resolve_image=lambda: resolve_active_image(settings_repo),
            resolve_lt_image=lambda: resolve_active_languagetool_image(settings_repo),
            resolve_office_image=lambda: resolve_active_office_image(settings_repo, "convert"),
        )

    @provide
    def get_job_handler_registry(
        self, office_convert: IOfficeConvertService, verifier: DetachedSignatureVerifier, pdf_stamper: PdfStamper
    ) -> JobHandlerRegistry:
        # Обработчики не-compile видов регистрируют слайсы своих семейств.
        registry = JobHandlerRegistry()
        registry.register(JobKind.office_convert, OfficeConvertHandler(office_convert))
        registry.register(JobKind.verify_detached, VerifyDetachedHandler(verifier))
        registry.register(JobKind.pack_submission, PackHandler(PackExecutor(pdf_stamper)))
        return registry

    @provide
    def get_job_dispatcher(
        self,
        compile_runner: ICompileJobRunner,
        handlers: JobHandlerRegistry,
        log_stream: IJobLogStream,
        compile_registry: CompileRunner,
        outputs: IJobOutputs,
    ) -> IJobDispatcher:
        return LocalJobDispatcher(
            compile_runner=compile_runner,
            handlers=handlers,
            log_stream=log_stream,
            compile_registry=compile_registry,
            outputs=outputs,
            round_trip=settings.jobs.round_trip_payloads,
        )

    @provide
    def get_pdf_stamper(self) -> PdfStamper:
        return PdfStamper()

    @provide
    def get_pyhanko_signer(self) -> PyHankoPdfSigner:
        return PyHankoPdfSigner()

    @provide
    def get_pack_planner(self, template_service: ProjectTemplateService) -> PackPlanner:
        return PackPlanner(template_service)

    @provide
    def get_project_file_probe_factory(self) -> IProjectFileProbeFactory:
        return FsProjectFileProbeFactory()

    @provide
    def get_gpg_keyring(self) -> AnyOf[GpgKeyring, IOpenPgpKeyImporter, IPublicKeyExporter]:
        return GpgKeyring(settings.data_dir.expanduser() / "gnupg")

    @provide
    def get_trusted_root_store(self) -> TrustedRootStore:
        return TrustedRootStore(settings.data_dir.expanduser() / "trusted_roots")

    @provide
    def get_chain_fetcher(self) -> AnyOf[ChainFetcher, IChainFetcher]:
        return ChainFetcher(settings.data_dir.expanduser() / "chain_cache")

    @provide
    def get_detached_signature_verifier(
        self, keyring: GpgKeyring, root_store: TrustedRootStore, fetcher: ChainFetcher
    ) -> DetachedSignatureVerifier:
        return DetachedSignatureVerifier(keyring, root_store.directory, fetcher.directory)

    @provide
    def get_trust_material_provider(
        self, root_store: TrustedRootStore, fetcher: ChainFetcher
    ) -> AnyOf[LocalTrustMaterialProvider, ITrustMaterialProvider]:
        return LocalTrustMaterialProvider(root_store.directory, fetcher.directory)

    # --- Git-синхронизация: секреты и доступы (каталог данных читается при создании, как у хранилища шрифтов) ---

    @provide
    def get_git_key_store(self) -> KeyFileStore:
        cfg = settings.secrets
        return KeyFileStore(
            settings.data_dir.expanduser() / "secrets" / "master.keys.json",
            env_key=None if cfg.key is None else cfg.key.get_secret_value(),
            env_key_file=cfg.key_file,
            retired_keys=None if cfg.retired_keys is None else cfg.retired_keys.get_secret_value(),
        )

    @provide
    def get_secret_cipher(self, key_store: KeyFileStore) -> ISecretCipher:
        return FernetSecretCipher(key_store)

    @provide
    def get_git_credential_repo(self, cipher: ISecretCipher) -> IGitCredentialRepository:
        return JsonGitCredentialRepository(settings.data_dir.expanduser(), cipher)

    @provide
    def get_ssh_key_generator(self) -> ISshKeyGenerator:
        return Ed25519KeyGenerator()

    @provide
    def get_known_hosts_store(self) -> IKnownHostsStore:
        return FileKnownHostsStore(settings.data_dir.expanduser())

    @provide
    def get_egress_policy(self) -> IEgressPolicy:
        if settings.mode is StudioMode.local:
            return AllowAllEgressPolicy()
        return ResolvingEgressPolicy(settings.egress.allowlist)

    @provide
    def get_host_key_scanner(self, egress: IEgressPolicy) -> IHostKeyScanner:
        return SshKeyscanScanner(settings.git, _server_egress(egress))

    @provide
    def get_git_host_settings_repo(self) -> IGitHostSettingsRepository:
        return JsonGitHostSettingsRepository(settings.data_dir.expanduser())

    @provide
    def get_git_certificate_service(self, egress: IEgressPolicy) -> ICertificateService:
        return TlsCertificateService(settings.git.scan_timeout_s, _server_egress(egress))

    @provide
    def get_git_provider_detector(self, egress: IEgressPolicy) -> IProviderDetector:
        return HttpProviderDetector(settings.git.provider_detect_timeout_s, _server_egress(egress))

    @provide
    def get_git_token_introspector(
        self, certificates: ICertificateService, egress: IEgressPolicy
    ) -> ITokenIntrospector:
        return HttpTokenIntrospector(
            settings.git.token_check_timeout_s,
            certificates,
            allow_insecure_http=settings.git.allow_insecure_http,
            egress=_server_egress(egress),
        )

    @provide
    def get_git_credential_usage(self, locator: IProjectLocator, projects: IProjectRepository) -> IGitCredentialUsage:
        return StoreConfigCredentialUsage(locator, projects)

    @provide
    def get_local_author_profile(self, settings_repo: ISettingsRepository) -> ILocalAuthorProfile:
        return ConfigAuthorProfile(settings_repo)

    @provide
    def get_ci_renderer(self) -> ICiRenderer:
        return JinjaCiRenderer()

    @provide
    def get_git_sync_policy(self) -> GitSyncPolicy:
        cfg = settings.git
        return GitSyncPolicy(
            enabled=cfg.enabled,
            allow_insecure_http=cfg.allow_insecure_http,
            # На общем сервере локальные адреса открыли бы чтение его файлов.
            allow_local_remotes=cfg.allow_local_remotes and settings.mode is StudioMode.local,
            bot_email=settings.vcs.author_email,
            large_file_bytes=cfg.large_file_warn_bytes,
            max_incoming_blob_bytes=cfg.max_incoming_blob_bytes,
            max_incoming_total_bytes=cfg.max_incoming_total_bytes,
            first_push_timeout_s=cfg.clone_timeout_s,
        )

    @provide
    def get_store_git(self) -> StoreGit:
        return StoreGit(settings.vcs.author_name, settings.vcs.author_email)

    @provide
    def get_git_repo_reader(self, store_git: StoreGit) -> IGitRepoReader:
        return GitRepoReader(store_git)

    @provide
    def get_git_sync_state_repo(self) -> IGitSyncStateRepository:
        return JsonGitSyncStateRepository()

    @provide
    def get_git_store_guard(self, policy: GitSyncPolicy) -> IGitStoreGuard:
        return GitStoreGuard(allow_http=policy.allow_insecure_http, allow_local=policy.allow_local_remotes)

    @provide
    def get_git_remote_runner(
        self,
        credentials: IGitCredentialRepository,
        known_hosts: IKnownHostsStore,
        scanner: IHostKeyScanner,
        host_settings: IGitHostSettingsRepository,
        certificates: ICertificateService,
        egress: IEgressPolicy,
    ) -> IGitRemoteRunner:
        return GitRemoteRunner(
            settings.git,
            credentials,
            local_mode=settings.mode is StudioMode.local,
            known_hosts=known_hosts,
            scanner=scanner,
            host_settings=host_settings,
            certificates=certificates,
            egress=_server_egress(egress),
        )

    @provide
    def get_git_transport(self, runner: IGitRemoteRunner) -> IGitTransport:
        return GitTransport(runner, settings.git)

    @provide
    def get_git_operation_registry(self) -> IGitOperationRegistry:
        # Общий на процесс: перенос и удаление проекта смотрят в тот же реестр, что и синхронизация.
        return InMemoryGitOperationRegistry()

    @provide
    def get_git_remote_registry(self, locator: IProjectLocator) -> IGitRemoteRegistry:
        return ConfigScanRemoteRegistry(locator)

    @provide
    def get_ref_status_memo(self) -> RefStatusMemo:
        return RefStatusMemo()

    @provide
    def get_git_fetch_book(self) -> FetchBook:
        # Общий на процесс: кнопка «обновить» и фоновый цикл должны видеть одни замки и один счёт сбоев.
        return FetchBook()

    @provide
    def get_git_store_remotes(self, vcs_service: IVcsService, store_git: StoreGit) -> IGitStoreRemotes:
        if not isinstance(vcs_service, GitVcsService):
            raise TypeError("git remotes need the git VCS service")
        return GitStoreRemotes(vcs_service, store_git)

    @provide
    def get_git_clone_store(self, vcs_service: IVcsService, store_git: StoreGit) -> IGitCloneStore:
        if not isinstance(vcs_service, GitVcsService):
            raise TypeError("git clone needs the git VCS service")
        return GitCloneStore(vcs_service, store_git)

    @provide
    def get_commit_author_provider(self, local_profile: ILocalAuthorProfile) -> ICommitAuthorProvider:
        cfg = settings.vcs
        return ActorCommitAuthorProvider(
            VcsAuthor(cfg.author_name, cfg.author_email),
            # Профиль живёт в config.json этой машины; общий сервер подписывает людьми, не профилем.
            local_profile=local_profile if settings.mode is StudioMode.local else None,
        )

    @provide
    def get_vcs_service(self, author_provider: ICommitAuthorProvider) -> IVcsService:
        cfg = settings.vcs
        return GitVcsService(
            author_name=cfg.author_name,
            author_email=cfg.author_email,
            diff_max_bytes=cfg.diff_max_bytes,
            default_branch=cfg.default_branch,
            author_provider=author_provider,
        )

    @provide
    def get_git_merge_committer(
        self, author_provider: ICommitAuthorProvider, store_git: StoreGit
    ) -> IGitMergeCommitter:
        return GitMergeCommitter(author_provider, store_git)

    @provide
    def get_git_bundle_service(self, runner: IGitRemoteRunner) -> IGitBundleService:
        return GitBundleService(runner, settings.git)

    @provide
    def get_git_merge_engine(self) -> IGitMergeEngine:
        return GitMergeFileEngine(OURS_LABEL, BASE_LABEL, THEIRS_LABEL)

    @provide
    def get_state_file_merge(self) -> StateFileMerge:
        return StateFileMerge(
            {
                "project": lambda value: deserialize_project(value, Path(".")),
                "signatures": deserialize_signatures_state,
                "form": deserialize_form_state,
            }
        )

    @provide
    def get_remote_project_check(self) -> IRemoteProjectCheck:
        return ProjectDocumentCheck()

    @provide
    def get_conflict_planner(
        self, reader: IGitRepoReader, engine: IGitMergeEngine, state_merge: StateFileMerge, policy: GitSyncPolicy
    ) -> ConflictPlanner:
        # App-scoped: план определяется тройкой коммитов, и экран конфликтов читает его десятки раз подряд.
        return ConflictPlanner(reader=reader, engine=engine, structured=state_merge, policy=policy)

    @provide
    def get_shared_folder_detector(self, paths: PathMapping) -> ISharedFolderDetector:
        return SharedFolderDetector(paths)

    @provide
    def get_vcs_folder_locks(self) -> IVcsFolderLocks:
        # App-scoped: the lock map must be shared across requests AND the compile
        # task so the compile-success auto-commit serializes against snapshots.
        return VcsFolderLocks()

    # ── template updates (core.template_update) ──────────────────────────────
    @provide
    def get_template_base_store(self, vcs_service: IVcsService) -> ITemplateBaseStore:
        if not isinstance(vcs_service, GitVcsService):
            raise TypeError("template base store needs the git VCS service")
        return GitTemplateBaseStore(vcs_service)

    @provide
    def get_merge_engine(self) -> IMergeEngine:
        return GitMergeFileEngine()

    @provide
    def get_template_tree_renderer(
        self, template_repo: ITemplateRepository, template_renderer: TemplateRenderer
    ) -> ITemplateTreeRenderer:
        return TemplateTreeRenderer(template_repo, template_renderer)

    @provide
    def get_template_tracking_repo(self) -> ITemplateTrackingRepository:
        return JsonTemplateTrackingRepository()

    @provide
    def get_update_journal_repo(self) -> IUpdateJournalRepository:
        return JsonUpdateJournalRepository()

    @provide
    def get_template_base_service(
        self, tree_renderer: ITemplateTreeRenderer, base_store: ITemplateBaseStore, vcs_service: IVcsService
    ) -> TemplateBaseService:
        return TemplateBaseService(tree_renderer, base_store, vcs_service)

    @provide
    def get_template_update_planner(
        self,
        template_repo: ITemplateRepository,
        base_service: TemplateBaseService,
        merge_engine: IMergeEngine,
        tracking_repo: ITemplateTrackingRepository,
        signature_repo: ISignatureRepository,
    ) -> TemplateUpdatePlanner:
        return TemplateUpdatePlanner(template_repo, base_service, merge_engine, tracking_repo, signature_repo)

    @provide
    def get_project_access_service(
        self, template_repo: ITemplateRepository, journal_repo: IUpdateJournalRepository
    ) -> ProjectAccessService:
        return ProjectAccessService(template_repo, journal_repo)

    @provide
    def get_vcs_edit_throttle(self) -> IVcsEditThrottle:
        # App-scoped: the per-folder last-commit timestamps must persist across
        # the requests that save files.
        return VcsEditThrottle(min_interval_seconds=settings.vcs.edit_min_interval_seconds)
