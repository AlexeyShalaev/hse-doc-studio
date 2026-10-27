"""Проверки перед операциями с переносным файлом: они не ходят в сеть и не требуют подключённого репозитория.

Файл выгружается из ветки проекта и принимается в неё же. Эта ветка берётся из hse-sync.json или из config
хранилища, а без них (проект ни разу не подключали) это ветка, на которой стоит HEAD.
"""

from __future__ import annotations

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import (
    IGitRepoReader,
    IGitStoreGuard,
    IGitStoreRemotes,
    IGitSyncStateRepository,
    ILocalAuthorProfile,
)
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.template_update.protocols import IUpdateJournalRepository
from hse_doc_studio.use_cases.git_sync.status import HEADS_PREFIX, default_state

_OPEN_MERGE = (
    "В проекте открыто слияние с конфликтами. Решите их или откажитесь от слияния, потом принимайте файл",
    "The project has a merge with conflicts open. Resolve them or discard the merge before importing a file",
)


class LocalSyncGate:
    def __init__(
        self,
        *,
        store_remotes: IGitStoreRemotes,
        state_repo: IGitSyncStateRepository,
        reader: IGitRepoReader,
        guard: IGitStoreGuard,
        profile: ILocalAuthorProfile,
        journals: IUpdateJournalRepository,
        policy: GitSyncPolicy,
    ) -> None:
        self._remotes = store_remotes
        self._states = state_repo
        self._reader = reader
        self._guard = guard
        self._profile = profile
        self._journals = journals
        self._policy = policy

    def check(self, project: Project, *, needs_profile: bool, refuse_open_merge: bool = False) -> str:
        """Возвращает ветку проекта или бросает ошибку с кодом, по которому клиент подскажет, что сделать.

        Блокирует на запусках git: вызывающий уводит вызов в поток.
        """
        self._policy.require_enabled()
        if needs_profile and self._profile.get() is None:
            raise git_error(GitErrorCode.profile_required)
        folder = project.folder
        self._guard.ensure_trusted(folder)
        current = self._reader.current_branch(folder)
        branch = self._branch(project, current)
        if branch is None or current != branch:
            raise git_error(GitErrorCode.off_branch)
        if self._reader.rev_parse(folder, f"{HEADS_PREFIX}{branch}") is None:
            raise git_error(GitErrorCode.branch_missing)
        if self._journals.get(folder) is not None:
            raise git_error(GitErrorCode.sync_incomplete)
        if refuse_open_merge and self._has_open_merge(project):
            raise GitSyncError(GitErrorCode.sync_incomplete, localized_error(*_OPEN_MERGE))
        return branch

    def _has_open_merge(self, project: Project) -> bool:
        state = self._states.get(project.folder)
        return state is not None and state.pending is not None

    def _branch(self, project: Project, current: str | None) -> str | None:
        state = self._states.get(project.folder)
        if state is not None:
            return state.local_branch
        config = self._remotes.read(project)
        return default_state(config, current).local_branch if config is not None else current
