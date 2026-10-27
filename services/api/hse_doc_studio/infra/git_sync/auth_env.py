"""Окружение для git: допустимые транспорты и доставка токена.

Токен идёт только в окружение одного процесса git: `GIT_CONFIG_COUNT` и пара KEY_0/VALUE_0 задают
`http.<адрес>.extraheader` с заголовком Basic. Ключ привязан к схеме, хосту и порту адреса, поэтому
при подмене адреса заголовок не уйдёт на другой хост. После редиректа git сохранил бы заголовок для всех
следующих запросов, поэтому раннер запускает git с токеном при `http.followRedirects=false`. В argv токена нет,
на диск он не пишется, а credential helper и askpass не участвуют.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from hse_doc_studio.core.git_sync.entities import GitCredential, GitCredentialKind
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import RemoteKind, RemoteUrl
from hse_doc_studio.core.i18n import localized_error

# Логин для Basic, когда в доступе он не задан: GitHub, GitLab и Gitea принимают любой при токене в пароле.
DEFAULT_TOKEN_USERNAME = "x-access-token"  # noqa: S105 — имя пользователя, не секрет


@dataclass(frozen=True)
class HttpAuth:
    env: dict[str, str]
    # Строки, которые нельзя оставлять в выводе git: сам токен и пара логин:токен.
    secrets: tuple[str, ...]


def allowed_protocols(remote: RemoteUrl) -> str:
    """Значение GIT_ALLOW_PROTOCOL: только транспорты, нужные этому адресу, и без ext, fd, git."""
    allowed = ["https", "ssh"]
    if remote.kind is RemoteKind.http:
        allowed.append("http")
    if remote.kind is RemoteKind.file:
        allowed.append("file")
    return ":".join(allowed)


def _mismatch(ru: str, en: str, code: GitErrorCode = GitErrorCode.credential_host_mismatch) -> GitSyncError:
    return GitSyncError(code, localized_error(ru, en))


def check_credential_matches(remote: RemoteUrl, credential: GitCredential) -> None:
    """Доступ годится только для своего хоста: токен GitHub не уйдёт на чужой сервер по правке адреса."""
    if remote.host is None or credential.host.lower() != remote.host.lower():
        raise _mismatch(
            "Этот доступ создан для другого сервера",
            "This access was created for a different server",
        )
    if remote.kind is RemoteKind.ssh and credential.port is not None and credential.port != (remote.port or 22):  # noqa: PLR2004
        raise _mismatch(
            "Этот ключ создан для другого порта сервера",
            "This key was created for a different server port",
        )


def build_http_auth(remote: RemoteUrl, credential: GitCredential, secret: Secret) -> HttpAuth:
    if remote.kind not in {RemoteKind.https, RemoteKind.http}:
        raise git_error(GitErrorCode.credentials_missing)
    if credential.kind is not GitCredentialKind.pat:
        raise _mismatch(
            "Для адреса https нужен токен, а не ключ ssh",
            "An https address needs a token, not an ssh key",
            GitErrorCode.credential_invalid,
        )
    check_credential_matches(remote, credential)
    token = secret.reveal()
    pair = f"{credential.username or DEFAULT_TOKEN_USERNAME}:{token}"
    header = "Authorization: Basic " + base64.b64encode(pair.encode()).decode("ascii")
    authority = f"{remote.host}:{remote.port}" if remote.port else str(remote.host)
    env = {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"http.{remote.kind.value}://{authority}/.extraheader",
        "GIT_CONFIG_VALUE_0": header,
    }
    return HttpAuth(env=env, secrets=(token, pair))
