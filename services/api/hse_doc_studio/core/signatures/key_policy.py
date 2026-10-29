"""Политика серверных ключей подписи установки: разрешены ли ключи, которые хранит сервер."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

KEY_SERVER_KEYS = "signing.server_keys"


class ServerKeyPolicy(StrEnum):
    allowed = "allowed"
    forbidden = "forbidden"


def server_key_policy_from(values: Mapping[str, object]) -> ServerKeyPolicy:
    """Без записи или с непонятной записью ключи на сервере запрещены."""
    raw = values.get(KEY_SERVER_KEYS)
    try:
        return ServerKeyPolicy(raw) if isinstance(raw, str) else ServerKeyPolicy.forbidden
    except ValueError:
        return ServerKeyPolicy.forbidden
