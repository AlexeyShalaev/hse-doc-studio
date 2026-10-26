"""Подключение проекта к удалённому репозиторию в config его хранилища (порт IGitStoreRemotes).

Адрес и привязка к доступу лежат в самом хранилище, а не в project.json: они принадлежат этой машине и вместе
с проектом к коллегам не уезжают, зато переезжают с папкой. Читать config через git нужно только у
подключённых проектов: у остальных хватает беглого просмотра файла, поэтому опрос статуса ничего не стоит.
"""

from __future__ import annotations

from pathlib import Path

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.git_sync.entities import StoreRemoteConfig
from hse_doc_studio.infra.git_sync.remote_registry import store_has_remote
from hse_doc_studio.infra.git_sync.store_git import StoreGit
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService, store_git_dir

_TRACKING = "refs/remotes/origin/"


class GitStoreRemotes:
    def __init__(self, vcs: GitVcsService, git: StoreGit | None = None) -> None:
        self._vcs = vcs
        self._git = git or StoreGit()

    def git_dir(self, project: Project) -> Path:
        return store_git_dir(project.folder)

    def read(self, project: Project) -> StoreRemoteConfig | None:
        if not store_has_remote(project.folder):
            return None
        return self._vcs.read_remote_config(project)

    def write(self, project: Project, config: StoreRemoteConfig) -> None:
        self._vcs.write_remote_config(project, config)

    def clear(self, project: Project) -> None:
        self._vcs.clear_remote_config(project)
        self.drop_tracking_refs(project)

    def drop_tracking_refs(self, project: Project) -> None:
        folder = project.folder
        listed = self._git.text(folder, ["for-each-ref", "--format=%(refname)", _TRACKING], check=False)
        for ref in listed.split():
            if ref.startswith(_TRACKING):
                self._git.run(folder, ["update-ref", "-d", ref], check=False)
