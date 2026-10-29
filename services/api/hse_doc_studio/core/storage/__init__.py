"""Объектное хранилище: порты IObjectStore и IBlobStore без привязки к S3 или диску."""

from hse_doc_studio.core.storage.errors import (
    ChecksumMismatchError,
    InvalidObjectKeyError,
    ObjectNotFoundError,
    ObjectStoreError,
    ObjectTooLargeError,
)
from hse_doc_studio.core.storage.keys import blob_key, is_sha256, validate_key
from hse_doc_studio.core.storage.models import BlobInfo, ObjectInfo, PresignedUrl
from hse_doc_studio.core.storage.ports import IBlobStore, IObjectStore

__all__ = [
    "BlobInfo",
    "ChecksumMismatchError",
    "IBlobStore",
    "IObjectStore",
    "InvalidObjectKeyError",
    "ObjectInfo",
    "ObjectNotFoundError",
    "ObjectStoreError",
    "ObjectTooLargeError",
    "PresignedUrl",
    "blob_key",
    "is_sha256",
    "validate_key",
]
