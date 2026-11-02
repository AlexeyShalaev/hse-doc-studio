"""Назначения бэкапов в админке: список, создание, правка, удаление, проверка подключения."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.backup.destinations import key_hint, validate_spec
from hse_doc_studio.core.backup.entities import (
    PROBE_PREFIX,
    BackupDestination,
    DestinationSecrets,
    DestinationSpec,
    StoredDestination,
)
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.backup.protocols import IBackupDestinationRepository, IBackupRunRepository, IBackupStoreFactory
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.core.storage.errors import ObjectStoreError
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.backup.service import DEST_TABLE, KEY_COLUMN, SECRET_COLUMN, BackupService, short_error

PROBE_BODY = b"hse-doc-studio backup probe\n"


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    error: str | None
    warnings: tuple[str, ...]
    checked_at: datetime


@dataclass(frozen=True)
class DestinationInput:
    spec: DestinationSpec
    # None: оставить как есть (при создании это «нет значения»); пустая строка у ключей не допускается.
    access_key: str | None = None
    secret_key: str | None = None
    make_default: bool = False


async def probe_store(
    stores: IBackupStoreFactory, spec: DestinationSpec, secrets: DestinationSecrets, now: datetime
) -> CheckResult:
    """Пишет, читает, сверяет и удаляет пробный объект."""
    warnings: list[str] = []
    if stores.is_primary(spec):
        warnings.append("same_as_primary")
    key = f"{(spec.prefix + '/') if spec.prefix else ''}{PROBE_PREFIX}{uuid4().hex}"
    try:
        store = stores.open(spec, secrets)
        await store.check()
        await store.put(key, PROBE_BODY)
        try:
            if await store.get(key) != PROBE_BODY:
                return CheckResult(False, "the probe object came back different", tuple(warnings), now)
        finally:
            await store.delete(key)
    except (ObjectStoreError, BackupError, OSError) as exc:
        return CheckResult(False, short_error(exc), tuple(warnings), now)
    return CheckResult(True, None, tuple(warnings), now)


class ListDestinationsUC:
    def __init__(self, destinations: IBackupDestinationRepository) -> None:
        self._destinations = destinations

    async def execute(self, actor: Actor) -> list[BackupDestination]:
        require_admin(actor)
        return await self._destinations.list_all()


class _DestinationBase:
    def __init__(
        self,
        destinations: IBackupDestinationRepository,
        runs: IBackupRunRepository,
        cipher: ISecretCipher,
        stores: IBackupStoreFactory,
        service: BackupService,
        audit: IAuditLog,
        uow: IUnitOfWork,
        clock: Clock = utc_now,
    ) -> None:
        self._destinations = destinations
        self._runs = runs
        self._cipher = cipher
        self._stores = stores
        self._service = service
        self._audit = audit
        self._uow = uow
        self._clock = clock

    def _seal(self, dest_id: str, column: str, value: str) -> str:
        return self._cipher.encrypt(Secret(value), aad=column_aad(DEST_TABLE, column, dest_id))

    @staticmethod
    def _require_keys(spec: DestinationSpec, access: str | None, secret: str | None) -> None:
        if spec.kind.value == "s3" and (not access or not secret):
            raise BackupError(
                BackupErrorCode.invalid_input, "access key and secret key are required", field="access_key"
            )


class CreateDestinationUC(_DestinationBase):
    async def execute(self, actor: Actor, data: DestinationInput) -> BackupDestination:
        return await self.create(require_admin(actor), data)

    async def create(self, admin_id: str | None, data: DestinationInput) -> BackupDestination:
        """Создание без проверки роли: для админки (после `require_admin`) и провижининга (`admin_id=None`)."""
        spec = validate_spec(data.spec)
        self._require_keys(spec, data.access_key, data.secret_key)
        if await self._destinations.name_taken(spec.name):
            raise BackupError(BackupErrorCode.conflict, "a destination with this name already exists", field="name")
        now = self._clock()
        dest_id = str(uuid4())
        is_s3 = spec.kind.value == "s3"
        destination = BackupDestination(
            id=dest_id,
            spec=spec,
            is_default=False,
            access_key_hint=key_hint(data.access_key) if is_s3 else None,
            secret_key_set=is_s3,
            created_at=now,
            updated_at=now,
        )
        stored = StoredDestination(
            destination,
            self._seal(dest_id, KEY_COLUMN, data.access_key or "") if is_s3 else None,
            self._seal(dest_id, SECRET_COLUMN, data.secret_key or "") if is_s3 else None,
        )
        async with self._uow.begin():
            await self._destinations.add(stored)
            if data.make_default:
                await self._destinations.set_default(dest_id)
            await self._audit.record(
                "backup.destination_create",
                actor_id=admin_id,
                target=dest_id,
                details={"name": spec.name, "kind": spec.kind.value, "bucket": spec.bucket, "endpoint": spec.endpoint},
            )
        saved = await self._destinations.get(dest_id)
        assert saved is not None  # noqa: S101
        return saved.destination


class UpdateDestinationUC(_DestinationBase):
    async def execute(self, actor: Actor, destination_id: str, data: DestinationInput) -> BackupDestination:
        admin_id = require_admin(actor)
        current = await self._destinations.get(destination_id)
        if current is None:
            raise BackupError(BackupErrorCode.not_found, "destination not found")
        spec = validate_spec(data.spec)
        if spec.kind is not current.destination.spec.kind:
            raise BackupError(BackupErrorCode.invalid_input, "the kind cannot be changed", field="kind")
        if await self._destinations.name_taken(spec.name, except_id=destination_id):
            raise BackupError(BackupErrorCode.conflict, "a destination with this name already exists", field="name")
        is_s3 = spec.kind.value == "s3"
        access_enc, secret_enc = current.access_key_enc, current.secret_key_enc
        hint = current.destination.access_key_hint
        if is_s3 and data.access_key:
            access_enc, hint = self._seal(destination_id, KEY_COLUMN, data.access_key), key_hint(data.access_key)
        if is_s3 and data.secret_key:
            secret_enc = self._seal(destination_id, SECRET_COLUMN, data.secret_key)
        updated = BackupDestination(
            id=destination_id,
            spec=spec,
            is_default=current.destination.is_default,
            access_key_hint=hint,
            secret_key_set=secret_enc is not None,
            created_at=current.destination.created_at,
            updated_at=self._clock(),
            # Проверка относилась к прежним параметрам.
            last_check_at=None,
            last_check_ok=None,
            last_check_error=None,
        )
        async with self._uow.begin():
            await self._destinations.update(StoredDestination(updated, access_enc, secret_enc))
            if data.make_default:
                await self._destinations.set_default(destination_id)
            await self._audit.record(
                "backup.destination_update",
                actor_id=admin_id,
                target=destination_id,
                details={
                    "name": spec.name,
                    "bucket": spec.bucket,
                    "endpoint": spec.endpoint,
                    "access_key_changed": bool(data.access_key),
                    "secret_key_changed": bool(data.secret_key),
                },
            )
        saved = await self._destinations.get(destination_id)
        assert saved is not None  # noqa: S101
        return saved.destination


class DeleteDestinationUC(_DestinationBase):
    async def execute(self, actor: Actor, destination_id: str) -> None:
        admin_id = require_admin(actor)
        current = await self._destinations.get(destination_id)
        if current is None:
            raise BackupError(BackupErrorCode.not_found, "destination not found")
        running = await self._runs.running()
        if running is not None and running.destination_id == destination_id:
            raise BackupError(BackupErrorCode.conflict, "a backup to this destination is running")
        async with self._uow.begin():
            await self._destinations.delete(destination_id)
            await self._audit.record(
                "backup.destination_delete",
                actor_id=admin_id,
                target=destination_id,
                details={"name": current.destination.spec.name},
            )


class TestDestinationUC(_DestinationBase):
    __test__ = False

    async def execute(self, actor: Actor, *, destination_id: str | None, data: DestinationInput | None) -> CheckResult:
        """Проверка сохранённого назначения (по id) или введённой формы; пустые ключи формы берутся из сохранённого."""
        admin_id = require_admin(actor)
        now = self._clock()
        stored = await self._destinations.get(destination_id) if destination_id else None
        if destination_id and stored is None:
            raise BackupError(BackupErrorCode.not_found, "destination not found")
        if data is not None:
            spec = validate_spec(data.spec)
            saved_keys = (
                self._service.open_secrets(stored)
                if stored is not None and stored.access_key_enc
                else DestinationSecrets()
            )
            secrets = DestinationSecrets(
                data.access_key or saved_keys.access_key, data.secret_key or saved_keys.secret_key
            )
        elif stored is not None:
            spec = stored.destination.spec
            secrets = self._service.open_secrets(stored)
        else:
            raise BackupError(BackupErrorCode.invalid_input, "nothing to test")
        if spec.kind.value == "s3" and not (secrets.access_key and secrets.secret_key):
            return CheckResult(False, "access key and secret key are required", (), now)
        result = await probe_store(self._stores, spec, secrets, now)
        if stored is not None and data is None:
            await self._destinations.record_check(stored.destination.id, at=now, ok=result.ok, error=result.error)
        await self._audit.record(
            "backup.destination_test",
            actor_id=admin_id,
            target=destination_id,
            details={"name": spec.name, "ok": result.ok},
        )
        return result
