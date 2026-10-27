"""Что есть в системе для сетевого git: версия git и клиент ssh. Проверяется один раз и запоминается."""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
from pathlib import Path

from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode

_VERSION = re.compile(r"git version (\d+)\.(\d+)(?:\.(\d+))?")
_VERSION_TIMEOUT_S = 10.0

GitVersion = tuple[int, int, int]


def parse_git_version(text: str) -> GitVersion | None:
    """`git version 2.54.0 (Apple Git-157)` или `git version 2.31.0.windows.1` в (2, 54, 0)."""
    match = _VERSION.search(text)
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def parse_min_version(text: str) -> tuple[int, int]:
    major, _, minor = text.partition(".")
    return int(major), int(minor or 0)


class GitCapabilities:
    """`git --version` запускается один раз; старый или отсутствующий git даёт git_unavailable."""

    def __init__(self, *, git_binary: str = "git", min_version: str = "2.31", ssh_binary: str = "ssh") -> None:
        self._git = git_binary
        self._minimum = parse_min_version(min_version)
        self._ssh = ssh_binary
        self._version: GitVersion | None = None
        self._lock = asyncio.Lock()

    @property
    def git_binary(self) -> str:
        return self._git

    def ssh_path(self) -> str | None:
        """Путь к клиенту ssh или None, если его нет в системе."""
        return shutil.which(self._ssh)

    async def ensure_git(self, *, cwd: Path, env: dict[str, str]) -> GitVersion:
        if self._version is not None:
            return self._version
        async with self._lock:
            if self._version is None:
                self._version = await self._detect(cwd=cwd, env=env)
            return self._version

    async def _detect(self, *, cwd: Path, env: dict[str, str]) -> GitVersion:
        try:
            process = await asyncio.create_subprocess_exec(
                self._git,
                "--version",
                stdin=subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
                cwd=cwd,
            )
        except OSError:
            raise git_error(GitErrorCode.git_unavailable) from None
        try:
            async with asyncio.timeout(_VERSION_TIMEOUT_S):
                stdout, _ = await process.communicate()
        except TimeoutError:
            process.kill()
            await process.wait()
            raise git_error(GitErrorCode.git_unavailable) from None
        version = parse_git_version(stdout.decode("utf-8", errors="replace"))
        if version is None or version[:2] < self._minimum:
            raise git_error(GitErrorCode.git_unavailable)
        return version
