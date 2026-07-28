"""API configuration."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from hse_doc_studio import __version__ as project_version
from hse_doc_studio.core.update.services import feed_disabled, official_feed_url

# parents: [0]=api/, [1]=hse_doc_studio/, [2]=service-root, [3]=services/, [4]=monorepo.
# В образе пакет лежит просто в /app — этих уровней там НЕТ, и безусловный
# parents[4] ронял контейнер IndexError'ом ещё на импорте конфига. Монорепы в
# образе нет: None означает «работаем от /app-дефолтов ниже».
_PARENTS = Path(__file__).resolve().parents
_MONOREPO_ROOT = _PARENTS[4] if len(_PARENTS) > 4 else None
_DEFAULT_PACKS_DIR = (
    _MONOREPO_ROOT / "packs"
    if _MONOREPO_ROOT is not None and (_MONOREPO_ROOT / "packs").is_dir()
    else Path("/app/packs")
)
# Курируемые заметки о релизах: в монорепе лежат в корне, в образе — рядом с паком
# (deploy/all-in-one/Dockerfile кладёт их отдельным COPY, как и packs).
_RELEASE_NOTES_NAME = "release-notes.json"
_DEFAULT_RELEASE_NOTES_FILE = (
    _MONOREPO_ROOT / _RELEASE_NOTES_NAME
    if _MONOREPO_ROOT is not None and (_MONOREPO_ROOT / _RELEASE_NOTES_NAME).is_file()
    else Path("/app") / _RELEASE_NOTES_NAME
)


class HttpServerConfig(BaseModel):
    """HTTP server configuration."""

    host: str = Field(default="0.0.0.0", description="Server bind address")  # noqa: S104
    port: int = Field(default=17240, description="Server port")
    workers: int = Field(default=1, description="Number of worker processes")
    timeout_keep_alive: int = Field(default=5, description="Keep-alive timeout in seconds")
    timeout_graceful_shutdown: int = Field(default=10, description="Graceful shutdown timeout in seconds")
    access_log: bool = Field(default=False, description="Enable uvicorn access log")
    proxy_headers: bool = Field(default=True, description="Trust proxy headers")
    forwarded_allow_ips: str = Field(default="*", description="Trusted proxy IPs")


class CorsConfig(BaseModel):
    """CORS configuration."""

    allow_origins: list[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:17240",
        ],
        description="Allowed origins",
    )
    allow_credentials: bool = Field(default=True)
    allow_methods: list[str] = Field(default=["*"])
    allow_headers: list[str] = Field(default=["*"])


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO", description="Log level")
    use_json: bool = Field(default=False, description="JSON format (False = console)")


class CompileConfig(BaseModel):
    """LaTeX compile pipeline settings."""

    image: str = Field(
        default="texlive/texlive:latest",
        description="Default active image when the user hasn't picked one in Settings → Образы.",
    )
    allowed_repos: list[str] = Field(
        default=["texlive/texlive"],
        description=(
            "Docker Hub repos the UI is allowed to list, pull and activate. "
            "Acts as a security allowlist — without it the API could pull arbitrary images."
        ),
    )
    docker_hub_base: str = Field(
        default="https://hub.docker.com/v2",
        description="Docker Hub v2 API base URL used to fetch tag lists.",
    )
    cache_volume_name: str = Field(
        default="hse-tex-cache",
        description="Named Docker volume that persists font/format caches across compiles.",
    )
    cache_volume_target: str = Field(
        default="/root",
        description="Mount target for the cache volume inside the TeX container.",
    )
    idle_timeout_s: float = Field(
        default=120.0,
        description="Kill the build if no output is produced for this many seconds.",
    )
    default_max_iterations: int = Field(
        default=5,
        description="Fallback for latexmk $max_repeat when the user setting is missing.",
    )
    # Скачивать ли образ TeX заранее, фоном после настройки. Иначе первый же
    # «Собрать» превращается в многоминутную загрузку без предупреждения. Мастер
    # выключает это переменной, если пользователь снял галочку.
    prefetch_image: bool = Field(
        default=True,
        description="Pull the TeX image in the background once the install is configured.",
    )
    # Path translation kicks in only when both fields are set, which is the
    # case when the backend itself runs in a container (compose deployment).
    # The docker daemon resolves `-v <src>:<dst>` against the HOST, so we
    # must rewrite our in-container project path back to the host path.
    projects_host_path: str | None = Field(
        default=None,
        description="Host-side root of the projects bind mount; required when backend runs in Docker.",
    )
    projects_container_path: str | None = Field(
        default=None,
        description="In-container mount point of projects; required when backend runs in Docker.",
    )


class FontCatalogFileConfig(BaseModel):
    """One downloadable file of a curated font (a single weight/style)."""

    filename: str = Field(description="Target filename in the fonts folder, e.g. 'PT_Serif-Web-Regular.ttf'.")
    url: str = Field(description="HTTPS source URL.")


class FontCatalogEntryConfig(BaseModel):
    """A curated free font the UI offers to download into the managed folder."""

    id: str = Field(description="Stable catalog id, e.g. 'pt-serif'.")
    label: str = Field(description="Human-friendly name.")
    family: str = Field(default="", description="Family grouping (serif / sans / mono).")
    description: str = Field(default="", description="Short RU description.")
    license: str = Field(default="", description="License (e.g. OFL-1.1).")
    files: list[FontCatalogFileConfig] = Field(default_factory=list)


def _pt_files(folder: str, stem: str) -> list[FontCatalogFileConfig]:
    base = f"https://raw.githubusercontent.com/google/fonts/main/ofl/{folder}/"
    return [
        FontCatalogFileConfig(filename=f"{stem}-Regular.ttf", url=f"{base}{stem}-Regular.ttf"),
        FontCatalogFileConfig(filename=f"{stem}-Bold.ttf", url=f"{base}{stem}-Bold.ttf"),
        FontCatalogFileConfig(filename=f"{stem}-Italic.ttf", url=f"{base}{stem}-Italic.ttf"),
        FontCatalogFileConfig(filename=f"{stem}-BoldItalic.ttf", url=f"{base}{stem}-BoldItalic.ttf"),
    ]


def _gf_files(folder: str, stem: str, weights: tuple[str, ...]) -> list[FontCatalogFileConfig]:
    """Static-instance TTFs from the google/fonts repo (`<folder>/<stem>-<weight>.ttf`)."""
    base = f"https://raw.githubusercontent.com/google/fonts/main/{folder}/"
    return [FontCatalogFileConfig(filename=f"{stem}-{w}.ttf", url=f"{base}{stem}-{w}.ttf") for w in weights]


# Standard 4 upright/italic × regular/bold weights present as STATIC TTFs.
_RBIB: tuple[str, ...] = ("Regular", "Bold", "Italic", "BoldItalic")


def _default_font_catalog() -> list[FontCatalogEntryConfig]:
    # Free, Cyrillic-capable fonts available as STATIC TTFs in github.com/google/fonts
    # (all URLs verified). Grouped serif → sans → mono. This is the recommended free
    # set — for pixel-exact ГОСТ output (Times New Roman / Consolas) the user uploads
    # their own licensed TTFs or imports them from the system instead. (Variable-only
    # families like Noto Serif / IBM Plex Sans are intentionally excluded — XeLaTeX
    # needs separate weight files.)
    return [
        # ── Serif ──
        FontCatalogEntryConfig(
            id="pt-serif",
            label="PT Serif",
            family="serif",
            license="OFL-1.1",
            description="Засечный шрифт с полной кириллицей (ParaType). Хорошая свободная замена Times.",
            files=_pt_files("ptserif", "PT_Serif-Web"),
        ),
        FontCatalogEntryConfig(
            id="old-standard-tt",
            label="Old Standard TT",
            family="serif",
            license="OFL-1.1",
            description="Классический «старинный» засечный шрифт с кириллицей — академический вид, близкий к Times.",
            files=_gf_files("ofl/oldstandardtt", "OldStandard", ("Regular", "Bold", "Italic")),
        ),
        FontCatalogEntryConfig(
            id="ibm-plex-serif",
            label="IBM Plex Serif",
            family="serif",
            license="OFL-1.1",
            description="Современный засечный шрифт IBM с полной кириллицей. Хорошо читается в теле работы.",
            files=_gf_files("ofl/ibmplexserif", "IBMPlexSerif", _RBIB),
        ),
        # ── Sans ──
        FontCatalogEntryConfig(
            id="pt-sans",
            label="PT Sans",
            family="sans",
            license="OFL-1.1",
            description="Рубленый шрифт с кириллицей (ParaType). Свободная замена Arial.",
            files=_pt_files("ptsans", "PT_Sans-Web"),
        ),
        FontCatalogEntryConfig(
            id="fira-sans",
            label="Fira Sans",
            family="sans",
            license="OFL-1.1",
            description="Гуманистический рубленый шрифт с кириллицей (Mozilla).",
            files=_gf_files("ofl/firasans", "FiraSans", _RBIB),
        ),
        # ── Mono ──
        FontCatalogEntryConfig(
            id="pt-mono",
            label="PT Mono",
            family="mono",
            license="OFL-1.1",
            description="Моноширинный шрифт с кириллицей (ParaType). Свободная замена Courier New.",
            files=[
                FontCatalogFileConfig(
                    filename="PTMono-Regular.ttf",
                    url="https://raw.githubusercontent.com/google/fonts/main/ofl/ptmono/PTM55FT.ttf",
                ),
            ],
        ),
        FontCatalogEntryConfig(
            id="ibm-plex-mono",
            label="IBM Plex Mono",
            family="mono",
            license="OFL-1.1",
            description="Моноширинный IBM Plex с кириллицей — для листингов кода.",
            files=_gf_files("ofl/ibmplexmono", "IBMPlexMono", _RBIB),
        ),
    ]


class FontsConfig(BaseModel):
    """Managed local fonts: a `<data_dir>/fonts` folder bind-mounted into the
    TeX compile container so XeLaTeX resolves `\\setmainfont{...}` by name."""

    dir_name: str = Field(default="fonts", description="Subdirectory of data_dir holding the fonts.")
    # Откуда брать «системные» шрифты для вкладки Настройки → Шрифты → Системные.
    # Нативно список стандартных каталогов ОС знает сам провайдер. В контейнере эти
    # каталоги принадлежат ОБРАЗУ, а не пользователю: показывать их — врать. Поэтому
    # шрифты хоста монтируются внутрь (compose.system-fonts.yml), и путь монтирования
    # указывается здесь; непустое значение ЗАМЕНЯЕТ каталоги ОС.
    system_dirs: list[str] = Field(
        default_factory=list,
        description="Explicit font roots to scan instead of the OS ones (host fonts bind-mounted into the container).",
    )
    # Каталог шрифтов на машине пользователя, если автоопределение промахнулось.
    # Отличается от `system_dirs` тем, что путь ХОСТОВЫЙ: его монтирует
    # одноразовый контейнер (см. DockerHostFontProvider), а не compose-оверлей.
    host_dir: str | None = Field(
        default=None,
        description="Explicit HOST font directory; empty means auto-detection over the known OS locations.",
    )
    container_mount: str = Field(
        default="/usr/local/share/fonts/hse",
        description="Where the fonts folder is mounted inside the TeX container (a fontconfig-scanned path).",
    )
    allowed_extensions: list[str] = Field(default_factory=lambda: [".ttf", ".otf", ".ttc"])
    download_timeout_s: float = Field(default=60.0, description="Per-file download timeout for catalog installs.")
    catalog: list[FontCatalogEntryConfig] = Field(default_factory=_default_font_catalog)
    # ── Online marketplace (Google Fonts) ──
    marketplace_metadata_url: str = Field(
        default="https://fonts.google.com/metadata/fonts",
        description="GF metadata (family/category/subsets) for the marketplace inventory.",
    )
    marketplace_tree_url: str = Field(
        default="https://api.github.com/repos/google/fonts/git/trees/main?recursive=1",
        description="github.com/google/fonts file tree — source of static TTF download URLs.",
    )
    marketplace_index_ttl_s: float = Field(
        default=86400.0,
        description="How long the in-memory marketplace index is reused before a refresh (seconds).",
    )
    marketplace_fetch_timeout_s: float = Field(
        default=60.0,
        description="Timeout for the marketplace index fetches (tree + metadata).",
    )


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


class VCSConfig(BaseModel):
    """ProjectVCS (system-git) settings.

    The store is per-project and isolated at ``<project>/.hse-studio/git/`` — it
    is never placed in the project root and never touches the user's own git.
    These are deployment defaults; per-project toggles (tracking, PDF, auto-commit
    on compile) live in project.meta["vcs"].
    """

    enabled: bool = Field(default=True, description="Master switch for ProjectVCS auto-tracking.")
    default_branch: str = Field(default="master", description="Initial branch name for a new project store.")
    author_name: str = Field(default="HSE Studio", description="Committer name for service commits.")
    author_email: str = Field(default="bot@hse-studio.local", description="Committer email for service commits.")
    diff_max_bytes: int = Field(default=256_000, description="Byte budget for an assembled diff before truncation.")
    track_pdf: bool = Field(
        default=False,
        description="Global default for whether compiled PDFs enter history (per-project setting overrides).",
    )
    edit_min_interval_seconds: float = Field(
        default=5.0,
        description="Throttle window for edit-commits (phase 2); edits within it are folded into the next commit.",
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


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        # HSE_STUDIO__, а не HSE_DOC_STUDIO__ — намеренно, это НЕ рассинхрон с именем
        # продукта. Префикс переменных, папка `.hse-studio/` внутри каждого проекта на
        # диске и ключи localStorage — часть контракта с уже существующими установками:
        # переименование потребовало бы миграции всех проектов пользователей и сброса
        # настроек UI. Оставлено как краткая форма (ср. PG_ для PostgreSQL).
        env_prefix="HSE_STUDIO__",
        extra="ignore",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    server: HttpServerConfig = Field(default_factory=HttpServerConfig)
    cors: CorsConfig = Field(default_factory=CorsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    compile: CompileConfig = Field(default_factory=CompileConfig)
    fonts: FontsConfig = Field(default_factory=FontsConfig)
    languagetool: LanguageToolConfig = Field(default_factory=LanguageToolConfig)
    office_convert: OfficeConvertConfig = Field(default_factory=OfficeConvertConfig)
    office_editor: OfficeEditorConfig = Field(default_factory=OfficeEditorConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    vcs: VCSConfig = Field(default_factory=VCSConfig)
    hse_persons: HsePersonsConfig = Field(default_factory=HsePersonsConfig)

    data_dir: Path = Field(
        default=Path.home() / ".config" / "hse-studio",
        description="Local data storage directory",
    )
    # Host-side path of data_dir, needed only when the backend runs in a container
    # and must bind-mount a data_dir subfolder (e.g. fonts) into a sibling docker
    # container — the daemon resolves `-v` against the HOST. None when running
    # natively (data_dir is already a host path). Compose sets HSE_STUDIO__HOST_DATA_DIR.
    host_data_dir: str | None = Field(
        default=None,
        description="Host path of data_dir for sibling-container mounts; None when backend runs natively.",
    )
    packs_dir: Path = Field(
        default=_DEFAULT_PACKS_DIR,
        description="Directory with template packs (auto-detected from monorepo root locally; /app/packs in docker)",
    )
    # NOTE: the LanguageTool enabled flag and server URL are *runtime* settings
    # persisted in config.json (see use_cases.settings.get_settings._DEFAULTS),
    # read live by the external check engine — they are deliberately NOT here as
    # env-based settings, to avoid the split-brain where the engine and the UI
    # read different sources. Container/image defaults live in `languagetool`.
    static_dir: Path | None = Field(
        default=None,
        description="Serve built frontend from this directory (all-in-one mode)",
    )
    # Аварийный переключатель для установок, где докер стоит нестандартно
    # (Colima, Rancher, урезанный PATH у службы). По умолчанию бэкенд ищет CLI
    # сам: PATH, затем известные места — см. infra/docker/cli.py.
    docker_binary: str | None = Field(
        default=None,
        description="Explicit path to the docker CLI; empty means auto-discovery (PATH, then known locations).",
    )

    # ── distribution / "About" metadata (surfaced via GET /system/info) ──
    # Kept configurable (env-overridable) rather than hardcoded in the UI so a
    # fork can repoint releases/images without touching code.
    github_repo: str = Field(
        default="AlexeyShalaev/hse-doc-studio",
        description="owner/repo on GitHub — source of release/changelog info and the canonical source link.",
    )
    image_base: str = Field(
        default="ghcr.io/alexeyshalaev/hse-doc-studio",
        description="GHCR image base for the published images (owner must be lowercase for GHCR).",
    )
    source_url: str = Field(
        default="https://github.com/AlexeyShalaev/hse-doc-studio",
        description="Canonical project source URL shown in About.",
    )
    license_name: str = Field(
        default="Apache-2.0",
        description="License shown in About.",
    )

    # ── update checks (see infra/update/feed.py) ──
    update_feed_url: str = Field(
        default="",
        description=(
            "Release feed for update checks. Empty → the official GitHub Releases of `github_repo`; "
            "`off` (or none/disabled/-/0/false) disables the check for offline installs."
        ),
    )
    update_check_timeout_s: float = Field(
        default=8.0,
        description="Timeout for one release-feed request — a slow feed must not hang the About screen.",
    )
    auto_update_interval_s: float = Field(
        default=6 * 60 * 60,
        description="How often the background auto-update checks the feed (the toggle itself is a user setting).",
    )
    auto_update_startup_delay_s: float = Field(
        default=5 * 60,
        description="Delay before the first auto-update check — never replace a container the user just started.",
    )
    built: str = Field(
        default="",
        description=(
            "Build timestamp (ISO-8601) baked into the image by CI via the HSE_STUDIO_BUILT build-arg. "
            "Empty in a source checkout — a dev run has no build date to show."
        ),
    )
    release_notes_file: Path = Field(
        default=_DEFAULT_RELEASE_NOTES_FILE,
        description="Curated bilingual release notes (release-notes.json), read once at startup.",
    )

    @staticmethod
    def get_app_version() -> str:
        # Версия приезжает исходником, а не переменной окружения: release-please
        # бампит __init__.py/pyproject/package.json в релизном PR, и образ собирается
        # уже с тега. Один источник — нечему рассинхронизироваться с тегом и changelog.
        return project_version

    def resolved_update_feed_url(self) -> str:
        """Фид релизов: явная настройка либо официальные релизы `github_repo`.

        Пустая настройка НЕ означает «выключено»: это «взять адрес по умолчанию»,
        поэтому проверка работает без конфигурации. Выключает явное `off`.
        """
        explicit = self.update_feed_url.strip()
        if not explicit:
            return official_feed_url(self.github_repo)
        return explicit

    def update_feed_enabled(self) -> bool:
        return not feed_disabled(self.resolved_update_feed_url())

    def get_uvicorn_kwargs(self) -> dict[str, Any]:
        """Build kwargs for uvicorn.run()."""
        return {
            "host": self.server.host,
            "port": self.server.port,
            "workers": self.server.workers,
            "timeout_keep_alive": self.server.timeout_keep_alive,
            "timeout_graceful_shutdown": self.server.timeout_graceful_shutdown,
            "access_log": self.server.access_log,
            "proxy_headers": self.server.proxy_headers,
            "forwarded_allow_ips": self.server.forwarded_allow_ips,
            "log_config": None,
            # httptools has a broken Windows wheel for Python 3.12; h11 is the safe fallback
            "http": "h11",
        }


settings = Settings()
