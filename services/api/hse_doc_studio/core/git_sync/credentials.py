"""Правила для учётных данных: проверка ввода, семейство токена, привязка шифртекста к записи."""

from __future__ import annotations

import re
import unicodedata
from uuid import UUID

from hse_doc_studio.core.git_sync.entities import GitCredentialKind
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError, GitUrlError
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import normalize_host
from hse_doc_studio.core.i18n import localized_error

MAX_LABEL_LENGTH = 80
MAX_USERNAME_LENGTH = 100
MAX_TOKEN_LENGTH = 512
_MAX_PORT = 65535

# Семейство токена: только префикс, по нему человек узнаёт свой токен в списке, а секрет не раскрывается.
_TOKEN_FAMILIES = (
    re.compile(r"^(github_pat)_"),
    re.compile(r"^(gh[pousr])_"),
    re.compile(r"^(glpat)-"),
    re.compile(r"^(gl(?:oas|dt|rt|cbt|ptt|ft|imt|agent))-"),
)
_SLUG_JUNK = re.compile(r"[^a-z0-9._-]+")


def _invalid(ru: str, en: str) -> GitSyncError:
    return GitSyncError(GitErrorCode.credential_invalid, localized_error(ru, en))


def normalize_label(raw: str) -> str:
    label = " ".join(raw.split())
    if not label or len(label) > MAX_LABEL_LENGTH or any(unicodedata.category(c) == "Cc" for c in label):
        raise _invalid(
            f"Название доступа: от 1 до {MAX_LABEL_LENGTH} символов без управляющих",
            f"Access name: 1 to {MAX_LABEL_LENGTH} characters, no control characters",
        )
    return label


def normalize_credential_host(raw: str) -> str:
    try:
        return normalize_host(raw)
    except GitUrlError:
        raise _invalid("Некорректное имя сервера", "The server name is not valid") from None


def normalize_username(raw: str | None) -> str | None:
    """Имя пользователя для Basic: пустое значит «не задано»; двоеточие делило бы заголовок."""
    if raw is None:
        return None
    name = raw.strip()
    if not name:
        return None
    if len(name) > MAX_USERNAME_LENGTH or ":" in name or not all(c.isprintable() and not c.isspace() for c in name):
        raise _invalid(
            "Имя пользователя без пробелов и двоеточий",
            "The username must have no spaces or colons",
        )
    return name


def normalize_port(port: int | None) -> int | None:
    if port is None:
        return None
    if not 0 < port <= _MAX_PORT:
        raise _invalid("Порт вне диапазона 1-65535", "The port must be between 1 and 65535")
    return port


def normalize_token(raw: str) -> Secret:
    """Токен из буфера обмена: пробелы и перенос по краям отбрасываются, остальное должно быть печатным ASCII."""
    token = raw.strip()
    if not token or len(token) > MAX_TOKEN_LENGTH or not all("!" <= c <= "~" for c in token):
        raise _invalid(
            f"Токен: до {MAX_TOKEN_LENGTH} печатных символов ASCII без пробелов",
            f"The token must be up to {MAX_TOKEN_LENGTH} printable ASCII characters with no spaces",
        )
    return Secret(token)


def token_family(token: str) -> str | None:
    """Префикс токена (github_pat, ghp, glpat): не сам токен и не его хвост."""
    for pattern in _TOKEN_FAMILIES:
        match = pattern.match(token)
        if match:
            return match.group(1)
    return None


def secret_aad(credential_id: UUID, kind: GitCredentialKind) -> str:
    """Что привязывает шифртекст к записи: перенесённый в другую запись секрет не расшифруется."""
    return f"{credential_id}:{kind.value}"


def ssh_key_comment(label: str) -> str:
    """Комментарий публичного ключа: по нему ключ узнают на странице хостинга, личных данных там нет."""
    slug = _SLUG_JUNK.sub("-", label.lower()).strip("-.")[:40]
    return f"hse-doc-studio:{slug}" if slug else "hse-doc-studio"
