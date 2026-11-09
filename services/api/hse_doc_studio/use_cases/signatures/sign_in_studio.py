from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService, SignatureSlotService
from hse_doc_studio.core.value_objects import DetachedSignature, EmbeddedSignature, FrozenPdf
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC
from hse_doc_studio.use_cases.signatures._detached_store import require_fresh_frozen, require_slot
from hse_doc_studio.use_cases.signatures._doc_context import DocContext, load_doc_context
from hse_doc_studio.use_cases.signatures._studio_signer import (
    StudioSigner,
    current_marks_digest,
    project_lock,
    signer_for_identity,
)

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


@dataclass
class SignPadesOutput:
    signature: EmbeddedSignature


class SignInStudioUC:
    """Signs the frozen PDF with a key held by the Studio.

    OpenPGP identities go through gpg (`.asc`); PKCS#12 / self-signed identities
    produce a CAdES `.p7s` (RSA / ECDSA only: GOST keys live on tokens and
    cannot be used here). `sign_pades` appends an embedded PAdES signature on top
    of the frozen bytes instead. Only the slot's own signer may sign it with a key
    (docs/design/signature-plan.md, section 5).
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        signer: StudioSigner,
    ) -> None:
        self._signature_repo = signature_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._signer = signer
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: SignInStudioInput) -> SignInStudioOutput:
        ctx, identity = await self._prepare(inp)
        async with project_lock(ctx.project):
            frozen = await self._checked_frozen(ctx, inp, identity)
            state = self._signature_repo.get_state(ctx.project.folder)
            new_state, sig = await self._signer.sign_detached(ctx, state, frozen, inp.slot_id, identity, inp.passphrase)
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

    async def sign_pades(self, inp: SignInStudioInput) -> SignPadesOutput:
        ctx, identity = await self._prepare(inp)
        async with project_lock(ctx.project):
            frozen = await self._checked_frozen(ctx, inp, identity)
            state = self._signature_repo.get_state(ctx.project.folder)
            slot = state.slots.get(inp.slot_id)
            new_state, sig = await self._signer.sign_pades(
                ctx, state, frozen, inp.slot_id, identity, slot.sign_reason if slot is not None else ""
            )
            self._signature_repo.save_state(ctx.project.folder, new_state)
        logger.info("pades signature made in studio", project_id=str(inp.project_id), doc_id=inp.doc_id)
        return SignPadesOutput(signature=sig)

    async def _prepare(self, inp: SignInStudioInput) -> tuple[DocContext, SigningIdentity]:
        identity = await self._signer.identity_repo.get(inp.identity_id)
        if identity is None:
            raise NotFoundError(
                localized_error(f"Ключ подписи {inp.identity_id} не найден", f"Signing key {inp.identity_id} not found")
            )
        await self._signer.require_key_allowed()
        ctx = await load_doc_context(
            self._get_uc, self._template_repo, self._template_service, inp.project_id, inp.doc_id
        )
        require_slot(ctx, inp.slot_id)
        return ctx, identity

    async def _checked_frozen(self, ctx: DocContext, inp: SignInStudioInput, identity: SigningIdentity) -> FrozenPdf:
        state = self._signature_repo.get_state(ctx.project.folder)
        rslot = SignatureSlotService().find_runtime_slot(ctx.project, ctx.version, inp.slot_id)
        label = (rslot.label.get(ctx.lang) or rslot.label.get("ru") or inp.slot_id) if rslot else inp.slot_id
        signer = await signer_for_identity(identity, self._signer.keyring, self._signer.identity_repo)
        await self._signer.may_sign(ctx.project, state, inp.slot_id, label, signer, explicit=True)
        frozen = await require_fresh_frozen(ctx, state)
        if frozen.stamps_digest and current_marks_digest(ctx, state) != frozen.stamps_digest:
            raise ValueError(
                localized_error(
                    "Картинки или плашки изменились после фиксации: зафиксируйте PDF заново",
                    "Images or plates changed after freezing: freeze the PDF again",
                )
            )
        return frozen
