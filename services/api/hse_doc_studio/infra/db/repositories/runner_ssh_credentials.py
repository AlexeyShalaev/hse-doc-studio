"""Сохранённые SSH-доступы установки раннеров. Секрет только шифртекстом, привязанным к таблице, колонке и записи."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import delete, select, update

from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.runner_install import HostKey, SavedSshCredential, SshAuth, SshAuthKind
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.infra.db.orm.runner_ssh import RunnerSshCredentialRow
from hse_doc_studio.infra.db.session import SessionProvider

_TABLE = "runner_ssh_credentials"
_COLUMN = "secret_enc"


def seal_auth(cipher: ISecretCipher, credential_id: str, auth: SshAuth) -> str:
    body = {
        "kind": auth.kind.value,
        "secret": auth.secret.reveal(),
        "passphrase": auth.passphrase.reveal() if auth.passphrase else "",
    }
    return cipher.encrypt(Secret(json.dumps(body)), aad=column_aad(_TABLE, _COLUMN, credential_id))


def open_auth(cipher: ISecretCipher, credential_id: str, token: str) -> SshAuth:
    body = json.loads(cipher.decrypt(token, aad=column_aad(_TABLE, _COLUMN, credential_id)).reveal())
    passphrase = body.get("passphrase") or ""
    return SshAuth(SshAuthKind(body["kind"]), Secret(body["secret"]), Secret(passphrase) if passphrase else None)


def _entity(row: RunnerSshCredentialRow) -> SavedSshCredential:
    return SavedSshCredential(
        id=row.id,
        label=row.label,
        host=row.host,
        port=row.port,
        username=row.username,
        sudo=row.sudo,
        auth_kind=SshAuthKind(row.auth_kind),
        host_key=HostKey(row.host_key_type, row.host_key_fingerprint, row.host_key_public),
        created_by=row.created_by,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        runner_name=row.runner_name,
    )


class PostgresSshCredentialRepository:
    def __init__(self, sessions: SessionProvider, cipher: ISecretCipher) -> None:
        self._sessions = sessions
        self._cipher = cipher

    async def add(self, credential: SavedSshCredential, auth: SshAuth) -> None:
        sealed = seal_auth(self._cipher, credential.id, auth)
        async with self._sessions.use() as session:
            session.add(
                RunnerSshCredentialRow(
                    id=credential.id,
                    label=credential.label,
                    host=credential.host,
                    port=credential.port,
                    username=credential.username,
                    sudo=credential.sudo,
                    auth_kind=credential.auth_kind.value,
                    host_key_type=credential.host_key.key_type,
                    host_key_fingerprint=credential.host_key.fingerprint,
                    host_key_public=credential.host_key.public_key,
                    created_by=credential.created_by,
                    created_at=credential.created_at,
                    last_used_at=credential.last_used_at,
                    runner_name=credential.runner_name,
                    secret_enc=sealed,
                )
            )

    async def list(self) -> list[SavedSshCredential]:
        async with self._sessions.use() as session:
            rows = (
                await session.execute(select(RunnerSshCredentialRow).order_by(RunnerSshCredentialRow.created_at))
            ).scalars()
            return [_entity(row) for row in rows]

    async def get(self, credential_id: str) -> SavedSshCredential | None:
        async with self._sessions.use() as session:
            row = await session.get(RunnerSshCredentialRow, credential_id)
            return None if row is None else _entity(row)

    async def get_auth(self, credential_id: str) -> SshAuth | None:
        async with self._sessions.use() as session:
            row = await session.get(RunnerSshCredentialRow, credential_id)
            return None if row is None else open_auth(self._cipher, row.id, row.secret_enc)

    async def delete(self, credential_id: str) -> bool:
        async with self._sessions.use() as session:
            result = await session.execute(
                delete(RunnerSshCredentialRow)
                .where(RunnerSshCredentialRow.id == credential_id)
                .returning(RunnerSshCredentialRow.id)
            )
            return result.first() is not None

    async def mark_used(self, credential_id: str, at: datetime, runner_name: str | None) -> None:
        async with self._sessions.use() as session:
            await session.execute(
                update(RunnerSshCredentialRow)
                .where(RunnerSshCredentialRow.id == credential_id)
                .values(last_used_at=at, runner_name=runner_name)
            )
