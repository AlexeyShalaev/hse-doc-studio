"""Источник подписи документа (docs/design/signing-route.md, 12.4).

Правило одно: источник подписи это версия на подписи (`SignaturesState.pinned`), если она есть, иначе текущая
сборка. Его штампует фиксация, по нему считаются план, «С подписями» и итоговый файл. Рабочая сборка нужна
только для показа «есть изменения после отправки на подпись» (`working_sha256`).

Версию на подписи пишут сценарии маршрута (снятие при отправке и новой версии, R16) и снимает «Подписывать
текущую сборку» (`UnpinPdfUC`). Файл лежит рядом с зафиксированным PDF: `.hse-studio/frozen/<doc>.source.pdf`
(`pinned_rel`).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.value_objects import PinnedPdf, SignaturesState
from hse_doc_studio.use_cases.signatures._doc_context import FROZEN_DIR, DocContext, safe_name, sha256_file

PINNED_SUFFIX = ".source.pdf"


def pinned_rel(doc_id: str) -> str:
    """Где лежит версия на подписи документа, относительно папки проекта."""
    return str(PurePosixPath(FROZEN_DIR) / f"{safe_name(doc_id)}{PINNED_SUFFIX}")


def pinned_file(folder: Path, pinned: PinnedPdf) -> Path | None:
    """Файл версии на подписи; None, если путь из состояния ведёт за пределы `.hse-studio/frozen`.

    Состояние подписей приходит и через git: путь из него не должен указывать на произвольный файл проекта.
    """
    rel = PurePosixPath(pinned.path)
    if rel.is_absolute() or ".." in rel.parts or not rel.is_relative_to(FROZEN_DIR):
        return None
    return folder / rel


@dataclass(frozen=True)
class SigningSource:
    """Что подписывают: файл и его sha256 (None, если файла нет), и версия на подписи, если источник она."""

    path: Path | None
    sha256: str | None
    pinned: PinnedPdf | None = None

    @property
    def exists(self) -> bool:
        return self.sha256 is not None


async def _hash(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return await asyncio.to_thread(sha256_file, path)


async def source_of(folder: Path, compiled: Path | None, state: SignaturesState, doc_id: str) -> SigningSource:
    """Источник подписи документа по папке проекта и пути его сборки (`compiled`, None: сборки не бывает).

    Хэш считается по файлу на диске, а не берётся из записи: подмену версии на подписи мимо маршрута видно по
    нему (12.5). Версия на подписи, файла которой нет, остаётся источником без хэша: подписывать вместо неё
    текущую сборку значило бы подписать то, чего никто не согласовывал.
    """
    pinned = state.pinned.get(doc_id)
    if pinned is None:
        return SigningSource(path=compiled, sha256=await _hash(compiled))
    path = pinned_file(folder, pinned)
    return SigningSource(path=path, sha256=await _hash(path), pinned=pinned)


async def source_and_working(
    folder: Path, compiled: Path | None, state: SignaturesState, doc_id: str
) -> tuple[SigningSource, str | None]:
    """Источник подписи и sha256 текущей сборки (None, если не собрана). Без версии на подписи это один файл."""
    source = await source_of(folder, compiled, state, doc_id)
    if source.pinned is None:
        return source, source.sha256
    return source, await _hash(compiled)


async def signing_source(ctx: DocContext, state: SignaturesState) -> SigningSource:
    """Источник подписи документа контекста: версия на подписи или текущая сборка."""
    return await source_of(ctx.project.folder, ctx.compiled_path, state, ctx.doc.id)


def missing_source_message(ctx: DocContext, source: SigningSource) -> str:
    """Почему подписывать нечего: нет файла версии на подписи или документ не собран."""
    if source.pinned is not None:
        return localized_error(
            f"Версия на подписи не найдена: {source.pinned.path}. Отправьте новую версию или подписывайте "
            "текущую сборку",
            f"The version sent for signing is missing: {source.pinned.path}. Send a new version or sign the "
            "current build",
        )
    return localized_error(
        f"Собранный PDF не найден: {ctx.compiled_path.name}. Сначала соберите документ",
        f"Compiled PDF not found: {ctx.compiled_path.name}. Build the document first",
    )
