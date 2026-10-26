"""Правила имени и e-mail автора коммита: одни и те же для профиля и для актора запроса."""

from __future__ import annotations

import re
import unicodedata

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.vcs.errors import ProfileValidationError

PROFILE_NAME_KEY = "profile_name"
PROFILE_EMAIL_KEY = "profile_email"

MAX_NAME = 128
MAX_EMAIL = 254
# git обрезает эти символы по краям имени и отказывается от имени, где ничего больше нет.
_GIT_CRUD = " \t.,:;<>\"'\\"
_EMAIL = re.compile(r"[^@\s<>]+@[^@\s<>]+")
_EMAIL_WITH_DOT = re.compile(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+")


def _has_control(value: str) -> bool:
    return any(unicodedata.category(ch) == "Cc" for ch in value)


def normalize_name(raw: str | None) -> str:
    """Имя для подписи: NFC, лишние пробелы схлопнуты; иначе `ProfileValidationError`."""
    name = unicodedata.normalize("NFC", raw or "").strip()
    if not name:
        raise ProfileValidationError("name", "required", localized_error("Укажи имя.", "Enter a name."))
    if len(name) > MAX_NAME:
        raise ProfileValidationError(
            "name",
            "too_long",
            localized_error(f"Имя длиннее {MAX_NAME} символов.", f"The name is longer than {MAX_NAME} characters."),
        )
    if "<" in name or ">" in name or _has_control(name):
        raise ProfileValidationError(
            "name",
            "invalid",
            localized_error(
                "В имени не должно быть символов < и > и переводов строк.",
                "The name must not contain < or > or line breaks.",
            ),
        )
    name = re.sub(r"\s+", " ", name)
    if not name.strip(_GIT_CRUD):
        raise ProfileValidationError(
            "name",
            "invalid",
            localized_error("В имени нужна хотя бы одна буква.", "The name needs at least one letter."),
        )
    return name


def normalize_email(raw: str | None, *, require_domain_dot: bool = True) -> str:
    """E-mail для подписи: домен в нижнем регистре, локальная часть как есть.

    Точка в домене обязательна для профиля; у актора запроса её не требуем, чтобы не менять
    подпись у уже работающих локальных адресов вида `user@localhost`.
    """
    email = unicodedata.normalize("NFC", raw or "").strip()
    if not email:
        raise ProfileValidationError("email", "required", localized_error("Укажи e-mail.", "Enter an e-mail address."))
    if len(email) > MAX_EMAIL:
        raise ProfileValidationError(
            "email",
            "too_long",
            localized_error(
                f"E-mail длиннее {MAX_EMAIL} символов.", f"The e-mail is longer than {MAX_EMAIL} characters."
            ),
        )
    pattern = _EMAIL_WITH_DOT if require_domain_dot else _EMAIL
    if _has_control(email) or not pattern.fullmatch(email):
        raise _bad_email()
    local, domain = email.rsplit("@", 1)
    if require_domain_dot and not all(domain.split(".")):
        raise _bad_email()
    return f"{local}@{domain.lower()}"


def _bad_email() -> ProfileValidationError:
    return ProfileValidationError(
        "email",
        "invalid",
        localized_error("Укажи адрес вида name@example.com.", "Enter an address like name@example.com."),
    )
