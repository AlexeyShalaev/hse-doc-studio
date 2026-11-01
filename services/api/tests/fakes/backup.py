"""InMemory-реализации портов бэкапов для unit-тестов: репозитории, хранилища на каталоге, части из байтов."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from hse_doc_studio.core.backup.crypto import EncryptingWriter
from hse_doc_studio.core.backup.entities import (
    BackupDestination,
    BackupRun,
    DestinationKind,
    DestinationSecrets,
    DestinationSpec,
    RunStatus,
    StoredDestination,
)
from hse_doc_studio.core.backup.protocols import BackupPlan
from hse_doc_studio.core.listing import Found, Window
from hse_doc_studio.core.storage.ports import IObjectStore
from hse_doc_studio.infra.storage.fs import FsObjectStore


class InMemoryDestinations:
    def __init__(self) -> None:
        self.items: dict[str, StoredDestination] = {}

    async def list_all(self) -> list[BackupDestination]:
        return sorted((s.destination for s in self.items.values()), key=lambda d: (d.created_at, d.id))

    async def get(self, destination_id: str) -> StoredDestination | None:
        return self.items.get(destination_id)

    async def get_default(self) -> StoredDestination | None:
        return next((s for s in self.items.values() if s.destination.is_default), None)

    async def add(self, stored: StoredDestination) -> None:
        first = not self.items
        self.items[stored.destination.id] = replace(
            stored, destination=replace(stored.destination, is_default=first or stored.destination.is_default)
        )

    async def update(self, stored: StoredDestination) -> None:
        self.items[stored.destination.id] = stored

    async def delete(self, destination_id: str) -> None:
        gone = self.items.pop(destination_id, None)
        if gone and gone.destination.is_default and self.items:
            heir = min(self.items.values(), key=lambda s: s.destination.created_at)
            self.items[heir.destination.id] = replace(heir, destination=replace(heir.destination, is_default=True))

    async def set_default(self, destination_id: str) -> None:
        for key, stored in list(self.items.items()):
            self.items[key] = replace(stored, destination=replace(stored.destination, is_default=key == destination_id))

    async def record_check(self, destination_id: str, *, at: datetime, ok: bool, error: str | None) -> None:
        stored = self.items[destination_id]
        self.items[destination_id] = replace(
            stored, destination=replace(stored.destination, last_check_at=at, last_check_ok=ok, last_check_error=error)
        )

    async def name_taken(self, name: str, *, except_id: str | None = None) -> bool:
        return any(
            s.destination.spec.name.lower() == name.strip().lower() and s.destination.id != except_id
            for s in self.items.values()
        )


class InMemoryRuns:
    def __init__(self) -> None:
        self.items: dict[str, BackupRun] = {}

    async def start(self, run: BackupRun) -> bool:
        if any(r.status is RunStatus.running for r in self.items.values()):
            return False
        self.items[run.id] = run
        return True

    async def set_stage(self, run_id: str, stage: str) -> None:
        self.items[run_id] = replace(self.items[run_id], stage=stage)

    async def finish(
        self,
        run_id: str,
        *,
        status: RunStatus,
        at: datetime,
        size_bytes: int | None,
        backup_id: str | None,
        error: str | None,
        manifest_sha256: str | None,
    ) -> BackupRun:
        run = replace(
            self.items[run_id],
            status=status,
            stage=None,
            finished_at=at,
            size_bytes=size_bytes,
            backup_id=backup_id,
            error=error,
            manifest_sha256=manifest_sha256,
        )
        self.items[run_id] = run
        return run

    async def get(self, run_id: str) -> BackupRun | None:
        return self.items.get(run_id)

    async def page(self, window: Window) -> Found[BackupRun]:
        ordered = sorted(self.items.values(), key=lambda r: r.started_at, reverse=True)
        return Found(ordered[window.offset : window.offset + window.limit], len(ordered))

    async def alive_for(self, destination_id: str) -> list[BackupRun]:
        return [
            r
            for r in self.items.values()
            if r.destination_id == destination_id and r.status is RunStatus.ok and r.removed_at is None and r.backup_id
        ]

    async def mark_removed(self, run_id: str, at: datetime) -> None:
        self.items[run_id] = replace(self.items[run_id], removed_at=at)

    async def interrupt_running(self, at: datetime) -> int:
        count = 0
        for key, run in list(self.items.items()):
            if run.status is RunStatus.running:
                self.items[key] = replace(run, status=RunStatus.interrupted, finished_at=at, error="interrupted")
                count += 1
        return count

    async def running(self) -> BackupRun | None:
        return next((r for r in self.items.values() if r.status is RunStatus.running), None)

    async def last_finished(self) -> BackupRun | None:
        done = [r for r in self.items.values() if r.status is not RunStatus.running]
        return max(done, key=lambda r: r.started_at) if done else None


class DirStores:
    """Назначения на каталоге: `local_path` это подкаталог корня; `fail` имитирует недоступное хранилище."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.primary: set[str] = set()
        self.opened: list[DestinationSecrets] = []

    def open(self, spec: DestinationSpec, secrets: DestinationSecrets) -> IObjectStore:
        self.opened.append(secrets)
        if spec.kind is DestinationKind.s3 and spec.bucket == "broken-bucket":
            return _BrokenStore()  # type: ignore[return-value]
        return FsObjectStore(self.root / (spec.local_path or spec.bucket or "x"), max_object_bytes=1 << 30)

    def is_primary(self, spec: DestinationSpec) -> bool:
        return (spec.bucket or "") in self.primary


class _BrokenStore:
    async def check(self) -> None:
        from hse_doc_studio.core.storage.errors import ObjectStoreError  # noqa: PLC0415

        msg = "S3 недоступен: EndpointConnectionError"
        raise ObjectStoreError(msg)

    async def put(self, *args: object, **kwargs: object) -> None:
        await self.check()

    async def list_objects(self, prefix: str = "") -> list[object]:
        await self.check()
        return []

    async def delete(self, key: str) -> None:
        return None


class BytesProducer:
    def __init__(self, name: str, data: bytes, *, fail: bool = False) -> None:
        self.name = name
        self.data = data
        self.fail = fail

    async def produce(self, writer: EncryptingWriter) -> dict[str, int]:
        writer.write(self.data)
        if self.fail:
            msg = "pg_dump exited with 1: boom"
            raise RuntimeError(msg)
        return {"bytes": len(self.data)}


class FixedPlan:
    def __init__(self, *producers: BytesProducer) -> None:
        self.producers = list(producers)

    async def create(self) -> BackupPlan:
        return BackupPlan(producers=self.producers)


class FixedEnv:
    app_version = "9.9.9"

    async def schema_revision(self) -> str | None:
        return "bk_01_backups"

    async def installation_id(self) -> str | None:
        return "install-1"


class FixedKeys:
    def __init__(self, keys: list[bytes] | None = None, passphrase: str | None = None) -> None:
        self.keys = keys if keys is not None else [bytes(range(32))]
        self.phrase = passphrase

    async def installation_keys(self) -> list[bytes]:
        return self.keys

    async def passphrase(self) -> str | None:
        return self.phrase


class Admins:
    def __init__(self, *ids: str) -> None:
        self.ids = list(ids)

    async def active_admin_ids(self) -> list[str]:
        return self.ids


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, object, str | None]] = []

    async def notify(self, user_id: str, kind: object, payload: object, *, dedupe_key: str | None = None) -> None:
        self.sent.append((user_id, getattr(kind, "value", str(kind)), payload, dedupe_key))
