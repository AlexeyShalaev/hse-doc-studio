from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.infra.git_sync.git_capabilities import GitCapabilities, parse_git_version, parse_min_version


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("git version 2.54.0 (Apple Git-157)", (2, 54, 0)),
        ("git version 2.39.5", (2, 39, 5)),
        ("git version 2.31.0.windows.1", (2, 31, 0)),
        ("git version 2.45", (2, 45, 0)),
        ("not git", None),
        ("", None),
    ],
)
def test__parse_git_version__known_shapes(text: str, expected: tuple[int, int, int] | None) -> None:
    assert parse_git_version(text) == expected


def test__parse_min_version__major_minor() -> None:
    assert parse_min_version("2.31") == (2, 31)
    assert parse_min_version("3") == (3, 0)


def _fake_git(tmp_path: Path, banner: str) -> str:
    script = tmp_path / "fake-git"
    script.write_text(f"#!/bin/sh\necho '{banner}'\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return str(script)


@pytest.mark.skipif(os.name != "posix", reason="shell script")
async def test__ensure_git__old_git__git_unavailable(tmp_path: Path) -> None:
    caps = GitCapabilities(git_binary=_fake_git(tmp_path, "git version 2.30.9"), min_version="2.31")

    with pytest.raises(GitSyncError) as raised:
        await caps.ensure_git(cwd=tmp_path, env={})

    assert raised.value.code is GitErrorCode.git_unavailable


@pytest.mark.skipif(os.name != "posix", reason="shell script")
async def test__ensure_git__supported_git__version_is_cached(tmp_path: Path) -> None:
    binary = _fake_git(tmp_path, "git version 2.39.5")
    caps = GitCapabilities(git_binary=binary, min_version="2.31")

    assert await caps.ensure_git(cwd=tmp_path, env={}) == (2, 39, 5)
    Path(binary).unlink()
    assert await caps.ensure_git(cwd=tmp_path, env={}) == (2, 39, 5)


async def test__ensure_git__missing_binary__git_unavailable(tmp_path: Path) -> None:
    caps = GitCapabilities(git_binary="definitely-not-a-git-binary")

    with pytest.raises(GitSyncError) as raised:
        await caps.ensure_git(cwd=tmp_path, env={})

    assert raised.value.code is GitErrorCode.git_unavailable


@pytest.mark.skipif(os.name != "posix", reason="shell script")
async def test__ensure_git__garbage_banner__git_unavailable(tmp_path: Path) -> None:
    caps = GitCapabilities(git_binary=_fake_git(tmp_path, "hello"))

    with pytest.raises(GitSyncError):
        await caps.ensure_git(cwd=tmp_path, env={})


def test__ssh_path__missing_binary__none() -> None:
    assert GitCapabilities(ssh_binary="definitely-not-an-ssh-binary").ssh_path() is None
