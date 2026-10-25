"""Storage rules shared by the use cases that attach detached signatures."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import PurePosixPath

from hse_doc_studio.core.enums import DetachedOrigin
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.services import SignatureSlotService
from hse_doc_studio.core.value_objects import DetachedSignature, FrozenPdf, SignaturesState
from hse_doc_studio.infra.signatures.detached_verifier import VerifiedSignature
from hse_doc_studio.use_cases.signatures._doc_context import DETACHED_DIR, DocContext, safe_name, sha256_file


def require_slot(ctx: DocContext, slot_id: str) -> None:
    service = SignatureSlotService()
    rslot = service.find_runtime_slot(ctx.project, ctx.version, slot_id)
    if rslot is None or not service.slot_applies_to_doc(rslot, ctx.doc):
        raise NotFoundError(
            localized_error(
                f"Слот {slot_id!r} не относится к документу {ctx.doc.id!r}",
                f"Slot {slot_id!r} does not apply to document {ctx.doc.id!r}",
            )
        )


async def require_fresh_frozen(ctx: DocContext, state: SignaturesState) -> FrozenPdf:
    """The frozen PDF of the document, which must exist and match the current build."""
    frozen = state.frozen.get(ctx.doc.id)
    if frozen is None or not (ctx.project.folder / frozen.path).is_file():
        raise ValueError(
            localized_error(
                "Сначала зафиксируйте PDF на подпись",
                "Freeze the PDF for signing first",
            )
        )
    if ctx.compiled_path.is_file():
        current = await asyncio.to_thread(sha256_file, ctx.compiled_path)
        if current != frozen.source_sha256:
            raise ValueError(
                localized_error(
                    "Документ пересобран после фиксации: зафиксируйте PDF заново, прежние подписи к нему не подходят",
                    "The document was rebuilt after freezing: freeze the PDF again, earlier signatures no longer fit",
                )
            )
    return frozen


def note_plate_mismatch(state: SignaturesState, slot_id: str, verified: VerifiedSignature) -> None:
    """Flag a signature made by somebody else than the signer printed on the plate."""
    slot = state.slots.get(slot_id)
    expected = slot.signer if slot else None
    if expected and expected.signer_id and verified.signer_id and expected.signer_id != verified.signer_id:
        verified.notes.append("plate_signer_mismatch")


def store_signature(
    ctx: DocContext,
    state: SignaturesState,
    slot_id: str,
    verified: VerifiedSignature,
    sig_bytes: bytes,
    origin: DetachedOrigin,
    frozen: FrozenPdf,
) -> tuple[SignaturesState, DetachedSignature]:
    folder = ctx.project.folder
    rel = str(PurePosixPath(DETACHED_DIR) / safe_name(ctx.doc.id) / f"{safe_name(slot_id)}{verified.extension}")
    previous = state.detached.get(ctx.doc.id, {}).get(slot_id)
    if previous is not None and previous.file != rel:
        with contextlib.suppress(OSError):
            (folder / previous.file).unlink()
    target = folder / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(sig_bytes)
    sig = DetachedSignature(
        file=rel,
        format=verified.format,
        origin=origin,
        pdf_sha256=frozen.sha256,
        verdict=verified.verdict,
        signer=verified.signer,
        signer_id=verified.signer_id,
        added_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        issuer=verified.issuer,
        algorithm=verified.algorithm,
        signed_at=verified.signed_at,
        not_before=verified.not_before,
        not_after=verified.not_after,
        chain=verified.chain,
        notes=tuple(verified.notes),
    )
    doc_sigs = {**state.detached.get(ctx.doc.id, {}), slot_id: sig}
    return replace(state, detached={**state.detached, ctx.doc.id: doc_sigs}), sig
