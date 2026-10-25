from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.enums import SigningIdentityKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ISigningIdentityRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import SignatureSlotService
from hse_doc_studio.core.value_objects import SignatureSlot, SignerInfo
from hse_doc_studio.infra.signatures.cms_inspector import CmsParseError, describe_certificate
from hse_doc_studio.infra.signatures.openpgp import (
    GpgError,
    GpgKey,
    GpgKeyring,
    GpgUnavailableError,
    looks_like_openpgp_public_key,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()

_LEVELS = {"", "ukep", "unep"}


@dataclass
class UpdateSlotSignerInput:
    project_id: UUID
    slot_id: str
    # Exactly one source; all None clears the signer.
    certificate: bytes | None = None  # X.509 certificate or OpenPGP public key
    identity_id: UUID | None = None  # one of the Studio's own keys
    manual: SignerInfo | None = None
    # Change only the printed signature level, keeping the signer.
    level: str | None = None


@dataclass
class UpdateSlotSignerOutput:
    slot: SignatureSlot


def _openpgp_signer(key: GpgKey) -> SignerInfo:
    uid = key.uids[0] if key.uids else key.key_id
    owner = uid.split("<")[0].strip() or uid
    pretty = " ".join(key.key_id[i : i + 4] for i in range(0, len(key.key_id), 4))
    return SignerInfo(
        kind="openpgp",
        owner=owner,
        cert_id=pretty,
        valid_from=key.created.isoformat() if key.created else None,
        valid_to=key.expires.isoformat() if key.expires else None,
        signer_id=key.fingerprint,
    )


def _x509_signer(blob: bytes) -> SignerInfo:
    info = describe_certificate(blob)
    return SignerInfo(
        kind="x509",
        owner=info.owner,
        cert_id=info.serial,
        valid_from=info.not_before.isoformat(),
        valid_to=info.not_after.isoformat(),
        signer_id=info.fingerprint_sha256,
    )


class UpdateSlotSignerUC:
    """Sets who is expected to sign a slot: the data printed on the signature plate.

    The plate lives inside the PDF the signature covers, so it has to be known before
    freezing. It comes from the signer's public certificate or OpenPGP key, from one of
    the Studio's own keys, or is typed in. Later, the signature that arrives is compared
    with it.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        signing_identity_repo: ISigningIdentityRepository,
        template_repo: ITemplateRepository,
        keyring: GpgKeyring,
    ) -> None:
        self._signature_repo = signature_repo
        self._identity_repo = signing_identity_repo
        self._template_repo = template_repo
        self._keyring = keyring
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: UpdateSlotSignerInput) -> UpdateSlotSignerOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        if version is None or SignatureSlotService().find_runtime_slot(project, version, inp.slot_id) is None:
            raise NotFoundError(localized_error(f"Слот {inp.slot_id!r} не найден", f"Slot {inp.slot_id!r} not found"))
        state = self._signature_repo.get_state(project.folder)
        existing = state.slots.get(inp.slot_id) or SignatureSlot(None, None, None)
        if inp.level is not None:
            if inp.level not in _LEVELS:
                raise ValueError(localized_error("Неизвестный уровень подписи", "Unknown signature level"))
            signer = replace(existing.signer or SignerInfo(kind="manual", owner=""), level=inp.level)
        else:
            signer = await self._resolve(inp)
            # Picking another signer keeps the level chosen before.
            if signer is not None and existing.signer is not None and not signer.level:
                signer = replace(signer, level=existing.signer.level)
        new_slot = replace(existing, signer=signer)
        self._signature_repo.save_state(project.folder, replace(state, slots={**state.slots, inp.slot_id: new_slot}))
        logger.info(
            "slot signer updated", project_id=str(inp.project_id), slot_id=inp.slot_id, kind=signer and signer.kind
        )
        return UpdateSlotSignerOutput(slot=new_slot)

    async def _resolve(self, inp: UpdateSlotSignerInput) -> SignerInfo | None:  # noqa: C901
        if inp.manual is not None:
            return inp.manual
        if inp.identity_id is not None:
            identity = self._identity_repo.get(inp.identity_id)
            if identity is None:
                raise NotFoundError(localized_error("Ключ подписи не найден", "Signing key not found"))
            return await self._from_identity(identity)
        if inp.certificate is None:
            return None
        blob = inp.certificate
        if looks_like_openpgp_public_key(blob):
            try:
                keys = await asyncio.to_thread(self._keyring.import_key, blob)
            except GpgUnavailableError as exc:
                raise ValueError(localized_error("В системе нет gpg", "gpg is not installed")) from exc
            except GpgError as exc:
                raise ValueError(str(exc)) from exc
            if not keys:
                raise ValueError(localized_error("В файле нет ключа OpenPGP", "No OpenPGP key in the file"))
            return _openpgp_signer(keys[0])
        try:
            return _x509_signer(blob)
        except CmsParseError as exc:
            raise ValueError(
                localized_error(
                    "Файл не похож на сертификат X.509 (.cer, .crt, .pem) или открытый ключ OpenPGP (.asc)",
                    "The file is not an X.509 certificate (.cer, .crt, .pem) or an OpenPGP public key (.asc)",
                )
            ) from exc

    async def _from_identity(self, identity: SigningIdentity) -> SignerInfo:
        if identity.kind is SigningIdentityKind.openpgp and identity.fingerprint:
            key = await asyncio.to_thread(self._keyring.get_key, identity.fingerprint)
            if key is None:
                raise NotFoundError(
                    localized_error("Ключ OpenPGP не найден в связке", "OpenPGP key not in the keyring")
                )
            return _openpgp_signer(key)
        cert_pem = self._identity_repo.key_dir(identity.id) / "cert.pem"
        if not cert_pem.is_file():
            raise ValueError(localized_error("У ключа нет сертификата", "The key has no certificate"))
        return _x509_signer(cert_pem.read_bytes())
