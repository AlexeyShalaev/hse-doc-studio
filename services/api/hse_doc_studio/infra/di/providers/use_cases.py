from __future__ import annotations

from pathlib import Path

import httpx
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
from hse_doc_studio.core.fonts.entities import FontCatalog
from hse_doc_studio.core.fonts.repositories import (
    IFontDownloader,
    IFontMarketplace,
    IFontStore,
    ISystemFontProvider,
)
from hse_doc_studio.core.hse_persons.repositories import IHsePersonsGateway
from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.core.repositories import (
    IAgentPersonaRepository,
    IAIProviderRepository,
    IChangeLogRepository,
    IChatRepository,
    IFileRepository,
    IFilesystemBrowser,
    IFormStateRepository,
    IPackSubmissionRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ISettingsRepository,
    ISignatureRepository,
    ISigningIdentityRepository,
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
from hse_doc_studio.core.setup import (
    IDockerHealthProbe,
    IMountProbe,
    ISelfContainerInfo,
    ISetupApplier,
)
from hse_doc_studio.core.system_capacity import ISystemCapacityProbe
from hse_doc_studio.core.update.repositories import (
    ISelfUpdateGateway,
    IUpdateCheckRepository,
    IUpdateFeedGateway,
)
from hse_doc_studio.core.vcs.protocols import (
    IVcsEditThrottle,
    IVcsFolderLocks,
    IVcsService,
)
from hse_doc_studio.infra.ai.agent.edit_applier import FuzzySearchReplaceApplier
from hse_doc_studio.infra.ai.agent.run_bus import AgentRunBus
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager
from hse_doc_studio.infra.checks.runner import CheckRunner

# --- Compile ---
from hse_doc_studio.infra.compile.compile_runner import CompileRunner
from hse_doc_studio.infra.compile.concurrency import CompileConcurrencyLimiter
from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager
from hse_doc_studio.infra.compile.log_bus import CompileLogBus
from hse_doc_studio.infra.docker.cleanup_jobs import DockerCleanupJobManager
from hse_doc_studio.infra.docker.siblings import Reachability
from hse_doc_studio.infra.docker.system_manager import DockerSystemManager
from hse_doc_studio.infra.forms.form_renderer import FormOutputRenderer
from hse_doc_studio.infra.languagetool.container_manager import LanguageToolContainerManager
from hse_doc_studio.infra.office.convert_manager import OfficeConvertManager
from hse_doc_studio.infra.office.editor_manager import OfficeEditorManager
from hse_doc_studio.infra.persistence.compile import JsonCompileRepository
from hse_doc_studio.infra.project_init.template_renderer import TemplateRenderer
from hse_doc_studio.infra.runtime.environment import in_container
from hse_doc_studio.infra.signatures.pdf_stamper import PdfStamper
from hse_doc_studio.infra.signatures.pyhanko_signer import PyHankoPdfSigner
from hse_doc_studio.infra.submission.assembler import SubmissionAssembler

# --- Agent Personas (custom roles) ---
from hse_doc_studio.use_cases.agent_personas.create_agent_persona import CreateAgentPersonaUC
from hse_doc_studio.use_cases.agent_personas.delete_agent_persona import DeleteAgentPersonaUC
from hse_doc_studio.use_cases.agent_personas.get_agent_persona import GetAgentPersonaUC
from hse_doc_studio.use_cases.agent_personas.list_agent_personas import ListAgentPersonasUC
from hse_doc_studio.use_cases.agent_personas.list_selectable_personas import ListSelectablePersonasUC
from hse_doc_studio.use_cases.agent_personas.update_agent_persona import UpdateAgentPersonaUC

# --- AI Providers ---
from hse_doc_studio.use_cases.ai_providers.create_ai_provider import CreateAIProviderUC
from hse_doc_studio.use_cases.ai_providers.delete_ai_provider import DeleteAIProviderUC
from hse_doc_studio.use_cases.ai_providers.get_ai_provider import GetAIProviderUC
from hse_doc_studio.use_cases.ai_providers.list_ai_providers import ListAIProvidersUC
from hse_doc_studio.use_cases.ai_providers.list_provider_models import ListProviderModelsUC
from hse_doc_studio.use_cases.ai_providers.update_ai_provider import UpdateAIProviderUC

# --- AI Runtime (local Ollama) ---
from hse_doc_studio.use_cases.ai_runtime.delete_model import DeleteOllamaModelUC
from hse_doc_studio.use_cases.ai_runtime.detect_hardware import DetectHardwareUC
from hse_doc_studio.use_cases.ai_runtime.dismiss_pull import DismissPullUC
from hse_doc_studio.use_cases.ai_runtime.get_runtime_status import GetOllamaStatusUC
from hse_doc_studio.use_cases.ai_runtime.install_ollama_engine import InstallOllamaEngineUC
from hse_doc_studio.use_cases.ai_runtime.list_loaded_models import ListLoadedModelsUC
from hse_doc_studio.use_cases.ai_runtime.list_model_catalog import ListModelCatalogUC
from hse_doc_studio.use_cases.ai_runtime.list_pulls import ListPullsUC
from hse_doc_studio.use_cases.ai_runtime.search_registry import SearchRegistryUC
from hse_doc_studio.use_cases.ai_runtime.start_pull import StartPullUC
from hse_doc_studio.use_cases.ai_runtime.start_runtime import StartOllamaRuntimeUC
from hse_doc_studio.use_cases.ai_runtime.stop_runtime import StopOllamaRuntimeUC
from hse_doc_studio.use_cases.ai_runtime.sync_local_provider import SyncLocalOllamaProviderUC
from hse_doc_studio.use_cases.ai_runtime.unload_model import UnloadModelUC
from hse_doc_studio.use_cases.changelog.add_changelog_entry import AddChangelogEntryUC

# --- Changelog ---
from hse_doc_studio.use_cases.changelog.list_changelog import ListChangelogUC

# --- Chat (AI agent) ---
from hse_doc_studio.use_cases.chat._registry import ToolRegistry
from hse_doc_studio.use_cases.chat.cancel_chat_turn import CancelChatTurnUC
from hse_doc_studio.use_cases.chat.create_chat_session import CreateChatSessionUC
from hse_doc_studio.use_cases.chat.delete_chat_session import DeleteChatSessionUC
from hse_doc_studio.use_cases.chat.get_chat_run_stream import GetChatRunStreamUC
from hse_doc_studio.use_cases.chat.get_chat_session import GetChatSessionUC
from hse_doc_studio.use_cases.chat.list_agent_tools import ListAgentToolsUC
from hse_doc_studio.use_cases.chat.list_chat_sessions import ListChatSessionsUC
from hse_doc_studio.use_cases.chat.recover_stale_chat_runs import RecoverStaleChatRunsUC
from hse_doc_studio.use_cases.chat.rename_chat_session import RenameChatSessionUC
from hse_doc_studio.use_cases.chat.start_chat_turn import StartChatTurnUC
from hse_doc_studio.use_cases.chat.system_chat import (
    SystemCancelChatTurnUC,
    SystemCreateChatSessionUC,
    SystemDeleteChatSessionUC,
    SystemGetChatSessionUC,
    SystemListChatSessionsUC,
    SystemRenameChatSessionUC,
)
from hse_doc_studio.use_cases.chat.system_get_chat_run_stream import SystemGetChatRunStreamUC
from hse_doc_studio.use_cases.chat.system_start_chat_turn import SystemStartChatTurnUC
from hse_doc_studio.use_cases.chat.tools.ask_user import AskUserTool
from hse_doc_studio.use_cases.chat.tools.compile_document import CompileDocumentTool
from hse_doc_studio.use_cases.chat.tools.create_project import CreateProjectTool
from hse_doc_studio.use_cases.chat.tools.edit_tex import EditTexTool
from hse_doc_studio.use_cases.chat.tools.grep_project import GrepProjectTool
from hse_doc_studio.use_cases.chat.tools.list_check_findings import ListCheckFindingsTool
from hse_doc_studio.use_cases.chat.tools.list_documents import ListDocumentsTool
from hse_doc_studio.use_cases.chat.tools.list_projects import ListProjectsTool
from hse_doc_studio.use_cases.chat.tools.list_templates import ListTemplatesTool
from hse_doc_studio.use_cases.chat.tools.package_project import PackageProjectTool
from hse_doc_studio.use_cases.chat.tools.preview_requirements_format import PreviewRequirementsFormatTool
from hse_doc_studio.use_cases.chat.tools.read_pdf import ReadPdfTool
from hse_doc_studio.use_cases.chat.tools.read_tex import ReadTexTool
from hse_doc_studio.use_cases.chat.tools.set_engine import SetEngineTool
from hse_doc_studio.use_cases.chat.tools.set_language import SetLanguageTool
from hse_doc_studio.use_cases.chat.tools.set_project_meta import SetProjectMetaTool
from hse_doc_studio.use_cases.chat.tools.set_requirements_format import SetRequirementsFormatTool
from hse_doc_studio.use_cases.chat.tools.set_theme import SetThemeTool
from hse_doc_studio.use_cases.chat.tools.trace_requirements import TraceRequirementsTool
from hse_doc_studio.use_cases.chat.tools.vcs_diff import VcsDiffTool
from hse_doc_studio.use_cases.chat.tools.vcs_list_history import VcsListHistoryTool
from hse_doc_studio.use_cases.chat.tools.vcs_restore import VcsRestoreTool
from hse_doc_studio.use_cases.chat.tools.vcs_save_snapshot import VcsSaveSnapshotTool
from hse_doc_studio.use_cases.chat.tools.vcs_status import VcsStatusTool

# --- Checks ---
from hse_doc_studio.use_cases.checks.apply_check_fix import ApplyCheckFixUC
from hse_doc_studio.use_cases.checks.get_check_results import GetCheckResultsUC
from hse_doc_studio.use_cases.checks.get_normcontrol_report import GetNormcontrolReportUC
from hse_doc_studio.use_cases.checks.list_document_check_rules import ListDocumentCheckRulesUC
from hse_doc_studio.use_cases.checks.list_project_check_rules import ListProjectCheckRulesUC
from hse_doc_studio.use_cases.checks.run_checks import RunChecksUC
from hse_doc_studio.use_cases.compile.cancel_compile import CancelCompileUC
from hse_doc_studio.use_cases.compile.get_archived_pdf import GetArchivedPdfUC
from hse_doc_studio.use_cases.compile.get_compile import GetCompileUC
from hse_doc_studio.use_cases.compile.get_compile_stream import GetCompileStreamUC
from hse_doc_studio.use_cases.compile.get_docker_status import GetDockerStatusUC
from hse_doc_studio.use_cases.compile.install_image import InstallImageUC
from hse_doc_studio.use_cases.compile.list_compiles import ListCompilesUC
from hse_doc_studio.use_cases.compile.list_images import ListImagesUC
from hse_doc_studio.use_cases.compile.list_remote_tags import ListRemoteTagsUC
from hse_doc_studio.use_cases.compile.recover_stale_compiles import RecoverStaleCompilesUC
from hse_doc_studio.use_cases.compile.remove_image import RemoveImageUC
from hse_doc_studio.use_cases.compile.set_active_image import SetActiveImageUC
from hse_doc_studio.use_cases.compile.trigger_compile import TriggerCompileUC
from hse_doc_studio.use_cases.documents.get_document import GetDocumentUC

# --- Documents ---
from hse_doc_studio.use_cases.documents.list_documents import ListDocumentsUC
from hse_doc_studio.use_cases.documents.revert_custom_file import RevertCustomFileUC
from hse_doc_studio.use_cases.documents.update_document import UpdateDocumentUC
from hse_doc_studio.use_cases.documents.upload_custom_file import UploadCustomFileUC

# --- Export / Import (settings + AI providers bundle) ---
from hse_doc_studio.use_cases.export_import.export_data import ExportDataUC
from hse_doc_studio.use_cases.export_import.import_data import ImportDataUC

# --- Files ---
from hse_doc_studio.use_cases.files.create_dir import CreateDirUC
from hse_doc_studio.use_cases.files.delete_file import DeleteFileUC
from hse_doc_studio.use_cases.files.get_file import GetFileUC
from hse_doc_studio.use_cases.files.get_file_version import GetFileVersionUC
from hse_doc_studio.use_cases.files.list_file_tree import ListFileTreeUC
from hse_doc_studio.use_cases.files.move_file import MoveFileUC
from hse_doc_studio.use_cases.files.put_file import PutFileUC
from hse_doc_studio.use_cases.fonts.adopt_host_fonts import AdoptHostFontsUC
from hse_doc_studio.use_cases.fonts.get_font_file import GetFontFileUC
from hse_doc_studio.use_cases.fonts.import_system_fonts import ImportSystemFontsUC
from hse_doc_studio.use_cases.fonts.install_font import InstallFontUC
from hse_doc_studio.use_cases.fonts.install_marketplace_font import InstallMarketplaceFontUC
from hse_doc_studio.use_cases.fonts.list_font_catalog import ListFontCatalogUC
from hse_doc_studio.use_cases.fonts.list_fonts import ListFontsUC
from hse_doc_studio.use_cases.fonts.list_system_fonts import ListSystemFontsUC
from hse_doc_studio.use_cases.fonts.remove_font import RemoveFontUC
from hse_doc_studio.use_cases.fonts.search_marketplace import SearchMarketplaceUC
from hse_doc_studio.use_cases.fonts.upload_font import UploadFontUC

# --- Forms (pack-driven form engine; AI declaration is one form) ---
from hse_doc_studio.use_cases.forms.get_form import GetFormUC
from hse_doc_studio.use_cases.forms.list_forms import ListFormsUC
from hse_doc_studio.use_cases.forms.render_form import RenderFormUC
from hse_doc_studio.use_cases.forms.update_form import UpdateFormUC

# --- Filesystem ---
from hse_doc_studio.use_cases.fs.browse_filesystem import BrowseFilesystemUC
from hse_doc_studio.use_cases.fs.inspect_folder import InspectFolderUC
from hse_doc_studio.use_cases.hse_persons.get_facets import GetHseFacetsUC
from hse_doc_studio.use_cases.hse_persons.get_person_detail import GetHsePersonDetailUC
from hse_doc_studio.use_cases.hse_persons.search_persons import SearchHsePersonsUC

# --- LanguageTool ---
from hse_doc_studio.use_cases.languagetool.get_languagetool_status import GetLanguageToolStatusUC
from hse_doc_studio.use_cases.languagetool.install_languagetool_image import InstallLanguageToolImageUC
from hse_doc_studio.use_cases.languagetool.list_languagetool_images import ListLanguageToolImagesUC
from hse_doc_studio.use_cases.languagetool.list_languagetool_remote_tags import (
    ListLanguageToolRemoteTagsUC,
)
from hse_doc_studio.use_cases.languagetool.remove_languagetool_image import RemoveLanguageToolImageUC
from hse_doc_studio.use_cases.languagetool.set_active_languagetool_image import (
    SetActiveLanguageToolImageUC,
)

# --- Office editor (ONLYOFFICE Document Server) ---
from hse_doc_studio.use_cases.office_editor.get_editor_config import GetOfficeEditorConfigUC
from hse_doc_studio.use_cases.office_editor.handle_callback import OfficeEditorCallbackUC

# --- Office services (Gotenberg + ONLYOFFICE image management) ---
from hse_doc_studio.use_cases.office_services.get_office_services_status import (
    GetOfficeServicesStatusUC,
)
from hse_doc_studio.use_cases.office_services.install_office_service_image import (
    InstallOfficeServiceImageUC,
)
from hse_doc_studio.use_cases.office_services.list_office_service_images import (
    ListOfficeServiceImagesUC,
)
from hse_doc_studio.use_cases.office_services.list_office_service_remote_tags import (
    ListOfficeServiceRemoteTagsUC,
)
from hse_doc_studio.use_cases.office_services.set_active_office_service_image import (
    SetActiveOfficeServiceImageUC,
)
from hse_doc_studio.use_cases.projects.connect_project import ConnectProjectUC

# --- Projects ---
from hse_doc_studio.use_cases.projects.create_project import CreateProjectUC
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC
from hse_doc_studio.use_cases.projects.get_project_suggestions import (
    GetProjectSuggestionsUC,
)
from hse_doc_studio.use_cases.projects.list_projects import ListProjectsUC
from hse_doc_studio.use_cases.projects.manage_nda import (
    DeleteNdaFilesUC,
    GetNdaStatusUC,
    InstantiateNdaUC,
)
from hse_doc_studio.use_cases.projects.move_project import MoveProjectUC
from hse_doc_studio.use_cases.projects.unregister_project import UnregisterProjectUC
from hse_doc_studio.use_cases.projects.update_project import UpdateProjectUC
from hse_doc_studio.use_cases.projects.update_team_set import UpdateTeamSetUC

# --- Requirements ---
from hse_doc_studio.use_cases.requirements.get_requirements import GetRequirementsUC
from hse_doc_studio.use_cases.requirements.update_requirements_format import (
    UpdateRequirementsFormatUC,
)

# --- Settings ---
from hse_doc_studio.use_cases.settings.get_settings import GetSettingsUC
from hse_doc_studio.use_cases.settings.update_settings import UpdateSettingsUC
from hse_doc_studio.use_cases.setup.apply_setup import ApplySetupUC
from hse_doc_studio.use_cases.setup.inspect_setup import InspectSetupUC

# --- Signatures ---
from hse_doc_studio.use_cases.signatures.delete_signature_png import DeleteSignaturePngUC
from hse_doc_studio.use_cases.signatures.get_signatures import GetSignaturesUC
from hse_doc_studio.use_cases.signatures.get_signed_doc_pdf import GetSignedDocPdfUC
from hse_doc_studio.use_cases.signatures.update_signature_placement import UpdateSignaturePlacementUC
from hse_doc_studio.use_cases.signatures.update_slot_config import UpdateSlotConfigUC
from hse_doc_studio.use_cases.signatures.upload_signature_png import UploadSignaturePngUC
from hse_doc_studio.use_cases.signing_identities.create_self_signed import CreateSelfSignedUC
from hse_doc_studio.use_cases.signing_identities.delete_signing_identity import DeleteSigningIdentityUC
from hse_doc_studio.use_cases.signing_identities.import_pkcs12 import ImportPkcs12UC
from hse_doc_studio.use_cases.signing_identities.list_signing_identities import ListSigningIdentitiesUC
from hse_doc_studio.use_cases.submission.create_submission import CreateSubmissionUC
from hse_doc_studio.use_cases.submission.get_submission_file import GetSubmissionFileUC

# --- Submission ---
from hse_doc_studio.use_cases.submission.get_submission_profiles import GetSubmissionProfilesUC
from hse_doc_studio.use_cases.submission.list_submissions import ListSubmissionsUC
from hse_doc_studio.use_cases.submission.preview_custom_docs import PreviewSubmissionCustomDocsUC
from hse_doc_studio.use_cases.synctex.query_synctex import SyncTexUC

# --- System (Docker disk usage / cleanup, update checks) ---
from hse_doc_studio.use_cases.system.auto_update import AutoUpdateUC
from hse_doc_studio.use_cases.system.check_updates import CheckUpdatesUC
from hse_doc_studio.use_cases.system.cleanup_docker import (
    CancelDockerCleanupUC,
    GetDockerCleanupJobUC,
    StartDockerCleanupUC,
)
from hse_doc_studio.use_cases.system.get_docker_disk_usage import GetDockerDiskUsageUC
from hse_doc_studio.use_cases.system.get_update_status import GetUpdateStatusUC
from hse_doc_studio.use_cases.system.list_versions import ListVersionsUC

# --- VCS (ProjectVCS / "Версии") ---
from hse_doc_studio.use_cases.vcs.create_vcs_snapshot import CreateVcsSnapshotUC
from hse_doc_studio.use_cases.vcs.ensure_vcs import EnsureVcsUC
from hse_doc_studio.use_cases.vcs.get_vcs_commit import GetVcsCommitUC
from hse_doc_studio.use_cases.vcs.get_vcs_diff import GetVcsDiffUC
from hse_doc_studio.use_cases.vcs.get_vcs_settings import GetVcsSettingsUC
from hse_doc_studio.use_cases.vcs.get_vcs_status import GetVcsStatusUC
from hse_doc_studio.use_cases.vcs.list_vcs_history import ListVcsHistoryUC
from hse_doc_studio.use_cases.vcs.restore_vcs import RestoreVcsUC
from hse_doc_studio.use_cases.vcs.update_vcs_settings import UpdateVcsSettingsUC
from hse_doc_studio.use_cases.vcs.vcs_branches import (
    CreateVcsBranchUC,
    DeleteVcsBranchUC,
    ListVcsBranchesUC,
    SwitchVcsBranchUC,
)
from hse_doc_studio.use_cases.vcs.vcs_tags import (
    CreateVcsTagUC,
    DeleteVcsTagUC,
    ListVcsTagsUC,
)


def _docker_default_images() -> dict[str, str]:
    # settings-key → config default: the ACTIVE image of each managed category
    # (runtime override wins) is protected from disk cleanup.
    return {
        "compile_image": settings.compile.image,
        "languagetool_image": settings.languagetool.image,
        "office_convert_image": settings.office_convert.image,
        "office_editor_image": settings.office_editor.image,
    }


def _docker_always_protected() -> frozenset[str]:
    version = settings.get_app_version()
    return frozenset(
        {
            settings.ollama.image,
            f"{settings.image_base}:{version}",
            f"{settings.image_base}:latest",
        }
    )


class UseCaseProvider(Provider):
    scope = Scope.REQUEST

    # ------------------------------------------------------------------ Projects

    @provide
    def get_create_project_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        template_renderer: TemplateRenderer,
        vcs_service: IVcsService,
    ) -> CreateProjectUC:
        return CreateProjectUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            template_service=template_service,
            template_renderer=template_renderer,
            vcs_service=vcs_service,
        )

    @provide
    def get_update_team_set_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_renderer: TemplateRenderer,
        vcs_service: IVcsService,
    ) -> UpdateTeamSetUC:
        return UpdateTeamSetUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            template_renderer=template_renderer,
            vcs_service=vcs_service,
        )

    @provide
    def get_connect_project_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
    ) -> ConnectProjectUC:
        return ConnectProjectUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            vcs_service=vcs_service,
        )

    @provide
    def get_list_projects_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> ListProjectsUC:
        return ListProjectsUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
        )

    @provide
    def get_project_suggestions_uc(
        self,
        list_projects: ListProjectsUC,
    ) -> GetProjectSuggestionsUC:
        return GetProjectSuggestionsUC(
            list_projects=list_projects,
            default_projects_dir=settings.data_dir.expanduser() / "projects",
        )

    @provide
    def get_get_project_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> GetProjectUC:
        return GetProjectUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
        )

    @provide
    def get_update_project_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> UpdateProjectUC:
        return UpdateProjectUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
        )

    @provide
    def get_unregister_project_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> UnregisterProjectUC:
        return UnregisterProjectUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
        )

    @provide
    def get_move_project_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        compile_runner: CompileRunner,
    ) -> MoveProjectUC:
        return MoveProjectUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            compile_runner=compile_runner,
        )

    @provide
    def get_get_nda_status_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
    ) -> GetNdaStatusUC:
        return GetNdaStatusUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
        )

    @provide
    def get_instantiate_nda_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
    ) -> InstantiateNdaUC:
        return InstantiateNdaUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
        )

    @provide
    def get_delete_nda_files_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
    ) -> DeleteNdaFilesUC:
        return DeleteNdaFilesUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
        )

    # ------------------------------------------------------------------ Documents

    @provide
    def get_list_documents_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
    ) -> ListDocumentsUC:
        return ListDocumentsUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
        )

    @provide
    def get_get_document_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
    ) -> GetDocumentUC:
        return GetDocumentUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
        )

    @provide
    def get_update_document_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_renderer: TemplateRenderer,
    ) -> UpdateDocumentUC:
        return UpdateDocumentUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            template_renderer=template_renderer,
        )

    @provide
    def get_upload_custom_file_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        file_repo: IFileRepository,
        signature_repo: ISignatureRepository,
        office_manager: OfficeConvertManager,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
        vcs_throttle: IVcsEditThrottle,
    ) -> UploadCustomFileUC:
        return UploadCustomFileUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            file_repo=file_repo,
            signature_repo=signature_repo,
            office_manager=office_manager,
            vcs_service=vcs_service,
            vcs_locks=vcs_locks,
            vcs_throttle=vcs_throttle,
        )

    @provide
    def get_revert_custom_file_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
        vcs_throttle: IVcsEditThrottle,
    ) -> RevertCustomFileUC:
        return RevertCustomFileUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            file_repo=file_repo,
            vcs_service=vcs_service,
            vcs_locks=vcs_locks,
            vcs_throttle=vcs_throttle,
        )

    # ------------------------------------------------------------------ Checks

    @provide
    def get_list_document_check_rules_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        check_resolution_service: CheckResolutionService,
    ) -> ListDocumentCheckRulesUC:
        return ListDocumentCheckRulesUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            check_resolution_service=check_resolution_service,
        )

    @provide
    def get_list_project_check_rules_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        check_resolution_service: CheckResolutionService,
    ) -> ListProjectCheckRulesUC:
        return ListProjectCheckRulesUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            check_resolution_service=check_resolution_service,
        )

    @provide
    def get_get_check_results_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        check_resolution_service: CheckResolutionService,
        file_repo: IFileRepository,
    ) -> GetCheckResultsUC:
        return GetCheckResultsUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            check_resolution_service=check_resolution_service,
            file_repo=file_repo,
            compile_repo=JsonCompileRepository(),
        )

    @provide
    def get_run_checks_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        check_resolution_service: CheckResolutionService,
        check_runner: CheckRunner,
        lt_manager: LanguageToolContainerManager,
        settings_repo: ISettingsRepository,
    ) -> RunChecksUC:
        return RunChecksUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            template_service=template_service,
            check_resolution_service=check_resolution_service,
            check_runner=check_runner,
            lt_manager=lt_manager,
            settings_repo=settings_repo,
        )

    @provide
    def get_apply_check_fix_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
        vcs_throttle: IVcsEditThrottle,
    ) -> ApplyCheckFixUC:
        return ApplyCheckFixUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            file_repo=file_repo,
            vcs_service=vcs_service,
            vcs_locks=vcs_locks,
            vcs_throttle=vcs_throttle,
        )

    @provide
    def get_normcontrol_report_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
    ) -> GetNormcontrolReportUC:
        return GetNormcontrolReportUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            compile_repo=JsonCompileRepository(),
        )

    # ------------------------------------------------------------------ Forms engine

    @provide
    def get_list_forms_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        form_state_repo: IFormStateRepository,
        validation_service: FormValidationService,
    ) -> ListFormsUC:
        return ListFormsUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            form_state_repo=form_state_repo,
            validation_service=validation_service,
        )

    @provide
    def get_get_form_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        form_state_repo: IFormStateRepository,
        validation_service: FormValidationService,
    ) -> GetFormUC:
        return GetFormUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            form_state_repo=form_state_repo,
            validation_service=validation_service,
        )

    @provide
    def get_update_form_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        form_state_repo: IFormStateRepository,
        validation_service: FormValidationService,
    ) -> UpdateFormUC:
        return UpdateFormUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            form_state_repo=form_state_repo,
            validation_service=validation_service,
        )

    @provide
    def get_render_form_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        form_state_repo: IFormStateRepository,
        renderer: FormOutputRenderer,
    ) -> RenderFormUC:
        return RenderFormUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            form_state_repo=form_state_repo,
            renderer=renderer,
        )

    # ------------------------------------------------------------------ Changelog

    @provide
    def get_list_changelog_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        changelog_repo: IChangeLogRepository,
    ) -> ListChangelogUC:
        return ListChangelogUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            changelog_repo=changelog_repo,
        )

    @provide
    def get_add_changelog_entry_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        changelog_repo: IChangeLogRepository,
    ) -> AddChangelogEntryUC:
        return AddChangelogEntryUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            changelog_repo=changelog_repo,
        )

    # ------------------------------------------------------------------ VCS

    @provide
    def get_ensure_vcs_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
    ) -> EnsureVcsUC:
        return EnsureVcsUC(project_repo, project_index_repo, vcs_service)

    @provide
    def get_get_vcs_status_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
    ) -> GetVcsStatusUC:
        return GetVcsStatusUC(project_repo, project_index_repo, vcs_service)

    @provide
    def get_list_vcs_history_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
        template_repo: ITemplateRepository,
    ) -> ListVcsHistoryUC:
        return ListVcsHistoryUC(project_repo, project_index_repo, vcs_service, template_repo)

    @provide
    def get_get_vcs_commit_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
    ) -> GetVcsCommitUC:
        return GetVcsCommitUC(project_repo, project_index_repo, vcs_service)

    @provide
    def get_get_vcs_diff_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
    ) -> GetVcsDiffUC:
        return GetVcsDiffUC(project_repo, project_index_repo, vcs_service)

    @provide
    def get_create_vcs_snapshot_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
        changelog_repo: IChangeLogRepository,
        vcs_locks: IVcsFolderLocks,
    ) -> CreateVcsSnapshotUC:
        return CreateVcsSnapshotUC(project_repo, project_index_repo, vcs_service, changelog_repo, vcs_locks)

    @provide
    def get_restore_vcs_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
        changelog_repo: IChangeLogRepository,
        vcs_locks: IVcsFolderLocks,
    ) -> RestoreVcsUC:
        return RestoreVcsUC(project_repo, project_index_repo, vcs_service, changelog_repo, vcs_locks)

    @provide
    def get_get_vcs_settings_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> GetVcsSettingsUC:
        return GetVcsSettingsUC(project_repo, project_index_repo)

    @provide
    def get_update_vcs_settings_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> UpdateVcsSettingsUC:
        return UpdateVcsSettingsUC(project_repo, project_index_repo)

    @provide
    def get_list_vcs_branches_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
    ) -> ListVcsBranchesUC:
        return ListVcsBranchesUC(project_repo, project_index_repo, vcs_service)

    @provide
    def get_create_vcs_branch_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
    ) -> CreateVcsBranchUC:
        return CreateVcsBranchUC(project_repo, project_index_repo, vcs_service, vcs_locks)

    @provide
    def get_switch_vcs_branch_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
    ) -> SwitchVcsBranchUC:
        return SwitchVcsBranchUC(project_repo, project_index_repo, vcs_service, vcs_locks)

    @provide
    def get_delete_vcs_branch_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
    ) -> DeleteVcsBranchUC:
        return DeleteVcsBranchUC(project_repo, project_index_repo, vcs_service, vcs_locks)

    @provide
    def get_list_vcs_tags_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
    ) -> ListVcsTagsUC:
        return ListVcsTagsUC(project_repo, project_index_repo, vcs_service)

    @provide
    def get_create_vcs_tag_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
    ) -> CreateVcsTagUC:
        return CreateVcsTagUC(project_repo, project_index_repo, vcs_service, vcs_locks)

    @provide
    def get_delete_vcs_tag_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
    ) -> DeleteVcsTagUC:
        return DeleteVcsTagUC(project_repo, project_index_repo, vcs_service, vcs_locks)

    # ------------------------------------------------------------------ Files

    @provide
    def get_get_file_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
    ) -> GetFileUC:
        return GetFileUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            file_repo=file_repo,
        )

    @provide
    def get_get_file_version_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
    ) -> GetFileVersionUC:
        return GetFileVersionUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            file_repo=file_repo,
        )

    @provide
    def get_put_file_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
        vcs_throttle: IVcsEditThrottle,
    ) -> PutFileUC:
        return PutFileUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            file_repo=file_repo,
            vcs_service=vcs_service,
            vcs_locks=vcs_locks,
            vcs_throttle=vcs_throttle,
        )

    @provide
    def get_list_file_tree_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        template_repo: ITemplateRepository,
    ) -> ListFileTreeUC:
        return ListFileTreeUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            file_repo=file_repo,
            template_repo=template_repo,
        )

    @provide
    def get_delete_file_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        template_repo: ITemplateRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
        vcs_throttle: IVcsEditThrottle,
    ) -> DeleteFileUC:
        return DeleteFileUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            file_repo=file_repo,
            template_repo=template_repo,
            vcs_service=vcs_service,
            vcs_locks=vcs_locks,
            vcs_throttle=vcs_throttle,
        )

    @provide
    def get_move_file_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        template_repo: ITemplateRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
        vcs_throttle: IVcsEditThrottle,
    ) -> MoveFileUC:
        return MoveFileUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            file_repo=file_repo,
            template_repo=template_repo,
            vcs_service=vcs_service,
            vcs_locks=vcs_locks,
            vcs_throttle=vcs_throttle,
        )

    @provide
    def get_create_dir_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
    ) -> CreateDirUC:
        return CreateDirUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            file_repo=file_repo,
        )

    # ------------------------------------------------------------------ Requirements

    @provide
    def get_get_requirements_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        matching_service: RequirementMatchingService,
    ) -> GetRequirementsUC:
        return GetRequirementsUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            file_repo=file_repo,
            template_repo=template_repo,
            template_service=template_service,
            matching_service=matching_service,
        )

    @provide
    def get_update_requirements_format_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        matching_service: RequirementMatchingService,
    ) -> UpdateRequirementsFormatUC:
        return UpdateRequirementsFormatUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            matching_service=matching_service,
        )

    # ------------------------------------------------------------------ Filesystem

    @provide
    def get_browse_filesystem_uc(
        self,
        filesystem_browser: IFilesystemBrowser,
        paths: PathMapping,
    ) -> BrowseFilesystemUC:
        return BrowseFilesystemUC(browser=filesystem_browser, paths=paths)

    @provide
    def get_inspect_folder_uc(
        self,
        project_repo: IProjectRepository,
    ) -> InspectFolderUC:
        return InspectFolderUC(project_repo=project_repo)

    # ------------------------------------------------------------------ Settings

    @provide
    def get_get_settings_uc(
        self,
        settings_repo: ISettingsRepository,
        capacity_probe: ISystemCapacityProbe,
    ) -> GetSettingsUC:
        return GetSettingsUC(settings_repo=settings_repo, capacity_probe=capacity_probe)

    @provide
    def get_update_settings_uc(
        self,
        settings_repo: ISettingsRepository,
        capacity_probe: ISystemCapacityProbe,
    ) -> UpdateSettingsUC:
        return UpdateSettingsUC(settings_repo=settings_repo, capacity_probe=capacity_probe)

    # ------------------------------------------------------------------ Export / Import

    @provide
    def get_export_data_uc(
        self,
        settings_repo: ISettingsRepository,
        ai_provider_repo: IAIProviderRepository,
        agent_persona_repo: IAgentPersonaRepository,
        capacity_probe: ISystemCapacityProbe,
    ) -> ExportDataUC:
        return ExportDataUC(
            settings_repo=settings_repo,
            ai_provider_repo=ai_provider_repo,
            agent_persona_repo=agent_persona_repo,
            capacity_probe=capacity_probe,
        )

    @provide
    def get_import_data_uc(
        self,
        settings_repo: ISettingsRepository,
        ai_provider_repo: IAIProviderRepository,
        agent_persona_repo: IAgentPersonaRepository,
    ) -> ImportDataUC:
        return ImportDataUC(
            settings_repo=settings_repo,
            ai_provider_repo=ai_provider_repo,
            agent_persona_repo=agent_persona_repo,
        )

    # ------------------------------------------------------------------ AI Providers

    @provide
    def get_list_ai_providers_uc(
        self,
        ai_provider_repo: IAIProviderRepository,
    ) -> ListAIProvidersUC:
        return ListAIProvidersUC(ai_provider_repo=ai_provider_repo)

    @provide
    def get_get_ai_provider_uc(
        self,
        ai_provider_repo: IAIProviderRepository,
    ) -> GetAIProviderUC:
        return GetAIProviderUC(ai_provider_repo=ai_provider_repo)

    @provide
    def get_create_ai_provider_uc(
        self,
        ai_provider_repo: IAIProviderRepository,
    ) -> CreateAIProviderUC:
        return CreateAIProviderUC(ai_provider_repo=ai_provider_repo)

    @provide
    def get_update_ai_provider_uc(
        self,
        ai_provider_repo: IAIProviderRepository,
    ) -> UpdateAIProviderUC:
        return UpdateAIProviderUC(ai_provider_repo=ai_provider_repo)

    @provide
    def get_delete_ai_provider_uc(
        self,
        ai_provider_repo: IAIProviderRepository,
        settings_repo: ISettingsRepository,
    ) -> DeleteAIProviderUC:
        return DeleteAIProviderUC(ai_provider_repo=ai_provider_repo, settings_repo=settings_repo)

    @provide
    def get_list_provider_models_uc(
        self,
        ai_provider_repo: IAIProviderRepository,
        model_lister: IAIModelLister,
    ) -> ListProviderModelsUC:
        return ListProviderModelsUC(ai_provider_repo=ai_provider_repo, model_lister=model_lister)

    # ------------------------------------------------------------------ Agent Personas (custom roles)

    @provide
    def get_list_agent_personas_uc(self, agent_persona_repo: IAgentPersonaRepository) -> ListAgentPersonasUC:
        return ListAgentPersonasUC(agent_persona_repo=agent_persona_repo)

    @provide
    def get_get_agent_persona_uc(self, agent_persona_repo: IAgentPersonaRepository) -> GetAgentPersonaUC:
        return GetAgentPersonaUC(agent_persona_repo=agent_persona_repo)

    @provide
    def get_create_agent_persona_uc(self, agent_persona_repo: IAgentPersonaRepository) -> CreateAgentPersonaUC:
        return CreateAgentPersonaUC(agent_persona_repo=agent_persona_repo)

    @provide
    def get_update_agent_persona_uc(self, agent_persona_repo: IAgentPersonaRepository) -> UpdateAgentPersonaUC:
        return UpdateAgentPersonaUC(agent_persona_repo=agent_persona_repo)

    @provide
    def get_delete_agent_persona_uc(self, agent_persona_repo: IAgentPersonaRepository) -> DeleteAgentPersonaUC:
        return DeleteAgentPersonaUC(agent_persona_repo=agent_persona_repo)

    @provide
    def get_list_selectable_personas_uc(self, agent_persona_repo: IAgentPersonaRepository) -> ListSelectablePersonasUC:
        return ListSelectablePersonasUC(agent_persona_repo=agent_persona_repo)

    # ------------------------------------------------------------------ AI Runtime (local Ollama)

    @provide
    def get_detect_hardware_uc(
        self,
        hardware_probe: IHardwareProbe,
    ) -> DetectHardwareUC:
        return DetectHardwareUC(hardware_probe=hardware_probe)

    @provide
    def get_list_model_catalog_uc(
        self,
        hardware_probe: IHardwareProbe,
        catalog: ModelCatalog,
    ) -> ListModelCatalogUC:
        return ListModelCatalogUC(hardware_probe=hardware_probe, catalog=catalog)

    @provide
    def get_get_ollama_status_uc(
        self,
        runtime: IOllamaRuntime,
    ) -> GetOllamaStatusUC:
        return GetOllamaStatusUC(runtime=runtime)

    @provide
    def get_start_ollama_runtime_uc(
        self,
        runtime: IOllamaRuntime,
    ) -> StartOllamaRuntimeUC:
        return StartOllamaRuntimeUC(runtime=runtime)

    @provide
    def get_stop_ollama_runtime_uc(
        self,
        runtime: IOllamaRuntime,
    ) -> StopOllamaRuntimeUC:
        return StopOllamaRuntimeUC(runtime=runtime)

    @provide
    def get_install_ollama_engine_uc(
        self,
        image_manager: DockerImageManager,
    ) -> InstallOllamaEngineUC:
        return InstallOllamaEngineUC(image_manager=image_manager, image=settings.ollama.image)

    @provide
    def get_start_pull_uc(
        self,
        jobs: IPullModelJobs,
        catalog: ModelCatalog,
    ) -> StartPullUC:
        return StartPullUC(
            jobs=jobs,
            catalog=catalog,
            allow_custom=settings.ollama.allow_custom_models,
        )

    @provide
    def get_list_pulls_uc(self, jobs: IPullModelJobs) -> ListPullsUC:
        return ListPullsUC(jobs=jobs)

    @provide
    def get_dismiss_pull_uc(self, jobs: IPullModelJobs) -> DismissPullUC:
        return DismissPullUC(jobs=jobs)

    @provide
    def get_list_loaded_models_uc(self, runtime: IOllamaRuntime) -> ListLoadedModelsUC:
        return ListLoadedModelsUC(runtime=runtime)

    @provide
    def get_unload_model_uc(self, runtime: IOllamaRuntime) -> UnloadModelUC:
        return UnloadModelUC(runtime=runtime)

    @provide
    def get_search_registry_uc(
        self,
        registry: IOllamaRegistry,
    ) -> SearchRegistryUC:
        return SearchRegistryUC(registry=registry)

    @provide
    def get_delete_ollama_model_uc(
        self,
        runtime: IOllamaRuntime,
    ) -> DeleteOllamaModelUC:
        return DeleteOllamaModelUC(runtime=runtime)

    @provide
    def get_sync_local_ollama_provider_uc(
        self,
        runtime: IOllamaRuntime,
        ai_provider_repo: IAIProviderRepository,
    ) -> SyncLocalOllamaProviderUC:
        return SyncLocalOllamaProviderUC(
            runtime=runtime,
            ai_provider_repo=ai_provider_repo,
            provider_name=settings.ollama.provider_name,
        )

    # ------------------------------------------------------------------ Compile

    @provide
    def get_trigger_compile_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        check_resolution_service: CheckResolutionService,
        check_runner: CheckRunner,
        changelog_repo: IChangeLogRepository,
        log_bus: CompileLogBus,
        settings_repo: ISettingsRepository,
        compile_runner: CompileRunner,
        compile_limiter: CompileConcurrencyLimiter,
        executor: DockerCompileExecutor,
        image_manager: DockerImageManager,
        lt_manager: LanguageToolContainerManager,
        office_manager: OfficeConvertManager,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
        capacity_probe: ISystemCapacityProbe,
    ) -> TriggerCompileUC:
        return TriggerCompileUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            compile_repo=JsonCompileRepository(),
            template_repo=template_repo,
            template_service=template_service,
            check_resolution_service=check_resolution_service,
            check_runner=check_runner,
            changelog_repo=changelog_repo,
            log_bus=log_bus,
            settings_repo=settings_repo,
            compile_runner=compile_runner,
            compile_limiter=compile_limiter,
            executor=executor,
            image_manager=image_manager,
            lt_manager=lt_manager,
            office_manager=office_manager,
            vcs_service=vcs_service,
            vcs_locks=vcs_locks,
            capacity_probe=capacity_probe,
        )

    @provide
    def get_get_docker_status_uc(
        self,
        image_manager: DockerImageManager,
    ) -> GetDockerStatusUC:
        return GetDockerStatusUC(image_manager=image_manager)

    @provide
    def get_check_updates_uc(
        self,
        update_feed: IUpdateFeedGateway,
        update_cache: IUpdateCheckRepository,
    ) -> CheckUpdatesUC:
        return CheckUpdatesUC(
            feed=update_feed,
            cache=update_cache,
            current_version=settings.get_app_version(),
        )

    @provide
    def get_list_versions_uc(
        self,
        update_cache: IUpdateCheckRepository,
    ) -> ListVersionsUC:
        return ListVersionsUC(cache=update_cache, current_version=settings.get_app_version())

    @provide
    def get_auto_update_uc(
        self,
        check_updates: CheckUpdatesUC,
        settings_repo: ISettingsRepository,
        self_updater: ISelfUpdateGateway,
    ) -> AutoUpdateUC:
        return AutoUpdateUC(
            check_updates=check_updates,
            settings_repo=settings_repo,
            updater=self_updater,
            current_version=settings.get_app_version(),
        )

    @provide
    def get_get_update_status_uc(
        self,
        update_cache: IUpdateCheckRepository,
    ) -> GetUpdateStatusUC:
        return GetUpdateStatusUC(
            cache=update_cache,
            current_version=settings.get_app_version(),
            feed_enabled=settings.update_feed_enabled(),
        )

    @provide
    def get_adopt_host_fonts_uc(self, provider: ISystemFontProvider, store: IFontStore) -> AdoptHostFontsUC:
        return AdoptHostFontsUC(provider, store)

    # ------------------------------------------------------------------ Первоначальная настройка

    @provide
    def get_inspect_setup_uc(
        self,
        docker: IDockerHealthProbe,
        self_info: ISelfContainerInfo,
        paths: PathMapping,
    ) -> InspectSetupUC:
        return InspectSetupUC(
            docker,
            self_info,
            paths,
            in_container=in_container(),
            host_data_dir=settings.host_data_dir,
        )

    @provide
    def get_apply_setup_uc(self, probe: IMountProbe, applier: ISetupApplier) -> ApplySetupUC:
        return ApplySetupUC(probe, applier)

    @provide
    def get_get_docker_disk_usage_uc(
        self,
        docker_system_manager: DockerSystemManager,
        settings_repo: ISettingsRepository,
    ) -> GetDockerDiskUsageUC:
        return GetDockerDiskUsageUC(
            manager=docker_system_manager,
            settings_repo=settings_repo,
            default_images=_docker_default_images(),
            always_protected=_docker_always_protected(),
        )

    @provide
    def get_start_docker_cleanup_uc(
        self,
        docker_system_manager: DockerSystemManager,
        cleanup_jobs: DockerCleanupJobManager,
        settings_repo: ISettingsRepository,
    ) -> StartDockerCleanupUC:
        return StartDockerCleanupUC(
            manager=docker_system_manager,
            jobs=cleanup_jobs,
            settings_repo=settings_repo,
            default_images=_docker_default_images(),
            always_protected=_docker_always_protected(),
        )

    @provide
    def get_get_docker_cleanup_job_uc(
        self,
        cleanup_jobs: DockerCleanupJobManager,
    ) -> GetDockerCleanupJobUC:
        return GetDockerCleanupJobUC(jobs=cleanup_jobs)

    @provide
    def get_cancel_docker_cleanup_uc(
        self,
        cleanup_jobs: DockerCleanupJobManager,
    ) -> CancelDockerCleanupUC:
        return CancelDockerCleanupUC(jobs=cleanup_jobs)

    @provide
    def get_list_images_uc(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> ListImagesUC:
        return ListImagesUC(image_manager=image_manager, settings_repo=settings_repo)

    @provide
    def get_install_image_uc(
        self,
        image_manager: DockerImageManager,
    ) -> InstallImageUC:
        return InstallImageUC(image_manager=image_manager)

    @provide
    def get_list_remote_tags_uc(
        self,
        image_manager: DockerImageManager,
    ) -> ListRemoteTagsUC:
        return ListRemoteTagsUC(image_manager=image_manager)

    @provide
    def get_set_active_image_uc(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> SetActiveImageUC:
        return SetActiveImageUC(image_manager=image_manager, settings_repo=settings_repo)

    @provide
    def get_remove_image_uc(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> RemoveImageUC:
        return RemoveImageUC(image_manager=image_manager, settings_repo=settings_repo)

    # --- Fonts ---

    @provide
    def get_list_fonts_uc(self, font_store: IFontStore) -> ListFontsUC:
        return ListFontsUC(store=font_store)

    @provide
    def get_upload_font_uc(self, font_store: IFontStore) -> UploadFontUC:
        return UploadFontUC(store=font_store)

    @provide
    def get_remove_font_uc(self, font_store: IFontStore) -> RemoveFontUC:
        return RemoveFontUC(store=font_store)

    @provide
    def get_get_font_file_uc(self, font_store: IFontStore) -> GetFontFileUC:
        return GetFontFileUC(store=font_store)

    @provide
    def get_list_font_catalog_uc(self, font_catalog: FontCatalog, font_store: IFontStore) -> ListFontCatalogUC:
        return ListFontCatalogUC(catalog=font_catalog, store=font_store)

    @provide
    def get_install_font_uc(
        self,
        font_catalog: FontCatalog,
        font_downloader: IFontDownloader,
        font_store: IFontStore,
    ) -> InstallFontUC:
        return InstallFontUC(catalog=font_catalog, downloader=font_downloader, store=font_store)

    @provide
    def get_list_system_fonts_uc(
        self, system_font_provider: ISystemFontProvider, font_store: IFontStore
    ) -> ListSystemFontsUC:
        return ListSystemFontsUC(provider=system_font_provider, store=font_store)

    @provide
    def get_import_system_fonts_uc(
        self, system_font_provider: ISystemFontProvider, font_store: IFontStore
    ) -> ImportSystemFontsUC:
        return ImportSystemFontsUC(provider=system_font_provider, store=font_store)

    @provide
    def get_search_marketplace_uc(self, font_marketplace: IFontMarketplace) -> SearchMarketplaceUC:
        return SearchMarketplaceUC(marketplace=font_marketplace)

    @provide
    def get_search_hse_persons_uc(self, hse_persons_gateway: IHsePersonsGateway) -> SearchHsePersonsUC:
        return SearchHsePersonsUC(gateway=hse_persons_gateway)

    @provide
    def get_hse_person_detail_uc(self, hse_persons_gateway: IHsePersonsGateway) -> GetHsePersonDetailUC:
        return GetHsePersonDetailUC(gateway=hse_persons_gateway)

    @provide
    def get_hse_facets_uc(self, hse_persons_gateway: IHsePersonsGateway) -> GetHseFacetsUC:
        return GetHseFacetsUC(gateway=hse_persons_gateway)

    @provide
    def get_install_marketplace_font_uc(
        self,
        font_marketplace: IFontMarketplace,
        font_downloader: IFontDownloader,
        font_store: IFontStore,
    ) -> InstallMarketplaceFontUC:
        return InstallMarketplaceFontUC(marketplace=font_marketplace, downloader=font_downloader, store=font_store)

    @provide
    def get_get_compile_stream_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        log_bus: CompileLogBus,
    ) -> GetCompileStreamUC:
        # GetCompileStreamUC needs the concrete JsonCompileRepository for get_for_project.
        return GetCompileStreamUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            compile_repo=JsonCompileRepository(),
            log_bus=log_bus,
        )

    @provide
    def get_get_compile_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> GetCompileUC:
        return GetCompileUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            compile_repo=JsonCompileRepository(),
        )

    @provide
    def get_archived_pdf_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> GetArchivedPdfUC:
        return GetArchivedPdfUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
        )

    @provide
    def get_synctex_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
    ) -> SyncTexUC:
        return SyncTexUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            template_service=template_service,
        )

    @provide
    def get_list_compiles_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> ListCompilesUC:
        return ListCompilesUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            compile_repo=JsonCompileRepository(),
        )

    @provide
    def get_cancel_compile_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        compile_runner: CompileRunner,
        log_bus: CompileLogBus,
    ) -> CancelCompileUC:
        return CancelCompileUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            compile_repo=JsonCompileRepository(),
            compile_runner=compile_runner,
            log_bus=log_bus,
        )

    @provide
    def get_recover_stale_compiles_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> RecoverStaleCompilesUC:
        return RecoverStaleCompilesUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            compile_repo=JsonCompileRepository(),
        )

    # ------------------------------------------------------------------ LanguageTool

    @provide
    def get_get_languagetool_status_uc(
        self,
        container_manager: LanguageToolContainerManager,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> GetLanguageToolStatusUC:
        return GetLanguageToolStatusUC(
            container_manager=container_manager,
            image_manager=image_manager,
            settings_repo=settings_repo,
        )

    @provide
    def get_list_languagetool_images_uc(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> ListLanguageToolImagesUC:
        return ListLanguageToolImagesUC(image_manager=image_manager, settings_repo=settings_repo)

    @provide
    def get_list_languagetool_remote_tags_uc(
        self,
        image_manager: DockerImageManager,
    ) -> ListLanguageToolRemoteTagsUC:
        return ListLanguageToolRemoteTagsUC(image_manager=image_manager)

    @provide
    def get_install_languagetool_image_uc(
        self,
        image_manager: DockerImageManager,
    ) -> InstallLanguageToolImageUC:
        return InstallLanguageToolImageUC(image_manager=image_manager)

    @provide
    def get_set_active_languagetool_image_uc(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> SetActiveLanguageToolImageUC:
        return SetActiveLanguageToolImageUC(image_manager=image_manager, settings_repo=settings_repo)

    @provide
    def get_remove_languagetool_image_uc(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> RemoveLanguageToolImageUC:
        return RemoveLanguageToolImageUC(image_manager=image_manager, settings_repo=settings_repo)

    # ------------------------------------------------------------------ Office editor (ONLYOFFICE)

    @provide
    def get_get_office_editor_config_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        office_editor_manager: OfficeEditorManager,
        reachability: Reachability,
        settings_repo: ISettingsRepository,
        ai_provider_repo: IAIProviderRepository,
    ) -> GetOfficeEditorConfigUC:
        # reachability — как DS-контейнер достучится до нас: по общей сети или
        # через хостовый шлюз, выясняется в рантайме.
        # settings_repo — runtime-выбор образа DS (office_editor_image).
        # ai_provider_repo — синк наших AI-провайдеров в AI-плагин DS.
        return GetOfficeEditorConfigUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            manager=office_editor_manager,
            reachability=reachability,
            settings_repo=settings_repo,
            ai_provider_repo=ai_provider_repo,
        )

    @provide
    def get_office_editor_callback_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        office_editor_manager: OfficeEditorManager,
        put_file_uc: PutFileUC,
        office_convert_manager: OfficeConvertManager,
        settings_repo: ISettingsRepository,
        client: httpx.Client,
    ) -> OfficeEditorCallbackUC:
        # Запись сохранённого документа идёт через put-file: guard путей +
        # edit-коммит в ProjectVCS — как у любой другой правки файла.
        # convert_manager + settings_repo — фоновая доконвертация pptx→PDF
        # после сохранения, чтобы «Превью» обновлялось без пересборки.
        return OfficeEditorCallbackUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            manager=office_editor_manager,
            put_file_uc=put_file_uc,
            convert_manager=office_convert_manager,
            settings_repo=settings_repo,
            client=client,
        )

    # ------------------------------------------------------------------ Office services (images)

    @provide
    def get_get_office_services_status_uc(
        self,
        office_convert_manager: OfficeConvertManager,
        office_editor_manager: OfficeEditorManager,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> GetOfficeServicesStatusUC:
        return GetOfficeServicesStatusUC(
            convert_manager=office_convert_manager,
            editor_manager=office_editor_manager,
            image_manager=image_manager,
            settings_repo=settings_repo,
        )

    @provide
    def get_list_office_service_images_uc(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> ListOfficeServiceImagesUC:
        return ListOfficeServiceImagesUC(image_manager=image_manager, settings_repo=settings_repo)

    @provide
    def get_list_office_service_remote_tags_uc(
        self,
        image_manager: DockerImageManager,
    ) -> ListOfficeServiceRemoteTagsUC:
        return ListOfficeServiceRemoteTagsUC(image_manager=image_manager)

    @provide
    def get_set_active_office_service_image_uc(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> SetActiveOfficeServiceImageUC:
        return SetActiveOfficeServiceImageUC(image_manager=image_manager, settings_repo=settings_repo)

    @provide
    def get_install_office_service_image_uc(
        self,
        image_manager: DockerImageManager,
    ) -> InstallOfficeServiceImageUC:
        return InstallOfficeServiceImageUC(image_manager=image_manager)

    # ------------------------------------------------------------------ Signatures

    @provide
    def get_get_signatures_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
    ) -> GetSignaturesUC:
        return GetSignaturesUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            signature_repo=signature_repo,
            template_repo=template_repo,
        )

    @provide
    def get_update_signature_placement_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
    ) -> UpdateSignaturePlacementUC:
        return UpdateSignaturePlacementUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            signature_repo=signature_repo,
            template_repo=template_repo,
        )

    @provide
    def get_upload_signature_png_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
    ) -> UploadSignaturePngUC:
        return UploadSignaturePngUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            signature_repo=signature_repo,
            template_repo=template_repo,
        )

    @provide
    def get_delete_signature_png_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
    ) -> DeleteSignaturePngUC:
        return DeleteSignaturePngUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            signature_repo=signature_repo,
        )

    @provide
    def get_get_signed_doc_pdf_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        signing_identity_repo: ISigningIdentityRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        pdf_stamper: PdfStamper,
        pyhanko_signer: PyHankoPdfSigner,
    ) -> GetSignedDocPdfUC:
        return GetSignedDocPdfUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            signature_repo=signature_repo,
            signing_identity_repo=signing_identity_repo,
            template_repo=template_repo,
            template_service=template_service,
            pdf_stamper=pdf_stamper,
            pyhanko_signer=pyhanko_signer,
        )

    # ------------------------------------------------------------------ Submission

    @provide
    def get_get_submission_profiles_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
    ) -> GetSubmissionProfilesUC:
        return GetSubmissionProfilesUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
        )

    @provide
    def get_preview_submission_custom_docs_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        submission_profile_service: SubmissionProfileService,
    ) -> PreviewSubmissionCustomDocsUC:
        return PreviewSubmissionCustomDocsUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            submission_profile_service=submission_profile_service,
        )

    @provide
    def get_create_submission_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        submission_repo: IPackSubmissionRepository,
        submission_profile_service: SubmissionProfileService,
        signature_repo: ISignatureRepository,
        assembler: SubmissionAssembler,
        changelog_repo: IChangeLogRepository,
        render_form_uc: RenderFormUC,
    ) -> CreateSubmissionUC:
        return CreateSubmissionUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            submission_repo=submission_repo,
            submission_profile_service=submission_profile_service,
            signature_repo=signature_repo,
            assembler=assembler,
            changelog_repo=changelog_repo,
            render_form_uc=render_form_uc,
        )

    @provide
    def get_list_submissions_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        submission_repo: IPackSubmissionRepository,
        template_repo: ITemplateRepository,
    ) -> ListSubmissionsUC:
        return ListSubmissionsUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            submission_repo=submission_repo,
            template_repo=template_repo,
        )

    @provide
    def get_get_submission_file_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        submission_repo: IPackSubmissionRepository,
    ) -> GetSubmissionFileUC:
        return GetSubmissionFileUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            submission_repo=submission_repo,
        )

    # ------------------------------------------------------------------ Chat (AI agent)

    @provide
    def get_list_agent_tools_uc(self, registry: ToolRegistry) -> ListAgentToolsUC:
        return ListAgentToolsUC(registry)

    @provide
    def get_list_chat_sessions_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        chat_repo: IChatRepository,
        run_manager: AgentRunManager,
    ) -> ListChatSessionsUC:
        return ListChatSessionsUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            chat_repo=chat_repo,
            run_manager=run_manager,
        )

    @provide
    def get_create_chat_session_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        chat_repo: IChatRepository,
    ) -> CreateChatSessionUC:
        return CreateChatSessionUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            chat_repo=chat_repo,
        )

    @provide
    def get_rename_chat_session_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        chat_repo: IChatRepository,
    ) -> RenameChatSessionUC:
        return RenameChatSessionUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            chat_repo=chat_repo,
        )

    @provide
    def get_delete_chat_session_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        chat_repo: IChatRepository,
        run_manager: AgentRunManager,
    ) -> DeleteChatSessionUC:
        return DeleteChatSessionUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            chat_repo=chat_repo,
            run_manager=run_manager,
        )

    @provide
    def get_get_chat_session_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        chat_repo: IChatRepository,
        run_manager: AgentRunManager,
    ) -> GetChatSessionUC:
        return GetChatSessionUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            chat_repo=chat_repo,
            run_manager=run_manager,
        )

    @provide
    def get_chat_tool_registry(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        get_file_uc: GetFileUC,
        put_file_uc: PutFileUC,
        get_check_results_uc: GetCheckResultsUC,
        get_requirements_uc: GetRequirementsUC,
        update_requirements_format_uc: UpdateRequirementsFormatUC,
        update_settings_uc: UpdateSettingsUC,
        update_project_uc: UpdateProjectUC,
        trigger_compile_uc: TriggerCompileUC,
        create_submission_uc: CreateSubmissionUC,
        get_submission_profiles_uc: GetSubmissionProfilesUC,
        create_project_uc: CreateProjectUC,
        template_repo: ITemplateRepository,
        edit_applier: FuzzySearchReplaceApplier,
        get_vcs_status_uc: GetVcsStatusUC,
        list_vcs_history_uc: ListVcsHistoryUC,
        get_vcs_diff_uc: GetVcsDiffUC,
        create_vcs_snapshot_uc: CreateVcsSnapshotUC,
        restore_vcs_uc: RestoreVcsUC,
    ) -> ToolRegistry:
        # ONE unified catalog: project tools (requires_project=True) + app/system
        # tools (requires_project=False). The loop filters by whether the chat has
        # a project, so the same agent serves both project and no-project chats.
        get_project_uc = GetProjectUC(project_repo, project_index_repo)
        list_documents_uc = ListDocumentsUC(project_repo, project_index_repo)
        list_projects_uc = ListProjectsUC(project_repo, project_index_repo)
        definitions = [
            # --- project-scoped (require a project) ---
            ReadTexTool(get_file_uc).definition(),
            ReadPdfTool(get_file_uc).definition(),
            GrepProjectTool(file_repo, get_project_uc).definition(),
            ListCheckFindingsTool(get_check_results_uc).definition(),
            ListDocumentsTool(list_documents_uc).definition(),
            TraceRequirementsTool(get_requirements_uc).definition(),
            PreviewRequirementsFormatTool(get_requirements_uc).definition(),
            SetRequirementsFormatTool(update_requirements_format_uc, get_requirements_uc).definition(),
            EditTexTool(get_file_uc, put_file_uc, edit_applier).definition(),
            SetLanguageTool(update_project_uc).definition(),
            SetProjectMetaTool(update_project_uc).definition(),
            CompileDocumentTool(trigger_compile_uc, get_project_uc, JsonCompileRepository()).definition(),
            PackageProjectTool(create_submission_uc, get_submission_profiles_uc).definition(),
            # --- VCS / «Версии» (project-scoped) ---
            VcsStatusTool(get_vcs_status_uc).definition(),
            VcsListHistoryTool(list_vcs_history_uc).definition(),
            VcsDiffTool(get_vcs_diff_uc).definition(),
            VcsSaveSnapshotTool(create_vcs_snapshot_uc).definition(),
            VcsRestoreTool(restore_vcs_uc).definition(),
            # --- app/system (work without a project) ---
            AskUserTool().definition(),
            SetThemeTool(update_settings_uc).definition(),
            SetEngineTool(update_settings_uc).definition(),
            ListTemplatesTool(template_repo).definition(),
            ListProjectsTool(list_projects_uc).definition(),
            CreateProjectTool(create_project_uc).definition(),
        ]
        return ToolRegistry(definitions)

    @provide
    def get_start_chat_turn_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        chat_repo: IChatRepository,
        ai_provider_repo: IAIProviderRepository,
        settings_repo: ISettingsRepository,
        agent_provider: IAgentProvider,
        registry: ToolRegistry,
        approval_gate: IApprovalGate,
        bus: AgentRunBus,
        run_manager: AgentRunManager,
        context_service: ChatContextService,
        summarizer: IChatSummarizer,
        agent_persona_repo: IAgentPersonaRepository,
    ) -> StartChatTurnUC:
        return StartChatTurnUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            chat_repo=chat_repo,
            ai_provider_repo=ai_provider_repo,
            settings_repo=settings_repo,
            agent_provider=agent_provider,
            registry=registry,
            approval_gate=approval_gate,
            bus=bus,
            run_manager=run_manager,
            context_service=context_service,
            summarizer=summarizer,
            agent_persona_repo=agent_persona_repo,
        )

    @provide
    def get_get_chat_run_stream_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        chat_repo: IChatRepository,
        bus: AgentRunBus,
    ) -> GetChatRunStreamUC:
        return GetChatRunStreamUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            chat_repo=chat_repo,
            bus=bus,
        )

    @provide
    def get_cancel_chat_turn_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        chat_repo: IChatRepository,
        bus: AgentRunBus,
        run_manager: AgentRunManager,
    ) -> CancelChatTurnUC:
        return CancelChatTurnUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            chat_repo=chat_repo,
            bus=bus,
            run_manager=run_manager,
        )

    @provide
    def get_recover_stale_chat_runs_uc(
        self,
        project_index_repo: IProjectIndexRepository,
        chat_repo: IChatRepository,
        settings_repo: ISettingsRepository,
    ) -> RecoverStaleChatRunsUC:
        return RecoverStaleChatRunsUC(
            project_index_repo=project_index_repo,
            chat_repo=chat_repo,
            settings_repo=settings_repo,
        )

    # ---------------------------------------------------------------- System (no-project) agent

    def _system_folder(self) -> Path:
        # App-level root that hosts the system agent's chats, reusing the
        # per-project chat repo against this folder (under <data_dir>/system-chats).
        folder = Path(settings.data_dir).expanduser() / "system-chats"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @provide
    def get_system_list_chat_sessions_uc(
        self, chat_repo: IChatRepository, run_manager: AgentRunManager
    ) -> SystemListChatSessionsUC:
        return SystemListChatSessionsUC(self._system_folder(), chat_repo, run_manager)

    @provide
    def get_system_create_chat_session_uc(self, chat_repo: IChatRepository) -> SystemCreateChatSessionUC:
        return SystemCreateChatSessionUC(self._system_folder(), chat_repo)

    @provide
    def get_system_get_chat_session_uc(
        self, chat_repo: IChatRepository, run_manager: AgentRunManager
    ) -> SystemGetChatSessionUC:
        return SystemGetChatSessionUC(self._system_folder(), chat_repo, run_manager)

    @provide
    def get_system_rename_chat_session_uc(self, chat_repo: IChatRepository) -> SystemRenameChatSessionUC:
        return SystemRenameChatSessionUC(self._system_folder(), chat_repo)

    @provide
    def get_system_delete_chat_session_uc(
        self, chat_repo: IChatRepository, run_manager: AgentRunManager
    ) -> SystemDeleteChatSessionUC:
        return SystemDeleteChatSessionUC(self._system_folder(), chat_repo, run_manager)

    @provide
    def get_system_cancel_chat_turn_uc(
        self, chat_repo: IChatRepository, bus: AgentRunBus, run_manager: AgentRunManager
    ) -> SystemCancelChatTurnUC:
        return SystemCancelChatTurnUC(self._system_folder(), chat_repo, bus, run_manager)

    @provide
    def get_system_get_chat_run_stream_uc(
        self, chat_repo: IChatRepository, bus: AgentRunBus
    ) -> SystemGetChatRunStreamUC:
        return SystemGetChatRunStreamUC(self._system_folder(), chat_repo, bus)

    @provide
    def get_system_start_chat_turn_uc(
        self,
        chat_repo: IChatRepository,
        ai_provider_repo: IAIProviderRepository,
        settings_repo: ISettingsRepository,
        agent_provider: IAgentProvider,
        registry: ToolRegistry,
        approval_gate: IApprovalGate,
        bus: AgentRunBus,
        run_manager: AgentRunManager,
        context_service: ChatContextService,
        summarizer: IChatSummarizer,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        agent_persona_repo: IAgentPersonaRepository,
    ) -> SystemStartChatTurnUC:
        return SystemStartChatTurnUC(
            folder=self._system_folder(),
            chat_repo=chat_repo,
            ai_provider_repo=ai_provider_repo,
            settings_repo=settings_repo,
            agent_provider=agent_provider,
            registry=registry,
            approval_gate=approval_gate,
            bus=bus,
            run_manager=run_manager,
            context_service=context_service,
            summarizer=summarizer,
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            agent_persona_repo=agent_persona_repo,
        )

    @provide
    def get_update_slot_config_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        signing_identity_repo: ISigningIdentityRepository,
        template_repo: ITemplateRepository,
    ) -> UpdateSlotConfigUC:
        return UpdateSlotConfigUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            signature_repo=signature_repo,
            signing_identity_repo=signing_identity_repo,
            template_repo=template_repo,
        )

    # -------------------------------------------------------- Signing identities

    @provide
    def get_list_signing_identities_uc(
        self,
        repo: ISigningIdentityRepository,
    ) -> ListSigningIdentitiesUC:
        return ListSigningIdentitiesUC(repo=repo)

    @provide
    def get_create_self_signed_uc(
        self,
        repo: ISigningIdentityRepository,
    ) -> CreateSelfSignedUC:
        return CreateSelfSignedUC(repo=repo)

    @provide
    def get_import_pkcs12_uc(
        self,
        repo: ISigningIdentityRepository,
    ) -> ImportPkcs12UC:
        return ImportPkcs12UC(repo=repo)

    @provide
    def get_delete_signing_identity_uc(
        self,
        repo: ISigningIdentityRepository,
    ) -> DeleteSigningIdentityUC:
        return DeleteSigningIdentityUC(repo=repo)
