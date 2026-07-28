from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from asyncio import subprocess as asubprocess
from collections.abc import AsyncGenerator
from contextlib import suppress
from dataclasses import dataclass

import structlog

from hse_doc_studio.core.compile.docker_diagnosis import (
    DockerUnavailableReason,
    classify_docker_error,
)
from hse_doc_studio.infra.docker.cli import docker_binary

logger = structlog.get_logger()

# Путь сокета фиксирован контрактом compose (deploy/all-in-one/docker-compose.yml):
# именно его мы монтируем и именно его gid нужен для подсказки про group_add.
DOCKER_SOCKET_PATH = "/var/run/docker.sock"

_INSPECT_TIMEOUT_S = 5.0
_VERSION_TIMEOUT_S = 5.0
_LIST_TIMEOUT_S = 10.0
_REMOVE_TIMEOUT_S = 30.0
_HUB_TIMEOUT_S = 10.0
_HUB_PAGE_SIZE = 100
# docker pull can be silent for a while between layer transitions on a slow
# link; we still want some upper bound to detect a truly stuck daemon.
_PULL_IDLE_TIMEOUT_S = 600.0
_PROCESS_TERMINATE_TIMEOUT_S = 5.0


class _PullIdleTimeoutError(Exception):
    """Internal signal: `docker pull` produced no output for too long."""


def docker_socket_gid() -> int | None:
    """gid владельца docker-сокета — чтобы подсказка называла точное число.

    Возвращает None, когда сокета не видно (не смонтирован, запуск не в контейнере
    или ОС без POSIX-владельцев): подсказка тогда обходится общим текстом.
    """
    try:
        return os.stat(DOCKER_SOCKET_PATH).st_gid
    except OSError:
        return None


@dataclass(frozen=True)
class ImageInfo:
    image: str
    id: str
    size_bytes: int
    created: str


@dataclass(frozen=True)
class LocalImageInfo:
    repository: str
    tag: str
    id: str
    size_bytes: int
    created: str

    @property
    def image(self) -> str:
        return f"{self.repository}:{self.tag}"


@dataclass(frozen=True)
class RemoteTagInfo:
    name: str
    size_bytes: int
    last_updated: str | None


@dataclass(frozen=True)
class DockerStatus:
    available: bool
    version: str | None
    detail: str | None
    # Машиночитаемая причина недоступности + всё, что нужно фронтенду, чтобы
    # выдать готовую команду починки вместо сырого stderr.
    reason: DockerUnavailableReason | None = None
    socket_gid: int | None = None


class DockerImageManager:
    """Thin wrapper around `docker` CLI for image lifecycle queries.

    Uses the same docker binary the compile executor calls — so if compile
    works, this works, and vice versa. Used by the API to surface install
    state to the UI and stream `docker pull` output back to the user.
    """

    async def docker_status(self) -> DockerStatus:
        try:
            proc = await asyncio.create_subprocess_exec(
                docker_binary(),
                "version",
                "--format",
                "{{.Server.Version}}",
                stdout=asubprocess.PIPE,
                stderr=asubprocess.PIPE,
            )
        except OSError as exc:
            return DockerStatus(
                available=False,
                version=None,
                detail=f"docker CLI not found: {exc}",
                reason=DockerUnavailableReason.CLI_MISSING,
            )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_VERSION_TIMEOUT_S)
        except asyncio.TimeoutError:
            await _terminate_process(proc)
            return DockerStatus(
                available=False,
                version=None,
                detail="docker version timed out",
                reason=DockerUnavailableReason.TIMEOUT,
            )

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            reason = classify_docker_error(err)
            return DockerStatus(
                available=False,
                version=None,
                detail=err or "docker daemon unreachable",
                reason=reason,
                # gid читаем только когда он реально нужен для подсказки.
                socket_gid=(docker_socket_gid() if reason is DockerUnavailableReason.SOCKET_PERMISSION else None),
            )

        version = stdout.decode("utf-8", errors="replace").strip() or None
        return DockerStatus(available=True, version=version, detail=None)

    async def inspect(self, image: str) -> ImageInfo | None:
        """Return image metadata if present locally, else None.

        Uses `docker image inspect` which is a metadata-only call — no
        network, no daemon-heavy work. Suitable for preflight checks.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                docker_binary(),
                "image",
                "inspect",
                image,
                stdout=asubprocess.PIPE,
                stderr=asubprocess.PIPE,
            )
        except OSError as exc:
            logger.warning("docker inspect: CLI not found", exc=str(exc))
            return None

        try:
            stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=_INSPECT_TIMEOUT_S)
        except asyncio.TimeoutError:
            await _terminate_process(proc)
            return None

        if proc.returncode != 0:
            return None

        try:
            data = json.loads(stdout.decode("utf-8", errors="replace"))
            if not data:
                return None
            entry = data[0]
            return ImageInfo(
                image=image,
                id=str(entry.get("Id", "")),
                size_bytes=int(entry.get("Size", 0)),
                created=str(entry.get("Created", "")),
            )
        except (json.JSONDecodeError, ValueError, IndexError, KeyError) as exc:
            logger.warning("docker inspect: bad json", image=image, exc=str(exc))
            return None

    async def list_local(self, repo: str) -> list[LocalImageInfo]:
        """List all locally-installed tags for the given repo via `docker images`.

        Uses a pipe-separated output format so we get byte-accurate sizes
        through a follow-up `docker image inspect` per row — `docker images`'s
        `Size` is a human-readable string ("3.2 GB") that we don't want to parse.
        """
        stdout = await self._run_docker_images(repo)
        if stdout is None:
            return []

        result: list[LocalImageInfo] = []
        for raw in stdout.splitlines():
            row = _parse_images_row(raw)
            if row is None:
                continue
            repository, tag, image_id, created = row
            # Fetch the precise byte size via inspect — `docker images`'s `Size`
            # column rounds to MB/GB and isn't a number.
            info = await self.inspect(f"{repository}:{tag}")
            size_bytes = info.size_bytes if info is not None else 0
            result.append(
                LocalImageInfo(
                    repository=repository,
                    tag=tag,
                    id=image_id,
                    size_bytes=size_bytes,
                    created=created,
                )
            )
        return result

    async def _run_docker_images(self, repo: str) -> str | None:
        """Run `docker images <repo>` and return its raw stdout.

        Returns None when docker is missing, hangs or exits non-zero — all of
        which the caller reports as "no local images" rather than an error.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                docker_binary(),
                "images",
                repo,
                "--no-trunc",
                "--format",
                "{{.Repository}}|{{.Tag}}|{{.ID}}|{{.CreatedAt}}",
                stdout=asubprocess.PIPE,
                stderr=asubprocess.PIPE,
            )
        except OSError as exc:
            logger.warning("docker images: CLI not found", exc=str(exc))
            return None

        try:
            stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=_LIST_TIMEOUT_S)
        except asyncio.TimeoutError:
            await _terminate_process(proc)
            return None

        if proc.returncode != 0:
            return None

        return stdout.decode("utf-8", errors="replace")

    async def list_remote_tags(
        self,
        repo: str,
        hub_base: str,
    ) -> list[RemoteTagInfo]:
        """Query Docker Hub for available tags of a repo.

        Pulls the first page (newest first) — that's typically more than
        enough; surfacing 5 years of weekly tags would just be noise. No
        auth needed for public repos. Returns an empty list on any error
        instead of raising, so a transient network blip in the UI just
        shows "no remote tags" rather than a hard failure.
        """
        url = f"{hub_base.rstrip('/')}/repositories/{repo}/tags?page_size={_HUB_PAGE_SIZE}&ordering=last_updated"
        try:
            payload = await asyncio.to_thread(_http_get_json, url)
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as exc:
            logger.warning("docker hub: tag fetch failed", repo=repo, exc=str(exc))
            return []

        # `payload` is untyped JSON: keep the shape check here so the loop below
        # works on a real list instead of whatever Hub happened to return.
        entries = payload.get("results")
        if not isinstance(entries, list):
            return []

        result: list[RemoteTagInfo] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                continue
            size_raw = entry.get("full_size", 0)
            try:
                size_bytes = int(size_raw)
            except (TypeError, ValueError):
                size_bytes = 0
            last_updated_raw = entry.get("last_updated")
            last_updated = last_updated_raw if isinstance(last_updated_raw, str) else None
            result.append(
                RemoteTagInfo(
                    name=name,
                    size_bytes=size_bytes,
                    last_updated=last_updated,
                )
            )
        return result

    async def remove(self, image: str) -> tuple[bool, str | None]:
        """Remove a local image via `docker image rm <image>`.

        Returns `(removed, error_detail)`. Refuses to force; if the image
        is in use by a stopped container, docker will fail and we surface
        that to the user instead of silently force-rm'ing it.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                docker_binary(),
                "image",
                "rm",
                image,
                stdout=asubprocess.PIPE,
                stderr=asubprocess.PIPE,
            )
        except OSError as exc:
            return False, f"docker CLI not found: {exc}"

        try:
            _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_REMOVE_TIMEOUT_S)
        except asyncio.TimeoutError:
            await _terminate_process(proc)
            return False, "docker image rm timed out"

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            return False, err or "docker image rm failed"
        return True, None

    async def pull(self, image: str) -> AsyncGenerator[str, None]:
        """Stream `docker pull <image>` output line by line.

        The terminal sentinel `__DONE__` / `__FAILED__` is yielded last so
        the consumer can distinguish completion from disconnect.
        """
        return self._pull_stream(image)

    async def _pull_stream(self, image: str) -> AsyncGenerator[str, None]:
        yield f"[pull] starting docker pull {image}"
        try:
            proc = await asyncio.create_subprocess_exec(
                docker_binary(),
                "pull",
                image,
                stdout=asubprocess.PIPE,
                stderr=asubprocess.STDOUT,
            )
        except OSError as exc:
            yield f"[error] docker pull failed to start: {exc}"
            yield "__FAILED__"
            return

        assert proc.stdout is not None  # noqa: S101

        try:
            async for line in _read_pull_lines(proc.stdout):
                yield line
        except _PullIdleTimeoutError:
            yield f"[error] no output for {_PULL_IDLE_TIMEOUT_S:.0f}s, killing pull"
            await _terminate_process(proc)
            yield "__FAILED__"
            return
        except asyncio.CancelledError:
            await _terminate_process(proc)
            raise

        await proc.wait()
        if proc.returncode != 0:
            yield f"[error] docker pull exited with code {proc.returncode}"
            yield "__FAILED__"
            return

        yield f"[pull] done: {image}"
        yield "__DONE__"


def _parse_images_row(raw: str) -> tuple[str, str, str, str] | None:
    """Split one `{{.Repository}}|{{.Tag}}|{{.ID}}|{{.CreatedAt}}` row.

    Returns None for blank or short rows, and for dangling images (left over
    from interrupted pulls) — skipped because they aren't useful to surface in
    the UI and would clutter the list.
    """
    line = raw.strip()
    if not line:
        return None
    parts = line.split("|")
    if len(parts) < 4:
        return None
    repository, tag, image_id, created = parts[0], parts[1], parts[2], parts[3]
    if tag == "<none>" or repository == "<none>":
        return None
    return repository, tag, image_id, created


async def _read_pull_lines(stdout: asyncio.StreamReader) -> AsyncGenerator[str, None]:
    """Yield decoded lines of a running `docker pull` until its stdout hits EOF.

    Raises `_PullIdleTimeoutError` when the stream stays silent longer than
    `_PULL_IDLE_TIMEOUT_S`, so the caller can kill a stuck daemon; normal quiet
    stretches between layer transitions stay well inside that bound.
    """
    while True:
        try:
            raw_line = await asyncio.wait_for(stdout.readline(), timeout=_PULL_IDLE_TIMEOUT_S)
        except asyncio.TimeoutError as exc:
            raise _PullIdleTimeoutError from exc
        if not raw_line:
            return
        yield raw_line.decode("utf-8", errors="replace").rstrip()


def _http_get_json(url: str) -> dict[str, object]:
    """Sync HTTP GET that the manager schedules via `asyncio.to_thread`.

    Kept synchronous so we don't pull `httpx`/`aiohttp` into the dep tree
    just for one Docker Hub call. stdlib `urllib` is enough.
    """
    req = urllib.request.Request(  # noqa: S310 - URL validated by caller
        url,
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=_HUB_TIMEOUT_S) as resp:  # noqa: S310
        body = resp.read()
    parsed = json.loads(body.decode("utf-8"))
    if not isinstance(parsed, dict):
        return {}
    return parsed


async def _terminate_process(proc: asubprocess.Process) -> None:
    if proc.returncode is not None:
        return
    with suppress(ProcessLookupError):
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=_PROCESS_TERMINATE_TIMEOUT_S)
    except asyncio.TimeoutError:
        with suppress(ProcessLookupError):
            proc.kill()
