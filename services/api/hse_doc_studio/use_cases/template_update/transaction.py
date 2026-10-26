"""Запись решения обновления на диск как транзакция с журналом.

Порядок: копии затрагиваемых файлов и журнал → файлы проекта → `project.json`
(смена lock — точка фиксации) и `template.json` → коммит истории → ссылка базы
целевой версии → журнал удаляется. Любой сбой до коммита откатывается по
журналу: копии возвращаются, добавленные файлы удаляются. Сбой после коммита
обновление доводит (коммит — уже факт истории, откатывать его нельзя тихо).

Та же транзакция применяет слияние Git-синхронизации (журнал `kind=sync`):
коммит слияния делает вызывающий (`commit=`), а «коммит уже сделан» определяется
по трейлеру `Hse-Sync: <id>` у HEAD или по тому, что HEAD дошёл до `merge_parent`
(быстрая перемотка).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import VcsCommitKind
from hse_doc_studio.core.template_update.entities import (
    FileWrite,
    FileWriteKind,
    UpdateJournal,
    UpdateJournalKind,
    UpdateJournalState,
)
from hse_doc_studio.core.template_update.protocols import ITemplateBaseStore, IUpdateJournalRepository
from hse_doc_studio.core.vcs.protocols import IVcsService

logger = structlog.get_logger()

UPDATE_TRAILER = "Hse-Template-Update"
SYNC_TRAILER = "Hse-Sync"
STATE_PATHS = (".hse-studio/project.json", ".hse-studio/template.json")


def new_update_id() -> str:
    return uuid.uuid4().hex[:12]


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _prune_empty_dirs(folder: Path, start: Path) -> None:
    current = start
    while current != folder and folder in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _has_trailer(message: str, trailer: str, value: str) -> bool:
    wanted = f"{trailer}: {value}"
    return any(line.strip() == wanted for line in message.splitlines())


def apply_write(folder: Path, write: FileWrite) -> None:
    target = folder / write.path
    if write.kind == FileWriteKind.delete:
        if target.is_file():
            target.unlink()
            _prune_empty_dirs(folder, target.parent)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.hse-update.tmp")
    tmp.write_bytes(write.content or b"")
    os.replace(tmp, target)


CommittedPredicate = Callable[[Project, UpdateJournal], bool]


class TemplateUpdateTransaction:
    """Журналируемая запись на диск; `trailer` и `committed` задают вид транзакции.

    По умолчанию это обновление шаблона. Для слияния синхронизации используют
    `sync_transaction`: свой трейлер и своё «коммит уже сделан».
    """

    def __init__(
        self,
        journal_repo: IUpdateJournalRepository,
        base_store: ITemplateBaseStore,
        vcs_service: IVcsService,
        *,
        trailer: str = UPDATE_TRAILER,
        committed: CommittedPredicate | None = None,
    ) -> None:
        self._journals = journal_repo
        self._store = base_store
        self._vcs = vcs_service
        self._trailer = trailer
        self._is_committed = committed or self._head_has_trailer

    def start_journal(
        self,
        *,
        from_version: str,
        to_version: str,
        pre_commit: str,
        base_commit: str | None,
        reverts: str | None = None,
    ) -> UpdateJournal:
        return UpdateJournal(
            id=new_update_id(),
            state=UpdateJournalState.applying,
            from_version=from_version,
            to_version=to_version,
            pre_commit=pre_commit,
            base_commit=base_commit,
            started_at=now_iso(),
            reverts=reverts,
        )

    def start_sync_journal(self, *, pre_commit: str, merge_parent: str, sync_id: str) -> UpdateJournal:
        return UpdateJournal(
            id=new_update_id(),
            state=UpdateJournalState.applying,
            from_version="",
            to_version="",
            pre_commit=pre_commit,
            base_commit=None,
            started_at=now_iso(),
            kind=UpdateJournalKind.sync,
            merge_parent=merge_parent,
            sync_id=sync_id,
        )

    def run(
        self,
        project: Project,
        journal: UpdateJournal,
        writes: Sequence[FileWrite],
        *,
        save_state: Callable[[], None],
        message: str = "",
        commit: Callable[[], str | None] | None = None,
    ) -> str | None:
        """Применить записи и состояние, закоммитить; вернуть id коммита.

        `commit` делает сам коммит (слияние синхронизации ставит свой трейлер и
        двигает ветку); без него это коммит обновления шаблона с `message`.
        """
        if commit is None and journal.kind == UpdateJournalKind.sync:
            raise ValueError("sync journal needs its own commit")
        folder = project.folder
        touched = [w.path for w in writes if (folder / w.path).exists()]
        touched += [rel for rel in STATE_PATHS if (folder / rel).exists()]
        added = [w.path for w in writes if w.kind == FileWriteKind.write and not (folder / w.path).exists()]
        added += [rel for rel in STATE_PATHS if not (folder / rel).exists()]
        journal = replace(journal, touched_paths=tuple(touched), added_paths=tuple(added))
        self._journals.backup(folder, touched)
        self._journals.save(folder, journal)
        try:
            for write in writes:
                apply_write(folder, write)
            save_state()
            commit_id = commit() if commit is not None else self._commit_template_update(project, journal, message)
            self._finalize(project, journal)
        except BaseException:
            self.recover(project, journal)
            raise
        return commit_id

    def _commit_template_update(self, project: Project, journal: UpdateJournal, message: str) -> str | None:
        commit = self._vcs.commit(
            project,
            message=f"{message}\n\n{self._trailer}: {journal.id}",
            kind=VcsCommitKind.template_update,
        )
        return commit.id if commit is not None else None

    def _finalize(self, project: Project, journal: UpdateJournal) -> None:
        if journal.base_commit:
            self._store.set_ref(project, journal.to_version, journal.base_commit)
        self._journals.clear(project.folder)

    def _head_has_trailer(self, project: Project, journal: UpdateJournal) -> bool:
        head = self._store.head(project)
        if head is None or head == journal.pre_commit:
            return False
        return _has_trailer(self._store.commit_message(project, head), self._trailer, journal.id)

    def recover(self, project: Project, journal: UpdateJournal) -> bool:
        """Довести или откатить прерванное обновление. True — обновление доведено."""
        if self._is_committed(project, journal):
            self._finalize(project, journal)
            logger.info("interrupted template update finalized", update_id=journal.id, folder=str(project.folder))
            return True
        folder = project.folder
        for rel in journal.touched_paths:
            if not self._journals.restore(folder, rel):
                logger.warning("template update rollback: no backup", path=rel, update_id=journal.id)
        for rel in journal.added_paths:
            target = folder / rel
            if target.is_file():
                target.unlink()
                _prune_empty_dirs(folder, target.parent)
        self._journals.clear(folder)
        logger.info("interrupted template update rolled back", update_id=journal.id, folder=str(folder))
        return False


def sync_transaction(
    journal_repo: IUpdateJournalRepository,
    base_store: ITemplateBaseStore,
    vcs_service: IVcsService,
) -> TemplateUpdateTransaction:
    """Транзакция применения слияния Git-синхронизации (журнал `kind=sync`)."""

    def committed(project: Project, journal: UpdateJournal) -> bool:
        head = base_store.head(project)
        if head is None or head == journal.pre_commit:
            return False
        if journal.merge_parent is not None and head == journal.merge_parent:
            return True
        return journal.sync_id is not None and _has_trailer(
            base_store.commit_message(project, head), SYNC_TRAILER, journal.sync_id
        )

    return TemplateUpdateTransaction(journal_repo, base_store, vcs_service, trailer=SYNC_TRAILER, committed=committed)
