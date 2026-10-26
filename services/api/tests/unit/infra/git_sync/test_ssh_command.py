from __future__ import annotations

import os
import shlex
import stat
import time
from pathlib import Path

import pytest
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.infra.git_sync.ssh_command import (
    KEY_DIR_PREFIX,
    build_ssh_command,
    sweep_stale_key_dirs,
    temporary_key_file,
)

_posix_only = pytest.mark.skipif(os.name != "posix", reason="file modes are posix-only")


def _options(command: str) -> dict[str, str]:
    argv = shlex.split(command)
    return {part.split("=", 1)[0]: part.split("=", 1)[1] for part in argv if "=" in part and not part.startswith("-")}


def test__build_ssh_command__sets_the_hardened_option_set() -> None:
    command = build_ssh_command(
        "/usr/bin/ssh", key_file=Path("/tmp/hse-ssh-x/id"), known_hosts=Path("/data/git/known_hosts")
    )

    argv = shlex.split(command)
    assert argv[:5] == ["/usr/bin/ssh", "-F", os.devnull, "-i", "/tmp/hse-ssh-x/id"]
    assert _options(command) == {
        "IdentitiesOnly": "yes",
        "BatchMode": "yes",
        "StrictHostKeyChecking": "yes",
        "UserKnownHostsFile": "/data/git/known_hosts",
        "GlobalKnownHostsFile": os.devnull,
        "IdentityAgent": "none",
        "ProxyCommand": "none",
        "ProxyJump": "none",
        "PasswordAuthentication": "no",
        "KbdInteractiveAuthentication": "no",
        "ForwardAgent": "no",
        "ForwardX11": "no",
        "PermitLocalCommand": "no",
        "VerifyHostKeyDNS": "no",
        "UpdateHostKeys": "no",
        "HashKnownHosts": "no",
        "ConnectTimeout": "15",
        "ServerAliveInterval": "15",
        "ServerAliveCountMax": "4",
    }
    assert "accept-new" not in command


def test__build_ssh_command__path_with_spaces_stays_one_ssh_config_value() -> None:
    command = build_ssh_command(
        "/usr/bin/ssh", key_file=Path("/tmp/a b/id"), known_hosts=Path("/my data/git/known_hosts")
    )

    argv = shlex.split(command)
    assert argv[argv.index("-i") + 1] == "/tmp/a b/id"
    assert 'UserKnownHostsFile="/my data/git/known_hosts"' in argv


def test__build_ssh_command__percent_in_paths_is_escaped_for_ssh() -> None:
    command = build_ssh_command("ssh", key_file=Path("/tmp/100%/id"), known_hosts=Path("/data/%h/known_hosts"))

    argv = shlex.split(command)
    assert argv[argv.index("-i") + 1] == "/tmp/100%%/id"
    assert "UserKnownHostsFile=/data/%%h/known_hosts" in argv


def test__build_ssh_command__shell_metacharacters_in_paths_cannot_inject() -> None:
    command = build_ssh_command("ssh", key_file=Path("/tmp/x; touch pwned/id"), known_hosts=Path("/d/$(id)/kh"))

    argv = shlex.split(command)
    assert "/tmp/x; touch pwned/id" in argv
    assert "UserKnownHostsFile=/d/$(id)/kh" in argv


@_posix_only
def test__temporary_key_file__is_private_ends_with_newline_and_is_removed() -> None:
    with temporary_key_file(
        Secret("-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----")
    ) as path:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert path.parent.name.startswith(KEY_DIR_PREFIX)
        assert path.read_text().endswith("PRIVATE KEY-----\n")
        directory = path.parent

    assert not directory.exists()


def test__temporary_key_file__is_removed_when_the_block_raises() -> None:
    seen: list[Path] = []

    def use_and_fail() -> None:
        with temporary_key_file(Secret("key")) as path:
            seen.append(path.parent)
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        use_and_fail()

    assert seen
    assert not seen[0].exists()


def test__sweep_stale_key_dirs__removes_only_old_hse_ssh_dirs(tmp_path: Path) -> None:
    old = tmp_path / f"{KEY_DIR_PREFIX}old"
    fresh = tmp_path / f"{KEY_DIR_PREFIX}fresh"
    other = tmp_path / "unrelated"
    for directory in (old, fresh, other):
        directory.mkdir()
        (directory / "id").write_text("k")
    stale = time.time() - 7200
    os.utime(old, (stale, stale))
    os.utime(other, (stale, stale))

    removed = sweep_stale_key_dirs(root=tmp_path)

    assert removed == 1
    assert not old.exists()
    assert fresh.exists()
    assert other.exists()
