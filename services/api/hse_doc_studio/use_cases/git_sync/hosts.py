"""Известные хосты ssh: список, доверие ключу, забвение.

Доверие выдаётся только отпечатку, который человек видел и подтвердил. Сервер сканирует хост заново и
записывает ровно те ключи, чей отпечаток совпал с подтверждённым: если хост успел предъявить другой
ключ между показом и подтверждением, запись не появится.
"""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.git_sync.credentials import normalize_credential_host, normalize_port
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.host_keys import is_fingerprint, normalize_known_port
from hse_doc_studio.core.git_sync.protocols import IHostKeyScanner, IKnownHostsStore, KnownHost
from hse_doc_studio.core.i18n import localized_error


def _normalize(host: str, port: int | None) -> tuple[str, int | None]:
    return normalize_credential_host(host), normalize_known_port(normalize_port(port))


def _changed(expected: str, actual: str) -> GitSyncError:
    return GitSyncError(
        GitErrorCode.host_key_changed,
        localized_error(
            "Ключ сервера не совпал с подтверждённым или с запомненным ранее",
            "The server key does not match the confirmed one or the one remembered earlier",
        ),
        expected=expected,
        actual=actual,
    )


class ListHostsUC:
    def __init__(self, store: IKnownHostsStore) -> None:
        self._store = store

    async def execute(self) -> list[KnownHost]:
        return self._store.list()


@dataclass
class TrustHostInput:
    host: str
    port: int | None
    fingerprint_sha256: str
    replace: bool = False
    confirm_host: str | None = None


class TrustHostUC:
    def __init__(self, store: IKnownHostsStore, scanner: IHostKeyScanner) -> None:
        self._store = store
        self._scanner = scanner

    async def execute(self, inp: TrustHostInput) -> None:
        host, port = _normalize(inp.host, inp.port)
        confirmed = inp.fingerprint_sha256.strip()
        if not is_fingerprint(confirmed):
            raise GitSyncError(
                GitErrorCode.credential_invalid,
                localized_error(
                    "Отпечаток ключа: SHA256: и 43 символа base64",
                    "The key fingerprint must be SHA256: followed by 43 base64 characters",
                ),
            )
        scanned = await self._scanner.scan(host, port)
        matching = [key for key in scanned if key.fingerprint_sha256 == confirmed]
        if not matching:
            raise _changed(confirmed, scanned[0].fingerprint_sha256)
        known = self._store.find(host, port)
        if known is not None and confirmed not in known.fingerprints_sha256 and not inp.replace:
            raise _changed(known.fingerprints_sha256[0], confirmed)
        if inp.replace and (inp.confirm_host or "").strip().lower() != host:
            raise _changed(known.fingerprints_sha256[0] if known else confirmed, confirmed)
        self._store.trust(host, port, matching, replace=inp.replace)


class ForgetHostUC:
    def __init__(self, store: IKnownHostsStore) -> None:
        self._store = store

    async def execute(self, host: str, port: int | None) -> None:
        normalized_host, normalized_port = _normalize(host, port)
        self._store.forget(normalized_host, normalized_port)
