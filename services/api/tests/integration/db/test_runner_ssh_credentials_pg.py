"""Сохранённые SSH-доступы в Postgres: секрет только шифртекстом, привязка к записи, удаление, список без значений."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.runner_install import HostKey, SavedSshCredential, SshAuth, SshAuthKind
from hse_doc_studio.core.secrets import encrypted_columns
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.runner_ssh import RunnerSshCredentialRow
from hse_doc_studio.infra.db.repositories.runner_ssh_credentials import PostgresSshCredentialRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.secrets.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

_NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
_PASSWORD = "CANARY-ssh-password-123"
_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nCANARYKEYBODY\n-----END OPENSSH PRIVATE KEY-----"


def _credential(credential_id: str = "a" * 32) -> SavedSshCredential:
    return SavedSshCredential(
        id=credential_id,
        label="Лаборатория",
        host="srv.example.org",
        port=22,
        username="deploy",
        sudo=True,
        auth_kind=SshAuthKind.password,
        host_key=HostKey("ssh-ed25519", "SHA256:abc", "ssh-ed25519 AAAA"),
        created_by="boss",
        created_at=_NOW,
    )


@pytest_asyncio.fixture
async def repo(pg_migrated_engine: AsyncEngine, tmp_path: Path) -> PostgresSshCredentialRepository:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    cipher = FernetSecretCipher(KeyFileStore(tmp_path / "k.json", env_key=Fernet.generate_key().decode()))
    repository = PostgresSshCredentialRepository(sessions, cipher)
    return repository


async def _raw_rows(repo: PostgresSshCredentialRepository) -> list[RunnerSshCredentialRow]:
    async with repo._sessions.use() as session:  # noqa: SLF001
        return list((await session.execute(select(RunnerSshCredentialRow))).scalars())


async def test__roundtrip__password_and_key_with_passphrase(repo: PostgresSshCredentialRepository) -> None:
    await repo.add(_credential("a" * 32), SshAuth(SshAuthKind.password, Secret(_PASSWORD)))
    await repo.add(_credential("b" * 32), SshAuth(SshAuthKind.key, Secret(_KEY), Secret("pp-CANARY")))

    password = await repo.get_auth("a" * 32)
    key = await repo.get_auth("b" * 32)

    assert password is not None
    assert password.kind is SshAuthKind.password
    assert password.secret.reveal() == _PASSWORD
    assert password.passphrase is None
    assert key is not None
    assert (key.secret.reveal(), key.passphrase.reveal() if key.passphrase else None) == (_KEY, "pp-CANARY")


async def test__storage__secret_is_only_ciphertext(repo: PostgresSshCredentialRepository) -> None:
    await repo.add(_credential(), SshAuth(SshAuthKind.key, Secret(_KEY), Secret("pp-CANARY")))

    rows = await _raw_rows(repo)

    stored = rows[0].secret_enc
    for canary in ("CANARYKEYBODY", "pp-CANARY", "BEGIN OPENSSH"):
        assert canary not in stored
    dumped = str(
        [(c.name, getattr(rows[0], c.name)) for c in RunnerSshCredentialRow.__table__.columns if c.name != "secret_enc"]
    )
    assert "CANARY" not in dumped


async def test__listing__has_metadata_and_no_secret_attribute(repo: PostgresSshCredentialRepository) -> None:
    await repo.add(_credential(), SshAuth(SshAuthKind.password, Secret(_PASSWORD)))

    listed = await repo.list()
    one = await repo.get("a" * 32)

    assert [c.label for c in listed] == ["Лаборатория"]
    assert one is not None
    assert one.host_key.fingerprint == "SHA256:abc"
    assert _PASSWORD not in repr(listed) + repr(one)


async def test__ciphertext_is_bound_to_its_record(repo: PostgresSshCredentialRepository) -> None:
    await repo.add(_credential("a" * 32), SshAuth(SshAuthKind.password, Secret(_PASSWORD)))
    await repo.add(_credential("b" * 32), SshAuth(SshAuthKind.password, Secret("other-password")))
    rows = {row.id: row.secret_enc for row in await _raw_rows(repo)}
    async with repo._sessions.use() as session:  # noqa: SLF001
        await session.execute(
            update(RunnerSshCredentialRow)
            .where(RunnerSshCredentialRow.id == "b" * 32)
            .values(secret_enc=rows["a" * 32])
        )

    with pytest.raises(GitSyncError):
        await repo.get_auth("b" * 32)


async def test__delete_and_mark_used(repo: PostgresSshCredentialRepository) -> None:
    await repo.add(_credential(), SshAuth(SshAuthKind.password, Secret(_PASSWORD)))

    await repo.mark_used("a" * 32, _NOW, "hse-runner-1")
    used = await repo.get("a" * 32)
    deleted = await repo.delete("a" * 32)
    again = await repo.delete("a" * 32)

    assert used is not None
    assert (used.last_used_at, used.runner_name) == (_NOW, "hse-runner-1")
    assert (deleted, again) == (True, False)
    assert await repo.get_auth("a" * 32) is None


def test__secret_column_is_registered_for_key_rotation() -> None:
    assert "runner_ssh_credentials.secret_enc" in [column.label for column in encrypted_columns.all()]
