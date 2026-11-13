"""Якоря сборки на диске: файл позиций TeX в `.build/<doc_id>/` и его перевод в `anchors.json` (signing-route, 15.17).

Макросы `\\hseSignAnchor` и `\\hseDateAnchor` (эталон в `tex/anchors.tex` рядом с этим модулем, в пак его кладёт
`common/anchors.tex`) пишут `<stem>.hsepos` в каталог сборки. Этот файл переживает сборку, в которой его не
пишут: шаблон перестал подключать макросы, а прежний файл остался. Поэтому свежесть проверяется по `<stem>.fls`
(latexmk всегда зовёт движок с `-recorder`): файл позиций свежий, только если последний проход TeX его открыл на
запись. Удалять файл перед сборкой нельзя: пересборка без правок у xelatex перезапускает только xdvipdfmx, и
позиции прошлого прохода TeX это и есть позиции нового PDF.

Сбой здесь сборку не роняет: якоря становятся неизвестны (`anchors.json` удаляется), и это видно в журнале.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import stat
from pathlib import Path, PurePosixPath
from uuid import uuid4

import structlog
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from hse_doc_studio.core.jobs.artifacts import PositionsSource
from hse_doc_studio.core.signatures.anchors import (
    ANCHORS_SUFFIX,
    MAX_POSITIONS_BYTES,
    POSITIONS_SUFFIX,
    BuildAnchors,
    PdfPage,
    PositionsFormatError,
    bp_to_mm,
    encode_anchors,
    parse_positions,
)

logger = structlog.get_logger()

RECORDER_SUFFIX = ".fls"
# `.fls` большого документа с пакетами занимает сотни КБ; читать дальше незачем.
_MAX_RECORDER_BYTES = 8 * 1024 * 1024
_HASH_CHUNK = 1 << 20


def positions_path(build_dir: Path, stem: str) -> Path:
    return build_dir / f"{stem}{POSITIONS_SUFFIX}"


def anchors_path(build_dir: Path, stem: str) -> Path:
    return build_dir / f"{stem}{ANCHORS_SUFFIX}"


def fresh_positions(build_dir: Path, stem: str) -> Path | None:
    """Файл позиций, если его записал последний проход TeX этой сборки; иначе None."""
    path = positions_path(build_dir, stem)
    if not _regular(path) or not _recorded(build_dir / f"{stem}{RECORDER_SUFFIX}", path.name):
        return None
    return path


def publish_anchors(build_dir: Path, stem: str, pdf: Path, source: PositionsSource) -> BuildAnchors | None:
    """Пишет `<stem>.anchors.json` по файлу позиций и опубликованному PDF; None, если якоря неизвестны.

    Неизвестны они, когда файла позиций нет или он не от этой сборки, PDF не читается или файл позиций непригоден
    целиком: тогда прежний `anchors.json` удаляется, чтобы не выдать якоря прошлой сборки за якоря новой.
    """
    target = anchors_path(build_dir, stem)
    try:
        anchors = _anchors(build_dir, stem, pdf, source)
    except (OSError, PyPdfError, ValueError, KeyError, TypeError) as exc:
        logger.warning("build anchors not read", pdf=pdf.name, exc=repr(exc))
        anchors = None
    if source is PositionsSource.absent:
        # Чужой для этой сборки файл позиций не нужен и следующей: удаляем, чтобы его никто не принял за свежий.
        _unlink(positions_path(build_dir, stem))
    if anchors is None:
        _unlink(target)
        return None
    try:
        _write_atomic(target, encode_anchors(anchors))
    except OSError as exc:
        logger.warning("build anchors not written", pdf=pdf.name, exc=repr(exc))
        _unlink(target)
        return None
    if anchors.problems or anchors.duplicates:
        logger.info(
            "build anchors with problems",
            pdf=pdf.name,
            problems=list(anchors.problem_codes()),
            duplicates=list(anchors.duplicates),
        )
    return anchors


def _anchors(build_dir: Path, stem: str, pdf: Path, source: PositionsSource) -> BuildAnchors | None:
    match source:
        case PositionsSource.absent:
            return None
        case PositionsSource.tex:
            path = fresh_positions(build_dir, stem)
        case PositionsSource.runner:
            candidate = positions_path(build_dir, stem)
            path = candidate if _regular(candidate) else None
    if path is None:
        return None
    raw = _read_limited(path, MAX_POSITIONS_BYTES + 1)
    pdf_sha256 = _sha256(pdf)
    try:
        return parse_positions(raw, pdf_pages(pdf), pdf_sha256)
    except PositionsFormatError as exc:
        logger.warning("build positions file rejected", pdf=pdf.name, code=exc.code)
        return None


def pdf_pages(pdf: Path) -> tuple[PdfPage, ...]:
    """Размеры (`MediaBox`, мм) и поворот страниц PDF."""
    reader = PdfReader(pdf)
    pages: list[PdfPage] = []
    for page in reader.pages:
        box = page.mediabox
        pages.append(
            PdfPage(
                width_mm=bp_to_mm(abs(float(box.width))),
                height_mm=bp_to_mm(abs(float(box.height))),
                rotate=int(page.rotation or 0),
            )
        )
    return tuple(pages)


def _recorded(recorder: Path, name: str) -> bool:
    """Последний проход TeX открывал `name` на запись: в `.fls` есть строка `OUTPUT <путь>/<name>`."""
    if not _regular(recorder):
        return False
    try:
        raw = _read_limited(recorder, _MAX_RECORDER_BYTES)
    except OSError:
        return False
    for line in raw.decode("utf-8", errors="replace").splitlines():
        kind, _, path = line.partition(" ")
        if kind == "OUTPUT" and PurePosixPath(path.strip().replace("\\", "/")).name == name:
            return True
    return False


def _regular(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def _read_limited(path: Path, limit: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as handle:
        return handle.read(limit)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _write_atomic(target: Path, data: bytes) -> None:
    temp = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temp.write_bytes(data)
        os.replace(temp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            temp.unlink(missing_ok=True)
        raise


def _unlink(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)
