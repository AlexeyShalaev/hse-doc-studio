from __future__ import annotations

import hashlib
from typing import BinaryIO

from hse_doc_studio.core.storage.ports import ObjectSource

_CHUNK = 1024 * 1024


def measure(source: ObjectSource) -> tuple[int, str]:
    """Размер и sha256 источника; файл читается от текущей позиции и возвращается на неё."""
    if isinstance(source, bytes):
        return len(source), hashlib.sha256(source).hexdigest()
    return _measure_stream(source)


def _measure_stream(stream: BinaryIO) -> tuple[int, str]:
    start = stream.tell()
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(_CHUNK):
        digest.update(chunk)
        size += len(chunk)
    stream.seek(start)
    return size, digest.hexdigest()
