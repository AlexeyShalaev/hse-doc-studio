"""Инфраструктура обновления шаблона на настоящем git: база, слияние, транзакция."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from hse_doc_studio.core.catalog import DynamicInclude
from hse_doc_studio.core.enums import TemplateBaseProvenance, VcsCommitKind
from hse_doc_studio.core.template_update.entities import FileWrite, FileWriteKind, TemplateBase
from hse_doc_studio.core.vcs.constants import DEFAULT_VCS_EXCLUDE, vcs_exclude_for
from hse_doc_studio.infra.template_update.merge_engine import GitMergeFileEngine
from hse_doc_studio.infra.template_update.state import JsonUpdateJournalRepository
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService
from hse_doc_studio.infra.vcs.template_base_store import GitTemplateBaseStore
from hse_doc_studio.use_cases.template_update.transaction import TemplateUpdateTransaction

from tests.factories import make_project, make_template_version

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available"),
]


def _project(tmp_path: Path):  # type: ignore[no-untyped-def]
    project = make_project(folder=tmp_path)
    (tmp_path / "doc").mkdir()
    (tmp_path / "doc" / "a.tex").write_text("a\n", encoding="utf-8", newline="\n")
    vcs = GitVcsService(author_name="Test", author_email="t@t.local")
    vcs.init(project, list(DEFAULT_VCS_EXCLUDE))
    return project, vcs


def test__merge_engine__clean_and_conflicting() -> None:
    engine = GitMergeFileEngine()
    clean = engine.merge(b"mine\nb\nc\n", b"a\nb\nc\n", b"a\nb\ntheirs\n")
    assert clean.conflicts == 0
    assert clean.content == b"mine\nb\ntheirs\n"

    conflict = engine.merge(b"mine\n", b"base\n", b"theirs\n")
    assert conflict.conflicts == 1
    assert "<<<<<<< ваш вариант".encode() in conflict.content
    assert "||||||| шаблон: было".encode() in conflict.content


def test__base_store__save_load_and_binary_content(tmp_path: Path) -> None:
    project, vcs = _project(tmp_path)
    store = GitTemplateBaseStore(vcs)
    base = TemplateBase(
        version="2026.1",
        files={"doc/a.tex": b"a\n", "doc/logo.png": b"\x00\x01\x02", "doc/x.pdf": b"%PDF"},
        provenance=TemplateBaseProvenance.root,
        approximate_paths=frozenset({"doc/logo.png"}),
    )

    commit = store.save(project, base, message="база")
    loaded = store.load(project, "2026.1")

    assert loaded is not None
    assert loaded.commit == commit
    assert dict(loaded.files) == dict(base.files)  # и *.pdf, исключённый из истории, тоже
    assert loaded.provenance == TemplateBaseProvenance.root
    assert loaded.approximate_paths == frozenset({"doc/logo.png"})
    # База не видна ни в ветках, ни в истории, ни в индексе пользователя.
    assert [b.name for b in vcs.list_branches(project)] == ["master"]
    assert len(vcs.log(project)) == 1
    assert vcs.commit(project, message="noop", kind=VcsCommitKind.manual) is None


def test__base_store__root_snapshot_and_trailer_search(tmp_path: Path) -> None:
    project, vcs = _project(tmp_path)
    store = GitTemplateBaseStore(vcs)
    root = store.root_snapshot(project)
    assert root is not None
    assert dict(root.files) == {"doc/a.tex": b"a\n"}
    assert "Hse-Kind: init" in root.message

    (tmp_path / "doc" / "a.tex").write_text("b\n", encoding="utf-8", newline="\n")
    commit = vcs.commit(project, message="Обновление\n\nHse-Template-Update: abc", kind=VcsCommitKind.template_update)
    assert commit is not None
    assert store.find_commit(project, "Hse-Template-Update", "abc") == commit.id
    assert store.find_commit(project, "Hse-Template-Update", "zzz") is None
    assert store.changed_paths(project, root.commit, commit.id) == ["doc/a.tex"]
    assert store.files_at(project, root.commit, ["doc/a.tex"]) == {"doc/a.tex": b"a\n"}


def _transaction(vcs: GitVcsService) -> tuple[TemplateUpdateTransaction, JsonUpdateJournalRepository]:
    journals = JsonUpdateJournalRepository()
    return TemplateUpdateTransaction(journals, GitTemplateBaseStore(vcs), vcs), journals


def test__transaction__failure_rolls_back_every_file(tmp_path: Path) -> None:
    project, vcs = _project(tmp_path)
    transaction, journals = _transaction(vcs)
    head = GitTemplateBaseStore(vcs).head(project)
    assert head is not None
    journal = transaction.start_journal(from_version="1", to_version="2", pre_commit=head, base_commit=None)
    writes = [
        FileWrite("doc/a.tex", FileWriteKind.write, b"changed\n"),
        FileWrite("doc/new/b.tex", FileWriteKind.write, b"new\n"),
    ]

    def boom() -> None:
        raise RuntimeError("сбой посреди обновления")

    with pytest.raises(RuntimeError):
        transaction.run(project, journal, writes, save_state=boom, message="Обновление")

    assert (tmp_path / "doc" / "a.tex").read_text(encoding="utf-8") == "a\n"
    assert not (tmp_path / "doc" / "new").exists()
    assert journals.get(tmp_path) is None
    assert not (tmp_path / ".hse-studio" / "update").exists()


def test__transaction__crash_before_commit_is_rolled_back_on_recovery(tmp_path: Path) -> None:
    project, vcs = _project(tmp_path)
    transaction, journals = _transaction(vcs)
    head = GitTemplateBaseStore(vcs).head(project)
    assert head is not None
    journal = transaction.start_journal(from_version="1", to_version="2", pre_commit=head, base_commit=None)
    # Имитация падения процесса: журнал и копии записаны, файлы частично заменены.
    journal = replace(journal, touched_paths=("doc/a.tex",), added_paths=("doc/c.tex",))
    journals.backup(tmp_path, ["doc/a.tex"])
    journals.save(tmp_path, journal)
    (tmp_path / "doc" / "a.tex").write_text("half\n", encoding="utf-8", newline="\n")
    (tmp_path / "doc" / "c.tex").write_text("added\n", encoding="utf-8", newline="\n")

    assert transaction.recover(project, journal) is False

    assert (tmp_path / "doc" / "a.tex").read_text(encoding="utf-8") == "a\n"
    assert not (tmp_path / "doc" / "c.tex").exists()
    assert journals.get(tmp_path) is None


def test__transaction__crash_after_commit_is_finalized(tmp_path: Path) -> None:
    project, vcs = _project(tmp_path)
    transaction, journals = _transaction(vcs)
    store = GitTemplateBaseStore(vcs)
    pre = store.head(project)
    assert pre is not None
    base_commit = store.save(
        project,
        TemplateBase(version="2", files={"doc/a.tex": b"b\n"}, provenance=TemplateBaseProvenance.recorded),
        message="база",
        set_ref=False,
    )
    journal = transaction.start_journal(from_version="1", to_version="2", pre_commit=pre, base_commit=base_commit)
    journals.save(tmp_path, journal)
    (tmp_path / "doc" / "a.tex").write_text("b\n", encoding="utf-8", newline="\n")
    vcs.commit(project, message=f"Обновление\n\nHse-Template-Update: {journal.id}", kind=VcsCommitKind.template_update)

    assert transaction.recover(project, journal) is True

    assert (tmp_path / "doc" / "a.tex").read_text(encoding="utf-8") == "b\n"
    assert store.load(project, "2") is not None
    assert journals.get(tmp_path) is None


def test__vcs_exclude_for__covers_dynamic_outputs_in_every_base() -> None:
    version = replace(
        make_template_version(),
        dynamic_includes=(
            DynamicInclude("common/meta.tex.j2", "common/meta.tex"),
            DynamicInclude("common/fonts.tex.j2", "common/fonts.tex"),
        ),
    )
    assert vcs_exclude_for(None) == list(DEFAULT_VCS_EXCLUDE)
    assert ".hse-studio/update/" in DEFAULT_VCS_EXCLUDE
    patterns = vcs_exclude_for(version)
    assert "**/common/meta.tex" in patterns
    assert "**/common/fonts.tex" in patterns
