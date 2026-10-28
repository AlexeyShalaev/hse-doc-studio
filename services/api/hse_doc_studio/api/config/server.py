"""Сборка настроек серверного режима из корневых Settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from hse_doc_studio.api.config.storage import StorageConfig

if TYPE_CHECKING:
    from hse_doc_studio.api.config.settings import Settings


@dataclass(frozen=True)
class ServerCapabilities:
    """Возможности клиента общего сервера. Флаг admin считается на запрос и сюда не входит."""

    fs_browse: bool = False
    connect_folder: bool = False
    open_in_editor: bool = False
    move_project: bool = False
    docker_ui: bool = False
    self_update: bool = False
    local_services_ui: bool = False
    personal_signing_keys: bool = True


@dataclass(frozen=True)
class ServerConfig:
    projects_root: Path
    s3: StorageConfig
    caps: ServerCapabilities = field(default_factory=ServerCapabilities)
    project_retention_days: int = 30
    project_purge_interval_s: float = 3600.0

    @classmethod
    def from_settings(cls, cfg: Settings) -> ServerConfig:
        root = cfg.server.projects_root or cfg.data_dir.expanduser() / "projects"
        return cls(
            projects_root=root.expanduser(),
            s3=cfg.s3,
            project_retention_days=cfg.server.project_retention_days,
            project_purge_interval_s=cfg.server.project_purge_interval_s,
        )
