from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.git_sync.entities import ScannedHostKey
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.host_keys import key_fingerprint
from hse_doc_studio.infra.git_sync.known_hosts import FileKnownHostsStore
from hse_doc_studio.use_cases.git_sync.hosts import ForgetHostUC, ListHostsUC, TrustHostInput, TrustHostUC

from tests.unit.core.git_sync.test_host_keys import GITHUB_ED25519, GITHUB_FINGERPRINT

_OTHER = "AAAAC3NzaC1lZDI1NTE5AAAAIGk1Zq6mYQdkYxjqU4tUq0h8Y1m7X6uQ0mHk2m9o3a4B"
_OTHER_FINGERPRINT = key_fingerprint(_OTHER)


def _scanned(blob: str) -> ScannedHostKey:
    return ScannedHostKey("ssh-ed25519", blob, key_fingerprint(blob))


class _Scanner:
    def __init__(self, keys: list[ScannedHostKey] | Exception) -> None:
        self.keys = keys
        self.calls: list[tuple[str, int | None]] = []

    async def scan(self, host: str, port: int | None) -> list[ScannedHostKey]:
        self.calls.append((host, port))
        if isinstance(self.keys, Exception):
            raise self.keys
        return self.keys


@pytest.fixture
def store(tmp_path: Path) -> FileKnownHostsStore:
    return FileKnownHostsStore(tmp_path)


def _trust(store: FileKnownHostsStore, scanner: _Scanner) -> TrustHostUC:
    return TrustHostUC(store, scanner)


async def test__trust__confirmed_fingerprint_is_stored(store: FileKnownHostsStore) -> None:
    scanner = _Scanner([_scanned(GITHUB_ED25519)])

    await _trust(store, scanner).execute(TrustHostInput("GitHub.com", None, GITHUB_FINGERPRINT))

    assert scanner.calls == [("github.com", None)]
    listed = await ListHostsUC(store).execute()
    assert [(h.host, h.fingerprints_sha256) for h in listed] == [("github.com", (GITHUB_FINGERPRINT,))]


async def test__trust__stores_only_the_key_that_was_confirmed(store: FileKnownHostsStore) -> None:
    ecdsa = ScannedHostKey("ecdsa-sha2-nistp256", _OTHER, "SHA256:" + "A" * 43)
    scanner = _Scanner([ecdsa, _scanned(GITHUB_ED25519)])

    await _trust(store, scanner).execute(TrustHostInput("github.com", None, GITHUB_FINGERPRINT))

    host = await store.find("github.com", None)
    assert host is not None
    assert host.key_types == ("ssh-ed25519",)


async def test__trust__host_presents_another_key_than_confirmed__host_key_changed(store: FileKnownHostsStore) -> None:
    scanner = _Scanner([_scanned(_OTHER)])

    with pytest.raises(GitSyncError) as raised:
        await _trust(store, scanner).execute(TrustHostInput("github.com", None, GITHUB_FINGERPRINT))

    assert raised.value.code is GitErrorCode.host_key_changed
    assert raised.value.ctx == {"expected": GITHUB_FINGERPRINT, "actual": _OTHER_FINGERPRINT}
    assert await store.find("github.com", None) is None


async def test__trust__known_host_with_another_key_needs_replace__host_key_changed(store: FileKnownHostsStore) -> None:
    await store.trust("github.com", None, [_scanned(GITHUB_ED25519)])
    scanner = _Scanner([_scanned(_OTHER)])

    with pytest.raises(GitSyncError) as raised:
        await _trust(store, scanner).execute(TrustHostInput("github.com", None, _OTHER_FINGERPRINT))

    assert raised.value.code is GitErrorCode.host_key_changed
    assert raised.value.ctx == {"expected": GITHUB_FINGERPRINT, "actual": _OTHER_FINGERPRINT}
    host = await store.find("github.com", None)
    assert host is not None
    assert host.fingerprints_sha256 == (GITHUB_FINGERPRINT,)


async def test__trust__replace_without_the_typed_hostname__rejected(store: FileKnownHostsStore) -> None:
    await store.trust("github.com", None, [_scanned(GITHUB_ED25519)])
    scanner = _Scanner([_scanned(_OTHER)])

    for typed in (None, "", "gitlab.com", "github.co"):
        with pytest.raises(GitSyncError) as raised:
            await _trust(store, scanner).execute(
                TrustHostInput("github.com", None, _OTHER_FINGERPRINT, replace=True, confirm_host=typed)
            )
        assert raised.value.code is GitErrorCode.host_key_changed

    host = await store.find("github.com", None)
    assert host is not None
    assert host.fingerprints_sha256 == (GITHUB_FINGERPRINT,)


async def test__trust__replace_with_the_typed_hostname__swaps_the_key(store: FileKnownHostsStore) -> None:
    await store.trust("github.com", None, [_scanned(GITHUB_ED25519)])
    scanner = _Scanner([_scanned(_OTHER)])

    await _trust(store, scanner).execute(
        TrustHostInput("github.com", None, _OTHER_FINGERPRINT, replace=True, confirm_host=" GitHub.com ")
    )

    host = await store.find("github.com", None)
    assert host is not None
    assert host.fingerprints_sha256 == (_OTHER_FINGERPRINT,)


async def test__trust__already_trusted_key_is_idempotent(store: FileKnownHostsStore) -> None:
    await store.trust("github.com", None, [_scanned(GITHUB_ED25519)])
    scanner = _Scanner([_scanned(GITHUB_ED25519)])

    await _trust(store, scanner).execute(TrustHostInput("github.com", 22, GITHUB_FINGERPRINT))

    assert len(store.file_path().read_text().splitlines()) == 1


@pytest.mark.parametrize("fingerprint", ["", "SHA256:short", "MD5:aa:bb:cc", GITHUB_FINGERPRINT[:-1]])
async def test__trust__malformed_fingerprint__credential_invalid_and_no_scan(
    store: FileKnownHostsStore, fingerprint: str
) -> None:
    scanner = _Scanner([_scanned(GITHUB_ED25519)])

    with pytest.raises(GitSyncError) as raised:
        await _trust(store, scanner).execute(TrustHostInput("github.com", None, fingerprint))

    assert raised.value.code is GitErrorCode.credential_invalid
    assert scanner.calls == []


@pytest.mark.parametrize("host", ["", "-oProxyCommand=x", "a b", "host;rm", "[::1]"])
async def test__trust__hostile_host__credential_invalid(store: FileKnownHostsStore, host: str) -> None:
    scanner = _Scanner([_scanned(GITHUB_ED25519)])

    with pytest.raises(GitSyncError) as raised:
        await _trust(store, scanner).execute(TrustHostInput(host, None, GITHUB_FINGERPRINT))

    assert raised.value.code is GitErrorCode.credential_invalid
    assert scanner.calls == []


async def test__trust__scan_failure_is_passed_on(store: FileKnownHostsStore) -> None:
    scanner = _Scanner(GitSyncError(GitErrorCode.offline, "offline"))

    with pytest.raises(GitSyncError) as raised:
        await _trust(store, scanner).execute(TrustHostInput("github.com", None, GITHUB_FINGERPRINT))

    assert raised.value.code is GitErrorCode.offline


async def test__forget__removes_only_the_given_port(store: FileKnownHostsStore) -> None:
    await store.trust("github.com", None, [_scanned(GITHUB_ED25519)])
    await store.trust("github.com", 443, [_scanned(GITHUB_ED25519)])

    await ForgetHostUC(store).execute("GitHub.com", 443)
    await ForgetHostUC(store).execute("never-seen.example", None)

    assert [(h.host, h.port) for h in await store.list()] == [("github.com", None)]
