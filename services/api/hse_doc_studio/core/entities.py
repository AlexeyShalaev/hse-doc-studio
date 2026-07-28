from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from hse_doc_studio.core.agent.entities import TokenUsage
from hse_doc_studio.core.catalog import ExtraSubmissionItem, SubmissionDocItem
from hse_doc_studio.core.enums import (
    AgentRunStatus,
    AIProviderType,
    ChangeLogKind,
    ChatContentKind,
    ChatMessageRole,
    CompileStatus,
    DocumentStatus,
    EngineType,
    GpuVendor,
    Lang,
    OllamaRuntimeMode,
    ProjectKind,
    ProjectStaffing,
    SigningIdentityKind,
    ToolApprovalDecision,
)
from hse_doc_studio.core.value_objects import (
    Author,
    CheckResult,
    ChecksOverride,
    CustomFileOverride,
    Person,
    ProjectLock,
    RequirementsFormat,
)


@dataclass
class Document:
    id: str
    status: DocumentStatus
    chosen_variant: str | None
    last_compile_id: UUID | None
    checks_override: ChecksOverride
    # Инстанс-модель (team mode): `def_id` — id определения документа в паке
    # (в solo совпадает с id; в team личный док имеет id "{def_id}--{owner}").
    # `owner` — слаг автора-владельца; None — общий документ (team: живёт в
    # shared/, solo: в корне). Все join'ы с паком идут через def_id.
    def_id: str = ""
    owner: str | None = None
    # User-uploaded replacement for the pack-generated file. When set, it
    # supersedes `chosen_variant` everywhere a source is resolved; see
    # CustomFileOverride for why `chosen_variant` is kept as-is.
    custom_file: CustomFileOverride | None = None

    def __post_init__(self) -> None:
        if not self.def_id:
            self.def_id = self.id


@dataclass
class Project:
    id: UUID
    name: str
    folder: Path
    lock: ProjectLock
    kind: ProjectKind
    staffing: ProjectStaffing
    lang: Lang
    authors: list[Author]
    meta: dict[str, Any]
    supervisor: Person | None
    co_supervisor: Person | None
    documents: list[Document]
    created_at: datetime
    updated_at: datetime
    # Академический руководитель ОП (блок «УТВЕРЖДАЮ» на титулах);
    # None → шаблон подставляет дефолт пака.
    academic_supervisor: Person | None = None
    # Team mode: ведём ли в этом проекте общие (shared) документы — команда
    # может договориться, что общее ТЗ живёт у другого участника. В solo
    # игнорируется (документы всегда в корне).
    shared_enabled: bool = True
    pinned: bool = False
    archived: bool = False
    checks_override: ChecksOverride = field(default_factory=ChecksOverride)
    # Per-project override of the requirements detection format. None → inherit
    # the pack template's RequirementsFormat (see TemplateVersion).
    requirements_format: RequirementsFormat | None = None


@dataclass
class CompileRecord:
    id: UUID
    project_folder: Path
    doc_id: str
    engine: EngineType
    status: CompileStatus
    started_at: datetime
    finished_at: datetime | None
    log: str
    output_path: Path | None
    check_results: list[CheckResult]
    pages: int | None
    # Prose totals from texcount on a successful build (None = not computed /
    # texcount unavailable). Count what renders as text, headings included.
    words: int | None = None
    chars: int | None = None


@dataclass
class ChangeLogEntry:
    id: UUID
    at: datetime
    kind: ChangeLogKind
    doc_id: str | None
    summary: str
    note: str | None


@dataclass
class PackSubmissionRecord:
    id: UUID
    project_folder: Path
    profile_id: str
    created_at: datetime
    doc_items: list[SubmissionDocItem]
    extra_items: list[ExtraSubmissionItem]
    # Archive of the submission (zip/tar.gz/7z/rar). `archive_format` records
    # which one was produced. `output_dir` is the unpacked folder of stamped
    # PDFs + extras that sits alongside the archive (browse/open-in-editor).
    output_path: Path
    output_dir: Path | None = None
    archive_format: str = "zip"


@dataclass
class AIProvider:
    # A configured AI backend the user can point agents at. `api_key` is stored
    # locally (data_dir/ai_providers.json) but is NEVER serialized into API
    # responses — the response schema exposes only `has_api_key`. `base_url` is
    # used by `openai`/`openai_compat` (empty = the SDK's default OpenAI host).
    id: UUID
    name: str
    type: AIProviderType
    api_key: str
    base_url: str
    models: list[str]
    created_at: datetime
    # Connection knobs (defaulted so older records without them still load):
    # ssl_verify=False disables TLS verification (self-signed/internal hosts);
    # connect_timeout_s caps the TCP/TLS handshake, request_timeout_s caps the
    # whole request.
    ssl_verify: bool = True
    connect_timeout_s: float = 10.0
    request_timeout_s: float = 60.0


@dataclass
class SigningIdentity:
    """A local signing credential (certificate + private key reference).

    Stored in data_dir/signing_identities.json (metadata) and
    data_dir/signing_keys/<id>/ (key material — never exposed via API).
    `trusted` is False for self-signed identities; True only when the
    certificate chains to an externally-accredited root CA (e.g. a real УЦ).
    """

    id: UUID
    label: str
    kind: SigningIdentityKind
    subject_cn: str
    not_after: datetime  # certificate expiry, UTC
    trusted: bool  # False for self-signed / internal
    created_at: datetime


@dataclass
class AgentPersona:
    # A user-defined agent role, stored locally (data_dir/agent_personas.json),
    # alongside AI providers. `instruction` is the system-prompt block prepended
    # when this role is selected. Shipped "built-in" roles live in
    # use_cases/chat/personas.py and are NOT persisted here.
    id: UUID
    label: str
    description: str
    instruction: str
    created_at: datetime


@dataclass(frozen=True)
class HardwareInfo:
    # Best-effort snapshot of the host's compute resources, used to size local
    # model recommendations. Any field may be None when detection fails (the
    # probe never raises). `docker_gpu_supported` is True only when the detected
    # GPU can actually be passed into a Docker container on THIS platform
    # (NVIDIA on Linux / Windows-WSL2) — it is False for Apple Metal and AMD,
    # where a managed container would fall back to CPU.
    gpu_vendor: GpuVendor
    gpu_name: str | None
    vram_mb: int | None
    total_ram_mb: int | None
    cpu_count: int | None
    docker_gpu_supported: bool


@dataclass(frozen=True)
class CatalogModel:
    # A curated Ollama model the UI offers to install locally. `name` is the
    # exact `ollama pull` tag. The hardware hints (`min_vram_gb` / `min_ram_gb`)
    # drive the recommendation; `family` groups variants in the UI.
    name: str
    label: str
    family: str
    params_b: float
    size_gb: float
    min_vram_gb: float
    min_ram_gb: float
    tasks: list[str]
    description: str


@dataclass(frozen=True)
class LoadedModel:
    # A model currently held in memory by Ollama (from /api/ps). Ollama unloads
    # it automatically after the keep_alive idle window; `expires_at` is when.
    # `vram_bytes` is how much sits in VRAM (0 = running on CPU).
    name: str
    size_bytes: int
    vram_bytes: int
    expires_at: str | None


@dataclass(frozen=True)
class PullJob:
    # A background model-download job. Runs in a backend task independent of any
    # request/SSE connection, so closing the UI never stops it. `message` is the
    # latest progress line (it embeds the percent); `state` flips to
    # success/failure when the pull finishes.
    name: str
    state: str  # "running" | "success" | "failure"
    message: str
    error: str | None


@dataclass(frozen=True)
class RegistryModel:
    # A model discovered by searching the public Ollama registry (ollama.com).
    # Best-effort: only `name` is guaranteed; the rest may be empty when the
    # scrape can't extract them. `name` is the base library name (pull defaults
    # to `:latest`); `pulls` is the human-readable popularity string.
    name: str
    description: str
    pulls: str
    capabilities: list[str]


@dataclass(frozen=True)
class OllamaRuntimeStatus:
    # Live view of the local runtime resolved by the runtime manager: which
    # transport is serving (native binary vs our container vs nothing), the
    # endpoint to talk to, and the models already pulled. `docker_available`
    # tells the UI whether the container fallback is even possible, and
    # `engine_image_installed` whether the `ollama/ollama` image is already
    # pulled (so the UI shows "install engine" vs "start").
    mode: OllamaRuntimeMode
    base_url: str | None
    version: str | None
    docker_available: bool
    engine_image_installed: bool
    installed_models: list[str]


# ── AI agent chat ────────────────────────────────────────────────────────────


@dataclass
class ChatContentBlock:
    # One ordered piece of a ChatMessage. A flat tagged union (by `kind`) instead
    # of a class hierarchy, matching the project's dataclass style. `call_id`
    # links a tool_call to its tool_result so the transcript round-trips to both
    # the OpenAI (tool_call_id) and Anthropic (tool_use_id) message shapes.
    kind: ChatContentKind
    text: str | None = None  # kind == text
    call_id: str | None = None  # tool_call & tool_result
    tool_name: str | None = None  # tool_call
    args: dict[str, Any] = field(default_factory=dict)  # tool_call
    result: str | None = None  # tool_result (human-readable)
    is_error: bool = False  # tool_result


@dataclass
class ChatMessage:
    # One persisted transcript entry. `seq` (monotonic per session, assigned at
    # append) drives replay order and the compaction cutoff — clock-skew immune.
    # `compacted` flips True when a summary covers this message; the raw text is
    # never removed from disk, only excluded from what is replayed to the model.
    id: UUID
    session_id: UUID
    run_id: UUID | None
    seq: int
    role: ChatMessageRole
    blocks: list[ChatContentBlock]
    created_at: datetime
    model: str | None = None
    provider_id: UUID | None = None
    usage: TokenUsage | None = None
    approval: ToolApprovalDecision = ToolApprovalDecision.auto
    compacted: bool = False


@dataclass
class ChatSession:
    # Manifest for one project-scoped conversation. `project_folder` is derived
    # from the on-disk location, never serialized (mirrors CompileRecord).
    id: UUID
    project_folder: Path
    title: str
    doc_id: str | None
    created_at: datetime
    updated_at: datetime
    archived: bool = False
    # The project this chat is bound to (for the unified agent's project tools +
    # context). None = a global/system chat. `project_folder` is the on-disk
    # storage location and is independent of this.
    project_id: UUID | None = None
    default_provider_id: UUID | None = None
    default_model: str | None = None
    # The agent role for this chat: a persona id ("methodologist", "custom", …) or
    # None (neutral / fall back to the project-level default). `persona_instructions`
    # holds the free-form text when persona == "custom".
    persona: str | None = None
    persona_instructions: str | None = None
    message_count: int = 0  # == next seq to assign
    last_run_id: UUID | None = None
    compacted_through_seq: int = -1  # messages with seq <= this are summarized
    summary_count: int = 0
    estimated_context_tokens: int = 0  # of the replayed context; drives compaction


@dataclass
class AgentRunRecord:
    # One agent turn running as a background task; the recovery target on restart.
    id: UUID
    session_id: UUID
    project_folder: Path
    status: AgentRunStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    trigger_seq: int  # the user-message seq that started this turn
    first_emitted_seq: int | None = None
    last_emitted_seq: int | None = None
    model: str | None = None
    provider_id: UUID | None = None
    iterations: int = 0
    usage: TokenUsage | None = None
    error: str | None = None
    # Per-turn diagnostics captured by the agent loop (stop reasons, tool
    # timings, warnings) for post-hoc debugging — survives reloads via the run JSON.
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ChatSummaryBlock:
    # A rolling compaction summary covering messages [covers_from_seq, covers_to_seq].
    id: UUID
    session_id: UUID
    covers_from_seq: int
    covers_to_seq: int
    created_at: datetime
    text: str
    model: str | None = None
    token_estimate: int | None = None
