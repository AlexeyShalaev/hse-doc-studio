"""PostgresSigningIdentityRepository: ключ шифртекстом, подпись через сессию, политика, изоляция владельцев."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from hse_doc_studio.core.access.context import ActorRequired
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import SigningIdentity, SigningKeyMaterial
from hse_doc_studio.core.enums import SigningIdentityKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.secrets import encrypted_columns
from hse_doc_studio.core.signatures.key_policy import SERVER_KEY_STORAGE_SETTING, SigningKeyStorageDeniedError
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.signing_identities import SigningIdentityRow
from hse_doc_studio.infra.db.repositories.identity import SqlInstanceSettingsRepository, SqlUserRepository
from hse_doc_studio.infra.db.repositories.signing_identities import PostgresSigningIdentityRepository
from hse_doc_studio.infra.db.repositories.signing_key_policy import InstanceSigningKeyPolicy, SqlServerKeyCounter
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.secrets.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from hse_doc_studio.infra.signatures.cades_signer import sign_detached
from hse_doc_studio.use_cases.signing_identities.create_self_signed import CreateSelfSignedInput, CreateSelfSignedUC
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_identity_contract import make_user
from tests.fixtures.actors import as_actor

pytestmark = pytest.mark.pg

_ANNA = Actor.user("anna", name="Анна")
_BORIS = Actor.user("boris", name="Борис")
_T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


@dataclass
class World:
    sessions: SessionProvider
    repo: PostgresSigningIdentityRepository
    settings: SqlInstanceSettingsRepository
    tmp_root: Path


@pytest_asyncio.fixture
async def world(pg_migrated_engine: AsyncEngine, tmp_path: Path) -> World:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    for user_id in ("anna", "boris"):
        await users.add(make_user(user_id))
    cipher = FernetSecretCipher(KeyFileStore(tmp_path / "k.json", env_key=Fernet.generate_key().decode()))
    settings = SqlInstanceSettingsRepository(sessions)
    tmp_root = tmp_path / "tmp"
    tmp_root.mkdir()
    repo = PostgresSigningIdentityRepository(sessions, cipher, InstanceSigningKeyPolicy(settings), tmp_root=tmp_root)
    return World(sessions, repo, settings, tmp_root)


async def _allow(world: World) -> None:
    await world.settings.set(SERVER_KEY_STORAGE_SETTING, "allowed", source="admin")


def _identity(kind: SigningIdentityKind = SigningIdentityKind.self_signed) -> SigningIdentity:
    return SigningIdentity(
        id=uuid4(), label="Моя", kind=kind, subject_cn="Иван", not_after=_T0, trusted=False, created_at=_T0
    )


async def _material() -> SigningKeyMaterial:
    class _Capture:
        material: SigningKeyMaterial | None = None

        async def create(self, identity: SigningIdentity, material: SigningKeyMaterial | None = None) -> None:
            self.material = material

    capture = _Capture()
    await CreateSelfSignedUC(capture).execute(CreateSelfSignedInput(label="x", subject_cn="Иван"))  # type: ignore[arg-type]
    assert capture.material is not None
    return capture.material


async def test__policy_default__forbids_storing_a_private_key_and_nothing_is_saved(world: World) -> None:
    identity = _identity()
    with as_actor(_ANNA):
        with pytest.raises(SigningKeyStorageDeniedError):
            await world.repo.create(identity, await _material())
        assert await world.repo.get(identity.id) is None
        assert await world.repo.list_all() == []


async def test__server_key_counter__counts_only_identities_with_a_stored_private_key(world: World) -> None:
    await _allow(world)
    material = await _material()
    with as_actor(_ANNA):
        await world.repo.create(_identity(), material)
        await world.repo.create(_identity(SigningIdentityKind.openpgp))
    with as_actor(_BORIS):
        await world.repo.create(_identity(), material)

    assert await SqlServerKeyCounter(world.sessions).count_server_keys() == 2


async def test__policy_denied__identity_without_private_key_is_still_stored(world: World) -> None:
    identity = _identity(SigningIdentityKind.openpgp)
    with as_actor(_ANNA):
        await world.repo.create(identity)
        assert [i.id for i in await world.repo.list_all()] == [identity.id]
        with pytest.raises(ValueError, match=".+"):
            async with world.repo.private_key_session(identity.id):
                pass


async def test__create_allowed__key_is_ciphertext_and_cert_is_open(world: World) -> None:
    await _allow(world)
    material = await _material()
    identity = _identity()
    with as_actor(_ANNA):
        await world.repo.create(identity, material)
        assert await world.repo.read_cert(identity.id) == material.cert_pem
    async with world.sessions.use() as session:
        row = (await session.execute(select(SigningIdentityRow))).scalar_one()
    assert row.key_enc is not None
    assert "PRIVATE KEY" not in row.key_enc
    assert row.cert_pem == material.cert_pem.decode()
    assert ("signing_identities", "key_enc") in {(c.table, c.column) for c in encrypted_columns.all()}


async def test__private_key_session__signs_and_directory_is_gone_afterwards(world: World, tmp_path: Path) -> None:
    await _allow(world)
    material = await _material()
    identity = _identity()
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    sig = tmp_path / "doc.sig"
    with as_actor(_ANNA):
        await world.repo.create(identity, material)
        async with world.repo.private_key_session(identity.id) as directory:
            assert directory.parent == world.tmp_root
            assert (directory / "key.pem").read_bytes() == material.key_pem
            await asyncio.to_thread(sign_detached, pdf, sig, directory)
        assert not directory.exists()
    assert sig.stat().st_size > 0
    assert list(world.tmp_root.iterdir()) == []


async def test__private_key_session__directory_is_gone_after_failure_inside(world: World) -> None:
    await _allow(world)
    identity = _identity()
    with as_actor(_ANNA):
        await world.repo.create(identity, await _material())
        with pytest.raises(RuntimeError):
            async with world.repo.private_key_session(identity.id):
                raise RuntimeError("boom")
    assert list(world.tmp_root.iterdir()) == []


async def test__isolation__foreign_identity_is_invisible_and_cannot_be_used_or_deleted(world: World) -> None:
    await _allow(world)
    identity = _identity()
    with as_actor(_ANNA):
        await world.repo.create(identity, await _material())
    with as_actor(_BORIS):
        assert await world.repo.get(identity.id) is None
        assert await world.repo.list_all() == []
        assert await world.repo.read_cert(identity.id) is None
        assert await world.repo.delete(identity.id) is False
        with pytest.raises(NotFoundError):
            async with world.repo.private_key_session(identity.id):
                pass
    with as_actor(_ANNA):
        assert await world.repo.get(identity.id) is not None


async def test__delete__removes_record_and_user_deletion_cascades(world: World) -> None:
    await _allow(world)
    first, second = _identity(), _identity()
    with as_actor(_ANNA):
        await world.repo.create(first, await _material())
        await world.repo.create(second, await _material())
        assert await world.repo.delete(first.id) is True
        assert await world.repo.get(first.id) is None
    async with world.sessions.use() as session:
        await session.execute(text("DELETE FROM users WHERE id = 'anna'"))
    async with world.sessions.use() as session:
        assert (await session.execute(select(SigningIdentityRow))).first() is None


async def test__actor_required__without_user_actor_nothing_is_visible(world: World) -> None:
    with pytest.raises(ActorRequired):
        await world.repo.list_all()
