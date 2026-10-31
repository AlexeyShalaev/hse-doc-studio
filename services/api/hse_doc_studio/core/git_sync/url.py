"""Единственные ворота для адреса репозитория, который попадёт в git.

Чистая функция без ввода-вывода. Векторы разбора общие с фронтендом: contracts/git-sync/url_cases.json
(parseRemoteUrl читает тот же файл). Порядок проверок такой: сначала всё, что делает адрес
некорректным (url_invalid), и лишь затем запрещённые схемы и политика (url_scheme_forbidden).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitUrlError
from hse_doc_studio.core.git_sync.providers import GitProvider, provider_for_host
from hse_doc_studio.core.i18n import localized_error

MAX_URL_LENGTH = 2048
DEFAULT_SSH_USER = "git"
# Открытый http к своему компьютеру: токен не уходит в сеть. Пускается вместе с локальными адресами (`allow_local`,
# только локальная Студия), как вход на сервер Студии по `http://localhost` (use_cases.git_sync.studio_servers).
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1"})

_FORBIDDEN_CHARS = frozenset("\\`\"'<>|;$&{}()*!^[]#?")
_ENCODED_CONTROL = re.compile(r"%(?:[01][0-9a-f]|7f)", re.IGNORECASE)
_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*)://(.*)$", re.DOTALL)
_SCP_LIKE = re.compile(r"^([^@/:]+)@([^:/]+):(.+)$")
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_SSH_USER = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")
_MAX_HOST_LENGTH = 253
_MAX_PORT = 65535


class RemoteKind(StrEnum):
    https = "https"
    ssh = "ssh"
    file = "file"
    http = "http"


@dataclass(frozen=True)
class RemoteUrl:
    """Разобранный адрес. `display_url` без userinfo пароля и токена: его можно показывать, логировать и сохранять."""

    display_url: str
    kind: RemoteKind
    host: str | None
    port: int | None
    # Пользователь ssh (по умолчанию git); у остальных схем None.
    user: str | None
    provider: GitProvider
    owner: str | None
    repo: str | None
    # В адресе был userinfo https/http (токен или логин с паролем): он отброшен и нигде не хранится.
    token_stripped: bool

    @property
    def host_key(self) -> str | None:
        """Ключ записи known_hosts: `host` или `[host]:port`."""
        if self.host is None:
            return None
        return f"[{self.host}]:{self.port}" if self.port else self.host


def _invalid() -> GitUrlError:
    return GitUrlError(
        GitErrorCode.url_invalid,
        localized_error("Некорректный адрес репозитория", "The repository address is not valid"),
    )


def _forbidden() -> GitUrlError:
    return GitUrlError(
        GitErrorCode.url_scheme_forbidden,
        localized_error("Этот вид адреса не поддерживается", "This kind of address is not supported"),
    )


def _has_bad_char(raw: str) -> bool:
    for char in raw:
        if char in _FORBIDDEN_CHARS or char.isspace():
            return True
        if unicodedata.category(char) in {"Cc", "Cf", "Zs", "Zl", "Zp"}:
            return True
    return bool(_ENCODED_CONTROL.search(raw))


def _punycode(host: str) -> str:
    """Punycode хоста. Кодек `idna` из stdlib это IDNA 2003 с nameprep: он молча подменяет символы (ß на ss, полную
    ширину на латиницу, конечную сигму), и токен, выданный для одного домена, ушёл бы на другой. Поэтому хост,
    который nameprep изменил бы, отвергается: браузеры и curl читают такой адрес иначе, чем кодек."""
    try:
        ascii_host = host.encode("idna").decode("ascii")
        if ascii_host.encode("ascii").decode("idna") != host:
            raise _invalid()
    except UnicodeError:
        raise _invalid() from None
    return ascii_host


def _clean_host(raw_host: str) -> str:
    host = raw_host.lower()
    if not host.isascii():
        host = _punycode(unicodedata.normalize("NFC", host))
    labels = host.split(".")
    if len(host) > _MAX_HOST_LENGTH or not all(_HOST_LABEL.match(label) for label in labels):
        raise _invalid()
    return host


def normalize_host(raw: str) -> str:
    """Имя хоста для учётных данных и known_hosts: те же правила, что для хоста в адресе."""
    text = raw.strip()
    if not text or text.startswith("-") or _has_bad_char(text):
        raise _invalid()
    return _clean_host(text)


def _split_port(hostport: str) -> tuple[str, int | None]:
    host, sep, port_text = hostport.rpartition(":")
    if not sep:
        return hostport, None
    if not (port_text.isascii() and port_text.isdigit()) or not 0 < int(port_text) <= _MAX_PORT:
        raise _invalid()
    return host, int(port_text)


def _clean_path(path: str) -> list[str]:
    """Сегменты пути без хвостового слэша; пустые и точечные сегменты недопустимы."""
    if not path.startswith("/"):
        raise _invalid()
    body = path[1:]
    if body.endswith("/"):
        body = body[:-1]
    segments = body.split("/")
    for segment in segments:
        decoded = segment.replace("%2e", ".").replace("%2E", ".")
        if segment == "" or decoded in {".", ".."}:
            raise _invalid()
    return segments


def _owner_repo(segments: list[str], *, with_owner: bool) -> tuple[str | None, str]:
    last = segments[-1]
    repo = last.removesuffix(".git") or last
    owner = "/".join(segments[:-1]) if with_owner and len(segments) > 1 else None
    return owner, repo


def _build(
    kind: RemoteKind,
    *,
    host: str | None,
    port: int | None,
    user: str | None,
    segments: list[str],
    token_stripped: bool,
) -> RemoteUrl:
    path = "/" + "/".join(segments)
    authority = ""
    if host is not None:
        authority = (f"{user}@" if user else "") + host + (f":{port}" if port else "")
    owner, repo = _owner_repo(segments, with_owner=kind != RemoteKind.file)
    return RemoteUrl(
        display_url=f"{kind.value}://{authority}{path}",
        kind=kind,
        host=host,
        port=port,
        user=user,
        provider=provider_for_host(host),
        owner=owner,
        repo=repo,
        token_stripped=token_stripped,
    )


def _from_authority(kind: RemoteKind, rest: str) -> RemoteUrl:
    authority, slash, tail = rest.partition("/")
    if not slash:
        raise _invalid()
    userinfo, at, hostport = authority.rpartition("@")
    user: str | None = None
    token_stripped = False
    if kind == RemoteKind.ssh:
        if at:
            if ":" in userinfo or not _SSH_USER.match(userinfo):
                raise _invalid()
            user = userinfo
        user = user or DEFAULT_SSH_USER
    else:
        token_stripped = bool(at)
    host_text, port = _split_port(hostport)
    host = _clean_host(host_text)
    return _build(
        kind, host=host, port=port, user=user, segments=_clean_path("/" + tail), token_stripped=token_stripped
    )


def _from_scp_like(match: re.Match[str]) -> RemoteUrl:
    user, host_text, path = match.groups()
    if not _SSH_USER.match(user):
        raise _invalid()
    host = _clean_host(host_text)
    return _build(
        RemoteKind.ssh,
        host=host,
        port=None,
        user=user,
        segments=_clean_path("/" + path.lstrip("/")),
        token_stripped=False,
    )


def _from_file(path: str) -> RemoteUrl:
    return _build(RemoteKind.file, host=None, port=None, user=None, segments=_clean_path(path), token_stripped=False)


def _check_text(text: str) -> None:
    if not text or len(text) > MAX_URL_LENGTH or text.startswith("-") or _has_bad_char(text):
        raise _invalid()
    if "::" in text.split("/", 1)[0]:
        raise _forbidden()


def parse_remote_url(raw: str, *, allow_http: bool = False, allow_local: bool = False) -> RemoteUrl:
    """Разобрать и нормализовать адрес репозитория.

    Принимаются https, ssh, scp-подобный `user@host:путь` (переписывается в ssh://),
    http только при `allow_http` (к localhost и при `allow_local`), file:// и абсолютный путь только при `allow_local`.
    Всё остальное (ext::, fd::, git://, ведущий дефис, управляющие символы, пробелы) отвергается.
    Токен в userinfo https/http отбрасывается и не возвращается.
    """
    text = raw.strip()
    _check_text(text)
    scheme_match = _SCHEME.match(text)
    if scheme_match:
        scheme, rest = scheme_match.group(1).lower(), scheme_match.group(2)
        return _parse_with_scheme(scheme, rest, allow_http=allow_http, allow_local=allow_local)
    if text.startswith("/"):
        return _checked_local(_from_file(text), allow_local=allow_local)
    scp_match = _SCP_LIKE.match(text)
    if scp_match:
        return _from_scp_like(scp_match)
    raise _invalid()


def _checked_local(parsed: RemoteUrl, *, allow_local: bool) -> RemoteUrl:
    if not allow_local:
        raise _forbidden()
    return parsed


def _parse_with_scheme(scheme: str, rest: str, *, allow_http: bool, allow_local: bool) -> RemoteUrl:
    if scheme in {"https", "ssh"}:
        return _from_authority(RemoteKind(scheme), rest)
    if scheme == "http":
        parsed = _from_authority(RemoteKind.http, rest)
        if not allow_http and not (allow_local and parsed.host in LOOPBACK_HOSTS):
            raise _forbidden()
        return parsed
    if scheme == "file":
        if not rest.startswith("/"):
            raise _invalid()
        return _checked_local(_from_file(rest), allow_local=allow_local)
    raise _forbidden()


def is_loopback_http(url: RemoteUrl) -> bool:
    """Открытый http к своему компьютеру (localhost): токен по нему в сеть не уходит."""
    return url.kind is RemoteKind.http and url.host in LOOPBACK_HOSTS
