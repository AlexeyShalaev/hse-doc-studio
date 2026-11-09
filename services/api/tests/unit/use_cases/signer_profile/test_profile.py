"""Свой профиль подписанта: только владелец, только PNG и только открытая часть ключа, каждое изменение в аудите."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.signatures.signer_profile import (
    MAX_PROFILE_IMAGE_BYTES,
    PublicKeyKind,
    SecretKeyMaterialError,
)
from hse_doc_studio.infra.signatures.public_key_reader import PublicKeyReader
from hse_doc_studio.use_cases.signer_profile.profile import (
    ClearProfileImageUC,
    ClearProfilePublicKeyUC,
    GetSignerProfileUC,
    ReadProfileImageUC,
    SaveProfileImageUC,
    SaveProfilePublicKeyUC,
)

from tests.fakes.signer_profile import InMemorySignerProfileRepository, make_png, make_self_signed

ANNA = Actor.user("anna", name="Анна")
BORIS = Actor.user("boris", name="Борис")
GUEST = Actor.guest("gs_1", name="Гость", link_id="lnk")


def certificate(owner: str = "Анна Смирнова") -> tuple[bytes, bytes]:
    pair = make_self_signed(owner, serial=77)
    return pair.cert_pem, pair.key_pem


@dataclass
class _Audit:
    records: list[tuple[str, Mapping[str, object]]] = field(default_factory=list)

    async def record(self, action: str, *, project_id: object, details: Mapping[str, object]) -> None:
        assert project_id is None
        self.records.append((action, dict(details)))


class _NoGpg:
    available = False

    def contains_secret_key(self, data: bytes) -> bool:
        raise AssertionError("not an OpenPGP file")

    def show_keys(self, data: bytes) -> list[object]:
        raise AssertionError("not an OpenPGP file")


@dataclass
class World:
    repo: InMemorySignerProfileRepository = field(default_factory=InMemorySignerProfileRepository)
    audit: _Audit = field(default_factory=_Audit)

    def save_image(self) -> SaveProfileImageUC:
        return SaveProfileImageUC(self.repo, self.audit)

    def save_key(self) -> SaveProfilePublicKeyUC:
        return SaveProfilePublicKeyUC(self.repo, PublicKeyReader(_NoGpg()), self.audit)  # type: ignore[arg-type]


@pytest.fixture
def world() -> World:
    return World()


async def test__get__no_profile__empty_profile_of_the_actor(world: World) -> None:
    profile = await GetSignerProfileUC(world.repo).execute(ANNA)

    assert (profile.user_id, profile.image, profile.public_key) == ("anna", None, None)


@pytest.mark.parametrize("actor", [GUEST, Actor.local()], ids=["guest", "local"])
async def test__every_use_case__not_a_signed_in_person__auth_required(world: World, actor: Actor) -> None:
    calls = [
        GetSignerProfileUC(world.repo).execute(actor),
        ReadProfileImageUC(world.repo).execute(actor),
        world.save_image().execute(actor, make_png()),
        ClearProfileImageUC(world.repo, world.audit).execute(actor),
        world.save_key().execute(actor, certificate()[0]),
        ClearProfilePublicKeyUC(world.repo, world.audit).execute(actor),
    ]
    for call in calls:
        with pytest.raises(IdentityError) as caught:
            await call
        assert caught.value.code is IdentityErrorCode.auth_required

    assert world.repo.profiles == {}
    assert world.audit.records == []


async def test__save_image__png__stored_with_size_and_hash_and_audited_without_content(world: World) -> None:
    image = make_png(320, 120)

    profile = await world.save_image().execute(ANNA, image)

    assert profile.image is not None
    assert (profile.image.width_px, profile.image.height_px) == (320, 120)
    assert profile.image.sha256 == hashlib.sha256(image).hexdigest()
    assert profile.image.size == len(image)
    assert await ReadProfileImageUC(world.repo).execute(ANNA) == image
    assert world.audit.records == [("signature.profile_image", {"sha256": profile.image.sha256})]


@pytest.mark.parametrize(
    ("blob", "reason"),
    [
        (b"", "пустой"),
        (b"GIF89a not a png", "PNG"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * MAX_PROFILE_IMAGE_BYTES, "2 МБ"),
    ],
    ids=["empty", "not-png", "too-large"],
)
async def test__save_image__bad_file__refused_and_nothing_stored(world: World, blob: bytes, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        await world.save_image().execute(ANNA, blob)

    assert world.repo.profiles == {}
    assert world.audit.records == []


async def test__profile__other_person__sees_only_their_own(world: World) -> None:
    await world.save_image().execute(ANNA, make_png())
    await world.save_key().execute(ANNA, certificate()[0])

    boris = await GetSignerProfileUC(world.repo).execute(BORIS)

    assert (boris.image, boris.public_key) == (None, None)
    assert await ReadProfileImageUC(world.repo).execute(BORIS) is None


async def test__clear_image__keeps_the_key_and_audits_only_a_real_removal(world: World) -> None:
    await world.save_image().execute(ANNA, make_png())
    await world.save_key().execute(ANNA, certificate()[0])
    world.audit.records.clear()

    first = await ClearProfileImageUC(world.repo, world.audit).execute(ANNA)
    await ClearProfileImageUC(world.repo, world.audit).execute(ANNA)

    assert first.image is None
    assert first.public_key is not None
    assert world.audit.records == [("signature.profile_image_cleared", {})]


async def test__save_public_key__certificate__plate_data_and_audit_by_fingerprint(world: World) -> None:
    cert_pem, _ = certificate("Анна Смирнова")

    profile = await world.save_key().execute(ANNA, cert_pem)

    key = profile.public_key
    assert key is not None
    assert key.kind is PublicKeyKind.x509
    assert key.data == cert_pem
    assert (key.plate.kind, key.plate.owner, key.plate.cert_id) == ("x509", "Анна Смирнова", "4D")
    assert world.audit.records == [("signature.profile_key", {"kind": "x509", "signer_id": key.plate.signer_id})]


@pytest.mark.parametrize("bundle", ["key", "cert+key"])
async def test__save_public_key__private_key_inside__refused_and_nothing_stored(world: World, bundle: str) -> None:
    cert_pem, key_pem = certificate()

    with pytest.raises(SecretKeyMaterialError):
        await world.save_key().execute(ANNA, key_pem if bundle == "key" else cert_pem + key_pem)

    assert world.repo.profiles == {}
    assert world.audit.records == []


async def test__save_public_key__replaces_the_previous_one(world: World) -> None:
    await world.save_key().execute(ANNA, certificate("Первый")[0])

    profile = await world.save_key().execute(ANNA, certificate("Второй")[0])

    assert profile.public_key is not None
    assert profile.public_key.plate.owner == "Второй"


async def test__clear_public_key__last_half__profile_disappears(world: World) -> None:
    await world.save_key().execute(ANNA, certificate()[0])

    profile = await ClearProfilePublicKeyUC(world.repo, world.audit).execute(ANNA)

    assert profile.empty
    assert world.repo.profiles == {}
    assert world.audit.records[-1] == ("signature.profile_key_cleared", {})
