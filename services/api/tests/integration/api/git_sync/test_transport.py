"""Транспорт Git-синхронизации против настоящего git: file:// и git http-backend на 127.0.0.1."""

from __future__ import annotations

import asyncio
import base64
import os
import socket
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import structlog
from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.entities import (
    CredentialStatus,
    GitCredential,
    GitCredentialKind,
    GitResult,
    RemoteTarget,
)
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import RemoteKind, RemoteUrl, parse_remote_url
from hse_doc_studio.infra.git_sync.credential_repository import JsonGitCredentialRepository
from hse_doc_studio.infra.git_sync.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.git_sync.git_remote_runner import GitRemoteRunner
from hse_doc_studio.infra.git_sync.git_transport import GitTransport
from hse_doc_studio.infra.git_sync.key_store import KeyFileStore
from hse_doc_studio.infra.git_sync.process_runner import GitProcessRunner

from tests.fixtures.git_remote import BareRemote, GitHttpServer, StudioPair, make_bare_remote, seed_remote

_TOKEN = "ghp_CANARYtokenValue1234567890abcdef"
_PROJECT_JSON = '{"id": "6f1c9a0e-0000-4000-8000-000000000001", "name": "Course paper"}\n'
_posix_only = pytest.mark.skipif(os.name != "posix", reason="process groups are posix-only")


class _Spy(GitProcessRunner):
    """Записывает всё, что уходит в процесс git, и сами процессы."""

    def __init__(self) -> None:
        self.argvs: list[list[str]] = []
        self.envs: list[dict[str, str]] = []
        self.processes: list[asyncio.subprocess.Process] = []

    async def run(
        self, argv: Sequence[str], *, env: object, cwd: Path, timeout_s: float, on_progress: object = None
    ) -> GitResult:
        self.argvs.append(list(argv))
        self.envs.append(dict(env))  # type: ignore[call-overload]
        return await super().run(argv, env=env, cwd=cwd, timeout_s=timeout_s, on_progress=on_progress)  # type: ignore[arg-type]

    def _started(self, process: asyncio.subprocess.Process) -> None:
        self.processes.append(process)

    def network_calls(self) -> list[int]:
        return [i for i, argv in enumerate(self.argvs) if any(a in argv for a in ("fetch", "push", "ls-remote"))]


@dataclass
class Stack:
    spy: _Spy
    credentials: JsonGitCredentialRepository
    runner: GitRemoteRunner
    transport: GitTransport

    async def add_pat(self, *, host: str = "127.0.0.1", token: str = _TOKEN, username: str | None = None) -> UUID:
        credential = GitCredential(
            id=uuid4(),
            kind=GitCredentialKind.pat,
            label="Тестовый токен",
            host=host,
            username=username,
            status=CredentialStatus.unverified,
            created_at=datetime(2026, 10, 26, tzinfo=timezone.utc),
            token_family="ghp",
        )
        await self.credentials.add(credential, Secret(token))
        return credential.id


@pytest.fixture
def stack_factory(tmp_path: Path) -> Callable[..., Stack]:
    def make(*, local_mode: bool = True, allow_http: bool = True, probe_timeout_s: float = 20.0) -> Stack:
        data = tmp_path / "data"
        credentials = JsonGitCredentialRepository(data, FernetSecretCipher(KeyFileStore(data / "secrets" / "k.json")))
        config = GitConfig(allow_insecure_http=allow_http, allow_local_remotes=True, probe_timeout_s=probe_timeout_s)
        spy = _Spy()
        runner = GitRemoteRunner(config, credentials, local_mode=local_mode, process=spy)
        return Stack(spy, credentials, runner, GitTransport(runner, config))

    return make


@pytest.fixture
def stack(stack_factory: Callable[..., Stack]) -> Stack:
    return stack_factory()


def _url(raw: str) -> RemoteUrl:
    return parse_remote_url(raw, allow_http=True, allow_local=True)


def _file_target(remote: BareRemote) -> RemoteTarget:
    return RemoteTarget(_url(remote.url))


def _http_target(
    server: GitHttpServer, repo: str, credential_id: UUID | None, *, insecure: bool = True
) -> RemoteTarget:
    return RemoteTarget(_url(server.url(repo)), credential_id=credential_id, insecure_http=insecure)


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _alive_after(pid: int, within_s: float = 3.0) -> bool:
    deadline = time.monotonic() + within_s
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        await asyncio.sleep(0.05)
    return True


# ── probe ────────────────────────────────────────────────────────────────────


async def test__probe__empty_remote__ok_and_empty(stack: Stack, bare_remote: BareRemote) -> None:
    probe = await stack.transport.probe(_file_target(bare_remote))

    assert (probe.ok, probe.reachable, probe.auth_ok, probe.empty) == (True, True, True, True)
    assert probe.branches == ()
    assert probe.default_branch is None
    assert probe.error is None


async def test__probe__default_branch_is_not_main__reports_it(stack: Stack, tmp_path: Path) -> None:
    remote = make_bare_remote(tmp_path / "trunk.git", branch="trunk")
    seed_remote(remote, {"a.txt": "a"}, branch="trunk")
    seed_remote(remote, {"b.txt": "b"}, branch="feature/x")

    probe = await stack.transport.probe(_file_target(remote))

    assert probe.default_branch == "trunk"
    assert set(probe.branches) == {"trunk", "feature/x"}
    assert probe.empty is False


async def test__probe__missing_repository__not_found_or_no_access(stack: Stack, tmp_path: Path) -> None:
    target = RemoteTarget(_url(f"file://{tmp_path}/nowhere.git"))

    probe = await stack.transport.probe(target)

    assert probe.ok is False
    assert probe.error is not None
    assert probe.error.code is GitErrorCode.not_found_or_no_access
    assert probe.reachable is True
    assert probe.auth_ok is False


async def test__probe__over_http_with_pat__ok_and_credential_marked_used(
    stack: Stack, http_git_server: GitHttpServer
) -> None:
    http_git_server.create_repo("r.git")
    credential_id = await stack.add_pat(token=http_git_server.token or "")

    probe = await stack.transport.probe(_http_target(http_git_server, "r.git", credential_id))

    assert probe.ok is True
    stored = await stack.credentials.get(credential_id)
    assert stored is not None
    assert stored.status is CredentialStatus.ok
    assert stored.last_used_at is not None


async def test__probe__wrong_token__auth_failed_and_credential_marked(
    stack: Stack, http_git_server: GitHttpServer
) -> None:
    http_git_server.create_repo("r.git")
    credential_id = await stack.add_pat(token="ghp_WRONGtokenValue1234567890abcdef")

    probe = await stack.transport.probe(_http_target(http_git_server, "r.git", credential_id))

    assert probe.ok is False
    assert probe.error is not None
    assert probe.error.code is GitErrorCode.auth_failed
    assert probe.reachable is True
    stored = await stack.credentials.get(credential_id)
    assert stored is not None
    assert stored.status is CredentialStatus.auth_failed


async def test__probe__401_without_credential__credentials_missing(
    stack: Stack, http_git_server: GitHttpServer
) -> None:
    http_git_server.create_repo("r.git")

    probe = await stack.transport.probe(_http_target(http_git_server, "r.git", None))

    assert probe.error is not None
    assert probe.error.code is GitErrorCode.credentials_missing


async def test__probe__closed_port__offline(stack: Stack) -> None:
    target = RemoteTarget(_url(f"http://127.0.0.1:{_closed_port()}/r.git"), insecure_http=True)

    probe = await stack.transport.probe(target)

    assert probe.ok is False
    assert probe.error is not None
    assert probe.error.code is GitErrorCode.offline
    assert probe.reachable is False


@_posix_only
async def test__probe__server_hangs__timeout_and_child_is_killed(
    stack_factory: Callable[..., Stack], http_git_server: GitHttpServer
) -> None:
    stack = stack_factory(probe_timeout_s=1.0)
    http_git_server.create_repo("r.git")
    http_git_server.mode = "hang"
    credential_id = await stack.add_pat(token=http_git_server.token or "")

    started = time.monotonic()
    probe = await stack.transport.probe(_http_target(http_git_server, "r.git", credential_id))

    assert probe.error is not None
    assert probe.error.code is GitErrorCode.timeout
    assert time.monotonic() - started < 15
    git_processes = [p for p in stack.spy.processes if p.returncode is not None]
    assert len(git_processes) == len(stack.spy.processes)
    for process in stack.spy.processes:
        assert not await _alive_after(process.pid, within_s=0.2)


async def test__probe__drop_connection__offline(stack: Stack, http_git_server: GitHttpServer) -> None:
    http_git_server.create_repo("r.git")
    http_git_server.mode = "drop"
    credential_id = await stack.add_pat(token=http_git_server.token or "")

    probe = await stack.transport.probe(_http_target(http_git_server, "r.git", credential_id))

    assert probe.ok is False
    assert probe.error is not None
    assert probe.error.code in {GitErrorCode.offline, GitErrorCode.git_error}


# ── secrets ──────────────────────────────────────────────────────────────────


async def test__run__pat__token_absent_from_argv_and_present_only_in_env(
    stack: Stack, http_git_server: GitHttpServer
) -> None:
    http_git_server.create_repo("r.git")
    credential_id = await stack.add_pat(token=http_git_server.token or "")

    await stack.transport.probe(_http_target(http_git_server, "r.git", credential_id))

    token = http_git_server.token or ""
    assert stack.spy.argvs
    assert all(token not in part for argv in stack.spy.argvs for part in argv)
    with_header = [env for env in stack.spy.envs if "GIT_CONFIG_VALUE_0" in env]
    assert len(with_header) == 1
    header = with_header[0]["GIT_CONFIG_VALUE_0"]
    assert header.startswith("Authorization: Basic ")
    assert token in base64.b64decode(header.rsplit(" ", 1)[1]).decode()
    assert with_header[0]["GIT_CONFIG_KEY_0"] == f"http.{http_git_server.base_url}/.extraheader"


async def test__run__pat__token_never_reaches_logs_or_error_text(stack: Stack, http_git_server: GitHttpServer) -> None:
    http_git_server.create_repo("r.git")
    credential_id = await stack.add_pat(token=_TOKEN)

    with structlog.testing.capture_logs() as logs:
        probe = await stack.transport.probe(_http_target(http_git_server, "r.git", credential_id))

    assert probe.error is not None
    assert _TOKEN not in probe.error.detail
    assert _TOKEN not in repr(logs)
    assert any(entry.get("event") == "git remote command finished" for entry in logs)


async def test__run__child_env_has_no_server_secrets_and_a_protocol_allow_list(
    stack: Stack, bare_remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HSE_STUDIO__SECRET_CANARY", "canary")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-canary")
    monkeypatch.setenv("GIT_TRACE", "1")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agent.sock")  # noqa: S108

    await stack.transport.probe(_file_target(bare_remote))

    for env in stack.spy.envs:
        assert not {"HSE_STUDIO__SECRET_CANARY", "OPENAI_API_KEY", "GIT_TRACE", "SSH_AUTH_SOCK"} & set(env)
        assert env["GIT_TERMINAL_PROMPT"] == "0"
    network = [stack.spy.envs[i] for i in stack.spy.network_calls()]
    assert network
    assert all(env["GIT_ALLOW_PROTOCOL"] == "https:ssh:file" for env in network)
    assert all(env["GIT_PROTOCOL_FROM_USER"] == "0" for env in network)


async def test__run__credential_for_another_host__refused_before_spawn(
    stack: Stack, http_git_server: GitHttpServer
) -> None:
    http_git_server.create_repo("r.git")
    credential_id = await stack.add_pat(host="github.com")

    probe = await stack.transport.probe(_http_target(http_git_server, "r.git", credential_id))

    assert probe.error is not None
    assert probe.error.code is GitErrorCode.credential_host_mismatch
    assert stack.spy.network_calls() == []


async def test__run__unknown_credential__credentials_missing(stack: Stack, http_git_server: GitHttpServer) -> None:
    http_git_server.create_repo("r.git")

    probe = await stack.transport.probe(_http_target(http_git_server, "r.git", uuid4()))

    assert probe.error is not None
    assert probe.error.code is GitErrorCode.credentials_missing


async def test__fetch__redirect_to_another_host__header_is_not_leaked(
    stack: Stack, http_git_server_factory: Callable[..., GitHttpServer], studio_pair: StudioPair
) -> None:
    origin = http_git_server_factory()
    evil = http_git_server_factory(token=None)
    origin.create_repo("r.git")
    origin.redirect_to = evil.base_url
    credential_id = await stack.add_pat(token=origin.token or "")

    with pytest.raises(GitSyncError):
        await stack.transport.fetch(
            studio_pair.first.git_dir, _http_target(origin, "r.git", credential_id), branch="main"
        )

    assert evil.requests == [], "with a token redirects must not be followed at all"
    assert evil.authorizations() == []


async def test__fetch__redirect_to_server_with_same_repo__token_does_not_reach_it(
    stack: Stack, http_git_server_factory: Callable[..., GitHttpServer], studio_pair: StudioPair
) -> None:
    # Чужой сервер отдаёт настоящий репозиторий, поэтому git не обрывается после первого прыжка и шлёт на него
    # все следующие запросы (git-upload-pack): заголовок доступа не должен уйти ни в одном из них.
    origin = http_git_server_factory()
    evil = http_git_server_factory(token=None)
    seed_remote(origin.create_repo("r.git"), {"a.txt": "a"})
    seed_remote(evil.create_repo("r.git"), {"a.txt": "a"})
    origin.redirect_to = evil.base_url
    credential_id = await stack.add_pat(token=origin.token or "")

    with pytest.raises(GitSyncError):
        await stack.transport.fetch(
            studio_pair.first.git_dir, _http_target(origin, "r.git", credential_id), branch="main"
        )

    assert evil.authorizations() == []


# ── policy ───────────────────────────────────────────────────────────────────


async def test__run__file_remote_in_server_mode__url_scheme_forbidden(
    stack_factory: Callable[..., Stack], bare_remote: BareRemote
) -> None:
    stack = stack_factory(local_mode=False)

    probe = await stack.transport.probe(_file_target(bare_remote))

    assert probe.error is not None
    assert probe.error.code is GitErrorCode.url_scheme_forbidden
    assert stack.spy.network_calls() == []


async def test__run__plain_http_without_per_remote_flag__url_scheme_forbidden(
    stack: Stack, http_git_server: GitHttpServer
) -> None:
    http_git_server.create_repo("r.git")

    probe = await stack.transport.probe(_http_target(http_git_server, "r.git", None, insecure=False))

    assert probe.error is not None
    assert probe.error.code is GitErrorCode.url_scheme_forbidden


async def test__run__plain_http_when_server_forbids__url_scheme_forbidden(
    stack_factory: Callable[..., Stack], http_git_server: GitHttpServer
) -> None:
    stack = stack_factory(allow_http=False)
    http_git_server.create_repo("r.git")

    probe = await stack.transport.probe(_http_target(http_git_server, "r.git", None))

    assert probe.error is not None
    assert probe.error.code is GitErrorCode.url_scheme_forbidden


async def test__run__ssh_remote_without_known_hosts_store__ssh_unavailable(stack: Stack) -> None:
    probe = await stack.transport.probe(RemoteTarget(parse_remote_url("git@github.com:hse/course.git")))

    assert probe.error is not None
    assert probe.error.code is GitErrorCode.ssh_unavailable


async def test__run__ext_transport_smuggled_past_the_parser__blocked_by_allow_list(
    stack: Stack, tmp_path: Path
) -> None:
    marker = tmp_path / "pwned"
    crafted = RemoteUrl(
        display_url=f"ext::sh -c touch% {marker}",
        kind=RemoteKind.https,
        host="github.com",
        port=None,
        user=None,
        provider=_url("https://github.com/a/b.git").provider,
        owner="a",
        repo="b",
        token_stripped=False,
    )

    probe = await stack.transport.probe(RemoteTarget(crafted))

    assert probe.ok is False
    assert not marker.exists()


async def test__run__file_transport_for_an_https_address__blocked_by_allow_list(
    stack: Stack, bare_remote: BareRemote
) -> None:
    seed_remote(bare_remote, {"a.txt": "a"})
    crafted = RemoteUrl(
        display_url=bare_remote.url,
        kind=RemoteKind.https,
        host="github.com",
        port=None,
        user=None,
        provider=_url("https://github.com/a/b.git").provider,
        owner="a",
        repo="b",
        token_stripped=False,
    )

    probe = await stack.transport.probe(RemoteTarget(crafted))

    assert probe.ok is False
    assert probe.error is not None
    assert "not allowed" in probe.error.detail


# ── fetch and push ───────────────────────────────────────────────────────────


async def test__fetch__file_remote__tracking_ref_points_at_remote_tip(stack: Stack, studio_pair: StudioPair) -> None:
    tip = seed_remote(studio_pair.remote, {"a.txt": "a"})

    await stack.transport.fetch(studio_pair.first.git_dir, _file_target(studio_pair.remote), branch="main")

    assert studio_pair.first.tracking() == tip


async def test__fetch__reports_monotonic_progress_when_git_prints_it(stack: Stack, studio_pair: StudioPair) -> None:
    files = {f"chapter-{i}.tex": f"text {i} " * 400 for i in range(150)}
    seed_remote(studio_pair.remote, files)
    seen: list[float | None] = []

    await stack.transport.fetch(
        studio_pair.first.git_dir,
        _file_target(studio_pair.remote),
        branch="main",
        on_progress=lambda percent, _line: seen.append(percent),
    )

    percents = [p for p in seen if p is not None]
    assert percents, "git was expected to print progress with --progress"
    assert percents == sorted(percents)
    assert percents[0] >= 0
    assert percents[-1] <= 100


async def test__fetch__missing_branch__branch_missing(stack: Stack, studio_pair: StudioPair) -> None:
    seed_remote(studio_pair.remote, {"a.txt": "a"})

    with pytest.raises(GitSyncError) as raised:
        await stack.transport.fetch(studio_pair.first.git_dir, _file_target(studio_pair.remote), branch="release")

    assert raised.value.code is GitErrorCode.branch_missing


@pytest.mark.parametrize("branch", ["-x", "a..b", "with space", "", "HEAD", "x:y"])
async def test__fetch__unsafe_branch_name__rejected_without_spawn(
    stack: Stack, studio_pair: StudioPair, branch: str
) -> None:
    with pytest.raises(GitSyncError) as raised:
        await stack.transport.fetch(studio_pair.first.git_dir, _file_target(studio_pair.remote), branch=branch)

    assert raised.value.code is GitErrorCode.branch_missing
    assert stack.spy.argvs == []


async def test__push__to_empty_remote__creates_branch_and_updates_tracking_ref(
    stack: Stack, studio_pair: StudioPair
) -> None:
    sha = studio_pair.first.head()

    await stack.transport.push(
        studio_pair.first.git_dir, _file_target(studio_pair.remote), local_sha=sha, remote_branch="main"
    )

    assert studio_pair.remote.head("main") == sha
    assert studio_pair.first.tracking() == sha


async def test__push__local_master_to_remote_main__branch_mapping_works(stack: Stack, studio_pair: StudioPair) -> None:
    studio_pair.first.write("notes.txt", "hello")
    sha = studio_pair.first.commit("notes")

    await stack.transport.push(
        studio_pair.first.git_dir, _file_target(studio_pair.remote), local_sha=sha, remote_branch="trunk"
    )

    assert studio_pair.remote.head("trunk") == sha


async def test__push__remote_moved_on__remote_moved_and_nothing_is_overwritten(
    stack: Stack, studio_pair: StudioPair
) -> None:
    target = _file_target(studio_pair.remote)
    studio_pair.first.write("theirs.txt", "first")
    first_sha = studio_pair.first.commit("first")
    await stack.transport.push(studio_pair.first.git_dir, target, local_sha=first_sha, remote_branch="main")
    studio_pair.second.write("mine.txt", "second")
    second_sha = studio_pair.second.commit("second")

    with pytest.raises(GitSyncError) as raised:
        await stack.transport.push(studio_pair.second.git_dir, target, local_sha=second_sha, remote_branch="main")

    assert raised.value.code is GitErrorCode.remote_moved
    assert studio_pair.remote.head("main") == first_sha


@pytest.mark.parametrize("sha", ["main", "HEAD", "--force", "abc", "x" * 40, ""])
async def test__push__not_a_commit_id__rejected_without_spawn(stack: Stack, studio_pair: StudioPair, sha: str) -> None:
    with pytest.raises(GitSyncError):
        await stack.transport.push(
            studio_pair.first.git_dir, _file_target(studio_pair.remote), local_sha=sha, remote_branch="main"
        )

    assert stack.spy.argvs == []


async def test__push__argv_never_has_force_or_bulk_flags(stack: Stack, studio_pair: StudioPair) -> None:
    await stack.transport.push(
        studio_pair.first.git_dir,
        _file_target(studio_pair.remote),
        local_sha=studio_pair.first.head(),
        remote_branch="main",
    )

    push = next(argv for argv in stack.spy.argvs if "push" in argv)
    assert not {"--force", "-f", "--all", "--mirror", "--force-with-lease", "--tags"} & set(push)
    assert "--porcelain" in push
    assert push[push.index("--") + 1] == studio_pair.remote.url


async def test__push__over_http_with_pat__remote_receives_commit(
    stack: Stack, http_git_server: GitHttpServer, studio_pair: StudioPair
) -> None:
    remote = http_git_server.create_repo("r.git")
    credential_id = await stack.add_pat(token=http_git_server.token or "")
    sha = studio_pair.first.head()

    await stack.transport.push(
        studio_pair.first.git_dir,
        _http_target(http_git_server, "r.git", credential_id),
        local_sha=sha,
        remote_branch="main",
    )

    assert remote.head("main") == sha


async def test__push__server_answers_403__forbidden_write(
    stack: Stack, http_git_server: GitHttpServer, studio_pair: StudioPair
) -> None:
    http_git_server.create_repo("r.git")
    http_git_server.mode = "push_403"
    credential_id = await stack.add_pat(token=http_git_server.token or "")

    with pytest.raises(GitSyncError) as raised:
        await stack.transport.push(
            studio_pair.first.git_dir,
            _http_target(http_git_server, "r.git", credential_id),
            local_sha=studio_pair.first.head(),
            remote_branch="main",
        )

    assert raised.value.code is GitErrorCode.forbidden_write
    stored = await stack.credentials.get(credential_id)
    assert stored is not None
    assert stored.status is not CredentialStatus.auth_failed


async def test__two_studios__push_then_fetch_over_http__second_sees_first(
    stack: Stack, http_git_server: GitHttpServer, studio_pair: StudioPair
) -> None:
    http_git_server.create_repo("r.git")
    credential_id = await stack.add_pat(token=http_git_server.token or "")
    target = _http_target(http_git_server, "r.git", credential_id)
    studio_pair.first.write("shared.txt", "from first")
    sha = studio_pair.first.commit("first edit")
    await stack.transport.push(studio_pair.first.git_dir, target, local_sha=sha, remote_branch="main")

    await stack.transport.fetch(studio_pair.second.git_dir, target, branch="main")

    assert studio_pair.second.tracking() == sha
    assert studio_pair.second.git("show", f"{sha}:shared.txt") == "from first"


@_posix_only
async def test__fetch__cancelled_while_server_hangs__child_is_killed(
    stack: Stack, http_git_server: GitHttpServer, studio_pair: StudioPair
) -> None:
    http_git_server.create_repo("r.git")
    http_git_server.mode = "hang"
    credential_id = await stack.add_pat(token=http_git_server.token or "")
    task = asyncio.create_task(
        stack.transport.fetch(
            studio_pair.first.git_dir, _http_target(http_git_server, "r.git", credential_id), branch="main"
        )
    )
    for _ in range(100):
        if http_git_server.requests:
            break
        await asyncio.sleep(0.05)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert stack.spy.processes
    for process in stack.spy.processes:
        assert process.returncode is not None
        assert not await _alive_after(process.pid, within_s=0.2)


# ── tip file ─────────────────────────────────────────────────────────────────


async def test__read_tip_file__file_remote__returns_project_json(stack: Stack, bare_remote: BareRemote) -> None:
    seed_remote(bare_remote, {".hse-studio/project.json": _PROJECT_JSON, "main.tex": "x" * 5000})

    content = await stack.transport.read_tip_file(
        _file_target(bare_remote), branch="main", path=".hse-studio/project.json"
    )

    assert content == _PROJECT_JSON.encode()


async def test__read_tip_file__absent_path__none(stack: Stack, bare_remote: BareRemote) -> None:
    seed_remote(bare_remote, {"readme.md": "hi"})

    content = await stack.transport.read_tip_file(
        _file_target(bare_remote), branch="main", path=".hse-studio/project.json"
    )

    assert content is None


async def test__read_tip_file__missing_branch__branch_missing(stack: Stack, bare_remote: BareRemote) -> None:
    seed_remote(bare_remote, {"readme.md": "hi"})

    with pytest.raises(GitSyncError) as raised:
        await stack.transport.read_tip_file(_file_target(bare_remote), branch="release", path="readme.md")

    assert raised.value.code is GitErrorCode.branch_missing


async def test__read_tip_file__over_http_with_pat__returns_project_json(
    stack: Stack, http_git_server: GitHttpServer
) -> None:
    remote = http_git_server.create_repo("r.git")
    seed_remote(remote, {".hse-studio/project.json": _PROJECT_JSON})
    credential_id = await stack.add_pat(token=http_git_server.token or "")

    content = await stack.transport.read_tip_file(
        _http_target(http_git_server, "r.git", credential_id), branch="main", path=".hse-studio/project.json"
    )

    assert content == _PROJECT_JSON.encode()


@pytest.mark.parametrize("path", ["../etc/passwd", "/etc/passwd", "-x", "a/../../b"])
async def test__read_tip_file__unsafe_path__rejected_without_spawn(
    stack: Stack, bare_remote: BareRemote, path: str
) -> None:
    with pytest.raises(GitSyncError):
        await stack.transport.read_tip_file(_file_target(bare_remote), branch="main", path=path)

    assert stack.spy.argvs == []


async def test__probe__never_leaves_temp_stores_behind(stack: Stack, bare_remote: BareRemote) -> None:
    await stack.transport.probe(_file_target(bare_remote))

    stores = [Path(argv[argv.index("--git-dir") + 1]) for argv in stack.spy.argvs if "--git-dir" in argv]
    assert stores
    assert all(not store.exists() for store in stores)
    assert all(not store.parent.exists() for store in stores)
