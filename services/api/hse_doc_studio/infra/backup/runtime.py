"""Окружение бэкапа: ключи установки, версия, ревизия схемы, id установки, состав частей."""

from __future__ import annotations

import base64
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from hse_doc_studio import __version__
from hse_doc_studio.api.config import Settings
from hse_doc_studio.core.backup.protocols import BackupPlan, IBackupDestinationRepository
from hse_doc_studio.core.backup.settings import KEY_PASSPHRASE
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.core.storage.ports import IObjectStore
from hse_doc_studio.infra.backup.pgtools import resolve_binary, server_major
from hse_doc_studio.infra.backup.producers import (
    ARC_DATA,
    ARC_PROJECTS,
    DbDumpProducer,
    FilesProducer,
    FilesRoot,
    ObjectsProducer,
    SettingsProducer,
    excluded_names,
)
from hse_doc_studio.infra.db.engine import async_dsn
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.secrets.key_ring import KeyRing
from hse_doc_studio.infra.secrets.key_store import KeyFileStore

INSTALLATION_ID_KEY = "installation_id"


def raw_keys(ring: KeyRing | None) -> list[bytes]:
    """Сырые 32 байта ключей связки: первичный первым."""
    if ring is None:
        return []
    ordered = [ring.primary, *(key for kid, key in ring.keys.items() if kid != ring.primary_id)]
    return [base64.urlsafe_b64decode(key) for key in ordered]


class BackupKeySource:
    def __init__(self, key_store: KeyFileStore, settings: IInstanceSettingsRepository, cipher: ISecretCipher) -> None:
        self._store = key_store
        self._settings = settings
        self._cipher = cipher

    async def installation_keys(self) -> list[bytes]:
        return raw_keys(self._store.load())

    async def passphrase(self) -> str | None:
        token = await self._settings.get_secret(KEY_PASSPHRASE)
        if token is None:
            return None
        try:
            return self._cipher.decrypt(
                token, aad=column_aad("instance_settings", "secret_enc", KEY_PASSPHRASE)
            ).reveal()
        except GitSyncError:
            return None


class BackupEnvironment:
    app_version = __version__

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def schema_revision(self) -> str | None:
        async with self._sessions.use() as session:
            return (await session.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))).scalar_one_or_none()

    async def installation_id(self) -> str | None:
        async with self._sessions.use() as session:
            await session.execute(
                text("INSERT INTO instance_meta (key, value) VALUES (:k, :v) ON CONFLICT (key) DO NOTHING"),
                {"k": INSTALLATION_ID_KEY, "v": str(uuid4())},
            )
            return (
                await session.execute(
                    text("SELECT value FROM instance_meta WHERE key = :k"), {"k": INSTALLATION_ID_KEY}
                )
            ).scalar_one_or_none()


class BackupPlanFactory:
    def __init__(
        self,
        cfg: Settings,
        object_store: IObjectStore,
        settings: IInstanceSettingsRepository,
        destinations: IBackupDestinationRepository,
        local_root: Path,
        tmp_dir: Path,
        engine: AsyncEngine,
    ) -> None:
        self._cfg = cfg
        self._store = object_store
        self._settings = settings
        self._destinations = destinations
        self._local_root = local_root
        self._tmp_dir = tmp_dir
        self._engine = engine

    async def create(self) -> BackupPlan:
        cfg = self._cfg
        data_dir = cfg.data_dir.expanduser()
        fs_objects = None if cfg.s3.bucket else (cfg.s3.fs_root or data_dir / "objects").expanduser()
        extra = [self._local_root, self._tmp_dir, *([fs_objects] if fs_objects else [])]
        roots = [FilesRoot(ARC_DATA, data_dir, excluded_names(data_dir, extra))]
        projects_root = (cfg.server.projects_root or data_dir / "projects").expanduser()
        if not projects_root.resolve().is_relative_to(data_dir.resolve()):
            roots.append(FilesRoot(ARC_PROJECTS, projects_root))
        timeout = cfg.backups.dump_timeout_s
        major = await server_major(self._engine)
        return BackupPlan(
            producers=[
                DbDumpProducer(async_dsn(cfg.db.dsn), resolve_binary(cfg.backups.pg_dump_binary, major), timeout),
                FilesProducer(roots),
                ObjectsProducer(self._store),
                SettingsProducer(self._settings, self._destinations),
            ]
        )
