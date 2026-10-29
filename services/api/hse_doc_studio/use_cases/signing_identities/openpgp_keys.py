from __future__ import annotations

import asyncio
import datetime
import uuid
from dataclasses import dataclass, field
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.enums import SigningIdentityKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISigningIdentityRepository
from hse_doc_studio.core.signatures.errors import GpgError, GpgUnavailableError
from hse_doc_studio.infra.signatures.openpgp import GpgKey, GpgKeyring

logger = structlog.get_logger()

# Keys without expiry still need a `not_after` on the identity record.
_NO_EXPIRY = datetime.datetime(9999, 12, 31, tzinfo=datetime.timezone.utc)


def _no_gpg() -> ValueError:
    return ValueError(
        localized_error(
            "В системе нет gpg (пакет gnupg): ключи OpenPGP недоступны",
            "gpg (the gnupg package) is not installed: OpenPGP keys are unavailable",
        )
    )


def _identity_for(key: GpgKey, label: str, protected: bool) -> SigningIdentity:
    return SigningIdentity(
        id=uuid.uuid4(),
        label=label,
        kind=SigningIdentityKind.openpgp,
        subject_cn=key.uids[0] if key.uids else key.key_id,
        not_after=key.expires or _NO_EXPIRY,
        trusted=False,
        created_at=datetime.datetime.now(datetime.timezone.utc),
        fingerprint=key.fingerprint,
        protected=protected,
    )


@dataclass
class CreateOpenPgpKeyInput:
    name: str
    email: str = ""
    label: str = ""
    # Empty = no passphrase: signing is one click, the key sits unprotected in the data folder.
    passphrase: str = ""


@dataclass
class CreateOpenPgpKeyOutput:
    identity: SigningIdentity


class CreateOpenPgpKeyUC:
    """Generates an ed25519 OpenPGP signing key in the Studio keyring."""

    def __init__(self, repo: ISigningIdentityRepository, keyring: GpgKeyring) -> None:
        self._repo = repo
        self._keyring = keyring

    async def execute(self, inp: CreateOpenPgpKeyInput) -> CreateOpenPgpKeyOutput:
        name = inp.name.strip()
        if not name:
            raise ValueError(localized_error("Укажите имя владельца ключа", "Enter the key owner's name"))
        try:
            key = await asyncio.to_thread(self._keyring.generate, name, inp.email.strip(), inp.passphrase)
        except GpgUnavailableError as exc:
            raise _no_gpg() from exc
        except GpgError as exc:
            raise ValueError(str(exc)) from exc
        identity = _identity_for(key, inp.label.strip() or name, protected=bool(inp.passphrase))
        await self._repo.create(identity)
        logger.info("signing_identity: openpgp key generated", id=str(identity.id), fpr=key.fingerprint)
        return CreateOpenPgpKeyOutput(identity=identity)


@dataclass
class ImportOpenPgpKeyInput:
    data: bytes
    passphrase: str = ""
    label: str = ""


@dataclass
class ImportOpenPgpKeyOutput:
    # Secret keys become identities the Studio can sign with.
    identities: list[SigningIdentity] = field(default_factory=list)
    # Public keys only: used to check other people's signatures.
    public_keys: list[GpgKey] = field(default_factory=list)


class ImportOpenPgpKeyUC:
    """Imports an armored OpenPGP key: a secret key turns into an identity, a public key just joins the keyring."""

    def __init__(self, repo: ISigningIdentityRepository, keyring: GpgKeyring) -> None:
        self._repo = repo
        self._keyring = keyring

    async def execute(self, inp: ImportOpenPgpKeyInput) -> ImportOpenPgpKeyOutput:
        if not inp.data:
            raise ValueError(localized_error("Загружен пустой файл", "Empty file upload"))
        try:
            keys = await asyncio.to_thread(self._keyring.import_key, inp.data, inp.passphrase or None)
        except GpgUnavailableError as exc:
            raise _no_gpg() from exc
        except GpgError as exc:
            raise ValueError(str(exc)) from exc

        known = {i.fingerprint for i in await self._repo.list_all() if i.kind is SigningIdentityKind.openpgp}
        out = ImportOpenPgpKeyOutput()
        for key in keys:
            if not key.has_secret:
                out.public_keys.append(key)
                continue
            if key.fingerprint in known:
                continue
            protected = await asyncio.to_thread(self._keyring.is_protected, key.fingerprint)
            label = inp.label.strip() or (key.uids[0] if key.uids else key.key_id)
            identity = _identity_for(key, label, protected)
            await self._repo.create(identity)
            out.identities.append(identity)
        logger.info(
            "openpgp key imported", identities=len(out.identities), public=len(out.public_keys), total=len(keys)
        )
        return out


@dataclass
class ExportOpenPgpPublicKeyInput:
    identity_id: UUID


@dataclass
class ExportOpenPgpPublicKeyOutput:
    armored: bytes
    file_name: str


class ExportOpenPgpPublicKeyUC:
    def __init__(self, repo: ISigningIdentityRepository, keyring: GpgKeyring) -> None:
        self._repo = repo
        self._keyring = keyring

    async def execute(self, inp: ExportOpenPgpPublicKeyInput) -> ExportOpenPgpPublicKeyOutput:
        identity = await self._repo.get(inp.identity_id)
        if identity is None or identity.kind is not SigningIdentityKind.openpgp or not identity.fingerprint:
            raise NotFoundError(localized_error("Ключ OpenPGP не найден", "OpenPGP key not found"))
        blob = await asyncio.to_thread(self._keyring.export_public, identity.fingerprint)
        return ExportOpenPgpPublicKeyOutput(armored=blob, file_name=f"public-key-{identity.fingerprint[-16:]}.asc")


@dataclass
class ListOpenPgpKeysOutput:
    keys: list[GpgKey]
    gpg_version: str | None


class ListOpenPgpKeysUC:
    """Every key in the Studio keyring (own and imported public ones) and the gpg version, if installed."""

    def __init__(self, keyring: GpgKeyring) -> None:
        self._keyring = keyring

    async def execute(self) -> ListOpenPgpKeysOutput:
        if not self._keyring.available:
            return ListOpenPgpKeysOutput(keys=[], gpg_version=None)
        keys = await asyncio.to_thread(self._keyring.list_keys)
        version = await asyncio.to_thread(self._keyring.version)
        return ListOpenPgpKeysOutput(keys=keys, gpg_version=version)
