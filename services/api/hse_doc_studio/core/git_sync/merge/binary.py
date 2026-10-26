"""Бинарные файлы: побеждает более новая версия, проигравшая остаётся рядом копией.

«Новее» определяют по последнему коммиту, тронувшему путь с каждой стороны: время коммита,
затем хеш коммита, затем хеш содержимого. Итог не зависит от того, какая сторона «моя»,
поэтому на обеих машинах побеждает одна и та же версия и создаётся один и тот же файл.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath

from hse_doc_studio.core.git_sync.merge.entities import MergeSide
from hse_doc_studio.core.git_sync.protocols import MergeMeta

# Подписанные PDF лежат в этих каталогах: это юридические файлы, их не пересобрать.
_SIGNATURE_DIRS = (".hse-studio/frozen/", ".hse-studio/detached/")


@dataclass(frozen=True)
class BinaryOutcome:
    winner: MergeSide
    copy_path: str | None
    copy_content: bytes | None


def blob_sha(content: bytes) -> str:
    """Хеш содержимого так, как его считает git для блоба."""
    return hashlib.sha1(b"blob %d\0" % len(content) + content, usedforsecurity=False).hexdigest()  # noqa: S324


def is_derived_pdf(path: str) -> bool:
    """PDF, который собирается из исходников: копия проигравшей версии не нужна."""
    return path.lower().endswith(".pdf") and not path.startswith(_SIGNATURE_DIRS)


def conflict_copy_name(path: str, loser: bytes) -> str:
    """Имя копии зависит только от пути и содержимого: `figure.png` → `figure.conflict-3fa9c1d.png`."""
    posix = PurePosixPath(path)
    return str(posix.with_name(f"{posix.stem}.conflict-{blob_sha(loser)[:7]}{posix.suffix}"))


def _stamp(changed_at: datetime | None, commit: str | None, content: bytes) -> tuple[float, str, bytes]:
    if changed_at is None:
        moment = float("-inf")
    else:
        moment = (changed_at if changed_at.tzinfo else changed_at.replace(tzinfo=UTC)).timestamp()
    return moment, commit or "", hashlib.sha256(content).digest()


def newest_side(ours: bytes, theirs: bytes, meta: MergeMeta) -> MergeSide:
    ours_stamp = _stamp(meta.ours_changed_at, meta.ours_commit, ours)
    theirs_stamp = _stamp(meta.theirs_changed_at, meta.theirs_commit, theirs)
    return MergeSide.ours if ours_stamp > theirs_stamp else MergeSide.theirs


def merge_binary(path: str, ours: bytes, theirs: bytes, meta: MergeMeta) -> BinaryOutcome:
    """Победитель и копия проигравшего; для собираемого PDF копии нет."""
    winner = newest_side(ours, theirs, meta)
    if is_derived_pdf(path):
        return BinaryOutcome(winner, None, None)
    loser = theirs if winner is MergeSide.ours else ours
    return BinaryOutcome(winner, conflict_copy_name(path, loser), loser)
