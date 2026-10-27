"""Настройки API.

Пакет разбит по зонам (auth, db, storage, jobs, admin, services, ...), чтобы срезы
сервера не конфликтовали в одном файле. Публичный импорт прежний:
``from hse_doc_studio.api.config import settings``.
"""

from hse_doc_studio.api.config.admin import AdminConfig
from hse_doc_studio.api.config.auth import AuthConfig, SecretsConfig
from hse_doc_studio.api.config.build import (
    CompileConfig,
    FontCatalogEntryConfig,
    FontCatalogFileConfig,
    FontsConfig,
)
from hse_doc_studio.api.config.db import DbConfig
from hse_doc_studio.api.config.git import GitConfig, VCSConfig
from hse_doc_studio.api.config.jobs import JobsConfig
from hse_doc_studio.api.config.observability import ObservabilityConfig
from hse_doc_studio.api.config.runtime import CorsConfig, HttpServerConfig, LoggingConfig
from hse_doc_studio.api.config.server import ServerCapabilities, ServerConfig
from hse_doc_studio.api.config.services import (
    AgentConfig,
    HsePersonsConfig,
    LanguageToolConfig,
    OfficeConvertConfig,
    OfficeEditorConfig,
    OllamaCatalogEntry,
    OllamaConfig,
)
from hse_doc_studio.api.config.settings import Settings, settings
from hse_doc_studio.api.config.storage import StorageConfig

__all__ = [
    "AdminConfig",
    "AgentConfig",
    "AuthConfig",
    "CompileConfig",
    "CorsConfig",
    "DbConfig",
    "FontCatalogEntryConfig",
    "FontCatalogFileConfig",
    "FontsConfig",
    "GitConfig",
    "HsePersonsConfig",
    "HttpServerConfig",
    "JobsConfig",
    "LanguageToolConfig",
    "LoggingConfig",
    "ObservabilityConfig",
    "OfficeConvertConfig",
    "OfficeEditorConfig",
    "OllamaCatalogEntry",
    "OllamaConfig",
    "SecretsConfig",
    "ServerCapabilities",
    "ServerConfig",
    "Settings",
    "StorageConfig",
    "VCSConfig",
    "settings",
]
