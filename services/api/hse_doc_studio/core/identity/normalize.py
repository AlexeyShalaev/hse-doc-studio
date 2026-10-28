"""Нормализация e-mail, правила slug и генерация токенов."""

from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_EMAIL_LENGTH = 254

_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
# Имена, которые заняли бы адреса самого приложения.
RESERVED_SLUGS = frozenset(
    {
        "admin",
        "api",
        "account",
        "auth",
        "login",
        "logout",
        "register",
        "first-run",
        "settings",
        "projects",
        "org",
        "orgs",
        "me",
        "new",
        "static",
        "assets",
        "health",
        "dev",
        "runner",
        "docs",
    }
)

TOKEN_BYTES = 32
TOKEN_PREFIX_LENGTH = 8


def normalize_email(email: str) -> str:
    """Ключ уникальности: NFC, без пробелов по краям, регистр снят. Плюс-адресация сохраняется."""
    return unicodedata.normalize("NFC", email).strip().casefold()


def is_valid_email(email: str) -> bool:
    value = normalize_email(email)
    return len(value) <= MAX_EMAIL_LENGTH and _EMAIL.match(value) is not None


def email_domain(email: str) -> str:
    return normalize_email(email).rpartition("@")[2]


def normalize_domain(domain: str) -> str:
    return unicodedata.normalize("NFC", domain).strip().lstrip("@").casefold()


def is_valid_slug(slug: str) -> bool:
    return _SLUG.match(slug) is not None


def is_reserved_slug(slug: str) -> bool:
    return slug in RESERVED_SLUGS


def new_token() -> str:
    """Непрозрачный секрет на 256 бит; в хранилище уходит только `hash_token`."""
    return secrets.token_urlsafe(TOKEN_BYTES)


PAT_PREFIX = "hsd_pat_"
PAT_SECRET_LENGTH = 32
PAT_DISPLAY_LENGTH = 11


def new_pat() -> str:
    """Персональный токен доступа: опознаваемый префикс и 32 случайных символа (около 190 бит)."""
    return PAT_PREFIX + secrets.token_urlsafe(PAT_SECRET_LENGTH)[:PAT_SECRET_LENGTH]


def is_pat(token: str) -> bool:
    return token.startswith(PAT_PREFIX)


def pat_display_prefix(token: str) -> str:
    """Начало токена для списка: по нему токен узнают, но не восстановят."""
    return token[:PAT_DISPLAY_LENGTH]


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def avatar_initials(name: str, email: str = "") -> str:
    """Одна-две заглавные буквы для аватара: первые буквы первых двух слов имени, иначе первая буква e-mail."""
    words = [w for w in name.split() if w[:1].isalnum()]
    if words:
        return "".join(w[0] for w in words[:2]).upper()
    return email.strip()[:1].upper() or "?"
