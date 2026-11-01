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
    compile_records_per_document: int = 50
    compile_log_limit_bytes: int = 1024 * 1024
    blob_gc_interval_s: float = 3600.0
    blob_gc_min_age_days: float = 14.0
    manifest_max_file_bytes: int = 256 * 1024 * 1024
    manifest_max_job_bytes: int = 1024 * 1024 * 1024
    project_quota_bytes: int = 2 * 1024**3
    project_quota_warn_percent: int = 80
    project_import_max_bytes: int = 500 * 1024**2
    project_import_max_files: int = 50_000
    project_usage_interval_s: float = 3600.0
    project_usage_batch: int = 20
    orphan_gc_interval_s: float = 21600.0
    orphan_gc_min_age_hours: float = 24.0

    @classmethod
    def from_settings(cls, cfg: Settings) -> ServerConfig:
        root = cfg.server.projects_root or cfg.data_dir.expanduser() / "projects"
        return cls(
            projects_root=root.expanduser(),
            s3=cfg.s3,
            project_retention_days=cfg.server.project_retention_days,
            project_purge_interval_s=cfg.server.project_purge_interval_s,
            compile_records_per_document=cfg.server.compile_records_per_document,
            compile_log_limit_bytes=cfg.server.compile_log_limit_bytes,
            blob_gc_interval_s=cfg.server.blob_gc_interval_s,
            blob_gc_min_age_days=cfg.server.blob_gc_min_age_days,
            manifest_max_file_bytes=cfg.server.manifest_max_file_bytes,
            manifest_max_job_bytes=cfg.server.manifest_max_job_bytes,
            project_quota_bytes=cfg.server.project_quota_bytes,
            project_quota_warn_percent=cfg.server.project_quota_warn_percent,
            project_import_max_bytes=cfg.server.project_import_max_bytes,
            project_import_max_files=cfg.server.project_import_max_files,
            project_usage_interval_s=cfg.server.project_usage_interval_s,
            project_usage_batch=cfg.server.project_usage_batch,
            orphan_gc_interval_s=cfg.server.orphan_gc_interval_s,
            orphan_gc_min_age_hours=cfg.server.orphan_gc_min_age_hours,
        )
