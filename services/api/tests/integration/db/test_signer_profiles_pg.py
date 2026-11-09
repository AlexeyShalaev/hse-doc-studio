"""PostgresSignerProfileRepository: картинка и ключ независимы, пустой профиль не хранится, уходит с человеком."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from hse_doc_studio.core.signatures.signer_profile import ProfileImage, ProfilePublicKey, PublicKeyKind
from hse_doc_studio.core.value_objects import SignerInfo
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.repositories.signer_profiles import PostgresSignerProfileRepository
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_identity_contract import make_user

pytestmark = pytest.mark.pg

_T0 = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
_PNG = b"\x89PNG\r\n\x1a\nfake-signature"
_IMAGE = ProfileImage(sha256="a" * 64, size=len(_PNG), width_px=300, height_px=100, updated_at=_T0)
_PLATE = SignerInfo(
    kind="openpgp",
    owner="Пётр Петров",
    cert_id="1A2B 3C4D 5E6F 7A8B",
    valid_from="2026-01-01T00:00:00+00:00",
    valid_to=None,
    signer_id="F" * 40,
)
_KEY = ProfilePublicKey(
    kind=PublicKeyKind.openpgp, data=b"-----BEGIN PGP PUBLIC KEY BLOCK-----", plate=_PLATE, updated_at=_T0
)


@dataclass
class World:
    engine: AsyncEngine
    repo: PostgresSignerProfileRepository

    async def rows(self) -> int:
        async with self.engine.connect() as conn:
            return int((await conn.execute(text("SELECT count(*) FROM signer_profiles"))).scalar_one())


@pytest_asyncio.fixture
async def world(pg_migrated_engine: AsyncEngine) -> World:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    for user_id in ("anna", "boris"):
        await users.add(make_user(user_id))
    return World(pg_migrated_engine, PostgresSignerProfileRepository(sessions))


async def test__get__no_row__empty_profile(world: World) -> None:
    profile = await world.repo.get("anna")

    assert profile.empty
    assert await world.repo.read_image("anna") is None


async def test__save_image_and_key__both_halves_read_back(world: World) -> None:
    await world.repo.save_image("anna", _PNG, _IMAGE)
    await world.repo.save_public_key("anna", _KEY)

    profile = await world.repo.get("anna")

    assert profile.image == _IMAGE
    assert profile.public_key == _KEY
    assert await world.repo.read_image("anna") == _PNG
    assert await world.rows() == 1


async def test__save_image__second_time__replaces_and_keeps_the_key(world: World) -> None:
    await world.repo.save_public_key("anna", _KEY)
    await world.repo.save_image("anna", _PNG, _IMAGE)
    newer = b"\x89PNG\r\n\x1a\nnewer"

    await world.repo.save_image("anna", newer, ProfileImage("b" * 64, len(newer), 10, 5, _T0))

    profile = await world.repo.get("anna")
    assert profile.image is not None
    assert (profile.image.sha256, profile.image.size, profile.image.width_px) == ("b" * 64, len(newer), 10)
    assert profile.public_key == _KEY


async def test__clear__one_half_keeps_the_row_the_last_half_removes_it(world: World) -> None:
    await world.repo.save_image("anna", _PNG, _IMAGE)
    await world.repo.save_public_key("anna", _KEY)

    assert await world.repo.clear_image("anna") is True
    assert await world.repo.clear_image("anna") is False
    assert (await world.repo.get("anna")).public_key == _KEY
    assert await world.rows() == 1

    assert await world.repo.clear_public_key("anna") is True
    assert (await world.repo.get("anna")).empty
    assert await world.rows() == 0


async def test__profiles__per_person(world: World) -> None:
    await world.repo.save_image("anna", _PNG, _IMAGE)

    assert (await world.repo.get("boris")).empty
    assert await world.repo.read_image("boris") is None
    assert await world.repo.clear_image("boris") is False
    assert (await world.repo.get("anna")).image == _IMAGE


async def test__user_deleted__profile_goes_with_them(world: World) -> None:
    await world.repo.save_image("anna", _PNG, _IMAGE)

    async with world.engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE id = 'anna'"))

    assert await world.rows() == 0


async def test__unknown_key_kind__refused_by_the_database(world: World) -> None:
    from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

    with pytest.raises(IntegrityError):
        async with world.engine.begin() as conn:
            await conn.execute(text("INSERT INTO signer_profiles (user_id, key_kind) VALUES ('anna', 'pkcs12')"))
