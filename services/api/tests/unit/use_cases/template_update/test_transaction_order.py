"""Порядок записей транзакции: удаления раньше записей, иначе при регистронезависимой ФС они съедают новое."""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.template_update.entities import FileWrite, FileWriteKind
from hse_doc_studio.infra.template_update.state import JsonUpdateJournalRepository
from hse_doc_studio.use_cases.template_update import transaction as transaction_module
from hse_doc_studio.use_cases.template_update.transaction import sync_transaction
from tests.factories import make_project

pytestmark = pytest.mark.unit


class _Store:
    def head(self, project: object) -> str | None:
        return None

    def commit_message(self, project: object, commit: str) -> str:
        return ""


def test__run__deletes_go_before_writes__case_only_rename_keeps_the_new_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = make_project(folder=tmp_path)
    journals = JsonUpdateJournalRepository()
    tx = sync_transaction(journals, _Store(), None)  # type: ignore[arg-type]
    applied: list[tuple[str, FileWriteKind]] = []
    monkeypatch.setattr(transaction_module, "apply_write", lambda _f, w: applied.append((w.path, w.kind)))
    # Как в переименовании notes/a.txt в Notes/a.txt: по алфавиту запись `Notes` идёт раньше удаления `notes`.
    writes = [
        FileWrite("Notes/a.txt", FileWriteKind.write, b"x"),
        FileWrite("notes/a.txt", FileWriteKind.delete),
        FileWrite("z.txt", FileWriteKind.write, b"y"),
        FileWrite("a.txt", FileWriteKind.delete),
    ]

    tx.run(
        project,
        tx.start_sync_journal(pre_commit="a", merge_parent="b", sync_id="s"),
        writes,
        save_state=lambda: None,
        commit=lambda: "c",
    )

    assert applied == [
        ("notes/a.txt", FileWriteKind.delete),
        ("a.txt", FileWriteKind.delete),
        ("Notes/a.txt", FileWriteKind.write),
        ("z.txt", FileWriteKind.write),
    ]
