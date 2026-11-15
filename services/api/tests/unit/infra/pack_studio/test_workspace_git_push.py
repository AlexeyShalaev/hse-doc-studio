"""Отправка рабочей ветки: argv push с push options GitLab, без принудительной отправки и без секретов в argv."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.entities import GitResult, RemoteTarget
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.core.pack_studio.git_flow import gitlab_push_options
from hse_doc_studio.infra.pack_studio.workspace_git import PackWorkspaceGit, workspace_dirs


class _Runner:
    def __init__(self) -> None:
        self.network: list[list[str]] = []

    async def run(self, args: Sequence[str], **_kwargs: Any) -> GitResult:
        self.network.append(list(args))
        return GitResult(0, b"", "remote:   https://gl.example/g/p/-/merge_requests/3\n")

    async def run_local(self, args: Sequence[str], **_kwargs: Any) -> GitResult:
        return GitResult(0, b"0123abcd\n", "")


async def test__push__argv_has_push_options_and_no_force(tmp_path: Path) -> None:
    runner = _Runner()
    git = PackWorkspaceGit(runner, GitConfig())  # type: ignore[arg-type]
    target = RemoteTarget(url=parse_remote_url("https://gitlab.example.org/fcs/packs.git"))
    options = gitlab_push_options(target_branch="main", title="fix(packs): x", description="тело")

    outcome = await git.push(workspace_dirs(tmp_path), target, branch="pack-studio/a/b", push_options=options)

    (argv,) = runner.network
    assert argv[:3] == ["push", "--porcelain", "--no-recurse-submodules"]
    assert argv[3:13] == [part for option in options for part in ("-o", option)]
    assert argv[-3:] == ["--", "https://gitlab.example.org/fcs/packs.git", "HEAD:refs/heads/pack-studio/a/b"]
    assert not any(arg.startswith(("--force", "-f", "+")) for arg in argv)
    assert outcome.sha == "0123abcd"
    assert "merge_requests/3" in outcome.remote_output
