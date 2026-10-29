"""Общая проверка перед записью: размер и sha256 сверяются до того, как хранилище что-то получит."""

from __future__ import annotations

from hse_doc_studio.core.storage.errors import ChecksumMismatchError, ObjectTooLargeError
from hse_doc_studio.core.storage.hashing import measure
from hse_doc_studio.core.storage.keys import is_sha256
from hse_doc_studio.core.storage.ports import ObjectSource


def check_source(source: ObjectSource, *, max_bytes: int, expected_sha256: str | None) -> tuple[int, str]:
    """Возвращает размер и фактический sha256 или бросает отказ; блокирует поток (вызывать из to_thread)."""
    if expected_sha256 is not None and not is_sha256(expected_sha256):
        msg = "заявленный sha256 не похож на sha256"
        raise ChecksumMismatchError(msg)
    size, actual = measure(source)
    if size > max_bytes:
        msg = f"объект {size} байт больше предела {max_bytes}"
        raise ObjectTooLargeError(msg)
    if expected_sha256 is not None and actual != expected_sha256:
        msg = "sha256 данных не совпал с заявленным"
        raise ChecksumMismatchError(msg)
    return size, actual
