"""Якоря источника подписи документа (docs/design/signing-route.md, 15.17.4, 15.17.6).

Сборка оставляет `.build/<doc_id>/<stem>.anchors.json` рядом со своим файлом позиций; версия на подписи хранит
копию якорей своей сборки в `.hse-studio/frozen/<doc>.source.anchors.json`. Якоря известны, только если их
`pdf_sha256` равен sha256 источника подписи: версии на подписи, если она есть, иначе текущей сборки. Другой PDF
(сборка раннером прежней версии, PDF из локальной Студии, свой загруженный PDF) значит «якоря неизвестны».
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import stat
from pathlib import Path, PurePosixPath

from hse_doc_studio.core.signatures.anchors import (
    ANCHORS_SUFFIX,
    MAX_ANCHORS_JSON_BYTES,
    BuildAnchors,
    decode_anchors,
)
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.use_cases.signatures._doc_context import sha256_file
from hse_doc_studio.use_cases.signatures.signing_source import pinned_anchors_file, pinned_file

BUILD_DIR = ".build"


def build_anchors_rel(source_file: str, doc_id: str) -> str:
    """Где сборка оставляет якоря, от корня проекта: `<каталог исходника>/.build/<doc_id>/<stem>.anchors.json`."""
    source = PurePosixPath(source_file.replace("\\", "/"))
    return (source.parent / BUILD_DIR / doc_id / f"{source.stem}{ANCHORS_SUFFIX}").as_posix()


def read_anchors(path: Path | None) -> BuildAnchors | None:
    """`anchors.json` по пути; None, если файла нет, это не обычный файл или он не той формы."""
    if path is None:
        return None
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            return None
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            raw = handle.read(MAX_ANCHORS_JSON_BYTES + 1)
    except OSError:
        return None
    return decode_anchors(raw)


async def anchors_for(anchors_file: Path | None, pdf: Path | None) -> BuildAnchors | None:
    """Якоря из файла, если они от этого PDF; PDF хэшируется, только когда якоря есть."""
    anchors = await asyncio.to_thread(read_anchors, anchors_file)
    if anchors is None or pdf is None:
        return None
    try:
        digest = await asyncio.to_thread(sha256_file, pdf)
    except OSError:
        return None
    return anchors if anchors.of(digest) else None


async def source_anchors(
    folder: Path,
    state: SignaturesState,
    doc_id: str,
    *,
    compiled: Path | None,
    source_file: str | None,
) -> BuildAnchors | None:
    """Якоря источника подписи документа; None, если они неизвестны.

    `compiled` путь PDF, который подписывают без версии на подписи (`resolve_signing_output`: сборка или свой
    загруженный файл), `source_file` главный файл документа от корня проекта (None: сборки у документа не бывает).
    """
    pinned = state.pinned.get(doc_id)
    if pinned is not None:
        return await anchors_for(pinned_anchors_file(folder, pinned), pinned_file(folder, pinned))
    if source_file is None or compiled is None:
        return None
    return await anchors_for(folder / build_anchors_rel(source_file, doc_id), compiled)


def drop_anchors_file(path: Path | None) -> None:
    if path is not None:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)
