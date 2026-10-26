from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.infra.git_sync import host_key_scanner
from hse_doc_studio.infra.git_sync.host_key_scanner import SshKeyscanScanner, parse_keyscan

from tests.unit.core.git_sync.test_host_keys import GITHUB_ED25519, GITHUB_FINGERPRINT

pytestmark = pytest.mark.skipif(os.name != "posix", reason="the fake ssh-keyscan is a posix script")

_OUTPUT = f"""# github.com:22 SSH-2.0-babeld
github.com ssh-ed25519 {GITHUB_ED25519}
github.com ssh-ed25519 {GITHUB_ED25519}
github.com ssh-dss AAAAB3NzaC1kc3MAAACBAP
github.com ssh-rsa not-base64!!
garbage
"""


def _script(tmp_path: Path, body: str) -> str:
    script = tmp_path / "ssh-keyscan"
    script.write_text(f"#!{sys.executable}\nimport sys, time\n{body}\n")
    script.chmod(0o755)
    return str(script)


def test__parse_keyscan__keeps_valid_unique_keys_and_computes_fingerprints() -> None:
    keys = parse_keyscan(_OUTPUT)

    assert [(k.type, k.key, k.fingerprint_sha256) for k in keys] == [
        ("ssh-ed25519", GITHUB_ED25519, GITHUB_FINGERPRINT)
    ]


async def test__scan__passes_a_safe_argv_and_returns_the_keys(tmp_path: Path) -> None:
    argv_file = tmp_path / "argv.txt"
    body = f"open({str(argv_file)!r}, 'w').write(' '.join(sys.argv[1:]))\nprint({_OUTPUT!r})"
    scanner = SshKeyscanScanner(GitConfig(ssh_keyscan_binary=_script(tmp_path, body)))

    keys = await scanner.scan("ssh.github.com", 443)

    assert [k.fingerprint_sha256 for k in keys] == [GITHUB_FINGERPRINT]
    argv = argv_file.read_text().split()
    assert argv[-2:] == ["--", "ssh.github.com"]
    assert argv[argv.index("-p") + 1] == "443"


async def test__scan__no_keys_means_the_server_is_not_reachable(tmp_path: Path) -> None:
    scanner = SshKeyscanScanner(GitConfig(ssh_keyscan_binary=_script(tmp_path, "pass")))

    with pytest.raises(GitSyncError) as raised:
        await scanner.scan("example.org", None)

    assert raised.value.code is GitErrorCode.offline


async def test__scan__missing_binary__ssh_unavailable(tmp_path: Path) -> None:
    scanner = SshKeyscanScanner(GitConfig(ssh_keyscan_binary=str(tmp_path / "no-such-keyscan")))

    with pytest.raises(GitSyncError) as raised:
        await scanner.scan("example.org", None)

    assert raised.value.code is GitErrorCode.ssh_unavailable


async def test__scan__hanging_tool__times_out_and_is_killed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(host_key_scanner, "_KILL_MARGIN_S", 0.1)
    scanner = SshKeyscanScanner(GitConfig(ssh_keyscan_binary=_script(tmp_path, "time.sleep(60)"), scan_timeout_s=1))

    with pytest.raises(GitSyncError) as raised:
        await scanner.scan("example.org", None)

    assert raised.value.code is GitErrorCode.timeout
