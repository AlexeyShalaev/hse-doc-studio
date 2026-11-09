"""Части сценариев подписанта без сервера: плашка из профиля, факты, ключ профиля в связке, проверка ключа.

docs/design/signing-route.md, разделы 6.5 (известные данные плашки), 6.2 (заполнение плашек перед фиксацией) и 8.1
(отказы подписи ключом Студии до записи согласия).
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.enums import SigningIdentityKind, SignMode
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.signatures.errors import GpgError
from hse_doc_studio.core.signatures.key_policy import SigningKeyStorageDeniedError
from hse_doc_studio.core.signatures.signer_profile import ProfilePublicKey, PublicKeyKind
from hse_doc_studio.core.signing_route.effects import FillPlate
from hse_doc_studio.core.signing_route.ports import NoSigningRoutes
from hse_doc_studio.core.value_objects import SignaturePlacement, SignatureSlot, SignaturesState, SignerInfo
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring
from hse_doc_studio.use_cases.signatures._studio_signer import KeyPassphraseRequiredError, StudioSigner
from hse_doc_studio.use_cases.signatures.default_key import DefaultKey
from hse_doc_studio.use_cases.signer_profile.plate_data import ProfileSignerPlateData, SlotSignerPlateData
from hse_doc_studio.use_cases.signing_route.effects import RouteFileEffects
from hse_doc_studio.use_cases.signing_route.facts import known_plates
from hse_doc_studio.use_cases.signing_route.key_signer import (
    KeyNotFoundError,
    KeyPassphraseInvalidError,
    KeyRequest,
    NoSigningKeyError,
    RouteKeySigner,
)
from hse_doc_studio.use_cases.signing_route.point import RoutePoint

from tests.fakes.signer_profile import InMemorySignerProfileRepository
from tests.unit.core.signing_route.world import DOC, make_route, participant

T0 = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
SLOT_SIGNER = SignerInfo(kind="manual", owner="Из слота", cert_id="01")
PROFILE_SIGNER = SignerInfo(kind="openpgp", owner="Из профиля", cert_id="1A2B", signer_id="FINGERPRINT")


def _profile_key(kind: PublicKeyKind = PublicKeyKind.openpgp, plate: SignerInfo = PROFILE_SIGNER) -> ProfilePublicKey:
    return ProfilePublicKey(kind=kind, data=b"public key bytes", plate=plate, updated_at=T0)


def _state(**slots: SignatureSlot) -> SignaturesState:
    placement = SignaturePlacement(enabled=True, page=1, x_mm=10, y_mm=10, width_mm=40)
    return SignaturesState(slots=dict(slots), placements={DOC: dict.fromkeys(slots, placement)})


def _plate_slot(signer: SignerInfo | None = None) -> SignatureSlot:
    return SignatureSlot(None, None, None, sign_mode=SignMode.detached_text, signer=signer)


# --- источник данных плашки -----------------------------------------------------------------------------------------


async def test__profile_plate_data__slot_signer_first__then_the_profile_key() -> None:
    profiles = InMemorySignerProfileRepository()
    await profiles.save_public_key("petrov", _profile_key())
    source = ProfileSignerPlateData(profiles)
    state = _state(with_signer=_plate_slot(SLOT_SIGNER), empty=_plate_slot())

    assert await source.plate_for(state, "with_signer", "petrov") == SLOT_SIGNER
    assert await source.plate_for(state, "empty", "petrov") == PROFILE_SIGNER
    # Слота в состоянии ещё нет (автор его не настраивал): профиль всё равно известен.
    assert await source.plate_for(state, "unknown", "petrov") == PROFILE_SIGNER


async def test__profile_plate_data__no_account_or_empty_profile__unknown() -> None:
    source = ProfileSignerPlateData(InMemorySignerProfileRepository())
    state = _state(empty=_plate_slot())

    assert await source.plate_for(state, "empty", None) is None
    assert await source.plate_for(state, "empty", "sidorov") is None


async def test__slot_plate_data__local_studio_reads_only_the_slot() -> None:
    source = SlotSignerPlateData()
    state = _state(with_signer=_plate_slot(SLOT_SIGNER), empty=_plate_slot())

    assert await source.plate_for(state, "with_signer", "petrov") == SLOT_SIGNER
    assert await source.plate_for(state, "empty", "petrov") is None


async def test__known_plates__per_participant_by_any_own_slot() -> None:
    profiles = InMemorySignerProfileRepository()
    with_profile = participant(2, "supervisor", ["supervisor"])
    by_image = participant(1, "author", ["author"])
    unknown = participant(3, "academic_supervisor", ["academic_supervisor"])
    invited = participant(4, "co_supervisor", ["co_supervisor"])
    invited = type(invited)(id=invited.id, step=4, persona="co_supervisor", assignments=invited.assignments)
    assert with_profile.user_id is not None
    assert by_image.user_id is not None
    await profiles.save_public_key(with_profile.user_id.hex, _profile_key())
    await profiles.save_public_key(by_image.user_id.hex, _profile_key(plate=SLOT_SIGNER))
    route = make_route([by_image, with_profile, unknown, invited])
    state = _state(
        author=SignatureSlot("a.png", 10, 4),
        supervisor=_plate_slot(),
        academic_supervisor=_plate_slot(),
        co_supervisor=_plate_slot(),
    )

    plates = await known_plates(route, state, ProfileSignerPlateData(profiles))

    # Подписант картинкой тоже спрашивается: он может сменить способ на ЭП на своём шаге.
    assert plates == {with_profile.user_id: PROFILE_SIGNER, by_image.user_id: SLOT_SIGNER}


# --- ключ профиля в связку при заполнении плашки --------------------------------------------------------------------


@dataclass
class _Signatures:
    state: SignaturesState
    saved: int = 0

    def get_state(self, folder: Path) -> SignaturesState:
        return self.state

    def save_state(self, folder: Path, state: SignaturesState) -> None:
        self.state = state
        self.saved += 1


@dataclass
class _Keyring:
    imported: list[bytes] = field(default_factory=list)
    refuse: bool = False

    def looks_like_public_key(self, blob: bytes) -> bool:
        return True

    def import_public_key(self, blob: bytes) -> None:
        if self.refuse:
            raise GpgError("no valid OpenPGP data found")
        self.imported.append(blob)


@dataclass
class _Project:
    folder: Path = Path("/nonexistent")
    id: UUID = field(default_factory=uuid4)


@dataclass
class _Point:
    project: _Project = field(default_factory=_Project)

    @property
    def project_id(self) -> UUID:
        return self.project.id


async def _fill(
    profile_key: ProfilePublicKey | None, signer: SignerInfo, keyring: _Keyring
) -> tuple[_Signatures, _Keyring]:
    supervisor = participant(2, "supervisor", ["supervisor"])
    route = make_route([participant(1, "author", ["author"]), supervisor])
    profiles = InMemorySignerProfileRepository()
    assert supervisor.user_id is not None
    if profile_key is not None:
        await profiles.save_public_key(supervisor.user_id.hex, profile_key)
    signatures = _Signatures(_state(supervisor=_plate_slot()))
    effects = RouteFileEffects(cast(Any, signatures), cast(Any, None), profiles, keyring)

    await effects.apply(cast(RoutePoint, _Point()), route, [FillPlate("supervisor", supervisor.id, signer)], at=T0)

    return signatures, keyring


async def test__fill_plate__openpgp_key_from_the_profile__imported_into_the_keyring() -> None:
    signatures, keyring = await _fill(_profile_key(), PROFILE_SIGNER, _Keyring())

    assert signatures.state.slots["supervisor"].signer == PROFILE_SIGNER
    assert keyring.imported == [b"public key bytes"]


async def test__fill_plate__certificate_or_other_key__keyring_untouched() -> None:
    x509 = SignerInfo(kind="x509", owner="Из профиля", cert_id="0A", signer_id="CERT")
    other_key = SignerInfo(kind="openpgp", owner="Другой ключ", cert_id="9Z", signer_id="OTHER")

    _, with_certificate = await _fill(_profile_key(PublicKeyKind.x509, x509), x509, _Keyring())
    # Плашку заполнили не ключом профиля (например, подписант задал ключ сам): импортировать нечего.
    _, with_other = await _fill(_profile_key(), other_key, _Keyring())
    _, without_profile = await _fill(None, PROFILE_SIGNER, _Keyring())

    assert (with_certificate.imported, with_other.imported, without_profile.imported) == ([], [], [])


async def test__fill_plate__keyring_refuses_the_key__plate_still_filled() -> None:
    signatures, keyring = await _fill(_profile_key(), PROFILE_SIGNER, _Keyring(refuse=True))

    assert signatures.state.slots["supervisor"].signer == PROFILE_SIGNER
    assert keyring.imported == []


async def test__fill_plate__plate_already_has_a_signer__nothing_imported_or_saved() -> None:
    supervisor = participant(2, "supervisor", ["supervisor"])
    route = make_route([supervisor])
    profiles = InMemorySignerProfileRepository()
    assert supervisor.user_id is not None
    await profiles.save_public_key(supervisor.user_id.hex, _profile_key())
    signatures = _Signatures(_state(supervisor=_plate_slot(SLOT_SIGNER)))
    keyring = _Keyring()
    effects = RouteFileEffects(cast(Any, signatures), cast(Any, None), profiles, keyring)

    await effects.apply(
        cast(RoutePoint, _Point()), route, [FillPlate("supervisor", supervisor.id, PROFILE_SIGNER)], at=T0
    )

    assert (signatures.saved, keyring.imported) == (0, [])
    assert signatures.state.slots["supervisor"].signer == SLOT_SIGNER


# --- проверка ключа Студии до записи согласия -----------------------------------------------------------------------


def _identity(*, protected: bool = True, kind: SigningIdentityKind = SigningIdentityKind.openpgp) -> SigningIdentity:
    return SigningIdentity(
        id=uuid4(),
        label="Мой ключ",
        kind=kind,
        subject_cn="Петров П. П.",
        not_after=datetime(2030, 1, 1, tzinfo=UTC),
        trusted=False,
        created_at=T0,
        fingerprint="ABCDEF0123456789",
        protected=protected,
    )


@dataclass
class _DefaultKeys:
    identities: list[SigningIdentity]

    async def get(self) -> DefaultKey:
        only = self.identities[0] if len(self.identities) == 1 else None
        return DefaultKey(None, only)

    async def resolve(self, identity_id: UUID | None) -> SigningIdentity | None:
        if identity_id is None:
            return (await self.get()).effective
        found = next((i for i in self.identities if i.id == identity_id), None)
        if found is None:
            raise NotFoundError(f"Ключ подписи {identity_id} не найден")
        return found


@dataclass
class _Policy:
    allowed: bool = True

    async def server_key_storage_allowed(self) -> bool:
        return self.allowed


@dataclass
class _SigningKeyring:
    passphrase: str = "correct horse"  # noqa: S105 — тестовое значение
    attempts: list[str] = field(default_factory=list)

    def sign_detached(self, data_path: Path, fingerprint: str, out_path: Path, passphrase: str = "") -> None:
        self.attempts.append(passphrase)
        if passphrase != self.passphrase:
            raise GpgError("Bad passphrase")
        out_path.write_bytes(b"signature")


def _key_signer(
    identities: list[SigningIdentity], *, allowed: bool = True, keyring: _SigningKeyring | None = None
) -> RouteKeySigner:
    none = cast(Any, None)
    studio = StudioSigner(none, cast(Any, keyring or _SigningKeyring()), none, none, none, none, none, _Policy(allowed))
    return RouteKeySigner(none, none, none, none, studio, cast(Any, _DefaultKeys(identities)), none)


async def test__check__default_key_with_right_passphrase__ready_to_sign() -> None:
    identity = _identity()
    keyring = _SigningKeyring()

    found = await _key_signer([identity], keyring=keyring).check(KeyRequest(passphrase="correct horse"))

    assert found is identity
    # Пароль проверен пробной подписью до любых записей маршрута.
    assert keyring.attempts == ["correct horse"]


async def test__check__passphrase_missing_or_wrong__refused_with_its_own_error() -> None:
    signer = _key_signer([_identity()])

    with pytest.raises(KeyPassphraseRequiredError):
        await signer.check(KeyRequest())
    with pytest.raises(KeyPassphraseInvalidError):
        await signer.check(KeyRequest(passphrase="wrong"))


async def test__check__unprotected_or_certificate_key__no_passphrase_probe() -> None:
    keyring = _SigningKeyring()
    plain = _identity(protected=False)
    certificate = _identity(kind=SigningIdentityKind.pkcs12)

    assert await _key_signer([plain], keyring=keyring).check(KeyRequest()) is plain
    assert await _key_signer([certificate], keyring=keyring).check(KeyRequest()) is certificate
    assert keyring.attempts == []


async def test__check__foreign_key_id_or_no_key_at_all__key_not_found() -> None:
    with pytest.raises(KeyNotFoundError):
        await _key_signer([_identity()]).check(KeyRequest(identity_id=uuid4(), passphrase="correct horse"))
    with pytest.raises(NoSigningKeyError):
        await _key_signer([]).check(KeyRequest(passphrase="correct horse"))
    # Два ключа без выбранного по умолчанию: подписывать нечем, пока ключ не назван.
    with pytest.raises(KeyNotFoundError):
        await _key_signer([_identity(), _identity()]).check(KeyRequest(passphrase="correct horse"))


async def test__check__server_keys_forbidden__refused_before_looking_for_the_key() -> None:
    signer = _key_signer([_identity()], allowed=False)

    with pytest.raises(SigningKeyStorageDeniedError):
        await signer.check(KeyRequest(identity_id=uuid4(), passphrase="correct horse"))
    with pytest.raises(SigningKeyStorageDeniedError):
        await signer.own_key(uuid4())
    assert await signer.default_plate() is None
    assert await signer.keys_allowed() is False


async def test__own_key__not_the_actors_key__key_not_found() -> None:
    mine = _identity()
    signer = _key_signer([mine])

    assert await signer.own_key(mine.id) is mine
    with pytest.raises(KeyNotFoundError):
        await signer.own_key(uuid4())


# --- локальная Студия -----------------------------------------------------------------------------------------------


async def test__no_signing_routes__every_slot_is_signed_as_usual() -> None:
    gate = NoSigningRoutes()

    await gate.require_turn(uuid4(), DOC, "supervisor")
    await gate.signature_written(uuid4(), DOC, "supervisor")


# --- настоящий gpg: пробная подпись отличает неверный пароль ---------------------------------------------------------


@pytest.mark.skipif(shutil.which("gpg") is None or sys.platform == "win32", reason="нужен gpg")
@pytest.mark.timeout(120)
async def test__check__real_gpg__wrong_passphrase_refused_right_one_accepted() -> None:
    # Каталог связки короткий: путь сокета gpg-agent ограничен по длине.
    home = Path(tempfile.mkdtemp(prefix="hds-r6-", dir="/tmp"))  # noqa: S108 — короткий путь для сокета gpg-agent
    keyring = GpgKeyring(home)
    try:
        key = keyring.generate("Петров Пётр", "petrov@example.org", passphrase="correct horse")
        identity = SigningIdentity(
            id=uuid4(),
            label="Ключ OpenPGP",
            kind=SigningIdentityKind.openpgp,
            subject_cn="Петров Пётр",
            not_after=datetime(2030, 1, 1, tzinfo=UTC),
            trusted=False,
            created_at=T0,
            fingerprint=key.fingerprint,
            protected=True,
        )
        signer = _key_signer([identity], keyring=cast(Any, keyring))

        with pytest.raises(KeyPassphraseInvalidError):
            await signer.check(KeyRequest(passphrase="wrong"))
        assert await signer.check(KeyRequest(passphrase="correct horse")) is identity
    finally:
        keyring.stop_agent()
        shutil.rmtree(home, ignore_errors=True)
