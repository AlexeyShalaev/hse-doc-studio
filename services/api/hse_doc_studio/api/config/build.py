"""Настройки сборки документов и каталога шрифтов."""

from pydantic import BaseModel, Field


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
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [".ttf", ".otf", ".ttc"],
        description="Расширения файлов, которые принимаются как шрифты.",
    )
    download_timeout_s: float = Field(default=60.0, description="Per-file download timeout for catalog installs.")
    catalog: list[FontCatalogEntryConfig] = Field(
        default_factory=_default_font_catalog, description="Каталог рекомендуемых бесплатных шрифтов с кириллицей."
    )
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
