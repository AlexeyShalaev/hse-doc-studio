from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    last_modified: datetime
    sha256: str | None = None
    etag: str | None = None


@dataclass(frozen=True)
class BlobInfo:
    sha256: str
    size: int


@dataclass(frozen=True)
class PresignedUrl:
    """Короткоживущая ссылка. GET принимает заголовок Range; для PUT клиент обязан передать `headers`."""

    url: str
    expires_at: datetime
    headers: dict[str, str] = field(default_factory=dict)
