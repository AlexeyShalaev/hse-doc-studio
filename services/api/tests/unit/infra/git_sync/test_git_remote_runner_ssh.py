"""Ветка ssh в GitRemoteRunner: временный ключ, жёсткие параметры, ключи хоста. Процесс git подменён."""

from __future__ import annotations

import os
import shlex
import stat
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.entities import (
    CredentialStatus,
    GitCredential,
    GitCredentialKind,
    GitResult,
    RemoteTarget,
    ScannedHostKey,
)
from hse_doc_studio.core.git_sync.error_classifier import GitOp
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.host_keys import key_fingerprint
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.infra.git_sync.git_remote_runner import GitRemoteRunner
from hse_doc_studio.infra.git_sync.known_hosts import FileKnownHostsStore

from tests.unit.core.git_sync.test_host_keys import GITHUB_ED25519
from tests.unit.infra.git_sync.test_git_remote_runner import _Caps, _Credentials, _Process

pytestmark = pytest.mark.skipif(os.name != "posix", reason="ssh keys and file modes are posix-only")

_PEM = "-----BEGIN OPENSSH PRIVATE KEY-----\nCANARYkeyBody1234567890\n-----END OPENSSH PRIVATE KEY-----"
_STORE = Path("/work/project/.hse-studio/git")
_OTHER = "AAAAC3NzaC1lZDI1NTE5AAAAIGk1Zq6mYQdkYxjqU4tUq0h8Y1m7X6uQ0mHk2m9o3a4B"
_NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)


def _scanned(blob: str = GITHUB_ED25519) -> ScannedHostKey:
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


def _ssh_credential(
    host: str = "github.com", port: int | None = None, kind: GitCredentialKind = GitCredentialKind.ssh_key
) -> GitCredential:
    return GitCredential(
        id=uuid4(),
        kind=kind,
        label="ключ",
        host=host,
        username="git",
        status=CredentialStatus.unverified,
        created_at=_NOW,
        port=port,
    )


class _Setup:
    def __init__(
        self, tmp_path: Path, process: _Process, scanner: _Scanner | None = None, *, known: bool = True
    ) -> None:
        self.known_hosts = FileKnownHostsStore(tmp_path / "data")
        self._known = known
        self.credentials = _Credentials()
        self.scanner = scanner or _Scanner([_scanned()])
        self.process = process
        self.runner = GitRemoteRunner(
            GitConfig(),
            self.credentials,  # type: ignore[arg-type]
            local_mode=True,
            process=process,
            capabilities=_Caps(),  # type: ignore[arg-type]
            known_hosts=self.known_hosts,
            scanner=self.scanner,
        )

    @classmethod
    async def create(
        cls, tmp_path: Path, process: _Process, scanner: _Scanner | None = None, *, known: bool = True
    ) -> _Setup:
        setup = cls(tmp_path, process, scanner, known=known)
        if known:
            await setup.known_hosts.trust("github.com", None, [_scanned()])
        return setup

    def add_key(self, **kwargs: object) -> RemoteTarget:
        credential = _ssh_credential(**kwargs)  # type: ignore[arg-type]
        self.credentials.add(credential, Secret(_PEM))
        return RemoteTarget(parse_remote_url("git@github.com:hse/course.git"), credential_id=credential.id)

    async def run(self, target: RemoteTarget, op: GitOp = GitOp.fetch) -> GitResult:
        return await self.runner.run(["fetch"], op=op, git_dir=_STORE, target=target, timeout_s=5)


async def test__run_ssh__builds_the_hardened_command_and_keeps_secrets_out_of_argv(tmp_path: Path) -> None:
    process = _Process()
    setup = await _Setup.create(tmp_path, process)
    target = setup.add_key()

    await setup.run(target)

    argv, env, _cwd = process.calls[0]
    command = shlex.split(env["GIT_SSH_COMMAND"])
    assert command[0] == "/usr/bin/ssh"
    assert command[1:3] == ["-F", os.devnull]
    for option in (
        "StrictHostKeyChecking=yes",
        "IdentitiesOnly=yes",
        "BatchMode=yes",
        "IdentityAgent=none",
        "ProxyCommand=none",
    ):
        assert option in command
    assert f"UserKnownHostsFile={setup.known_hosts.file_path()}" in command
    assert env["GIT_ALLOW_PROTOCOL"] == "https:ssh"
    assert "SSH_AUTH_SOCK" not in env
    assert all("CANARY" not in part for part in argv)
    assert "CANARY" not in env["GIT_SSH_COMMAND"]


async def test__run_ssh__key_file_is_private_while_running_and_removed_after_success(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def during(env: dict[str, str]) -> None:
        key = Path(shlex.split(env["GIT_SSH_COMMAND"])[shlex.split(env["GIT_SSH_COMMAND"]).index("-i") + 1])
        seen["path"] = key
        seen["mode"] = stat.S_IMODE(key.stat().st_mode)
        seen["dir_mode"] = stat.S_IMODE(key.parent.stat().st_mode)
        seen["text"] = key.read_text()

    setup = await _Setup.create(tmp_path, _Process(during=during))
    await setup.run(setup.add_key())

    assert seen["mode"] == 0o600
    assert seen["dir_mode"] == 0o700
    assert str(seen["text"]).startswith("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert str(seen["text"]).endswith("\n")
    path = seen["path"]
    assert isinstance(path, Path)
    assert not path.parent.exists()


async def test__run_ssh__key_file_is_removed_after_a_failure(tmp_path: Path) -> None:
    paths: list[Path] = []

    def during(env: dict[str, str]) -> None:
        command = shlex.split(env["GIT_SSH_COMMAND"])
        paths.append(Path(command[command.index("-i") + 1]))

    process = _Process(GitResult(128, stderr="git@github.com: Permission denied (publickey).\n"), during=during)
    setup = await _Setup.create(tmp_path, process)
    target = setup.add_key()

    with pytest.raises(GitSyncError) as raised:
        await setup.run(target)

    assert raised.value.code is GitErrorCode.auth_failed
    assert paths
    assert not paths[0].parent.exists()
    assert setup.credentials.marks == [(target.credential_id, CredentialStatus.auth_failed)]


async def test__run_ssh__key_file_is_removed_after_an_unexpected_error(tmp_path: Path) -> None:
    paths: list[Path] = []

    def during(env: dict[str, str]) -> None:
        command = shlex.split(env["GIT_SSH_COMMAND"])
        paths.append(Path(command[command.index("-i") + 1]))
        raise KeyboardInterrupt

    setup = await _Setup.create(tmp_path, _Process(during=during))
    target = setup.add_key()

    with pytest.raises(KeyboardInterrupt):
        await setup.run(target)

    assert not paths[0].parent.exists()


async def test__run_ssh__unknown_host__host_key_unknown_with_keys_and_no_process(tmp_path: Path) -> None:
    process = _Process()
    setup = await _Setup.create(tmp_path, process, known=False)
    target = setup.add_key()

    with pytest.raises(GitSyncError) as raised:
        await setup.run(target)

    assert raised.value.code is GitErrorCode.host_key_unknown
    assert [key.fingerprint_sha256 for key in raised.value.ctx["host_keys"]] == [key_fingerprint(GITHUB_ED25519)]  # type: ignore[attr-defined]
    assert process.calls == []
    assert setup.scanner.calls == [("github.com", None)]


async def test__run_ssh__unknown_host_without_a_credential__still_asks_to_confirm_the_host_first(
    tmp_path: Path,
) -> None:
    setup = await _Setup.create(tmp_path, _Process(), known=False)
    target = RemoteTarget(parse_remote_url("git@github.com:hse/course.git"))

    with pytest.raises(GitSyncError) as raised:
        await setup.run(target)

    assert raised.value.code is GitErrorCode.host_key_unknown


async def test__run_ssh__unknown_host_and_unreachable__scan_error_is_reported(tmp_path: Path) -> None:
    offline = GitSyncError(GitErrorCode.offline, "offline")
    setup = await _Setup.create(tmp_path, _Process(), _Scanner(offline), known=False)

    with pytest.raises(GitSyncError) as raised:
        await setup.run(setup.add_key())

    assert raised.value.code is GitErrorCode.offline


async def test__run_ssh__known_host_without_a_credential__credentials_missing(tmp_path: Path) -> None:
    process = _Process()
    setup = await _Setup.create(tmp_path, process)

    with pytest.raises(GitSyncError) as raised:
        await setup.run(RemoteTarget(parse_remote_url("git@github.com:hse/course.git")))

    assert raised.value.code is GitErrorCode.credentials_missing
    assert process.calls == []


async def test__run_ssh__token_instead_of_key__credential_invalid(tmp_path: Path) -> None:
    setup = await _Setup.create(tmp_path, _Process())
    credential = _ssh_credential(kind=GitCredentialKind.pat)
    setup.credentials.add(credential, Secret("ghp_x"))
    target = RemoteTarget(parse_remote_url("git@github.com:hse/course.git"), credential_id=credential.id)

    with pytest.raises(GitSyncError) as raised:
        await setup.run(target)

    assert raised.value.code is GitErrorCode.credential_invalid


async def test__run_ssh__key_for_another_host_or_port__credential_host_mismatch(tmp_path: Path) -> None:
    setup = await _Setup.create(tmp_path, _Process())
    other_host = setup.add_key(host="gitlab.com")
    other_port = setup.add_key(port=2222)

    for target in (other_host, other_port):
        with pytest.raises(GitSyncError) as raised:
            await setup.run(target)
        assert raised.value.code is GitErrorCode.credential_host_mismatch


async def test__run_ssh__host_key_changed__expected_and_actual_fingerprints(tmp_path: Path) -> None:
    process = _Process(
        GitResult(128, stderr="Offending ED25519 key in /d/known_hosts:1\nHost key verification failed.\n")
    )
    setup = await _Setup.create(tmp_path, process, _Scanner([_scanned(_OTHER)]))

    with pytest.raises(GitSyncError) as raised:
        await setup.run(setup.add_key())

    assert raised.value.code is GitErrorCode.host_key_changed
    assert raised.value.ctx == {"expected": key_fingerprint(GITHUB_ED25519), "actual": key_fingerprint(_OTHER)}


async def test__run_ssh__strict_check_failure_after_preflight__keys_from_a_fresh_scan(tmp_path: Path) -> None:
    process = _Process(
        GitResult(
            128,
            stderr=(
                "No ED25519 host key is known for github.com and you have requested strict checking.\n"
                "Host key verification failed.\n"
            ),
        )
    )
    setup = await _Setup.create(tmp_path, process)

    with pytest.raises(GitSyncError) as raised:
        await setup.run(setup.add_key())

    assert raised.value.code is GitErrorCode.host_key_unknown
    assert len(raised.value.ctx["host_keys"]) == 1  # type: ignore[arg-type]


async def test__run_ssh__scan_fails_while_explaining_a_changed_key__code_is_kept_without_fingerprints(
    tmp_path: Path,
) -> None:
    process = _Process(
        GitResult(128, stderr="REMOTE HOST IDENTIFICATION HAS CHANGED!\nHost key verification failed.\n")
    )
    setup = await _Setup.create(tmp_path, process, _Scanner(GitSyncError(GitErrorCode.offline, "offline")))

    with pytest.raises(GitSyncError) as raised:
        await setup.run(setup.add_key())

    assert raised.value.code is GitErrorCode.host_key_changed
    assert raised.value.ctx == {}


async def test__run_ssh__success__marks_the_credential_ok(tmp_path: Path) -> None:
    setup = await _Setup.create(tmp_path, _Process())
    target = setup.add_key()

    await setup.run(target)

    assert setup.credentials.marks == [(target.credential_id, CredentialStatus.ok)]


async def test__run_ssh__no_ssh_client__ssh_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    setup = await _Setup.create(tmp_path, _Process())
    target = setup.add_key()
    monkeypatch.setattr(_Caps, "ssh_path", lambda self: None)

    with pytest.raises(GitSyncError) as raised:
        await setup.run(target)

    assert raised.value.code is GitErrorCode.ssh_unavailable


async def test__run_ssh__runner_without_known_hosts_store__ssh_unavailable() -> None:
    runner = GitRemoteRunner(
        GitConfig(),
        _Credentials(),  # type: ignore[arg-type]
        local_mode=True,
        process=_Process(),
        capabilities=_Caps(),  # type: ignore[arg-type]
    )

    with pytest.raises(GitSyncError) as raised:
        await runner.run(
            ["fetch"],
            op=GitOp.fetch,
            git_dir=_STORE,
            target=RemoteTarget(parse_remote_url("git@github.com:hse/course.git")),
            timeout_s=1,
        )

    assert raised.value.code is GitErrorCode.ssh_unavailable
