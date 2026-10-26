"""Журнал `kind=sync`: падение процесса на каждом шаге применения слияния.

Падение имитируется так: транзакция не откатывается сама (как при убитом процессе),
а потом запускается то же восстановление, что и при старте Студии.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.template_update.entities import FileWrite, FileWriteKind, UpdateJournal, UpdateJournalKind
from hse_doc_studio.infra.git_sync.merge_committer import GitMergeCommitter
from hse_doc_studio.infra.template_update.state import JsonUpdateJournalRepository
from hse_doc_studio.infra.vcs.template_base_store import GitTemplateBaseStore
from hse_doc_studio.use_cases.template_update import transaction as transaction_module
from hse_doc_studio.use_cases.template_update.recover_template_updates import RecoverTemplateUpdatesUC
from hse_doc_studio.use_cases.template_update.transaction import (
    TemplateUpdateTransaction,
    sync_transaction,
)

from tests.unit.infra.git_sync.conftest import Repo

pytestmark = pytest.mark.unit

_SYNC_ID = "sync0001"


class _Killed(BaseException):
    """Процесс убит: BaseException, как KeyboardInterrupt, но без отката транзакцией."""


class _Projects:
    def __init__(self, project: Project) -> None:
        self._project = project

    def get(self, folder: Path) -> Project | None:
        return self._project if folder == self._project.folder else None

    def save(self, project: Project) -> None:
        raise AssertionError("recovery must not save the project")


class _Index:
    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def list_known(self) -> list[Path]:
        return [self._folder]


class Env:
    def __init__(self, repo: Repo) -> None:
        self.repo = repo
        self.journals = JsonUpdateJournalRepository()
        self.store = GitTemplateBaseStore(repo.svc)
        self.committer = GitMergeCommitter(repo.authors, repo.git)
        self.transaction = sync_transaction(self.journals, self.store, repo.svc)
        base = repo.head()
        repo.branch("side")
        self.theirs = repo.snap("side", side__file="theirs\n", vkr__vkr_tex="theirs-tex\n")
        repo.switch("master")
        self.ours = repo.snap("master", vkr__own="ours\n")
        assert base != self.ours
        self.writes = [
            FileWrite("side/file", FileWriteKind.write, b"theirs\n"),
            FileWrite("vkr/vkr_tex", FileWriteKind.write, b"merged\n"),
            FileWrite("vkr/own", FileWriteKind.delete),
        ]

    def journal(self) -> UpdateJournal:
        return self.transaction.start_sync_journal(pre_commit=self.ours, merge_parent=self.theirs, sync_id=_SYNC_ID)

    def merge_commit(self) -> str:
        return self.committer.commit_merge(
            self.repo.folder,
            ours=self.ours,
            theirs=self.theirs,
            changes={"side/file": b"theirs\n", "vkr/vkr_tex": b"merged\n", "vkr/own": None},
            message="Синхронизация: слияние",
            trailers={"Hse-Sync": _SYNC_ID},
        )

    def advance(self, new: str) -> None:
        assert self.committer.advance_branch(self.repo.folder, "master", expected=self.ours, new=new)

    def run(self, commit: Callable[[], str | None], save_state: Callable[[], None] | None = None) -> None:
        self.transaction.run(
            self.repo.project,
            self.journal(),
            self.writes,
            save_state=save_state or (lambda: None),
            commit=commit,
        )

    def crash(self, monkeypatch: pytest.MonkeyPatch, step: Callable[..., Any]) -> None:
        """Прогнать транзакцию, убив процесс на шаге; откат самой транзакции отключён."""
        monkeypatch.setattr(self.transaction, "recover", lambda *_a, **_k: False)
        with pytest.raises(_Killed):
            step()
        assert self.journals.get(self.repo.folder) is not None

    def recover(self) -> list[bool]:
        uc = RecoverTemplateUpdatesUC(
            _Projects(self.repo.project),  # type: ignore[arg-type]
            _Index(self.repo.folder),  # type: ignore[arg-type]
            self.journals,
            self.store,
            self.repo.svc,
        )
        return [item.finalized for item in uc._recover_all().recovered]

    def assert_pre_state(self) -> None:
        folder = self.repo.folder
        assert self.repo.head() == self.ours
        assert (folder / "vkr" / "own").read_text(encoding="utf-8") == "ours\n"
        assert (folder / "vkr" / "vkr.tex").read_text(encoding="utf-8") == "base\n"
        assert not (folder / "side").exists()
        assert not (folder / "vkr" / "vkr_tex").exists()
        assert self.repo.git.text(folder, ["status", "--porcelain"]).strip() == ""
        assert self.journals.get(folder) is None
        assert not (folder / ".hse-studio" / "update").exists()

    def assert_merged_state(self, head: str) -> None:
        folder = self.repo.folder
        assert self.repo.head() == head
        assert (folder / "side" / "file").read_text(encoding="utf-8") == "theirs\n"
        assert (folder / "vkr" / "vkr_tex").read_text(encoding="utf-8") == "merged\n"
        assert not (folder / "vkr" / "own").exists()
        assert self.repo.git.text(folder, ["status", "--porcelain"]).strip() == ""
        assert self.journals.get(folder) is None
        assert not (folder / ".hse-studio" / "update").exists()


@pytest.fixture
def env(repo: Repo) -> Env:
    return Env(repo)


def _killer() -> None:
    raise _Killed


def test__sync_journal__success_commits_and_clears_the_journal(env: Env) -> None:
    def commit() -> str:
        merge = env.merge_commit()
        env.advance(merge)
        return merge

    env.run(commit)

    env.assert_merged_state(env.repo.head())
    parents = env.repo.git.text(env.repo.folder, ["rev-list", "--parents", "-n1", "HEAD"]).split()
    assert parents[1:] == [env.ours, env.theirs]


def test__sync_journal__failure_rolls_back_in_process(env: Env) -> None:
    def boom() -> str | None:
        raise RuntimeError("сбой при коммите")

    with pytest.raises(RuntimeError):
        env.run(boom)

    env.assert_pre_state()


def test__sync_journal__sync_commit_is_required(env: Env) -> None:
    with pytest.raises(ValueError, match="own commit"):
        env.transaction.run(env.repo.project, env.journal(), env.writes, save_state=lambda: None)
    env.assert_pre_state()


def test__sync_journal__crash_in_the_middle_of_the_writes_is_rolled_back(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = transaction_module.apply_write
    calls: list[str] = []

    def flaky(folder: Path, write: FileWrite) -> None:
        calls.append(write.path)
        if len(calls) == 2:
            raise _Killed
        real(folder, write)

    monkeypatch.setattr(transaction_module, "apply_write", flaky)
    env.crash(monkeypatch, lambda: env.run(lambda: None))

    assert env.recover() == [False]
    env.assert_pre_state()


def test__sync_journal__crash_after_the_writes_before_the_commit_is_rolled_back(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    env.crash(monkeypatch, lambda: env.run(lambda: None, save_state=_killer))

    assert (env.repo.folder / "side" / "file").exists()
    assert env.recover() == [False]
    env.assert_pre_state()


def test__sync_journal__crash_after_commit_tree_before_the_branch_moves_is_rolled_back(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    def commit() -> str:
        env.merge_commit()
        raise _Killed

    env.crash(monkeypatch, lambda: env.run(commit))

    assert env.recover() == [False]
    env.assert_pre_state()


def test__sync_journal__crash_after_the_branch_moved_is_finalized(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    merge = ""

    def commit() -> str:
        nonlocal merge
        merge = env.merge_commit()
        env.advance(merge)
        raise _Killed

    env.crash(monkeypatch, lambda: env.run(commit))

    assert env.recover() == [True]
    env.assert_merged_state(merge)


def test__sync_journal__crash_before_the_journal_is_cleared_is_finalized(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    def commit() -> str:
        merge = env.merge_commit()
        env.advance(merge)
        return merge

    monkeypatch.setattr(env.journals, "clear", lambda _folder: (_ for _ in ()).throw(_Killed()))
    env.crash(monkeypatch, lambda: env.run(commit))
    monkeypatch.undo()

    assert env.recover() == [True]
    env.assert_merged_state(env.repo.head())


def test__sync_journal__fast_forward_is_recognised_by_the_merge_parent(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Быстрая перемотка: ours лежит в истории theirs, коммита слияния нет.
    env.repo.switch("side")
    env.ours = env.repo.head()
    env.theirs = env.repo.snap("later", later__file="x\n")
    env.repo.switch("master")
    env.repo.git.run(env.repo.folder, ["reset", "--hard", env.ours])
    env.writes = [FileWrite("later/file", FileWriteKind.write, b"x\n")]

    def commit() -> str:
        assert env.committer.fast_forward(env.repo.folder, "master", expected=env.ours, new=env.theirs)
        raise _Killed

    env.crash(monkeypatch, lambda: env.run(commit))

    assert env.recover() == [True]
    assert env.repo.head() == env.theirs
    assert (env.repo.folder / "later" / "file").read_text(encoding="utf-8") == "x\n"
    assert env.journals.get(env.repo.folder) is None


def test__sync_journal__template_transaction_does_not_take_a_sync_commit_for_its_own(env: Env) -> None:
    # Коммит с чужим трейлером не считается завершением обновления шаблона.
    merge = env.merge_commit()
    env.advance(merge)
    template = TemplateUpdateTransaction(env.journals, env.store, env.repo.svc)
    journal = env.journal()
    assert template.recover(env.repo.project, journal) is False
    assert journal.kind == UpdateJournalKind.sync


def test__sync_journal__is_stored_with_its_kind_and_ids(env: Env) -> None:
    journal = env.journal()
    env.journals.save(env.repo.folder, journal)

    raw = json.loads((env.repo.folder / ".hse-studio" / "update" / "journal.json").read_text(encoding="utf-8"))
    assert raw["kind"] == "sync"
    assert raw["merge_parent"] == env.theirs
    assert raw["sync_id"] == _SYNC_ID
    assert env.journals.get(env.repo.folder) == journal
