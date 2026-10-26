from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import (
    CredentialStatus,
    GitCredential,
    GitCredentialKind,
    GitResult,
    RemoteTarget,
)
from hse_doc_studio.core.git_sync.error_classifier import GitOp
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.infra.git_sync.git_remote_runner import GitRemoteRunner
from hse_doc_studio.infra.git_sync.process_runner import GitProcessRunner, ProcessTimeoutError

_TOKEN = "ghp_CANARYtokenValue1234567890abcdef"
_NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)


@dataclass
class _Process(GitProcessRunner):
    result: GitResult | Exception = field(default_factory=lambda: GitResult(0))
    calls: list[tuple[list[str], dict[str, str], Path]] = field(default_factory=list)
    # Вызывается в момент запуска процесса: тест видит то, что есть на диске, пока команда идёт.
    during: Callable[[dict[str, str]], None] | None = None

    async def run(  # type: ignore[override]
        self, argv: Sequence[str], *, env: Mapping[str, str], cwd: Path, timeout_s: float, on_progress: object = None
    ) -> GitResult:
        self.calls.append((list(argv), dict(env), cwd))
        if self.during is not None:
            self.during(dict(env))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _Caps:
    git_binary = "git"

    def ssh_path(self) -> str | None:
        return "/usr/bin/ssh"

    async def ensure_git(self, *, cwd: Path, env: dict[str, str]) -> tuple[int, int, int]:
        return (2, 54, 0)


class _Credentials:
    def __init__(self) -> None:
        self.items: dict[UUID, tuple[GitCredential, Secret]] = {}
        self.marks: list[tuple[UUID, CredentialStatus]] = []

    def add(self, credential: GitCredential, secret: Secret) -> None:
        self.items[credential.id] = (credential, secret)

    def get(self, credential_id: UUID) -> GitCredential | None:
        item = self.items.get(credential_id)
        return item[0] if item else None

    def get_secret(self, credential_id: UUID) -> Secret:
        if credential_id not in self.items:
            raise NotFoundError("credential")
        return self.items[credential_id][1]

    def mark(self, credential_id: UUID, status: CredentialStatus, *, used_at: datetime | None = None) -> None:
        self.marks.append((credential_id, status))


def _credential(host: str = "github.com") -> GitCredential:
    return GitCredential(
        id=uuid4(),
        kind=GitCredentialKind.pat,
        label="t",
        host=host,
        username=None,
        status=CredentialStatus.unverified,
        created_at=_NOW,
    )


def _runner(
    process: _Process, credentials: _Credentials | None = None, **config: object
) -> tuple[GitRemoteRunner, _Credentials]:
    creds = credentials or _Credentials()
    runner = GitRemoteRunner(
        GitConfig(**config),  # type: ignore[arg-type]
        creds,  # type: ignore[arg-type]
        local_mode=True,
        process=process,
        capabilities=_Caps(),  # type: ignore[arg-type]
    )
    return runner, creds


def _target(raw: str = "https://github.com/hse/course.git", credential_id: UUID | None = None) -> RemoteTarget:
    return RemoteTarget(parse_remote_url(raw, allow_http=True, allow_local=True), credential_id=credential_id)


_STORE = Path("/work/project/.hse-studio/git")


async def test__run__builds_argv_with_git_dir_and_hardening_before_the_subcommand() -> None:
    process = _Process()
    runner, _ = _runner(process)

    await runner.run(
        ["ls-remote", "--", "https://github.com/hse/course.git"],
        op=GitOp.probe,
        git_dir=_STORE,
        target=_target(),
        timeout_s=5,
    )

    argv, _env, cwd = process.calls[0]
    assert argv[:3] == ["git", "--git-dir", str(_STORE)]
    assert argv[-3:] == ["ls-remote", "--", "https://github.com/hse/course.git"]
    config = {argv[i + 1] for i, part in enumerate(argv) if part == "-c"}
    assert {
        "core.fsmonitor=false",
        "core.sshCommand=",
        "credential.helper=",
        "protocol.ext.allow=never",
        "transfer.fsckObjects=true",
        "http.followRedirects=initial",
        "gc.auto=0",
        "safe.directory=*",
    } <= config
    assert any(item.startswith("core.hooksPath=") for item in config)
    assert cwd == _STORE.parent


async def test__run__env_is_allow_listed_and_forces_c_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-canary")
    monkeypatch.setenv("GIT_TRACE_CURL", "1")
    process = _Process()
    runner, _ = _runner(process)

    await runner.run(["fetch"], op=GitOp.fetch, git_dir=_STORE, target=_target(), timeout_s=5)

    env = process.calls[0][1]
    assert env["LC_ALL"] == "C"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_ALLOW_PROTOCOL"] == "https:ssh"
    assert "OPENAI_API_KEY" not in env
    assert "GIT_TRACE_CURL" not in env


async def test__run__pat__goes_to_env_only_and_credential_is_marked_ok() -> None:
    credential = _credential()
    creds = _Credentials()
    creds.add(credential, Secret(_TOKEN))
    process = _Process()
    runner, _ = _runner(process, creds)

    await runner.run(
        ["fetch"], op=GitOp.fetch, git_dir=_STORE, target=_target(credential_id=credential.id), timeout_s=5
    )

    argv, env, _cwd = process.calls[0]
    assert all(_TOKEN not in part for part in argv)
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert creds.marks == [(credential.id, CredentialStatus.ok)]


async def test__run__credential_for_a_file_remote__is_ignored() -> None:
    credential = _credential()
    creds = _Credentials()
    creds.add(credential, Secret(_TOKEN))
    process = _Process()
    runner, _ = _runner(process, creds)

    await runner.run(
        ["fetch"], op=GitOp.fetch, git_dir=_STORE, target=_target("file:///srv/r.git", credential.id), timeout_s=5
    )

    assert "GIT_CONFIG_COUNT" not in process.calls[0][1]
    assert creds.marks == []


async def test__run__auth_failure_with_credential__auth_failed_and_credential_marked() -> None:
    credential = _credential()
    creds = _Credentials()
    creds.add(credential, Secret(_TOKEN))
    process = _Process(GitResult(128, stderr="fatal: Authentication failed for 'https://github.com/hse/course.git/'\n"))
    runner, _ = _runner(process, creds)

    with pytest.raises(GitSyncError) as raised:
        await runner.run(
            ["fetch"], op=GitOp.fetch, git_dir=_STORE, target=_target(credential_id=credential.id), timeout_s=5
        )

    assert raised.value.code is GitErrorCode.auth_failed
    assert creds.marks == [(credential.id, CredentialStatus.auth_failed)]


async def test__run__auth_failure_without_credential__credentials_missing() -> None:
    process = _Process(
        GitResult(128, stderr="fatal: could not read Username for 'https://x': terminal prompts disabled\n")
    )
    runner, creds = _runner(process)

    with pytest.raises(GitSyncError) as raised:
        await runner.run(["fetch"], op=GitOp.fetch, git_dir=_STORE, target=_target(), timeout_s=5)

    assert raised.value.code is GitErrorCode.credentials_missing
    assert creds.marks == []


async def test__run__forbidden_write__does_not_mark_the_credential_as_failed() -> None:
    credential = _credential()
    creds = _Credentials()
    creds.add(credential, Secret(_TOKEN))
    process = _Process(
        GitResult(
            128, stderr="fatal: unable to access 'https://github.com/x/y.git/': The requested URL returned error: 403\n"
        )
    )
    runner, _ = _runner(process, creds)

    with pytest.raises(GitSyncError) as raised:
        await runner.run(
            ["push"], op=GitOp.push, git_dir=_STORE, target=_target(credential_id=credential.id), timeout_s=5
        )

    assert raised.value.code is GitErrorCode.forbidden_write
    assert creds.marks == []


async def test__run__push_rejection_in_porcelain_stdout__remote_moved() -> None:
    process = _Process(
        GitResult(
            1,
            stdout=b"To https://h/o/r.git\n!\trefs/heads/main:refs/heads/main\t[rejected] (fetch first)\nDone\n",
            stderr="error: failed to push some refs\n",
        )
    )
    runner, _ = _runner(process)

    with pytest.raises(GitSyncError) as raised:
        await runner.run(["push"], op=GitOp.push, git_dir=_STORE, target=_target(), timeout_s=5)

    assert raised.value.code is GitErrorCode.remote_moved


async def test__run__unknown_failure__git_error_with_scrubbed_tail() -> None:
    credential = _credential()
    creds = _Credentials()
    creds.add(credential, Secret(_TOKEN))
    process = _Process(
        GitResult(1, stderr=f"fatal: something odd happened with {_TOKEN} in https://anna:{_TOKEN}@github.com/x\n")
    )
    runner, _ = _runner(process, creds)

    with pytest.raises(GitSyncError) as raised:
        await runner.run(
            ["fetch"], op=GitOp.fetch, git_dir=_STORE, target=_target(credential_id=credential.id), timeout_s=5
        )

    assert raised.value.code is GitErrorCode.git_error
    assert "something odd happened" in raised.value.detail
    assert _TOKEN not in raised.value.detail
    assert "anna" not in raised.value.detail


async def test__run__timeout__timeout_code() -> None:
    runner, _ = _runner(_Process(ProcessTimeoutError()))

    with pytest.raises(GitSyncError) as raised:
        await runner.run(["fetch"], op=GitOp.fetch, git_dir=_STORE, target=_target(), timeout_s=1)

    assert raised.value.code is GitErrorCode.timeout


async def test__run__git_binary_cannot_start__git_unavailable() -> None:
    runner, _ = _runner(_Process(FileNotFoundError("git")))

    with pytest.raises(GitSyncError) as raised:
        await runner.run(["fetch"], op=GitOp.fetch, git_dir=_STORE, target=_target(), timeout_s=1)

    assert raised.value.code is GitErrorCode.git_unavailable


async def test__run__unreadable_secret__secrets_unavailable_is_passed_through_before_spawn() -> None:
    class _Broken(_Credentials):
        def get_secret(self, credential_id: UUID) -> Secret:
            raise GitSyncError(GitErrorCode.secrets_unavailable)

    credential = _credential()
    creds = _Broken()
    creds.add(credential, Secret(_TOKEN))
    process = _Process()
    runner, _ = _runner(process, creds)

    with pytest.raises(GitSyncError) as raised:
        await runner.run(
            ["fetch"], op=GitOp.fetch, git_dir=_STORE, target=_target(credential_id=credential.id), timeout_s=1
        )

    assert raised.value.code is GitErrorCode.secrets_unavailable
    assert process.calls == []


async def test__run__credential_was_deleted__credentials_missing_before_spawn() -> None:
    process = _Process()
    runner, _ = _runner(process)

    with pytest.raises(GitSyncError) as raised:
        await runner.run(["fetch"], op=GitOp.fetch, git_dir=_STORE, target=_target(credential_id=uuid4()), timeout_s=1)

    assert raised.value.code is GitErrorCode.credentials_missing
    assert process.calls == []


async def test__run_local__env_allows_no_transport_and_failure_is_checked() -> None:
    process = _Process(GitResult(128, stderr="fatal: bad object\n"))
    runner, _ = _runner(process)

    with pytest.raises(GitSyncError) as raised:
        await runner.run_local(["cat-file", "-p", "x"], git_dir=_STORE, timeout_s=1)

    assert raised.value.code is GitErrorCode.git_error
    assert process.calls[0][1]["GIT_ALLOW_PROTOCOL"] == "none"
    assert "bad object" in raised.value.detail


async def test__run_local__check_false__returns_the_failed_result() -> None:
    process = _Process(GitResult(128, stderr="fatal: nope\n"))
    runner, _ = _runner(process)

    result = await runner.run_local(["cat-file", "-p", "x"], git_dir=_STORE, timeout_s=1, check=False)

    assert result.returncode == 128
