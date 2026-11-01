"""Политика паролей: длина, совпадение с e-mail, список частых паролей."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import normalize_email

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 256

_COMMON_FILE = Path(__file__).with_name("common_passwords.txt")


@cache
def common_passwords() -> frozenset[str]:
    lines = _COMMON_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip().casefold() for line in lines if line.strip() and not line.startswith("#"))


def password_problem(password: str, email: str | None = None) -> str | None:
    """Первая причина отказа или None. Правил состава нет: только длина и очевидные пароли."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return "too_short"
    if len(password) > PASSWORD_MAX_LENGTH:
        return "too_long"
    folded = password.casefold()
    if email and folded == normalize_email(email):
        return "equals_email"
    if folded in common_passwords():
        return "common"
    return None


def check_password(password: str, email: str | None = None) -> None:
    if password_problem(password, email) is not None:
        raise IdentityError(IdentityErrorCode.password_policy)
