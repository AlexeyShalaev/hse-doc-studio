"""Итоговый PDF документа по плану подписей (docs/design/signature-plan.md, разделы 4 и 8).

Итоговый файл это зафиксированный PDF B, а если на нём есть встроенные подписи PAdES, то F = B ‖ Δ1 ‖ ... .
Его отдают выгрузка «С подписями», пакет для подписанта и комплект LMS, поэтому все они видят одни и те же байты.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from hse_doc_studio.core.signatures.plan import DocFacts, frozen_is_current
from hse_doc_studio.core.signatures.stamps import legacy_stamps_digest, stamps_digest, stamps_for_doc
from hse_doc_studio.core.value_objects import FrozenPdf, SignaturesState
from hse_doc_studio.use_cases.signatures._doc_context import DocContext, sha256_file
from hse_doc_studio.use_cases.signatures._studio_signer import current_signed_file


@dataclass(frozen=True)
class FinalPdf:
    frozen: FrozenPdf
    base: Path  # B: зафиксированный PDF, открепленные подписи относятся к нему
    path: Path  # итоговый: F, если есть встроенные подписи, иначе B
    sha256: str

    @property
    def has_embedded(self) -> bool:
        return self.path != self.base


async def checked_final_pdf(folder: Path, frozen: FrozenPdf) -> FinalPdf:
    """Итоговый файл фиксации; ValueError, если F со встроенными подписями изменён вне Студии."""
    path = await current_signed_file(folder, frozen)
    sha = frozen.signed_sha256 if frozen.signed_path else frozen.sha256
    return FinalPdf(frozen=frozen, base=folder / frozen.path, path=path, sha256=sha)


async def doc_facts_of(ctx: DocContext, state: SignaturesState) -> DocFacts:
    """Сборка и видимый слой документа сейчас: то же, что план считает для этого документа."""
    folder = ctx.project.folder
    compiled = await asyncio.to_thread(sha256_file, ctx.compiled_path) if ctx.compiled_path.is_file() else None
    stamps = stamps_for_doc(state, ctx.doc.id, folder, ctx.lang)
    return DocFacts(
        compiled_sha256=compiled,
        marks_digest=stamps_digest(stamps, folder),
        legacy_marks_digest=legacy_stamps_digest(stamps),
    )


async def current_final_pdf(ctx: DocContext, state: SignaturesState) -> FinalPdf | None:
    """Итоговый файл актуальной фиксации.

    None, если фиксации нет или она устарела по плану: документ пересобран или видимый слой изменился
    (`frozen_is_current`). Тогда в плане все криптослоты ждут новой фиксации, и итогового файла у документа нет.
    """
    frozen = state.frozen.get(ctx.doc.id)
    if frozen is None or not (ctx.project.folder / frozen.path).is_file():
        return None
    if frozen_is_current(frozen, await doc_facts_of(ctx, state)) is not None:
        return None
    return await checked_final_pdf(ctx.project.folder, frozen)
