"""Storage rules shared by the use cases that attach detached signatures."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import PurePosixPath
from uuid import uuid4

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import DetachedOrigin
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.jobs.entities import JobSpec, job_tags
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.files import InlineBlob, ManifestFile
from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.jobs.verify import (
    CODE_GPG_UNAVAILABLE,
    CODE_UNKNOWN_SIGNATURE_FORMAT,
    VerifyDetachedPayload,
    VerifyDetachedResult,
)
from hse_doc_studio.core.services import SignatureSlotService
from hse_doc_studio.core.signatures.ports import ITrustMaterialProvider
from hse_doc_studio.core.signatures.verification import VerifiedSignature
from hse_doc_studio.core.value_objects import DetachedSignature, FrozenPdf, SignaturesState
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


def no_gpg_message() -> str:
    return localized_error(
        "В системе нет gpg: подписи OpenPGP проверить нельзя",
        "gpg is not installed: OpenPGP signatures cannot be checked",
    )


async def verify_frozen(
    dispatcher: IJobDispatcher,
    trust_provider: ITrustMaterialProvider,
    ctx: DocContext,
    frozen: FrozenPdf,
    content: bytes,
) -> VerifiedSignature:
    """Проверяет подпись замороженного PDF задачей signature.verify_detached.

    Обработчик отвечает кодами, тексты для пользователя собирает этот помощник. Вердикт
    invalid и unknown_key штатный результат, а не ошибка.
    """
    payload = VerifyDetachedPayload(
        pdf=ManifestFile(frozen.path, sha256=frozen.sha256),
        signature=InlineBlob.from_bytes(content),
        trust=await asyncio.to_thread(trust_provider.snapshot),
    )
    spec = JobSpec(
        id=uuid4(),
        kind=JobKind.verify_detached,
        tags=job_tags(JobKind.verify_detached, payload),
        project_id=ctx.project.id,
        actor=current_actor() or Actor.local(),
        locale=current_interface_language(),
        payload=payload,
        local_root=ctx.project.folder,
    )
    result = await dispatcher.run(spec)
    error = result.error
    if error is not None and error.code == CODE_UNKNOWN_SIGNATURE_FORMAT:
        raise ValueError(
            localized_error(
                "Файл не распознан как открепленная подпись (OpenPGP .asc/.sig или CMS .sig/.p7s): " + error.detail,
                "The file is not recognised as a detached signature (OpenPGP .asc/.sig or CMS .sig/.p7s): "
                + error.detail,
            )
        )
    if error is not None and error.code == CODE_GPG_UNAVAILABLE:
        raise ValueError(no_gpg_message())
    result.raise_for_error()
    return result.data_as(VerifyDetachedResult).signature


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
        root_subject=verified.root_subject,
        root_fingerprint=verified.root_fingerprint,
        notes=verified.notes,
    )
    doc_sigs = {**state.detached.get(ctx.doc.id, {}), slot_id: sig}
    return replace(state, detached={**state.detached, ctx.doc.id: doc_sigs}), sig
