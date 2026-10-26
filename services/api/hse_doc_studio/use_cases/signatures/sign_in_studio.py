from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.enums import DetachedOrigin, SigningIdentityKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ISigningIdentityRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.signatures.errors import GpgError, GpgUnavailableError
from hse_doc_studio.core.signatures.verification import note_plate_mismatch
from hse_doc_studio.core.value_objects import DetachedSignature
from hse_doc_studio.infra.signatures.cades_signer import sign_detached as sign_cades
from hse_doc_studio.infra.signatures.detached_verifier import DetachedSignatureVerifier
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC
from hse_doc_studio.use_cases.signatures._detached_store import (
    require_fresh_frozen,
    require_slot,
    store_signature,
)
from hse_doc_studio.use_cases.signatures._doc_context import load_doc_context

logger = structlog.get_logger()


@dataclass
class SignInStudioInput:
    project_id: UUID
    doc_id: str
    slot_id: str
    identity_id: UUID
    passphrase: str = ""


@dataclass
class SignInStudioOutput:
    signature: DetachedSignature


class SignInStudioUC:
    """Signs the frozen PDF with a key held by the Studio.

    OpenPGP identities go through gpg (`.asc`); PKCS#12 / self-signed identities
    produce a CAdES `.p7s` (RSA / ECDSA only: GOST keys live on tokens and
    cannot be used here).
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        signing_identity_repo: ISigningIdentityRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        verifier: DetachedSignatureVerifier,
        keyring: GpgKeyring,
    ) -> None:
        self._signature_repo = signature_repo
        self._identity_repo = signing_identity_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._verifier = verifier
        self._keyring = keyring
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: SignInStudioInput) -> SignInStudioOutput:
        identity = self._identity_repo.get(inp.identity_id)
        if identity is None:
            raise NotFoundError(
                localized_error(f"Ключ подписи {inp.identity_id} не найден", f"Signing key {inp.identity_id} not found")
            )
        ctx = await load_doc_context(
            self._get_uc, self._template_repo, self._template_service, inp.project_id, inp.doc_id
        )
        require_slot(ctx, inp.slot_id)
        state = self._signature_repo.get_state(ctx.project.folder)
        frozen = await require_fresh_frozen(ctx, state)
        pdf_path = ctx.project.folder / frozen.path

        sig_bytes = await asyncio.to_thread(self._sign, identity, pdf_path, inp.passphrase)
        verified = await asyncio.to_thread(self._verifier.verify, pdf_path, sig_bytes)
        verified = note_plate_mismatch(state, inp.slot_id, verified)
        new_state, sig = store_signature(ctx, state, inp.slot_id, verified, sig_bytes, DetachedOrigin.studio, frozen)
        self._signature_repo.save_state(ctx.project.folder, new_state)
        logger.info(
            "detached signature made in studio",
            project_id=str(inp.project_id),
            doc_id=inp.doc_id,
            slot_id=inp.slot_id,
            kind=identity.kind.value,
            verdict=sig.verdict.value,
        )
        return SignInStudioOutput(signature=sig)

    def _sign(self, identity: SigningIdentity, pdf_path: Path, passphrase: str) -> bytes:  # noqa: C901
        if identity.kind is SigningIdentityKind.openpgp:
            if not identity.fingerprint:
                raise ValueError(localized_error("У ключа нет отпечатка", "The key has no fingerprint"))
            if identity.protected and not passphrase:
                raise ValueError(
                    localized_error(
                        "Ключ защищён паролем: введите пароль", "The key is passphrase-protected: enter the passphrase"
                    )
                )
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "sig.asc"
                try:
                    self._keyring.sign_detached(pdf_path, identity.fingerprint, out, passphrase=passphrase)
                except GpgUnavailableError as exc:
                    raise ValueError(localized_error("В системе нет gpg", "gpg is not installed")) from exc
                except GpgError as exc:
                    raise ValueError(
                        localized_error(f"gpg отказал в подписи: {exc}", f"gpg refused to sign: {exc}")
                    ) from exc
                return out.read_bytes()
        if identity.kind in (SigningIdentityKind.self_signed, SigningIdentityKind.pkcs12):
            key_dir = self._identity_repo.key_dir(identity.id)
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "sig.p7s"
                try:
                    sign_cades(pdf_path, out, key_dir)
                except ValueError as exc:
                    raise ValueError(localized_error(f"Не удалось подписать: {exc}", f"Signing failed: {exc}")) from exc
                return out.read_bytes()
        raise ValueError(
            localized_error(
                "Этим ключом нельзя подписать в Студии. Подпишите файл в КриптоАРМ/КриптоПро и загрузите подпись",
                "This key cannot sign inside the Studio. Sign the file in CryptoARM/CryptoPro and upload the signature",
            )
        )
