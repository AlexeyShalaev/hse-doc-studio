"""Токен установки: одноразовый секрет мастера первого запуска, живёт только в памяти процесса."""

from __future__ import annotations

import hmac
import secrets

TOKEN_PREFIX = "st_"  # noqa: S105 — префикс токена, не секрет


class SetupToken:
    """Токен генерируется при старте процесса (после перезапуска печатается новый) и гасится, когда создан админ.

    Если оператор проверку отключил (сервер слушает только loopback или `SETUP_TOKEN_REQUIRED=false`),
    `required` ложно, токена нет, а `verify` пропускает любого.
    """

    def __init__(self, *, required: bool, value: str | None = None) -> None:
        self._required = required
        self._value = (value or TOKEN_PREFIX + secrets.token_urlsafe(24)) if required else None

    @property
    def required(self) -> bool:
        return self._required

    @property
    def value(self) -> str | None:
        return self._value

    def verify(self, candidate: str | None) -> bool:
        if not self._required or self._value is None:
            return True
        if not candidate:
            return False
        return hmac.compare_digest(candidate.encode("utf-8", "surrogatepass"), self._value.encode())

    def revoke(self) -> None:
        """После создания админа токен не нужен: потерянный в журнале больше ничего не открывает."""
        self._required = False
        self._value = None
