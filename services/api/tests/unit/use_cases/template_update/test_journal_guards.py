"""Один журнал на проект: идущая синхронизация делает проект «только чтение» и не пускает обновление шаблона."""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.project_access import ProjectAccessMode, ProjectAccessReason
from hse_doc_studio.core.template_update.entities import UpdateJournal, UpdateJournalKind, UpdateJournalState
from hse_doc_studio.core.template_update.errors import TemplateUpdateInProgressError
from hse_doc_studio.infra.template_update.state import JsonUpdateJournalRepository
from hse_doc_studio.use_cases.projects.get_project_access import ProjectAccessService
from hse_doc_studio.use_cases.template_update.support import ensure_no_active_journal
from tests.factories import make_project, make_template_version

pytestmark = pytest.mark.unit


class _Templates:
    def get_version(self, pack_id: str, template_id: str, version: str):  # type: ignore[no-untyped-def]
        return make_template_version()


def _journal(kind: UpdateJournalKind) -> UpdateJournal:
    return UpdateJournal(
        id="j1",
        state=UpdateJournalState.applying,
        from_version="1",
        to_version="2",
        pre_commit="a" * 40,
        base_commit=None,
        kind=kind,
        merge_parent="b" * 40 if kind == UpdateJournalKind.sync else None,
        sync_id="s1" if kind == UpdateJournalKind.sync else None,
    )


def _access(tmp_path: Path):  # type: ignore[no-untyped-def]
    journals = JsonUpdateJournalRepository()
    project = make_project(folder=tmp_path)
    service = ProjectAccessService(_Templates(), journals)  # type: ignore[arg-type]
    return project, journals, service


def test__access__no_journal_means_full_access(tmp_path: Path) -> None:
    project, _journals, service = _access(tmp_path)
    assert service.evaluate(project).mode == ProjectAccessMode.full


@pytest.mark.parametrize("kind", [UpdateJournalKind.template, UpdateJournalKind.sync])
def test__access__reports_update_in_progress_for_either_journal_kind(tmp_path: Path, kind: UpdateJournalKind) -> None:
    project, journals, service = _access(tmp_path)
    journals.save(tmp_path, _journal(kind))

    access = service.evaluate(project)

    assert access.mode == ProjectAccessMode.read_only
    assert ProjectAccessReason.update_in_progress in access.reasons

    journals.clear(tmp_path)
    assert service.evaluate(project).mode == ProjectAccessMode.full


def test__ensure_no_active_journal__passes_without_a_journal(tmp_path: Path) -> None:
    project, journals, _service = _access(tmp_path)
    ensure_no_active_journal(journals, project)


def test__ensure_no_active_journal__template_update_refuses_while_a_sync_journal_exists(tmp_path: Path) -> None:
    project, journals, _service = _access(tmp_path)
    journals.save(tmp_path, _journal(UpdateJournalKind.sync))

    with pytest.raises(TemplateUpdateInProgressError) as caught:
        ensure_no_active_journal(journals, project)

    assert "синхронизац" in str(caught.value).lower() or "sync" in str(caught.value).lower()


def test__ensure_no_active_journal__refuses_while_a_template_journal_exists(tmp_path: Path) -> None:
    project, journals, _service = _access(tmp_path)
    journals.save(tmp_path, _journal(UpdateJournalKind.template))

    with pytest.raises(TemplateUpdateInProgressError) as caught:
        ensure_no_active_journal(journals, project)

    assert "template update" in str(caught.value).lower() or "шаблона" in str(caught.value).lower()
