"""Учётные данные для удалённых репозиториев: `<data_dir>/git/credentials.json`.

Метаданные лежат открыто, секрет только шифртекстом (`hs1:...`). Список никогда не расшифровывает,
а запись, у которой нет подходящего ключа, показывается как unreadable. В лог попадают только
идентификаторы: тела записей туда не пишутся даже при ошибке разбора.
"""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.credentials import secret_aad
from hse_doc_studio.core.git_sync.entities import CredentialStatus, GitCredential, GitCredentialKind
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.infra.git_sync.key_store import store_unavailable_error, write_private_file

logger = structlog.get_logger()

_FILE_VERSION = 1

# Псевдонимы: внутри класса имя `list` занято методом и в аннотациях означало бы его.
_Record = dict[str, Any]
_Records = list[_Record]
_Credentials = list[GitCredential]


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _to_record(credential: GitCredential, sealed: str) -> dict[str, Any]:
    return {
        "id": str(credential.id),
        "kind": credential.kind.value,
        "label": credential.label,
        "host": credential.host,
        "port": credential.port,
        "username": credential.username,
        # unreadable вычисляется при чтении и на диск не пишется: ключ могут вернуть.
        "status": CredentialStatus.unverified.value
        if credential.status is CredentialStatus.unreadable
        else credential.status.value,
        "token_family": credential.token_family,
        "public_key": credential.public_key,
        "fingerprint_sha256": credential.fingerprint_sha256,
        "created_at": credential.created_at.isoformat(),
        "last_used_at": None if credential.last_used_at is None else credential.last_used_at.isoformat(),
        "expires_at": None if credential.expires_at is None else credential.expires_at.isoformat(),
        "secret": sealed,
    }


def _from_record(raw: dict[str, Any]) -> GitCredential:
    last_used = raw.get("last_used_at")
    expires = raw.get("expires_at")
    return GitCredential(
        id=UUID(raw["id"]),
        kind=GitCredentialKind(raw["kind"]),
        label=raw["label"],
        host=raw["host"],
        username=raw.get("username"),
        status=CredentialStatus(raw.get("status", CredentialStatus.unverified.value)),
        created_at=_parse_dt(raw["created_at"]),
        token_family=raw.get("token_family"),
        public_key=raw.get("public_key"),
        fingerprint_sha256=raw.get("fingerprint_sha256"),
        port=raw.get("port"),
        last_used_at=None if last_used is None else _parse_dt(last_used),
        expires_at=None if expires is None else _parse_dt(expires),
    )


class JsonGitCredentialRepository:
    def __init__(self, data_dir: Path, cipher: ISecretCipher) -> None:
        self._path = data_dir / "git" / "credentials.json"
        self._cipher = cipher
        self._lock = threading.RLock()

    async def list(self) -> _Credentials:
        with self._lock:
            return [self._entity(raw) for raw in self._records() if self._valid(raw)]

    async def get(self, credential_id: UUID) -> GitCredential | None:
        return next((c for c in await self.list() if c.id == credential_id), None)

    async def add(self, credential: GitCredential, secret: Secret) -> None:
        sealed = self._cipher.encrypt(secret, aad=secret_aad(credential.id, credential.kind))
        with self._lock:
            records = self._records(for_write=True)
            records.append(_to_record(credential, sealed))
            self._write(records)
        logger.info("git credential added", credential_id=str(credential.id), kind=credential.kind.value)

    async def update(self, credential: GitCredential, secret: Secret | None = None) -> None:
        with self._lock:
            records = self._records(for_write=True)
            for idx, raw in enumerate(records):
                if raw.get("id") != str(credential.id):
                    continue
                sealed = (
                    raw["secret"]
                    if secret is None
                    else self._cipher.encrypt(secret, aad=secret_aad(credential.id, credential.kind))
                )
                records[idx] = _to_record(credential, sealed)
                self._write(records)
                return
        raise NotFoundError(localized_error("Доступ не найден", "Credential not found"))

    async def delete(self, credential_id: UUID) -> bool:
        with self._lock:
            records = self._records(for_write=True)
            kept = [raw for raw in records if raw.get("id") != str(credential_id)]
            if len(kept) == len(records):
                return False
            self._write(kept)
        logger.info("git credential deleted", credential_id=str(credential_id))
        return True

    async def get_secret(self, credential_id: UUID) -> Secret:
        with self._lock:
            raw = next((r for r in self._records() if r.get("id") == str(credential_id)), None)
        if raw is None or not self._valid(raw):
            raise NotFoundError(localized_error("Доступ не найден", "Credential not found"))
        kind = GitCredentialKind(raw["kind"])
        return self._cipher.decrypt(raw["secret"], aad=secret_aad(credential_id, kind))

    async def mark(self, credential_id: UUID, status: CredentialStatus, *, used_at: datetime | None = None) -> None:
        if status is CredentialStatus.unreadable:
            return
        with self._lock:
            try:
                # Статус вторичен: ради него файл не откладывают и не перезаписывают, при сбое чтения пропускаем.
                records = self._records(for_write=True, set_aside=False)
            except GitSyncError:
                return
            for raw in records:
                if raw.get("id") == str(credential_id):
                    raw["status"] = status.value
                    if used_at is not None:
                        raw["last_used_at"] = used_at.isoformat()
                    self._write(records)
                    return

    def _entity(self, raw: dict[str, Any]) -> GitCredential:
        credential = _from_record(raw)
        if self._cipher.can_read(raw["secret"]):
            return credential
        return replace(credential, status=CredentialStatus.unreadable)

    @staticmethod
    def _valid(raw: dict[str, Any]) -> bool:
        try:
            _from_record(raw)
        except (KeyError, ValueError, TypeError):
            logger.warning("git credentials file: skipped a malformed record", credential_id=str(raw.get("id")))
            return False
        return isinstance(raw.get("secret"), str)

    def _records(self, *, for_write: bool = False, set_aside: bool = True) -> _Records:
        """Записи файла. Сбой чтения не считается порчей: читающему пусто, пишущий получает ошибку и файл цел.

        Откладывается в сторону только файл, который прочитался и не разобрался (`set_aside=False` это запрещает).
        """
        try:
            if not self._path.exists():
                return []
            content = self._path.read_bytes()
        except OSError as exc:
            logger.warning("git credentials file is not readable", path=str(self._path))
            if for_write:
                raise store_unavailable_error() from exc
            return []
        try:
            data = json.loads(content)
            records = data["credentials"] if data.get("version") == _FILE_VERSION else None
        except (ValueError, KeyError, AttributeError):
            records = None
        if not isinstance(records, list):
            logger.warning("git credentials file is damaged", path=str(self._path))
            if for_write and set_aside:
                self._set_aside()
            return []
        return [raw for raw in records if isinstance(raw, dict)]

    def _set_aside(self) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        self._path.replace(self._path.with_name(f"{self._path.name}.corrupt-{stamp}"))

    def _write(self, records: _Records) -> None:
        payload = {"version": _FILE_VERSION, "credentials": records}
        write_private_file(self._path, json.dumps(payload, ensure_ascii=False, indent=2).encode())
