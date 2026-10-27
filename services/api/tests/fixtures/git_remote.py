"""Удалённые репозитории для тестов Git-синхронизации: без сети и без внешних сервисов.

- `bare_remote` и `seed_remote`: голый репозиторий, на который смотрит адрес file://.
- `studio_pair`: две папки проекта со своими изолированными хранилищами и общий удалённый
  репозиторий: сценарий «два Студио» целиком на диске.
- `http_git_server`: настоящий `git http-backend` за Basic-авторизацией на 127.0.0.1. Умеет
  отвечать 403 на отправку, зависать, рвать соединение и перенаправлять на другой сервер, а все
  запросы записывает, чтобы тест видел, какие заголовки реально дошли.
- `fake_ssh`: скрипт под именем ssh. Записывает аргументы и состояние файла ключа в момент запуска
  и отвечает заданным сбоем, как настоящий ssh (отказ ключа, неизвестный или сменившийся ключ хоста,
  обрыв сети) либо зависает, чтобы проверить отмену.

Фикстуры не пропускают тест молча там, где git обязан быть (CI): без git или без http-backend
под переменной окружения CI тест падает, а не пропускается.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from hse_doc_studio.core.enums import VcsCommitKind
from hse_doc_studio.core.vcs.constants import DEFAULT_VCS_EXCLUDE
from hse_doc_studio.infra.vcs.git_env import base_git_env
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService

from tests.factories import make_project
from tests.fixtures.tls import TlsMaterial

_IDENTITY = {
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "author@test.local",
    "GIT_COMMITTER_NAME": "Test Author",
    "GIT_COMMITTER_EMAIL": "author@test.local",
}
_BACKEND_TIMEOUT_S = 60
_HANG_LIMIT_S = 60.0


def _unavailable(reason: str) -> None:
    """В CI отсутствие git это поломка окружения, а не повод пропустить проверки."""
    if os.environ.get("CI"):
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason)


def git_binary_available() -> bool:
    return shutil.which("git") is not None


def http_backend_available() -> bool:
    if not git_binary_available():
        return False
    result = subprocess.run(  # noqa: S603 — фиксированная команда проверки
        ["git", "http-backend"],  # noqa: S607
        capture_output=True,
        check=False,
        timeout=_BACKEND_TIMEOUT_S,
        env={**base_git_env(), "REQUEST_METHOD": "GET", "GIT_PROJECT_ROOT": os.devnull},
    )
    return b"Status:" in result.stdout


def require_git() -> None:
    if not git_binary_available():
        _unavailable("git binary not available")


def require_http_backend() -> None:
    require_git()
    if not http_backend_available():
        _unavailable("git http-backend not available")


def git_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    return {**base_git_env(), **_IDENTITY, **(extra or {})}


def run_git(
    *args: str,
    cwd: Path | None = None,
    git_dir: Path | None = None,
    work_tree: Path | None = None,
    check: bool = True,
) -> str:
    """Синхронный git для подготовки данных теста; возвращает stdout без хвостового перевода строки."""
    argv = ["git"]
    if git_dir is not None:
        argv += ["--git-dir", str(git_dir)]
    if work_tree is not None:
        argv += ["--work-tree", str(work_tree)]
    result = subprocess.run(  # noqa: S603 — аргументы собирает тест
        [*argv, *args],
        cwd=cwd,
        env=git_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=_BACKEND_TIMEOUT_S,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed ({result.returncode}): {result.stderr}")
    return result.stdout.rstrip("\n")


@dataclass(frozen=True)
class BareRemote:
    path: Path

    @property
    def url(self) -> str:
        return f"file://{self.path}"

    def git(self, *args: str, check: bool = True) -> str:
        return run_git(*args, git_dir=self.path, check=check)

    def head(self, branch: str = "main") -> str | None:
        out = self.git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
        return out or None


def make_bare_remote(path: Path, *, branch: str = "main") -> BareRemote:
    require_git()
    path.parent.mkdir(parents=True, exist_ok=True)
    run_git("init", "--bare", "--quiet", f"--initial-branch={branch}", str(path))
    run_git("config", "http.receivepack", "true", git_dir=path)
    return BareRemote(path)


def seed_remote(
    remote: BareRemote,
    files: Mapping[str, str | bytes],
    *,
    branch: str = "main",
    message: str = "seed",
    work: Path | None = None,
) -> str:
    """Положить в голый репозиторий коммит с файлами через временную рабочую копию; возвращает его sha."""
    work = work or remote.path.parent / f"{remote.path.name}.seed"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    run_git("init", "--quiet", f"--initial-branch={branch}", str(work))
    if remote.head(branch):
        run_git("fetch", "--quiet", remote.url, f"refs/heads/{branch}", cwd=work)
        run_git("reset", "--quiet", "--hard", "FETCH_HEAD", cwd=work)
    for rel, content in files.items():
        target = work / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode())
    run_git("add", "-A", cwd=work)
    run_git("commit", "--quiet", "--allow-empty", "-m", message, cwd=work)
    sha = run_git("rev-parse", "HEAD", cwd=work)
    run_git("push", "--quiet", remote.url, f"HEAD:refs/heads/{branch}", cwd=work)
    shutil.rmtree(work, ignore_errors=True)
    return sha


class StudioStore:
    """Папка проекта с изолированным хранилищем `.hse-studio/git`, как у настоящего проекта."""

    def __init__(self, folder: Path, *, branch: str = "main", files: Mapping[str, str | bytes] | None = None) -> None:
        """`files` попадают в корневой коммит: у разных проектов корни различаются, как в жизни."""
        folder.mkdir(parents=True, exist_ok=True)
        self.folder = folder
        self.git_dir = folder / ".hse-studio" / "git"
        self.project = make_project(folder=folder)
        self._service = GitVcsService(
            author_name="Test Author", author_email="author@test.local", default_branch=branch
        )
        for rel, content in (files if files is not None else {"seed.txt": str(self.project.id)}).items():
            self.write(rel, content)
        self._service.init(self.project, list(DEFAULT_VCS_EXCLUDE))

    def write(self, rel: str, content: str | bytes) -> None:
        target = self.folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode())

    def commit(self, message: str = "edit") -> str:
        commit = self._service.commit(self.project, message=message, kind=VcsCommitKind.manual)
        assert commit is not None, "nothing to commit"
        return commit.id

    def git(self, *args: str, check: bool = True) -> str:
        return run_git(*args, git_dir=self.git_dir, work_tree=self.folder, check=check)

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def tracking(self, branch: str = "main") -> str | None:
        return self.git("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}", check=False) or None


@dataclass(frozen=True)
class StudioPair:
    remote: BareRemote
    first: StudioStore
    second: StudioStore


@pytest.fixture
def bare_remote(tmp_path: Path) -> BareRemote:
    return make_bare_remote(tmp_path / "remotes" / "origin.git")


@pytest.fixture
def studio_pair(tmp_path: Path, bare_remote: BareRemote) -> StudioPair:
    return StudioPair(
        remote=bare_remote,
        first=StudioStore(tmp_path / "first" / "project"),
        second=StudioStore(tmp_path / "second" / "project"),
    )


@dataclass(frozen=True)
class RecordedRequest:
    method: str
    path: str
    headers: Mapping[str, str]

    @property
    def authorization(self) -> str | None:
        return self.headers.get("authorization")


# Ответ тестового API хостинга: статус, заголовки, тело JSON.
ApiReply = tuple[int, Mapping[str, str], object]
ApiHandler = Callable[[Mapping[str, str]], ApiReply]


@dataclass
class GitHttpServer:
    """git http-backend на 127.0.0.1:0. Режимы переключаются на ходу полем `mode`.

    `tls` включает https. `api` отвечает JSON на пути вида `/api/v4/version` до проверки доступа к git: так один
    сервер изображает и git, и API хостинга (GitLab, GitHub Enterprise, Gitea) для проверки определения провайдера.
    """

    root: Path
    token: str | None
    mode: str = "ok"
    redirect_to: str | None = None
    tls: TlsMaterial | None = None
    api: dict[str, ApiHandler] = field(default_factory=dict)
    requests: list[RecordedRequest] = field(default_factory=list)
    _server: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    _release: threading.Event = field(default_factory=threading.Event)

    @property
    def port(self) -> int:
        assert self._server is not None
        return int(self._server.server_address[1])

    @property
    def base_url(self) -> str:
        return f"{'https' if self.tls else 'http'}://127.0.0.1:{self.port}"

    def url(self, repo: str) -> str:
        return f"{self.base_url}/{repo}"

    def create_repo(self, name: str = "origin.git") -> BareRemote:
        return make_bare_remote(self.root / name)

    def authorizations(self) -> list[str]:
        return [request.authorization for request in self.requests if request.authorization]

    def basic(self, user: str = "x-access-token") -> str:
        assert self.token is not None
        return "Basic " + base64.b64encode(f"{user}:{self.token}".encode()).decode()

    def start(self) -> None:
        owner = self

        class Handler(_GitHandler):
            server_state = owner

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        if self.tls is not None:
            self._server.socket = self.tls.server_context().wrap_socket(self._server.socket, server_side=True)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._release.set()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=10)


class _GitHandler(BaseHTTPRequestHandler):
    server_state: GitHttpServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def do_GET(self) -> None:  # noqa: N802
        self._serve()

    def do_POST(self) -> None:  # noqa: N802
        self._serve()

    def _serve(self) -> None:
        state = self.server_state
        state.requests.append(
            RecordedRequest(self.command, self.path, {key.lower(): value for key, value in self.headers.items()})
        )
        body = self._read_body()
        if state.mode == "drop":
            self.close_connection = True
            self.connection.close()
            return
        if state.mode == "hang":
            state._release.wait(_HANG_LIMIT_S)
            self.close_connection = True
            return
        api = state.api.get(urlsplit(self.path).path)
        if api is not None:
            status, headers, payload = api(state.requests[-1].headers)
            self._reply(status, {"Content-Type": "application/json", **headers}, json.dumps(payload).encode())
            return
        if state.redirect_to is not None:
            self._reply(302, {"Location": state.redirect_to.rstrip("/") + self.path}, b"")
            return
        user = self._authenticated_user()
        if state.token is not None and user is None:
            self._reply(401, {"WWW-Authenticate": 'Basic realm="git"'}, b"unauthorized")
            return
        if state.mode == "push_403" and "git-receive-pack" in self.path:
            self._reply(403, {}, b"forbidden")
            return
        self._cgi(body, user or "anonymous")

    def _authenticated_user(self) -> str | None:
        state = self.server_state
        header = self.headers.get("Authorization", "")
        if state.token is None or not header.startswith("Basic "):
            return None
        try:
            user, _, password = base64.b64decode(header[6:]).decode().partition(":")
        except ValueError:
            return None
        return user if hmac.compare_digest(password.encode(), state.token.encode()) else None

    def _read_body(self) -> bytes:
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            chunks = bytearray()
            while True:
                size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    self.rfile.readline()
                    return bytes(chunks)
                chunks += self.rfile.read(size)
                self.rfile.readline()
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def _cgi(self, body: bytes, user: str) -> None:
        parts = urlsplit(self.path)
        env = {
            **base_git_env(),
            "GIT_PROJECT_ROOT": str(self.server_state.root),
            "GIT_HTTP_EXPORT_ALL": "1",
            "REQUEST_METHOD": self.command,
            "PATH_INFO": parts.path,
            "QUERY_STRING": parts.query,
            "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            "CONTENT_LENGTH": str(len(body)),
            "REMOTE_USER": user,
            "REMOTE_ADDR": "127.0.0.1",
        }
        if self.headers.get("Content-Encoding"):
            env["HTTP_CONTENT_ENCODING"] = self.headers["Content-Encoding"]
        if self.headers.get("Git-Protocol"):
            env["HTTP_GIT_PROTOCOL"] = self.headers["Git-Protocol"]
        result = subprocess.run(  # noqa: S603 — фиксированная команда тестового сервера
            ["git", "http-backend"],  # noqa: S607
            input=body,
            env=env,
            capture_output=True,
            check=False,
            timeout=_BACKEND_TIMEOUT_S,
        )
        raw_headers, _, payload = result.stdout.partition(b"\r\n\r\n")
        status = 200
        headers: dict[str, str] = {}
        for line in raw_headers.decode("latin-1").split("\r\n"):
            name, _, value = line.partition(":")
            if name.lower() == "status":
                status = int(value.strip().split(" ", 1)[0])
            elif name:
                headers[name] = value.strip()
        self._reply(status, headers, payload)

    def _reply(self, status: int, headers: Mapping[str, str], payload: bytes) -> None:
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(_one_line(name), _one_line(value))
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _one_line(text: str) -> str:
    return text.replace("\r", "").replace("\n", "")


@pytest.fixture
def http_git_server_factory(tmp_path: Path) -> Iterator[Callable[..., GitHttpServer]]:
    require_http_backend()
    servers: list[GitHttpServer] = []

    def make(*, token: str | None = "pat-token-0123456789", tls: TlsMaterial | None = None) -> GitHttpServer:
        server = GitHttpServer(root=tmp_path / f"http-root-{len(servers)}", token=token, tls=tls)
        server.root.mkdir(parents=True)
        server.start()
        servers.append(server)
        return server

    yield make
    for server in servers:
        server.stop()


@pytest.fixture
def http_git_server(http_git_server_factory: Callable[..., GitHttpServer]) -> GitHttpServer:
    return http_git_server_factory()


_FAKE_SSH_SCRIPT = """#!{python}
import json, os, stat, sys, time
here = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[1:]
key = argv[argv.index("-i") + 1] if "-i" in argv else None
state = None
if key is not None and os.path.exists(key):
    directory = os.path.dirname(key)
    state = {{
        "mode": oct(stat.S_IMODE(os.stat(key).st_mode)),
        "dir_mode": oct(stat.S_IMODE(os.stat(directory).st_mode)),
        "dir": directory,
        "key": key,
    }}
with open(os.path.join(here, "calls.jsonl"), "a") as log:
    log.write(json.dumps({{"argv": argv, "key": state, "env": sorted(os.environ), "pid": os.getpid()}}) + "\\n")
mode = open(os.path.join(here, "mode")).read().strip()
targets = [a for a in argv if "@" in a]
host = targets[-1].split("@")[-1] if targets else "host"
if mode == "hang":
    time.sleep(120)
tail = "fatal: Could not read from remote repository.\\n"
strict = " and you have requested strict checking.\\n"
messages = {{
    "auth_failed": "git@" + host + ": Permission denied (publickey).\\n" + tail,
    "host_unknown": "No ED25519 host key is known for " + host + strict + "Host key verification failed.\\n" + tail,
    "host_changed": "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!\\nOffending ED25519 key in k:1\\n" + tail,
    "network": "ssh: Could not resolve hostname " + host + ": Name or service not known\\n" + tail,
}}
sys.stderr.write(messages[mode])
sys.exit(255)
"""


@dataclass(frozen=True)
class FakeSsh:
    path: Path

    def mode(self, name: str) -> None:
        (self.path.parent / "mode").write_text(name)

    def calls(self) -> list[dict[str, Any]]:
        log = self.path.parent / "calls.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def wait_for_call(self, timeout_s: float = 10.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if calls := self.calls():
                return calls[-1]
            time.sleep(0.02)
        raise AssertionError("fake ssh was not started")


@pytest.fixture
def fake_ssh(tmp_path: Path) -> FakeSsh:
    require_git()
    directory = tmp_path / "fake-ssh"
    directory.mkdir()
    script = directory / "ssh"
    script.write_text(_FAKE_SSH_SCRIPT.format(python=sys.executable))
    script.chmod(0o755)
    fake = FakeSsh(script)
    fake.mode("auth_failed")
    return fake
