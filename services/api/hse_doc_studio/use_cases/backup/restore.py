"""Восстановление из бэкапа: проверка манифеста и частей, безопасные проверки цели, запись по стадиям.

Вызывается из CLI при остановленных api и раннерах; из работающего приложения восстановление не запускается
(см. docs/design/backups.md, раздел 5).
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from hse_doc_studio.core.backup.crypto import BackupCryptoError, DecryptingReader
from hse_doc_studio.core.backup.destinations import object_key
from hse_doc_studio.core.backup.entities import (
    MANIFEST_NAME,
    PART_DB,
    PART_FILES,
    PART_OBJECTS,
    Manifest,
    ManifestPart,
)
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.backup.keys import open_key
from hse_doc_studio.core.backup.manifest import manifest_sha256, parse_manifest
from hse_doc_studio.core.backup.protocols import IPartFetcher, IRestoreTarget, TargetState
from hse_doc_studio.core.storage.errors import ObjectNotFoundError
from hse_doc_studio.core.storage.ports import IObjectStore

Report = Callable[[str], None]
Confirm = Callable[[TargetState], bool]


@dataclass(frozen=True)
class BackupSource:
    """Папка одного бэкапа: хранилище и ключ папки в нём (пустой для каталога, указанного как корень)."""

    store: IObjectStore
    base: str = ""


@dataclass(frozen=True)
class VerifiedBackup:
    manifest: Manifest
    manifest_sha256: str
    key: bytes


@dataclass(frozen=True)
class RestoreResult:
    applied: bool
    database: bool = False
    files: int = 0
    objects: int = 0
    state: TargetState | None = None


class _HashingReader:
    def __init__(self, source: DecryptingReader) -> None:
        self._source = source
        self.digest = hashlib.sha256()
        self.size = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._source.read(size)
        self.digest.update(chunk)
        self.size += len(chunk)
        return chunk


def _drain(reader: _HashingReader) -> None:
    while reader.read(1024 * 1024):
        pass


def _check_plain(part: ManifestPart, reader: _HashingReader) -> None:
    if reader.size != part.plain_size or reader.digest.hexdigest() != part.plain_sha256:
        raise BackupError(BackupErrorCode.integrity, f"{part.name}: plaintext does not match the manifest")


class RestoreBackupUC:
    def __init__(self, target: IRestoreTarget, fetcher: IPartFetcher) -> None:
        self._target = target
        self._fetcher = fetcher

    async def load(
        self, source: BackupSource, *, installation_keys: list[bytes], passphrase: str | None
    ) -> VerifiedBackup:
        try:
            data = await source.store.get(object_key(source.base, MANIFEST_NAME))
        except ObjectNotFoundError as exc:
            raise BackupError(
                BackupErrorCode.not_found, "manifest.json not found: this is not a finished backup"
            ) from exc
        manifest = parse_manifest(data)
        key = open_key(manifest, installation_keys=installation_keys, passphrase=passphrase)
        return VerifiedBackup(manifest, manifest_sha256(data), key)

    async def verify(self, source: BackupSource, backup: VerifiedBackup, report: Report) -> None:
        """Скачивает и расшифровывает каждую часть без записи куда-либо; любое расхождение это `BackupError`."""
        for part in backup.manifest.parts:
            report(f"проверка {part.name} ({part.size} байт)")
            with await self._fetcher.fetch(source.store, object_key(source.base, part.name), part) as raw:
                await _verify_plain(part, raw, backup.key)
            report(f"  {part.name}: sha256 и расшифровка совпали")

    async def execute(
        self,
        source: BackupSource,
        backup: VerifiedBackup,
        *,
        apply: bool,
        overwrite: bool,
        confirm: Confirm,
        report: Report,
    ) -> RestoreResult:
        manifest = backup.manifest
        report(f"бэкап {manifest.backup_id}: версия {manifest.app_version}, схема {manifest.schema_revision or '-'}")
        if not await self._target.current_revision_known(manifest.schema_revision):
            raise BackupError(
                BackupErrorCode.unsupported,
                f"the backup schema {manifest.schema_revision} is newer than this image: "
                "run the same or a newer release",
            )
        await self.verify(source, backup, report)
        state = await self._target.describe()
        report(f"цель: пользователей {state.users}, проектов {state.projects}, объектов {state.objects}")
        if not apply:
            report("проверка пройдена; для восстановления добавьте --apply")
            return RestoreResult(applied=False, state=state)
        if await self._target.api_is_running():
            raise BackupError(
                BackupErrorCode.unsafe_target,
                "the database is in use by a running api: stop api and runners first (docker compose stop api runner)",
            )
        if not state.empty:
            if not overwrite:
                raise BackupError(
                    BackupErrorCode.unsafe_target,
                    "the target installation is not empty; the restore would destroy its data: "
                    "add --overwrite if that is intended",
                )
            if not confirm(state):
                raise BackupError(BackupErrorCode.unsafe_target, "overwrite was not confirmed")
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        done = await self._apply(source, backup, move_existing=not state.empty, stamp=stamp, report=report)
        return RestoreResult(applied=True, database=done[0], files=done[1], objects=done[2], state=state)

    async def _apply(
        self, source: BackupSource, backup: VerifiedBackup, *, move_existing: bool, stamp: str, report: Report
    ) -> tuple[bool, int, int]:
        manifest = backup.manifest
        database, files, objects = False, 0, 0
        for name in (PART_DB, PART_FILES, PART_OBJECTS):
            part = manifest.part(name)
            if part is None:
                report(f"часть {name} в бэкапе отсутствует, пропускаю")
                continue
            report(f"восстановление {name}")
            with await self._fetcher.fetch(source.store, object_key(source.base, name), part) as raw:
                reader = _HashingReader(_open_reader(raw, backup.key))
                try:
                    if name == PART_DB:
                        await self._target.restore_database(reader)  # type: ignore[arg-type]
                        database = True
                    elif name == PART_FILES:
                        files = await self._target.restore_files(reader, move_existing=move_existing, stamp=stamp)  # type: ignore[arg-type]
                    else:
                        objects = await self._target.restore_objects(reader)  # type: ignore[arg-type]
                    await asyncio.to_thread(_drain, reader)
                except BackupCryptoError as exc:
                    raise BackupError(BackupErrorCode.integrity, f"{name}: {exc}") from exc
                _check_plain(part, reader)
            report(f"  {name}: готово")
        return database, files, objects


def _open_reader(raw: object, key: bytes) -> DecryptingReader:
    try:
        return DecryptingReader(raw, key)  # type: ignore[arg-type]
    except BackupCryptoError as exc:
        raise BackupError(BackupErrorCode.integrity, str(exc)) from exc


async def _verify_plain(part: ManifestPart, raw: object, key: bytes) -> None:
    def run() -> None:
        reader = _HashingReader(_open_reader(raw, key))
        try:
            _drain(reader)
        except BackupCryptoError as exc:
            raise BackupError(BackupErrorCode.integrity, f"{part.name}: {exc}") from exc
        _check_plain(part, reader)

    await asyncio.to_thread(run)
