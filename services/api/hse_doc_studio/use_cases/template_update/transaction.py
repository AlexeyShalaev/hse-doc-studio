"""Запись решения обновления на диск как транзакция с журналом.

Порядок: копии затрагиваемых файлов и журнал → файлы проекта → `project.json`
(смена lock — точка фиксации) и `template.json` → коммит истории → ссылка базы
целевой версии → журнал удаляется. Любой сбой до коммита откатывается по
журналу: копии возвращаются, добавленные файлы удаляются. Сбой после коммита
обновление доводит (коммит — уже факт истории, откатывать его нельзя тихо).
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
from hse_doc_studio.core.template_update.entities import FileWrite, FileWriteKind, UpdateJournal, UpdateJournalState
from hse_doc_studio.core.template_update.protocols import ITemplateBaseStore, IUpdateJournalRepository
from hse_doc_studio.core.vcs.protocols import IVcsService

logger = structlog.get_logger()

UPDATE_TRAILER = "Hse-Template-Update"
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


class TemplateUpdateTransaction:
    def __init__(
        self,
        journal_repo: IUpdateJournalRepository,
        base_store: ITemplateBaseStore,
        vcs_service: IVcsService,
    ) -> None:
        self._journals = journal_repo
        self._store = base_store
        self._vcs = vcs_service

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

    def run(
        self,
        project: Project,
        journal: UpdateJournal,
        writes: Sequence[FileWrite],
        *,
        save_state: Callable[[], None],
        message: str,
    ) -> str | None:
        """Применить записи и состояние, закоммитить; вернуть id коммита."""
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
            commit = self._vcs.commit(
                project,
                message=f"{message}\n\n{UPDATE_TRAILER}: {journal.id}",
                kind=VcsCommitKind.template_update,
            )
            self._finalize(project, journal)
        except BaseException:
            self.recover(project, journal)
            raise
        return commit.id if commit is not None else None

    def _finalize(self, project: Project, journal: UpdateJournal) -> None:
        if journal.base_commit:
            self._store.set_ref(project, journal.to_version, journal.base_commit)
        self._journals.clear(project.folder)

    def _committed(self, project: Project, journal: UpdateJournal) -> bool:
        head = self._store.head(project)
        if head is None or head == journal.pre_commit:
            return False
        return f"{UPDATE_TRAILER}: {journal.id}" in self._store.commit_message(project, head)

    def recover(self, project: Project, journal: UpdateJournal) -> bool:
        """Довести или откатить прерванное обновление. True — обновление доведено."""
        if self._committed(project, journal):
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
