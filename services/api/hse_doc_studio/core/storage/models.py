from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


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


class LinkAudience(StrEnum):
    """Кто пойдёт по подписанной ссылке: подпись привязана к хосту, поэтому адрес выбирается до подписи.

    `internal` это тот, кто в одной сети с сервером (раннер в кластере или в compose), `outside` это браузер и
    всё, что вне этой сети (личный раннер на ноутбуке, локальная Студия). Без публичного адреса хранилища
    `outside` получает внутренний.
    """

    internal = "internal"
    outside = "outside"
