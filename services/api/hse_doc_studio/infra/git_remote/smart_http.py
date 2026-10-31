"""git Smart HTTP без CGI: прямой запуск `git upload-pack` и `git receive-pack` в режиме stateless-rpc.

Конфигурация хранилища недоверенная: поверх неё ставятся `hardened_git_config()` и скрытие служебных ссылок;
окружение собирается по белому списку (`base_git_env`). Тело запроса стримится в stdin (с распаковкой gzip и
пределом размера), ответ стримится из stdout; отмена клиента и таймаут убивают процесс.
"""

from __future__ import annotations

import asyncio
import contextlib
import zlib
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path

import structlog

from hse_doc_studio.core.git_remote.entities import GitService
from hse_doc_studio.core.git_remote.protocols import (
    GitBodyInvalidError,
    GitBodyTooLargeError,
    GitRpcOutcome,
)
from hse_doc_studio.infra.vcs.git_env import base_git_env, hardened_git_config

logger = structlog.get_logger()

_CHUNK = 64 * 1024
_STDERR_TAIL = 4096
_PROTOCOLS = frozenset({"version=1", "version=2"})
_HIDDEN_REFS = ("refs/hse", "refs/remotes", "refs/tags")


def pkt_line(text: str) -> bytes:
    data = text.encode()
    return f"{len(data) + 4:04x}".encode() + data


def git_protocol(header: str | None) -> str | None:
    """Из заголовка `Git-Protocol` берутся только известные значения: остальное в git не передаётся."""
    if header is None:
        return None
    values = [part.strip() for part in header.split(":") if part.strip() in _PROTOCOLS]
    return values[-1] if values else None


def common_config() -> list[str]:
    """Общие `-c` обоих сервисов: защита стора и видимость только веток и HEAD."""
    args = [*hardened_git_config()]
    for ref in _HIDDEN_REFS:
        args += ["-c", f"uploadpack.hideRefs={ref}", "-c", f"receive.hideRefs={ref}"]
    args += [
        "-c",
        "uploadpack.allowFilter=true",
        "-c",
        "uploadpack.allowAnySHA1InWant=false",
        "-c",
        "uploadpack.allowReachableSHA1InWant=false",
        "-c",
        "uploadpack.allowTipSHA1InWant=false",
        "-c",
        "safe.directory=*",
    ]
    return args


def git_args(service: GitService, git_dir: Path, *, advertise: bool, extra_config: Sequence[str] = ()) -> list[str]:
    command = service.value.removeprefix("git-")
    args = ["git", *common_config(), *extra_config, command, "--stateless-rpc"]
    if advertise:
        args.append("--advertise-refs")
    return [*args, str(git_dir)]


def git_env(protocol: str | None, extra_env: Mapping[str, str] | None = None) -> dict[str, str]:
    env = base_git_env()
    if protocol is not None:
        env["GIT_PROTOCOL"] = protocol
    if extra_env:
        env.update(extra_env)
    return env


class BodyReader:
    """Тело запроса: распаковка gzip по ходу и счётчик байтов (и сжатых, и распакованных)."""

    def __init__(self, source: AsyncIterator[bytes], *, gzip: bool, max_bytes: int) -> None:
        self._source = source
        self._max = max_bytes
        self._seen = 0
        self._inflate = zlib.decompressobj(16 + zlib.MAX_WBITS) if gzip else None

    def _count(self, size: int) -> None:
        self._seen += size
        if self._seen > self._max:
            raise GitBodyTooLargeError

    def _decode(self, raw: bytes) -> bytes:
        if self._inflate is None:
            self._count(len(raw))
            return raw
        try:
            data = self._inflate.decompress(raw, self._max + 1 - self._seen)
        except zlib.error as exc:
            raise GitBodyInvalidError from exc
        self._count(len(data))
        if self._inflate.unconsumed_tail:
            raise GitBodyTooLargeError
        return data

    def _finish(self) -> bytes:
        if self._inflate is None:
            return b""
        try:
            rest = self._inflate.flush()
        except zlib.error as exc:
            raise GitBodyInvalidError from exc
        self._count(len(rest))
        return rest

    async def chunks(self) -> AsyncIterator[bytes]:
        async for raw in self._source:
            if raw and (data := self._decode(raw)):
                yield data
        if rest := self._finish():
            yield rest


class GitSmartHttp:
    def __init__(self, *, max_body_bytes: int, timeout_s: float) -> None:
        self._max_body = max_body_bytes
        self._timeout = timeout_s

    async def advertise(self, service: GitService, git_dir: Path, *, protocol: str | None) -> bytes:
        proc = await asyncio.create_subprocess_exec(
            *git_args(service, git_dir, advertise=True),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=git_env(protocol),
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except BaseException:
            _kill(proc)
            await proc.wait()
            raise
        if proc.returncode != 0:
            logger.warning("git advertise failed", service=service.value, stderr=err.decode(errors="replace")[-500:])
            raise RuntimeError(f"git {service.value} --advertise-refs exited with {proc.returncode}")
        if protocol == "version=2":
            return out
        return pkt_line(f"# service={service.value}\n") + b"0000" + out

    async def rpc(  # noqa: PLR0913 — параметры одного запуска git
        self,
        service: GitService,
        git_dir: Path,
        body: AsyncIterator[bytes],
        *,
        gzip: bool,
        protocol: str | None,
        extra_config: Sequence[str] = (),
        extra_env: Mapping[str, str] | None = None,
        outcome: list[GitRpcOutcome] | None = None,
    ) -> AsyncIterator[bytes]:
        proc = await asyncio.create_subprocess_exec(
            *git_args(service, git_dir, advertise=False, extra_config=extra_config),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=git_env(protocol, extra_env),
        )
        reader = BodyReader(body, gzip=gzip, max_bytes=self._max_body)
        feed = asyncio.create_task(_feed(proc, reader))
        stderr = asyncio.create_task(_tail(proc.stderr))
        deadline = asyncio.get_running_loop().time() + self._timeout
        timed_out = [False]
        try:
            async for chunk in _stdout(proc, deadline, timed_out):
                yield chunk
            if timed_out[0]:
                _kill(proc)
            # Ошибка тела (слишком большое, битый gzip) всплывает здесь: ответ уже мог начаться, процесс убит.
            await feed
        finally:
            if not feed.done():
                feed.cancel()
            if proc.returncode is None:
                _kill(proc)
            with contextlib.suppress(Exception):
                await proc.wait()
            tail = ""
            with contextlib.suppress(Exception):
                tail = await stderr
            if outcome is not None:
                outcome.append(GitRpcOutcome(proc.returncode, tail, timed_out[0]))
            if proc.returncode not in (0, None):
                logger.info("git rpc finished", service=service.value, code=proc.returncode, stderr=tail[-500:])


async def _stdout(proc: asyncio.subprocess.Process, deadline: float, timed_out: list[bool]) -> AsyncIterator[bytes]:
    """Вывод процесса до конца или до общего срока; срок отмечается в `timed_out`."""
    assert proc.stdout is not None  # noqa: S101 — PIPE задан выше
    loop = asyncio.get_running_loop()
    while (remaining := deadline - loop.time()) > 0:
        try:
            chunk = await asyncio.wait_for(proc.stdout.read(_CHUNK), timeout=remaining)
        except TimeoutError:
            break
        if not chunk:
            return
        yield chunk
    timed_out[0] = True


async def _feed(proc: asyncio.subprocess.Process, reader: BodyReader) -> None:
    assert proc.stdin is not None  # noqa: S101 — PIPE задан выше
    try:
        async for chunk in reader.chunks():
            proc.stdin.write(chunk)
            await proc.stdin.drain()
    except (GitBodyTooLargeError, GitBodyInvalidError):
        _kill(proc)
        raise
    except (BrokenPipeError, ConnectionResetError):
        return
    finally:
        with contextlib.suppress(Exception):
            proc.stdin.close()


async def _tail(stream: asyncio.StreamReader | None) -> str:
    if stream is None:
        return ""
    buffer = b""
    while chunk := await stream.read(_CHUNK):
        buffer = (buffer + chunk)[-_STDERR_TAIL:]
    return buffer.decode(errors="replace")


def _kill(proc: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
