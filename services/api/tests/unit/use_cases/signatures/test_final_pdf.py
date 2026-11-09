"""Итоговый PDF плана: что отдают «С подписями» и пакет для подписанта (docs/design/signature-plan.md, 4 и 8)."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.signatures.stamps import legacy_stamps_digest, stamps_digest, stamps_for_doc
from hse_doc_studio.core.value_objects import FrozenPdf, SignaturePlacement, SignatureSlot, SignaturesState
from hse_doc_studio.use_cases.signatures._final_pdf import checked_final_pdf, current_final_pdf

_DOC = "annotation"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _state(folder: Path) -> SignaturesState:
    (folder / "signatures").mkdir(parents=True, exist_ok=True)
    (folder / "signatures" / "author.png").write_bytes(b"png")
    return SignaturesState(
        slots={"author": SignatureSlot("signatures/author.png", 10, 4, sign_mode=SignMode.image_crypto)},
        placements={_DOC: {"author": SignaturePlacement(enabled=True, page=1, x_mm=10, y_mm=10, width_mm=30)}},
    )


def _project(folder: Path, state: SignaturesState, *, pades: bool, digest: str | None = None) -> tuple[Any, FrozenPdf]:
    """Сборка, зафиксированный B и (по желанию) F = B ‖ Δ; контекст документа как у use case."""
    compiled = folder / "out" / "annotation.pdf"
    compiled.parent.mkdir(parents=True, exist_ok=True)
    compiled.write_bytes(b"%PDF compiled")
    base = folder / ".hse-studio" / "frozen" / "annotation.pdf"
    base.parent.mkdir(parents=True, exist_ok=True)
    base.write_bytes(b"%PDF frozen")
    stamps = stamps_for_doc(state, _DOC, folder, "ru")
    frozen = FrozenPdf(
        path=".hse-studio/frozen/annotation.pdf",
        sha256=_sha(base.read_bytes()),
        source_sha256=_sha(compiled.read_bytes()),
        size=base.stat().st_size,
        frozen_at="2026-11-09T10:00:00+00:00",
        stamps_digest=digest if digest is not None else stamps_digest(stamps, folder),
    )
    if pades:
        signed = base.with_name("annotation.signed.pdf")
        signed.write_bytes(base.read_bytes() + b"\n% PAdES revision\n")
        frozen = replace(
            frozen,
            signed_path=".hse-studio/frozen/annotation.signed.pdf",
            signed_sha256=_sha(signed.read_bytes()),
            signed_size=signed.stat().st_size,
        )
    ctx = SimpleNamespace(
        project=SimpleNamespace(folder=folder), doc=SimpleNamespace(id=_DOC), lang="ru", compiled_path=compiled
    )
    return ctx, frozen


async def test__current_final_pdf__pades_chain__returns_signed_file(tmp_path: Path) -> None:
    state = _state(tmp_path)
    ctx, frozen = _project(tmp_path, state, pades=True)

    final = await current_final_pdf(ctx, replace(state, frozen={_DOC: frozen}))

    assert final is not None
    assert final.has_embedded
    assert final.path == tmp_path / frozen.signed_path
    assert final.base == tmp_path / frozen.path
    assert final.sha256 == frozen.signed_sha256


async def test__current_final_pdf__no_pades__returns_frozen_file(tmp_path: Path) -> None:
    state = _state(tmp_path)
    ctx, frozen = _project(tmp_path, state, pades=False)

    final = await current_final_pdf(ctx, replace(state, frozen={_DOC: frozen}))

    assert final is not None
    assert not final.has_embedded
    assert (final.path, final.sha256) == (tmp_path / frozen.path, frozen.sha256)


async def test__current_final_pdf__not_frozen__none(tmp_path: Path) -> None:
    state = _state(tmp_path)
    ctx, _ = _project(tmp_path, state, pades=True)

    assert await current_final_pdf(ctx, state) is None


async def test__current_final_pdf__rebuilt_after_freeze__none(tmp_path: Path) -> None:
    state = _state(tmp_path)
    ctx, frozen = _project(tmp_path, state, pades=True)
    ctx.compiled_path.write_bytes(b"%PDF rebuilt")

    assert await current_final_pdf(ctx, replace(state, frozen={_DOC: frozen})) is None


async def test__current_final_pdf__marks_changed_after_freeze__none(tmp_path: Path) -> None:
    state = _state(tmp_path)
    ctx, frozen = _project(tmp_path, state, pades=True)
    moved = SignaturePlacement(enabled=True, page=1, x_mm=50, y_mm=10, width_mm=30)

    changed = replace(state, placements={_DOC: {"author": moved}}, frozen={_DOC: frozen})

    assert await current_final_pdf(ctx, changed) is None


async def test__current_final_pdf__legacy_digest__still_current(tmp_path: Path) -> None:
    state = _state(tmp_path)
    legacy = legacy_stamps_digest(stamps_for_doc(state, _DOC, tmp_path, "ru"))
    ctx, frozen = _project(tmp_path, state, pades=True, digest=legacy)

    final = await current_final_pdf(ctx, replace(state, frozen={_DOC: frozen}))

    assert final is not None
    assert final.has_embedded


async def test__checked_final_pdf__signed_file_tampered__value_error(tmp_path: Path) -> None:
    state = _state(tmp_path)
    _, frozen = _project(tmp_path, state, pades=True)
    signed = tmp_path / frozen.signed_path
    signed.write_bytes(signed.read_bytes() + b"% tampered\n")

    with pytest.raises(ValueError, match="изменился|changed"):
        await checked_final_pdf(tmp_path, frozen)
