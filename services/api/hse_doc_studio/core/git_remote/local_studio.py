"""Локальная Студия из облака (docs/design/local-from-cloud.md): совместимость версий и сведения для установки.

Версии сравниваются по `MAJOR.MINOR`: внутри одной пары формат проекта и протокол `/git/-/*` не ломаются,
отличие в PATCH это только исправления.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

DEFAULT_LOCAL_PORT = 17240
IMAGE = "ghcr.io/alexeyshalaev/hse-doc-studio"
_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?")


class StudioCompat(StrEnum):
    same = "same"
    compatible = "compatible"
    local_older = "local_older"
    local_newer = "local_newer"
    unknown = "unknown"


def parse_version(raw: str | None) -> tuple[int, int, int] | None:
    """`0.3.1`, `v0.3`, `0.3.0-rc.1` → (0, 3, 1), (0, 3, 0), (0, 3, 0); иначе None."""
    found = _VERSION_RE.match((raw or "").strip())
    if found is None:
        return None
    return int(found.group(1)), int(found.group(2)), int(found.group(3) or 0)


def studio_compat(local: str | None, server: str | None) -> StudioCompat:
    mine, theirs = parse_version(local), parse_version(server)
    if mine is None or theirs is None:
        return StudioCompat.unknown
    if mine == theirs:
        return StudioCompat.same
    if mine[:2] == theirs[:2]:
        return StudioCompat.compatible
    return StudioCompat.local_older if mine < theirs else StudioCompat.local_newer


def recommended_tag(server_version: str | None) -> str | None:
    """Тег образа той же линии, что и сервер (`0.3`); для непонятной версии None."""
    parsed = parse_version(server_version)
    return f"{parsed[0]}.{parsed[1]}" if parsed else None


@dataclass(frozen=True)
class LocalStudioInfo:
    server_url: str
    server_version: str
    git_remote_enabled: bool
    recommended_tag: str | None
    image: str
    install_base_url: str
    releases_url: str
    default_port: int


def local_studio_info(
    *, server_url: str, server_version: str, github_repo: str, git_remote_enabled: bool
) -> LocalStudioInfo:
    repo = github_repo.strip().strip("/")
    return LocalStudioInfo(
        server_url=server_url.rstrip("/"),
        server_version=server_version,
        git_remote_enabled=git_remote_enabled,
        recommended_tag=recommended_tag(server_version),
        image=IMAGE,
        install_base_url=f"https://raw.githubusercontent.com/{repo}/master/deploy",
        releases_url=f"https://github.com/{repo}/releases",
        default_port=DEFAULT_LOCAL_PORT,
    )
