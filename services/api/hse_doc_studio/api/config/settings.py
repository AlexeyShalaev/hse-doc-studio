"""Корневые настройки приложения (Settings)."""

from pathlib import Path
from typing import Any, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from hse_doc_studio import __version__ as project_version
from hse_doc_studio.api.config.admin import AdminConfig
from hse_doc_studio.api.config.auth import AuthConfig, SecretsConfig
from hse_doc_studio.api.config.build import CompileConfig, FontsConfig
from hse_doc_studio.api.config.db import DbConfig
from hse_doc_studio.api.config.egress import EgressConfig
from hse_doc_studio.api.config.git import GitConfig, VCSConfig
from hse_doc_studio.api.config.git_remote import GitRemoteConfig
from hse_doc_studio.api.config.jobs import JobsConfig
from hse_doc_studio.api.config.mail import MailConfig
from hse_doc_studio.api.config.observability import ObservabilityConfig
from hse_doc_studio.api.config.rate_limit import RateLimitConfig
from hse_doc_studio.api.config.runtime import CorsConfig, HttpServerConfig, LoggingConfig
from hse_doc_studio.api.config.services import (
    AgentConfig,
    HsePersonsConfig,
    LanguageToolConfig,
    OfficeConvertConfig,
    OfficeEditorConfig,
    OllamaConfig,
)
from hse_doc_studio.api.config.sharing import SharingConfig
from hse_doc_studio.api.config.storage import StorageConfig
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.update.services import feed_disabled, official_feed_url

# parents: [0]=config/, [1]=api/, [2]=hse_doc_studio/, [3]=service-root, [4]=services/, [5]=monorepo.
# В образе пакет лежит просто в /app — этих уровней там НЕТ, и безусловный
# parents[4] ронял контейнер IndexError'ом ещё на импорте конфига. Монорепы в
# образе нет: None означает «работаем от /app-дефолтов ниже».
_PARENTS = Path(__file__).resolve().parents
_MONOREPO_ROOT = _PARENTS[5] if len(_PARENTS) > 5 else None
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
    git: GitConfig = Field(default_factory=GitConfig)
    git_remote: GitRemoteConfig = Field(default_factory=GitRemoteConfig)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)
    jobs: JobsConfig = Field(default_factory=JobsConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    mail: MailConfig = Field(default_factory=MailConfig)
    db: DbConfig = Field(default_factory=DbConfig)
    s3: StorageConfig = Field(default_factory=StorageConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)
    egress: EgressConfig = Field(default_factory=EgressConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    hse_persons: HsePersonsConfig = Field(default_factory=HsePersonsConfig)
    sharing: SharingConfig = Field(default_factory=SharingConfig)

    # Режим инстанса (HSE_STUDIO__MODE). Не путать с DeploymentMode (all-in-one/standard/native):
    # тот описывает, где запущен бэкенд, этот — одна локальная установка или общий сервер.
    mode: StudioMode = Field(
        default=StudioMode.local,
        description="Instance mode: 'local' (single-user install) or 'server' (shared; not supported yet).",
    )
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

    @model_validator(mode="after")
    def _server_cors_has_no_wildcard_with_credentials(self) -> Self:
        # Браузер не принимает `*` вместе с cookie, а Starlette в таком случае отражает любой Origin:
        # любой сайт получил бы запросы от имени вошедшего пользователя.
        if self.mode is StudioMode.server and self.cors.allow_credentials and "*" in self.cors.allow_origins:
            msg = "cors.allow_origins must list explicit origins, not '*', while cors.allow_credentials is on"
            raise ValueError(msg)
        return self

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
