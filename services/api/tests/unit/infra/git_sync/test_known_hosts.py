from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from hse_doc_studio.core.git_sync.entities import ScannedHostKey
from hse_doc_studio.infra.git_sync.known_hosts import FileKnownHostsStore

from tests.unit.core.git_sync.test_host_keys import GITHUB_ED25519, GITHUB_FINGERPRINT

# Второй ключ: ecdsa-sha2-nistp256 у github.com.
_ECDSA = (
    "AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5"
    "wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg="
)


def _key(key_type: str = "ssh-ed25519", blob: str = GITHUB_ED25519) -> ScannedHostKey:
    from hse_doc_studio.core.git_sync.host_keys import key_fingerprint

    return ScannedHostKey(key_type, blob, key_fingerprint(blob))


@pytest.fixture
def store(tmp_path: Path) -> FileKnownHostsStore:
    return FileKnownHostsStore(tmp_path / "data")


async def test__trust__then_find_lists_the_key_with_its_fingerprint(store: FileKnownHostsStore) -> None:
    await store.trust("github.com", None, [_key()])

    host = await store.find("github.com", None)

    assert host is not None
    assert (host.host, host.port, host.key_types) == ("github.com", None, ("ssh-ed25519",))
    assert host.fingerprints_sha256 == (GITHUB_FINGERPRINT,)
    assert await store.find("gitlab.com", None) is None


async def test__trust__port_22_and_no_port_are_one_entry(store: FileKnownHostsStore) -> None:
    await store.trust("github.com", 22, [_key()])

    assert await store.find("github.com", None) is not None
    assert "[github.com]:22" not in store.file_path().read_text()


async def test__trust__other_port_is_a_separate_entry_and_forget_touches_only_it(store: FileKnownHostsStore) -> None:
    await store.trust("github.com", None, [_key()])
    await store.trust("github.com", 443, [_key()])

    assert [(h.host, h.port) for h in await store.list()] == [("github.com", None), ("github.com", 443)]
    await store.forget("github.com", 443)

    assert [(h.host, h.port) for h in await store.list()] == [("github.com", None)]


async def test__trust__same_key_twice_is_stored_once(store: FileKnownHostsStore) -> None:
    await store.trust("github.com", None, [_key()])
    await store.trust("github.com", None, [_key()])

    assert len(store.file_path().read_text().splitlines()) == 1


async def test__trust__second_key_type_is_added_and_replace_drops_the_old_ones(store: FileKnownHostsStore) -> None:
    await store.trust("github.com", None, [_key()])
    await store.trust("github.com", None, [_key("ecdsa-sha2-nistp256", _ECDSA)])
    host = await store.find("github.com", None)
    assert host is not None
    assert set(host.key_types) == {"ssh-ed25519", "ecdsa-sha2-nistp256"}

    await store.trust("github.com", None, [_key("ecdsa-sha2-nistp256", _ECDSA)], replace=True)

    host = await store.find("github.com", None)
    assert host is not None
    assert host.key_types == ("ecdsa-sha2-nistp256",)


async def test__trust__skips_keys_that_are_not_valid_host_keys(store: FileKnownHostsStore) -> None:
    await store.trust("github.com", None, [ScannedHostKey("ssh-dss", GITHUB_ED25519, "SHA256:x"), _key()])

    host = await store.find("github.com", None)
    assert host is not None
    assert host.key_types == ("ssh-ed25519",)


async def test__file__is_private_and_readable_by_openssh_format(store: FileKnownHostsStore) -> None:
    await store.trust("git.hse.ru", 2222, [_key()])

    path = store.file_path()
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    line = path.read_text().splitlines()[0].split()
    assert line[:3] == ["[git.hse.ru]:2222", "ssh-ed25519", GITHUB_ED25519]
    assert line[3].startswith("hse-added=")


async def test__list__survives_garbage_lines_and_a_missing_file(store: FileKnownHostsStore) -> None:
    assert await store.list() == []
    path = store.file_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        "# comment\n|1|hashed|entry ssh-ed25519 AAAA\nbad line\nhost,alias ssh-ed25519 "
        + GITHUB_ED25519
        + "\ngithub.com ssh-ed25519 "
        + GITHUB_ED25519
        + "\n"
    )

    assert [h.host for h in await store.list()] == ["github.com"]


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen is not installed")
async def test__file__round_trip_with_ssh_keygen_lookup(store: FileKnownHostsStore) -> None:
    await store.trust("github.com", None, [_key()])
    await store.trust("git.hse.ru", 2222, [_key("ecdsa-sha2-nistp256", _ECDSA)])

    for pattern in ("github.com", "[git.hse.ru]:2222"):
        found = subprocess.run(  # noqa: S603 — фиксированная команда проверки формата
            ["ssh-keygen", "-F", pattern, "-f", str(store.file_path())],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        assert found.returncode == 0, found.stderr
        assert pattern in found.stdout
