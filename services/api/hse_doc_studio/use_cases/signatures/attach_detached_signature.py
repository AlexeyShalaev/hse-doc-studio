from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.enums import DetachedOrigin, DetachedVerdict
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.signatures.errors import (
    CmsParseError,
    GpgError,
    GpgUnavailableError,
    UnknownSignatureFormatError,
)
from hse_doc_studio.core.signatures.ports import IChainFetcher, IOpenPgpKeyImporter
from hse_doc_studio.core.signatures.verification import note_plate_mismatch
from hse_doc_studio.core.value_objects import DetachedSignature
from hse_doc_studio.infra.signatures.detached_verifier import DetachedSignatureVerifier
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC
from hse_doc_studio.use_cases.signatures._detached_store import (
    require_fresh_frozen,
    require_slot,
    store_signature,
)
from hse_doc_studio.use_cases.signatures._doc_context import load_doc_context

logger = structlog.get_logger()


@dataclass
class AttachDetachedSignatureInput:
    project_id: UUID
    doc_id: str
    slot_id: str
    content: bytes
    # Public key of the signer (armored OpenPGP), for a signature made with a key the keyring lacks.
    public_key: bytes | None = None


@dataclass
class AttachDetachedSignatureOutput:
    signature: DetachedSignature
    # OpenPGP: key id the signature wants, when the verdict is `unknown_key`.
    missing_key_id: str | None = None


def _import_public_key(keyring: IOpenPgpKeyImporter, blob: bytes) -> None:
    if not keyring.looks_like_public_key(blob):
        raise ValueError(
            localized_error(
                "Файл не похож на открытый ключ OpenPGP (ожидается -----BEGIN PGP PUBLIC KEY BLOCK-----)",
                "The file does not look like an OpenPGP public key (expected -----BEGIN PGP PUBLIC KEY BLOCK-----)",
            )
        )
    try:
        keyring.import_public_key(blob)
    except GpgUnavailableError as exc:
        raise ValueError(_no_gpg()) from exc
    except GpgError as exc:
        raise ValueError(str(exc)) from exc


def _no_gpg() -> str:
    return localized_error(
        "В системе нет gpg: подписи OpenPGP проверить нельзя",
        "gpg is not installed: OpenPGP signatures cannot be checked",
    )


class _DetachedUCBase:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        verifier: DetachedSignatureVerifier,
        keyring: IOpenPgpKeyImporter,
    ) -> None:
        self._signature_repo = signature_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._verifier = verifier
        self._keyring = keyring
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def _attach(
        self,
        project_id: UUID,
        doc_id: str,
        slot_id: str,
        content: bytes | None,
        public_key: bytes | None,
    ) -> AttachDetachedSignatureOutput:
        """Verify `content` (or, when None, the signature already stored for the slot) and store it."""
        ctx = await load_doc_context(self._get_uc, self._template_repo, self._template_service, project_id, doc_id)
        require_slot(ctx, slot_id)
        state = self._signature_repo.get_state(ctx.project.folder)
        if content is None:
            existing = state.detached.get(doc_id, {}).get(slot_id)
            if existing is None:
                raise NotFoundError(
                    localized_error("К слоту не приложена подпись", "No signature is attached to this slot")
                )
            content = (ctx.project.folder / existing.file).read_bytes()
        elif not content:
            raise ValueError(localized_error("Загружен пустой файл", "Empty file upload"))
        frozen = await require_fresh_frozen(ctx, state)

        if public_key:
            await asyncio.to_thread(_import_public_key, self._keyring, public_key)
        pdf_path = ctx.project.folder / frozen.path
        try:
            verified = await asyncio.to_thread(self._verifier.verify, pdf_path, content)
        except UnknownSignatureFormatError as exc:
            raise ValueError(
                localized_error(
                    "Файл не распознан как открепленная подпись (OpenPGP .asc/.sig или CMS .sig/.p7s): " + str(exc),
                    "The file is not recognised as a detached signature (OpenPGP .asc/.sig or CMS .sig/.p7s): "
                    + str(exc),
                )
            ) from exc
        except GpgUnavailableError as exc:
            raise ValueError(_no_gpg()) from exc

        verified = note_plate_mismatch(state, slot_id, verified)
        new_state, sig = store_signature(ctx, state, slot_id, verified, content, DetachedOrigin.uploaded, frozen)
        self._signature_repo.save_state(ctx.project.folder, new_state)
        logger.info(
            "detached signature attached",
            project_id=str(project_id),
            doc_id=doc_id,
            slot_id=slot_id,
            format=sig.format.value,
            verdict=sig.verdict.value,
        )
        return AttachDetachedSignatureOutput(
            signature=sig,
            missing_key_id=verified.missing_key_id if sig.verdict is DetachedVerdict.unknown_key else None,
        )


class AttachDetachedSignatureUC(_DetachedUCBase):
    """Attaches a ready-made detached signature to a (doc, slot) and checks it.

    The format (OpenPGP or CMS/CAdES) is detected from the bytes. The signature
    is stored whatever the verdict, so the user sees why it does not fit. An
    OpenPGP signature by an unknown key is kept as `unknown_key` until the
    signer's public key is supplied (here or via `RecheckDetachedSignatureUC`).
    """

    async def execute(self, inp: AttachDetachedSignatureInput) -> AttachDetachedSignatureOutput:
        return await self._attach(inp.project_id, inp.doc_id, inp.slot_id, inp.content, inp.public_key)


@dataclass
class RecheckDetachedSignatureInput:
    project_id: UUID
    doc_id: str
    slot_id: str
    public_key: bytes | None = None


class RecheckDetachedSignatureUC(_DetachedUCBase):
    """Verifies the stored signature again, optionally after importing the signer's public key."""

    async def execute(self, inp: RecheckDetachedSignatureInput) -> AttachDetachedSignatureOutput:
        return await self._attach(inp.project_id, inp.doc_id, inp.slot_id, None, inp.public_key)


@dataclass
class CompleteChainInput:
    project_id: UUID
    doc_id: str
    slot_id: str


class CompleteDetachedChainUC(_DetachedUCBase):
    """Downloads the issuer certificates the signature's certificate points to (AIA), then checks again.

    A deliberate network action, triggered by the user. What it fetches only helps build the chain.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        verifier: DetachedSignatureVerifier,
        keyring: IOpenPgpKeyImporter,
        fetcher: IChainFetcher,
    ) -> None:
        super().__init__(
            project_repo, project_index_repo, signature_repo, template_repo, template_service, verifier, keyring
        )
        self._fetcher = fetcher

    async def execute(self, inp: CompleteChainInput) -> AttachDetachedSignatureOutput:
        ctx = await load_doc_context(
            self._get_uc, self._template_repo, self._template_service, inp.project_id, inp.doc_id
        )
        existing = self._signature_repo.get_state(ctx.project.folder).detached.get(inp.doc_id, {}).get(inp.slot_id)
        if existing is None:
            raise NotFoundError(
                localized_error("К слоту не приложена подпись", "No signature is attached to this slot")
            )
        blob = (ctx.project.folder / existing.file).read_bytes()
        try:
            await asyncio.to_thread(self._fetcher.complete, blob)
        except CmsParseError as exc:
            raise ValueError(
                localized_error(
                    "Цепочку можно достраивать только для подписи CMS/CAdES", "Only CMS/CAdES signatures have a chain"
                )
            ) from exc
        return await self._attach(inp.project_id, inp.doc_id, inp.slot_id, None, None)
