"""Помощники кода устройства (device code): общий для раннеров и для входа локальной Студии в git сервера.

Устройство получает длинный секрет с префиксом вида (`hsdc_` у раннеров, `hsdv_` у git), человек вводит
короткий код `XXXX-XXXX` из алфавита без похожих символов.
"""

from __future__ import annotations

import re
import secrets

USER_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ23456789"
USER_CODE_HALF = 4
_USER_CODE_RE = re.compile(rf"^[{USER_CODE_ALPHABET}]{{{USER_CODE_HALF * 2}}}$")


def new_user_code() -> str:
    raw = "".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(USER_CODE_HALF * 2))
    return f"{raw[:USER_CODE_HALF]}-{raw[USER_CODE_HALF:]}"


def normalize_user_code(value: str) -> str | None:
    """Ввод без учёта регистра, пробелов и дефиса; негодный код даёт None."""
    raw = re.sub(r"[\s-]", "", value).upper()
    if not _USER_CODE_RE.match(raw):
        return None
    return f"{raw[:USER_CODE_HALF]}-{raw[USER_CODE_HALF:]}"


def new_device_secret(prefix: str) -> str:
    """Секрет устройства: префикс вида и 32 случайных байта."""
    return prefix + secrets.token_urlsafe(32)
