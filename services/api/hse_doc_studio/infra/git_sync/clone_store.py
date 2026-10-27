"""Хранилище нового проекта при клонировании (порт IGitCloneStore).

Проект собирается в пустой папке: сначала пустое хранилище, потом выборка истории, и только после
проверки вершины дерево разворачивается в папку. Окружение и жёсткий набор `-c` те же, что у остальных
команд над хранилищем.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from hse_doc_studio.core.git_sync.entities import StoreRemoteConfig
from hse_doc_studio.core.vcs.refs import validate_ref_name
from hse_doc_studio.infra.git_sync.store_git import StoreGit
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService, store_git_dir


class GitCloneStore:
    def __init__(self, vcs: GitVcsService, git: StoreGit | None = None) -> None:
        self._vcs = vcs
        self._git = git or StoreGit()

    def init(self, folder: Path, branch: str) -> None:
        self._vcs.init_bare_store(folder, branch)

    def write_exclude(self, folder: Path, patterns: Sequence[str]) -> None:
        info = store_git_dir(folder) / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "exclude").write_text("\n".join(patterns) + "\n", encoding="utf-8")
        # До checkout: чужой `.gitattributes` не должен преобразовывать файлы при развёртывании дерева.
        self._vcs.write_attributes_at(folder)

    def checkout(self, folder: Path, branch: str, ref: str | None = None) -> None:
        branch = validate_ref_name(branch)
        self._git.run(
            folder,
            [
                "checkout",
                "--quiet",
                "--force",
                "--no-recurse-submodules",
                "-B",
                branch,
                ref or f"refs/remotes/origin/{branch}",
            ],
        )

    def write_remote(self, folder: Path, config: StoreRemoteConfig) -> None:
        self._vcs.write_remote_config_at(folder, config)
