"""Источник подписи: версия на подписи маршрута, иначе текущая сборка (docs/design/signing-route.md, 12.4)."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from hse_doc_studio.core.signatures.plan import DocFacts, PlanReason, reason_hint
from hse_doc_studio.core.signatures.stamps import stamps_digest, stamps_for_doc
from hse_doc_studio.core.value_objects import FrozenPdf, PinnedPdf, SignaturesState
from hse_doc_studio.use_cases.signatures._final_pdf import current_final_pdf, doc_facts_of
from hse_doc_studio.use_cases.signatures.signing_source import (
    pinned_file,
    pinned_rel,
    signing_source,
    source_and_working,
)

_DOC = "annotation"
_COMPILED = b"%PDF working build"
_SENT = b"%PDF version sent for signing"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ctx(folder: Path, *, built: bool = True) -> Any:
    compiled = folder / "out" / "annotation.pdf"
    if built:
        compiled.parent.mkdir(parents=True, exist_ok=True)
        compiled.write_bytes(_COMPILED)
    return SimpleNamespace(
        project=SimpleNamespace(folder=folder), doc=SimpleNamespace(id=_DOC), lang="ru", compiled_path=compiled
    )


def _pin(folder: Path, data: bytes = _SENT, *, write: bool = True) -> SignaturesState:
    rel = pinned_rel(_DOC)
    if write:
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_bytes(data)
    pinned = PinnedPdf(rel, _sha(data), len(data), "2026-11-10T14:32:00+00:00", "route-1", 1)
    return replace(SignaturesState.empty(), pinned={_DOC: pinned})


def test__pinned_rel__next_to_the_frozen_pdf() -> None:
    assert pinned_rel(_DOC) == ".hse-studio/frozen/annotation.source.pdf"
    assert pinned_rel("a/b") == ".hse-studio/frozen/a_b.source.pdf"


@pytest.mark.parametrize("path", ["../outside.pdf", "/etc/passwd", "main.pdf", ".hse-studio/frozen/../../x.pdf"])
def test__pinned_file__path_outside_the_frozen_folder__is_ignored(tmp_path: Path, path: str) -> None:
    assert pinned_file(tmp_path, PinnedPdf(path, "s", 1, "t")) is None


async def test__signing_source__without_pinned__is_the_current_build(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)

    source = await signing_source(ctx, SignaturesState.empty())

    assert (source.path, source.sha256, source.pinned) == (ctx.compiled_path, _sha(_COMPILED), None)


async def test__signing_source__with_pinned__is_the_version_sent_for_signing(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    state = _pin(tmp_path)

    source, working = await source_and_working(tmp_path, ctx.compiled_path, state, _DOC)

    assert source.path == tmp_path / pinned_rel(_DOC)
    assert source.sha256 == _sha(_SENT)
    assert source.pinned == state.pinned[_DOC]
    assert working == _sha(_COMPILED)


async def test__signing_source__hash_is_taken_from_the_file_not_the_record(tmp_path: Path) -> None:
    """Подмену версии на подписи мимо маршрута видно по хэшу файла (12.5)."""
    state = _pin(tmp_path)
    (tmp_path / pinned_rel(_DOC)).write_bytes(b"%PDF replaced")

    source = await signing_source(_ctx(tmp_path), state)

    assert source.sha256 == _sha(b"%PDF replaced")


async def test__signing_source__pinned_file_missing__no_fallback_to_the_build(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)

    source = await signing_source(ctx, _pin(tmp_path, write=False))

    assert source.pinned is not None
    assert not source.exists


async def test__doc_facts__pinned__compiled_is_the_source_and_working_differs(tmp_path: Path) -> None:
    facts = await doc_facts_of(_ctx(tmp_path), _pin(tmp_path))

    assert (facts.compiled_sha256, facts.working_sha256) == (_sha(_SENT), _sha(_COMPILED))
    assert facts.working_differs


async def test__doc_facts__pinned_equal_to_the_build__no_changes(tmp_path: Path) -> None:
    facts = await doc_facts_of(_ctx(tmp_path), _pin(tmp_path, _COMPILED))

    assert facts.compiled_sha256 == facts.working_sha256 == _sha(_COMPILED)
    assert not facts.working_differs


async def test__doc_facts__pinned_and_not_built__source_is_still_there(tmp_path: Path) -> None:
    facts = await doc_facts_of(_ctx(tmp_path, built=False), _pin(tmp_path))

    assert (facts.compiled_sha256, facts.working_sha256) == (_sha(_SENT), None)
    assert not facts.working_differs


async def test__doc_facts__without_pinned__working_is_the_build(tmp_path: Path) -> None:
    facts = await doc_facts_of(_ctx(tmp_path), SignaturesState.empty())

    assert facts.compiled_sha256 == facts.working_sha256 == _sha(_COMPILED)
    assert not facts.working_differs


def test__doc_facts__built_by_hand_without_working__never_differs() -> None:
    assert not DocFacts(compiled_sha256="a", marks_digest="").working_differs
    assert DocFacts(compiled_sha256="a", marks_digest="", working_sha256="b").working_differs
    assert not DocFacts(compiled_sha256=None, marks_digest="", working_sha256=None).working_differs


def _frozen_from(folder: Path, state: SignaturesState, source: bytes) -> FrozenPdf:
    base = folder / ".hse-studio" / "frozen" / "annotation.pdf"
    base.parent.mkdir(parents=True, exist_ok=True)
    base.write_bytes(b"%PDF frozen")
    return FrozenPdf(
        path=".hse-studio/frozen/annotation.pdf",
        sha256=_sha(base.read_bytes()),
        source_sha256=_sha(source),
        size=base.stat().st_size,
        frozen_at="2026-11-10T15:00:00+00:00",
        stamps_digest=stamps_digest(stamps_for_doc(state, _DOC, folder, "ru"), folder),
    )


async def test__current_final_pdf__frozen_from_the_pinned_version__stays_current_after_a_rebuild(
    tmp_path: Path,
) -> None:
    """Рабочая сборка новее версии на подписи: итоговый файл остаётся (12.4)."""
    state = _pin(tmp_path)
    state = replace(state, frozen={_DOC: _frozen_from(tmp_path, state, _SENT)})

    final = await current_final_pdf(_ctx(tmp_path), state)

    assert final is not None
    assert final.path == tmp_path / ".hse-studio/frozen/annotation.pdf"


async def test__current_final_pdf__frozen_from_the_build_but_a_new_version_is_pinned__outdated(
    tmp_path: Path,
) -> None:
    """B сделан из прежней версии, отправлена новая: итогового файла нет, пока новую не зафиксируют."""
    state = _pin(tmp_path)
    state = replace(state, frozen={_DOC: _frozen_from(tmp_path, state, _COMPILED)})

    assert await current_final_pdf(_ctx(tmp_path), state) is None


def test__reason_hint__rebuilt_of_a_pinned_document__waits_for_the_new_version() -> None:
    assert reason_hint(PlanReason.rebuilt, pinned=True) == "Ждёт фиксации новой версии"
    assert reason_hint(PlanReason.rebuilt).startswith("Документ пересобран")
    assert reason_hint(PlanReason.not_frozen, pinned=True) == reason_hint(PlanReason.not_frozen)
