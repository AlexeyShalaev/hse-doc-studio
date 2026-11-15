"""Подходит ли доступ к адресу удалённого репозитория: чистая проверка без секретов и процессов."""

from __future__ import annotations

from hse_doc_studio.core.git_sync.entities import GitCredential
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.url import RemoteKind, RemoteUrl
from hse_doc_studio.core.i18n import localized_error


def check_credential_matches(remote: RemoteUrl, credential: GitCredential) -> None:
    """Доступ годится только для своего хоста: токен GitHub не уйдёт на чужой сервер по правке адреса."""
    if remote.host is None or credential.host.lower() != remote.host.lower():
        raise _credential_mismatch(
            "Этот доступ создан для другого сервера",
            "This access was created for a different server",
        )
    if remote.kind is RemoteKind.ssh and credential.port is not None and credential.port != (remote.port or 22):  # noqa: PLR2004
        raise _credential_mismatch(
            "Этот ключ создан для другого порта сервера",
            "This key was created for a different server port",
        )


def _credential_mismatch(ru: str, en: str) -> GitSyncError:
    return GitSyncError(GitErrorCode.credential_host_mismatch, localized_error(ru, en))
