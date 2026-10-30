"""Внешние сервисы: LanguageTool, конвертация и редактор Office, Ollama, агент, справочник сотрудников ВШЭ."""

from pathlib import Path

from pydantic import BaseModel, Field


class LanguageToolConfig(BaseModel):
    """Managed LanguageTool container settings.

    LanguageTool runs as an optional, backend-managed Docker container (the
    same `docker` CLI pattern as the LaTeX compile image). These are deployment
    defaults; the user's chosen image and the enabled flag / server URL are
    runtime settings persisted in config.json.
    """

    image: str = Field(
        default="erikvl87/languagetool:latest",
        description="Default LanguageTool image when the user hasn't picked one in Settings.",
    )
    allowed_repos: list[str] = Field(
        default=["erikvl87/languagetool"],
        description="Docker Hub repos the UI may list/pull/run for LanguageTool (allowlist, separate from compile).",
    )
    docker_hub_base: str = Field(
        default="https://hub.docker.com/v2",
        description="Docker Hub v2 API base URL used to fetch LanguageTool tag lists.",
    )
    container_name: str = Field(
        default="hse-languagetool",
        description="Stable name of the managed LanguageTool container (used to adopt/reconcile across restarts).",
    )
    container_port: int = Field(
        default=8010,
        description="Port LanguageTool listens on inside the container; published to a free host port.",
    )
    health_path: str = Field(
        default="/v2/languages",
        description="HTTP path polled to decide the container is up and serving.",
    )
    model_volume_name: str = Field(
        default="hse-languagetool-cache",
        description="Named Docker volume persisting n-gram/model data across container restarts.",
    )
    request_timeout_s: float = Field(
        default=30.0,
        description="Timeout for a single LanguageTool /v2/check request (large documents are slow).",
    )
    health_timeout_s: float = Field(
        default=5.0,
        description="Timeout for a single container health probe.",
    )
    startup_timeout_s: float = Field(
        default=90.0,
        description="How long to wait for the container to become healthy after start.",
    )
    idle_timeout_s: float = Field(
        default=600.0,
        description="Stop the auto-started container after this many seconds with no checks (frees RAM).",
    )
    stop_on_shutdown: bool = Field(
        default=True,
        description="Stop the managed container when the backend shuts down (it auto-starts again on demand).",
    )
    pool_replicas: list[str] = Field(
        default_factory=list,
        description="Серверный режим: URL реплик LanguageTool за общим пулом (…LANGUAGETOOL__POOL_REPLICAS).",
    )
    pool_max_inflight: int = Field(default=4, ge=1, description="Одновременных запросов на одну реплику пула.")
    pool_user_rate_per_s: float = Field(
        default=2.0, gt=0, description="Пополнение доли пользователя, запросов в секунду."
    )
    pool_user_burst: int = Field(default=20, ge=1, description="Запас запросов у пользователя.")
    pool_circuit_failures: int = Field(default=3, ge=1, description="Подряд неудач реплики до размыкания цепи.")
    pool_circuit_open_s: float = Field(default=30.0, gt=0, description="Сколько реплика исключена после размыкания.")
    pool_cache_entries: int = Field(default=2048, ge=0, description="Размер LRU-кэша абзацев прокси, 0 выключает.")
    pool_max_text_chars: int = Field(default=400_000, ge=1, description="Наибольший текст одного запроса к прокси.")


class OfficeConvertConfig(BaseModel):
    """Managed Gotenberg (LibreOffice) container for office→PDF conversion.

    Powers the pptx-презентация preview: on every «Собрать» of a copy-only
    pptx variant the file is converted to a sibling PDF shown in the built-in
    viewer. Same lifecycle pattern as LanguageTool: lazy start on a free port,
    idle-stop; installing the image (`docker pull gotenberg/gotenberg:8`) is
    the opt-in — without it the build succeeds and the preview falls back to
    a download card.
    """

    image: str = Field(
        default="gotenberg/gotenberg:8",
        description="Default Gotenberg image when the user hasn't picked one in Settings (office→PDF conversion).",
    )
    allowed_repos: list[str] = Field(
        default=["gotenberg/gotenberg"],
        description="Docker Hub repos the UI may list/pull/run for the convert service (allowlist, as LanguageTool).",
    )
    docker_hub_base: str = Field(
        default="https://hub.docker.com/v2",
        description="Docker Hub v2 API base URL used to fetch Gotenberg tag lists.",
    )
    container_name: str = Field(
        default="hse-office-convert",
        description="Stable name of the managed Gotenberg container (adopted across backend restarts).",
    )
    container_port: int = Field(
        default=3000,
        description="Port Gotenberg listens on inside the container; published to a free host port.",
    )
    health_path: str = Field(
        default="/health",
        description="HTTP path polled to decide the container is up and serving.",
    )
    convert_timeout_s: float = Field(
        default=120.0,
        description="Timeout for a single LibreOffice conversion request (large decks are slow).",
    )
    health_timeout_s: float = Field(
        default=5.0,
        description="Timeout for a single container health probe.",
    )
    startup_timeout_s: float = Field(
        default=60.0,
        description="How long to wait for the container to become healthy after start.",
    )
    idle_timeout_s: float = Field(
        default=600.0,
        description="Stop the auto-started container after this many seconds without conversions (frees RAM).",
    )


class OfficeEditorConfig(BaseModel):
    """Managed ONLYOFFICE Document Server container for in-app pptx editing.

    Powers the «Редактировать» flow of the pptx-презентация: the Document
    Server is embedded via its JS API and saves edits back through the
    /office-editor/callback endpoint (writes go through the put-file use case,
    so they land in the per-project VCS). Same lifecycle pattern as Gotenberg:
    lazy start on a free port, idle-stop; installing the image (`docker pull
    onlyoffice/documentserver`) is the opt-in — without it the UI shows an
    install hint instead of the editor.
    """

    image: str = Field(
        default="onlyoffice/documentserver:latest",
        description="Default ONLYOFFICE Document Server image when the user hasn't picked one in Settings.",
    )
    allowed_repos: list[str] = Field(
        default=["onlyoffice/documentserver"],
        description="Docker Hub repos the UI may list/pull/run for the editor service (allowlist, as LanguageTool).",
    )
    docker_hub_base: str = Field(
        default="https://hub.docker.com/v2",
        description="Docker Hub v2 API base URL used to fetch Document Server tag lists.",
    )
    container_name: str = Field(
        default="hse-office-editor",
        description="Stable name of the managed Document Server container (adopted across backend restarts).",
    )
    container_port: int = Field(
        default=80,
        description="Port Document Server listens on inside the container; published to a free host port.",
    )
    health_path: str = Field(
        default="/healthcheck",
        description="HTTP path polled to decide the container is up and serving (body must contain 'true').",
    )
    startup_timeout_s: float = Field(
        default=180.0,
        description="How long to wait for the container to become healthy after start (DS is slow to boot).",
    )
    health_timeout_s: float = Field(
        default=5.0,
        description="Timeout for a single container health probe.",
    )
    idle_timeout_s: float = Field(
        default=1800.0,
        description="Stop the auto-started container after this many seconds without editor activity (frees RAM).",
    )
    backend_host_for_container: str = Field(
        default="host.docker.internal",
        description=(
            "How the Document Server container reaches THIS backend (document download + save callback). "
            "host.docker.internal works natively via --add-host=host-gateway; compose deployments may "
            "override with the backend service name."
        ),
    )
    pool_replicas: list[str] = Field(
        default_factory=list,
        description=(
            "Server mode: base URLs of the Document Server replicas (empty means the editor is unavailable). "
            "A document is pinned to one replica by rendezvous hashing of its key."
        ),
    )
    pool_max_sessions: int = Field(
        default=18,
        ge=1,
        description="Concurrent editing sessions across the installation (Community Edition allows about 20).",
    )
    pool_session_ttl_s: float = Field(
        default=1800.0,
        gt=0,
        description="A session without a callback or keepalive for this long is released.",
    )
    pool_probe_interval_s: float = Field(default=15.0, gt=0, description="How often replica health is re-polled.")
    pool_retry_after_s: int = Field(default=30, ge=1, description="Retry hint returned with the editor_busy state.")
    jwt_secret: str = Field(
        default="",
        description="Server mode: JWT secret shared with all replicas; derived from the key ring if empty.",
    )
    backend_internal_url: str = Field(
        default="",
        description="Server mode: base URL of this API as the Document Server replicas see it (document and callback).",
    )
    token_ttl_s: int = Field(
        default=43_200,
        ge=60,
        description="Lifetime of the signed document and callback tokens (a long editing session needs saves).",
    )


class OllamaCatalogEntry(BaseModel):
    """One curated local model surfaced (with hardware-fit hints) in the UI.

    `name` is the exact `ollama pull` tag. The catalog is the *recommended* set,
    not a hard allowlist: when `OllamaConfig.allow_custom_models` is on, the user
    may also pull any other validly-named model (free-text or registry search).
    """

    name: str = Field(description="Exact `ollama pull` tag, e.g. 'qwen2.5:7b'.")
    label: str = Field(description="Human-friendly name shown in the catalog.")
    family: str = Field(default="", description="Model family for grouping/filter (Qwen2.5, Llama, Gemma 2, …).")
    params_b: float = Field(description="Parameter count in billions (display + default-pick sizing).")
    size_gb: float = Field(description="Approximate download size in GB.")
    min_vram_gb: float = Field(description="VRAM needed to run comfortably on a GPU.")
    min_ram_gb: float = Field(description="System RAM needed to run on CPU (no GPU).")
    tasks: list[str] = Field(default_factory=list, description="What it's good for (вычитка, переписывание, …).")
    description: str = Field(default="", description="Short RU description.")


def _default_ollama_catalog() -> list[OllamaCatalogEntry]:
    # A broad set of instruct models across families and hardware tiers. Qwen2.5
    # is instruct-tuned by default in Ollama and strong on Russian; sizes are
    # approximate Q4 download sizes. Beyond this list the user can pull any model
    # by name (see allow_custom_models) — this is the curated *starting point*.
    return [
        # ── Tiny: CPU / weak laptops ────────────────────────────────────────
        OllamaCatalogEntry(
            name="qwen2.5:0.5b",
            label="Qwen2.5 0.5B",
            family="Qwen2.5",
            params_b=0.5,
            size_gb=0.4,
            min_vram_gb=1.0,
            min_ram_gb=2.0,
            tasks=["черновик"],
            description="Ультра-лёгкая: для самых слабых машин и быстрых проб.",
        ),
        OllamaCatalogEntry(
            name="llama3.2:1b",
            label="Llama 3.2 1B",
            family="Llama 3.x",
            params_b=1.0,
            size_gb=1.3,
            min_vram_gb=2.0,
            min_ram_gb=4.0,
            tasks=["вычитка", "черновик"],
            description="Очень лёгкая, запустится почти везде без видеокарты.",
        ),
        OllamaCatalogEntry(
            name="qwen2.5:1.5b",
            label="Qwen2.5 1.5B",
            family="Qwen2.5",
            params_b=1.5,
            size_gb=1.0,
            min_vram_gb=2.0,
            min_ram_gb=4.0,
            tasks=["вычитка", "черновик"],
            description="Лёгкая, хороша для вычитки русского текста на CPU.",
        ),
        OllamaCatalogEntry(
            name="gemma2:2b",
            label="Gemma 2 2B",
            family="Gemma 2",
            params_b=2.0,
            size_gb=1.6,
            min_vram_gb=3.0,
            min_ram_gb=6.0,
            tasks=["вычитка", "черновик"],
            description="Компактная модель Google, аккуратные формулировки.",
        ),
        OllamaCatalogEntry(
            name="llama3.2:3b",
            label="Llama 3.2 3B",
            family="Llama 3.x",
            params_b=3.0,
            size_gb=2.0,
            min_vram_gb=4.0,
            min_ram_gb=8.0,
            tasks=["вычитка", "переписывание", "черновик"],
            description="Лёгкая и шустрая, неплохой баланс качества.",
        ),
        OllamaCatalogEntry(
            name="qwen2.5:3b",
            label="Qwen2.5 3B",
            family="Qwen2.5",
            params_b=3.0,
            size_gb=2.0,
            min_vram_gb=4.0,
            min_ram_gb=8.0,
            tasks=["вычитка", "переписывание", "черновик"],
            description="Лёгкая и шустрая, хороша для вычитки и коротких правок русского текста.",
        ),
        OllamaCatalogEntry(
            name="phi3.5",
            label="Phi-3.5 Mini",
            family="Phi",
            params_b=3.8,
            size_gb=2.2,
            min_vram_gb=4.0,
            min_ram_gb=8.0,
            tasks=["переписывание", "разбор требований"],
            description="Сильная «маленькая» модель Microsoft.",
        ),
        # ── Mid: consumer GPU (6–10 ГБ) ─────────────────────────────────────
        OllamaCatalogEntry(
            name="mistral:7b",
            label="Mistral 7B",
            family="Mistral",
            params_b=7.0,
            size_gb=4.1,
            min_vram_gb=6.0,
            min_ram_gb=16.0,
            tasks=["переписывание", "развёрнутые правки"],
            description="Классическая 7B, быстрая и универсальная.",
        ),
        OllamaCatalogEntry(
            name="qwen2.5:7b",
            label="Qwen2.5 7B",
            family="Qwen2.5",
            params_b=7.0,
            size_gb=4.7,
            min_vram_gb=6.0,
            min_ram_gb=16.0,
            tasks=["вычитка", "переписывание", "развёрнутые правки"],
            description="Сбалансированная: заметно качественнее на больших фрагментах ВКР.",
        ),
        OllamaCatalogEntry(
            name="llama3.1:8b",
            label="Llama 3.1 8B",
            family="Llama 3.x",
            params_b=8.0,
            size_gb=4.9,
            min_vram_gb=6.0,
            min_ram_gb=16.0,
            tasks=["переписывание", "развёрнутые правки"],
            description="Альтернатива 7B-классу с другим характером формулировок.",
        ),
        OllamaCatalogEntry(
            name="deepseek-r1:8b",
            label="DeepSeek-R1 8B",
            family="DeepSeek-R1",
            params_b=8.0,
            size_gb=5.2,
            min_vram_gb=6.0,
            min_ram_gb=16.0,
            tasks=["рассуждения", "разбор требований"],
            description="Дистилляция с пошаговыми рассуждениями — полезна для разбора и логики.",
        ),
        OllamaCatalogEntry(
            name="gemma2:9b",
            label="Gemma 2 9B",
            family="Gemma 2",
            params_b=9.0,
            size_gb=5.4,
            min_vram_gb=8.0,
            min_ram_gb=18.0,
            tasks=["переписывание", "развёрнутые правки"],
            description="Качественная модель Google среднего класса.",
        ),
        # ── Large: 12+ ГБ видеопамяти ───────────────────────────────────────
        OllamaCatalogEntry(
            name="qwen2.5:14b",
            label="Qwen2.5 14B",
            family="Qwen2.5",
            params_b=14.0,
            size_gb=9.0,
            min_vram_gb=12.0,
            min_ram_gb=32.0,
            tasks=["переписывание", "сложные правки", "разбор требований"],
            description="Сильная модель для мощных GPU (≈12+ ГБ видеопамяти).",
        ),
        OllamaCatalogEntry(
            name="deepseek-r1:14b",
            label="DeepSeek-R1 14B",
            family="DeepSeek-R1",
            params_b=14.0,
            size_gb=9.0,
            min_vram_gb=12.0,
            min_ram_gb=32.0,
            tasks=["рассуждения", "сложные правки"],
            description="Более сильные рассуждения для требовательных задач.",
        ),
        OllamaCatalogEntry(
            name="gemma2:27b",
            label="Gemma 2 27B",
            family="Gemma 2",
            params_b=27.0,
            size_gb=16.0,
            min_vram_gb=20.0,
            min_ram_gb=48.0,
            tasks=["сложные правки", "разбор требований"],
            description="Топовая Gemma — для очень мощных GPU.",
        ),
        OllamaCatalogEntry(
            name="qwen2.5:32b",
            label="Qwen2.5 32B",
            family="Qwen2.5",
            params_b=32.0,
            size_gb=20.0,
            min_vram_gb=24.0,
            min_ram_gb=64.0,
            tasks=["сложные правки", "разбор требований"],
            description="Максимальное качество Qwen2.5 — нужен топовый GPU.",
        ),
    ]


class OllamaConfig(BaseModel):
    """Managed local-model runtime (Ollama) settings.

    The runtime is reached either via a user-run native Ollama (preferred — best
    GPU acceleration on every OS) or, as a fallback, a backend-managed
    `ollama/ollama` Docker container (same `docker` CLI pattern as LanguageTool).
    Dispatch reaches it through the existing OpenAI-compatible client; these are
    deployment defaults.
    """

    image: str = Field(
        default="ollama/ollama:latest",
        description="Docker image used for the managed (fallback) Ollama container.",
    )
    container_name: str = Field(
        default="hse-ollama",
        description="Stable name of the managed Ollama container (adopt/reconcile across restarts).",
    )
    container_port: int = Field(
        default=11434,
        description="Port Ollama listens on inside the container.",
    )
    host_port: int = Field(
        default=11434,
        description="Preferred host port to publish (Ollama's default; a free port is used if it's taken).",
    )
    local_base_url: str = Field(
        default="http://127.0.0.1:11434",
        description="Endpoint probed for a native Ollama and used as the managed provider's base URL.",
    )
    health_path: str = Field(
        default="/api/tags",
        description="HTTP path polled to decide Ollama is up and serving.",
    )
    model_volume_name: str = Field(
        default="hse-ollama-models",
        description="Named Docker volume persisting pulled models across container restarts.",
    )
    request_timeout_s: float = Field(
        default=60.0,
        description="Timeout for status/list/delete calls (NOT model pulls, which stream without a read timeout).",
    )
    health_timeout_s: float = Field(
        default=5.0,
        description="Timeout for a single runtime health probe.",
    )
    startup_timeout_s: float = Field(
        default=120.0,
        description="How long to wait for the managed container to become healthy after start.",
    )
    idle_timeout_s: float = Field(
        default=1800.0,
        description="Stop the managed container after this many seconds idle (frees RAM/VRAM).",
    )
    stop_on_shutdown: bool = Field(
        default=True,
        description="Stop the managed container when the backend shuts down (auto-starts again on demand).",
    )
    keep_alive: str = Field(
        default="5m",
        description=(
            "How long Ollama keeps a model loaded in RAM/VRAM after the last request, set as "
            "OLLAMA_KEEP_ALIVE on the managed container. '5m' = default, '0' = unload immediately, "
            "'-1' = keep loaded. Frees memory automatically between uses."
        ),
    )
    provider_name: str = Field(
        default="Ollama",
        description="Display name of the auto-managed AI provider record that points at the local runtime.",
    )
    allow_custom_models: bool = Field(
        default=True,
        description="Allow pulling any validly-named model (free-text / registry search), not just the catalog.",
    )
    registry_search_url: str = Field(
        default="https://ollama.com/search",
        description="ollama.com search page scraped for live model discovery (best-effort, graceful on failure).",
    )
    registry_timeout_s: float = Field(
        default=10.0,
        description="Timeout for a single registry search request.",
    )
    max_concurrent_pulls: int = Field(
        default=2,
        description="Max simultaneous background model downloads (bounds disk/network use).",
    )
    catalog: list[OllamaCatalogEntry] = Field(
        default_factory=_default_ollama_catalog,
        description="Curated local models offered in the UI (the recommended starting set, not a hard allowlist).",
    )


class AgentConfig(BaseModel):
    """AI agent chat runtime settings.

    The agent loop drives existing AI providers (OpenAI / Anthropic / local
    Ollama) through a thin provider-agnostic loop. These are deployment defaults;
    the chosen provider/model come from the runtime settings
    (default_ai_provider_id / default_ai_model) and may be overridden per chat.
    """

    token_budget: int = Field(
        default=128000,
        description="Conservative context-token ceiling per turn; real per-model window may override it.",
    )
    max_iterations: int = Field(
        default=25,
        description="Hard cap on tool-call iterations in a single turn (stops runaway loops).",
    )
    max_output_tokens: int = Field(
        default=4096,
        description="Max tokens the model may generate per round-trip.",
    )
    temperature: float = Field(default=0.2, description="Sampling temperature for agent turns.")
    max_tool_result_tokens: int = Field(
        default=25000,
        description="Token cap applied to a single tool result before it re-enters context (then paginated).",
    )
    compaction_trigger_ratio: float = Field(
        default=0.75,
        description="Compact history once the estimated context reaches this fraction of token_budget.",
    )
    keep_recent_tokens: int = Field(
        default=24000,
        description="Always keep at least this much of the most recent transcript verbatim when compacting.",
    )
    keep_recent_messages_min: int = Field(
        default=6,
        description="Always keep at least this many recent messages verbatim when compacting.",
    )
    summary_max_tokens: int = Field(
        default=1500,
        description="Max tokens for a rolling compaction summary.",
    )
    auto_approve_writes: bool = Field(
        default=False,
        description="When True, write/exec tools run without an explicit per-call approval prompt.",
    )
    retention_runs: int = Field(
        default=200,
        description="Max run records kept per session before the oldest are pruned (0 = unbounded).",
    )
    retention_max_transcript_bytes: int = Field(
        default=0,
        description="When >0, archive already-compacted transcript lines once a session exceeds this size.",
    )
    debug_trace: bool = Field(
        default=False,
        description=(
            "When True, write a verbose per-run JSONL trace (exact request, every raw stream chunk, "
            "the parsed turn, tool dispatch) to `<debug_trace_dir>/<run>.jsonl`. Diagnostic only; "
            "off by default. Enable with HSE_STUDIO__AGENT__DEBUG_TRACE=true."
        ),
    )
    debug_trace_dir: Path | None = Field(
        default=None,
        description="Directory for debug-trace files. None → `<data_dir>/agent-traces`.",
    )
    debug_trace_keep: int = Field(
        default=50,
        description="Max trace files kept (oldest pruned). 0 = unbounded.",
    )


class HsePersonsConfig(BaseModel):
    """Lookup of HSE staff from the public directory (hse.ru/org/persons).

    Powers the «Сотрудник из Вышки» picker on supervisor/employee fields. All
    access is server-side and deliberately polite: it honours the site's declared
    ``Crawl-delay: 3`` via a global min-interval gate, caches aggressively, and
    degrades gracefully so a slow/blocked hse.ru never breaks the UI. Only
    robots-allowed URLs are used (``/org/persons/?<facets>`` + ``/org/persons/<id>``);
    the disallowed ``search_person`` box is never used — the name is filtered locally.
    """

    base_url: str = Field(default="https://www.hse.ru", description="HSE site origin.")
    list_path: str = Field(default="/org/persons/", description="Directory listing path (facets appended).")
    user_agent: str = Field(
        default=("Mozilla/5.0 (compatible; hse-doc-studio; +https://github.com/AlexeyShalaev/hse-doc-studio)"),
        description="Identifying, honest User-Agent for outbound directory requests.",
    )
    campus_udept: dict[str, str] = Field(
        default_factory=lambda: {"moscow": "", "spb": "135083", "nn": "135288", "perm": "135213"},
        description="Friendly campus key → top-level `udept` id (Moscow is the default, no param).",
    )
    request_timeout_s: float = Field(default=15.0, description="Timeout for a single directory request.")
    min_request_interval_s: float = Field(
        default=3.0,
        description="Global minimum gap between outbound requests (honours the site's Crawl-delay: 3).",
    )
    max_concurrency: int = Field(default=2, description="Bounded concurrent outbound requests (second guard).")
    retries: int = Field(default=2, description="Retries on timeout / 5xx / 429 (honours Retry-After).")
    list_cache_ttl_s: float = Field(default=900.0, description="TTL of a cached listing page (querystring-keyed).")
    detail_cache_ttl_s: float = Field(default=86400.0, description="TTL of a cached profile detail (id-keyed).")
    facets_cache_ttl_s: float = Field(default=86400.0, description="TTL of a cached facet vocabulary (campus-keyed).")
