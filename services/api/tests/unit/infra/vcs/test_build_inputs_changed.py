"""Входы сборки в истории проекта: служебные записи сборку не старят, правки исходников и данных титула старят."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.builds.inputs import RUNNER_EXCLUDED_DIRS, is_build_input, same_project_inputs
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import VcsCommitKind
from hse_doc_studio.core.vcs.constants import DEFAULT_VCS_EXCLUDE
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.infra.jobs.queue_dispatcher import EXCLUDED_DIRS
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService

from tests.factories import make_project

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available"),
]

SETTINGS = VcsSettings()
DOCUMENT: dict[str, Any] = {"id": "vkr", "status": "draft", "last_compile_id": None, "chosen_variant": None}
PROJECT_JSON: dict[str, Any] = {
    "id": "p",
    "name": "КП",
    "meta": {"topic": "Тема", "vcs": {"track_pdf": False}},
    "supervisor": {"name": "Петров П. П."},
    "documents": [DOCUMENT],
    "updated_at": "2026-11-10T10:00:00+00:00",
}


def _write(folder: Path, rel: str, content: str | bytes) -> None:
    path = folder / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8", newline="\n")


def _project_json(folder: Path, **changes: Any) -> None:
    _write(folder, ".hse-studio/project.json", json.dumps({**PROJECT_JSON, **changes}, ensure_ascii=False))


def _built(tmp_path: Path) -> tuple[GitVcsService, Project, str]:
    """Проект с исходником и `project.json` и коммит, из которого «собран» PDF."""
    project = make_project(folder=tmp_path)
    svc = GitVcsService(author_name="Test Bot", author_email="bot@test.local")
    _write(tmp_path, "vkr/vkr.tex", "v1\n")
    _project_json(tmp_path)
    svc.init(project, list(DEFAULT_VCS_EXCLUDE))
    head = svc.status(project, SETTINGS).head
    assert head is not None
    return svc, project, head


def test__inputs__runner_manifest_and_staleness_skip_the_same_service_folders() -> None:
    assert EXCLUDED_DIRS == RUNNER_EXCLUDED_DIRS
    assert is_build_input("vkr/vkr.tex")
    assert is_build_input(".hse-studio/project.json")
    assert not is_build_input(".hse-studio/signatures.json")
    assert not is_build_input(".hse-studio/frozen/vkr.pdf")
    assert not is_build_input("authors/ivanov/.hse-studio/forms/f.json")


def test__inputs__project_json_state_fields_do_not_count() -> None:
    base = json.dumps(PROJECT_JSON).encode()
    state = {
        **PROJECT_JSON,
        "updated_at": "2026-11-11T00:00:00+00:00",
        "pinned": True,
        "meta": {**PROJECT_JSON["meta"], "vcs": {"track_pdf": True}},
        "documents": [{**DOCUMENT, "status": "ok", "last_compile_id": "c1"}],
        # Срок точки PDF не меняет (signing-route.md, 16.3): версия на подписи от него не устаревает.
        "deadlines": {"topic-approval": "2026-11-15T23:59:00+03:00"},
    }
    topic = {**PROJECT_JSON, "meta": {"topic": "Другая тема"}}

    assert same_project_inputs(base, json.dumps(state).encode())
    assert not same_project_inputs(base, json.dumps(topic).encode())
    assert not same_project_inputs(base, None)
    assert not same_project_inputs(base, b"{broken")


def test__changed__nothing_changed__false(tmp_path: Path) -> None:
    svc, project, head = _built(tmp_path)

    assert svc.build_inputs_changed(project, SETTINGS, head) is False


def test__changed__signature_state_frozen_and_detached_files__false(tmp_path: Path) -> None:
    svc, project, head = _built(tmp_path)
    _write(tmp_path, ".hse-studio/signatures.json", '{"slots": {}, "withheld": {"vkr": ["supervisor"]}}')
    _write(tmp_path, ".hse-studio/signatures/supervisor.png", b"\x89PNG")
    _write(tmp_path, ".hse-studio/frozen/vkr.pdf", b"%PDF frozen")
    _write(tmp_path, ".hse-studio/detached/vkr/author.asc", "sig")
    _write(tmp_path, "vkr/vkr.pdf", b"%PDF rebuilt")

    assert svc.status(project, SETTINGS).dirty is True
    assert svc.build_inputs_changed(project, SETTINGS, head) is False


def test__changed__later_service_commits_and_document_status__false(tmp_path: Path) -> None:
    svc, project, head = _built(tmp_path)
    _project_json(tmp_path, documents=[{**DOCUMENT, "status": "ok", "last_compile_id": "c1"}])
    _write(tmp_path, ".hse-studio/signatures.json", "{}")
    # Сборка соседнего документа и фиксация подписи с `add -f` делают коммиты: вершина уходит вперёд.
    svc.commit(project, message="Сборка: other", kind=VcsCommitKind.compile, force_paths=[".hse-studio/frozen"])

    assert svc.status(project, SETTINGS).head != head
    assert svc.build_inputs_changed(project, SETTINGS, head) is False


@pytest.mark.parametrize(
    "change",
    [
        pytest.param(lambda f: _write(f, "vkr/vkr.tex", "v2\n"), id="source-edited"),
        pytest.param(lambda f: _write(f, "vkr/chapter.tex", "new\n"), id="untracked-source"),
        pytest.param(lambda f: (f / "vkr" / "vkr.tex").unlink(), id="source-deleted"),
        pytest.param(lambda f: _project_json(f, meta={"topic": "Другая тема"}), id="title-data"),
        pytest.param(lambda f: (f / ".hse-studio" / "project.json").unlink(), id="project-json-gone"),
    ],
)
def test__changed__sources_or_title_data__true(tmp_path: Path, change: Any) -> None:
    svc, project, head = _built(tmp_path)
    change(tmp_path)

    assert svc.build_inputs_changed(project, SETTINGS, head) is True


def test__changed__committed_source_edit__true(tmp_path: Path) -> None:
    svc, project, head = _built(tmp_path)
    _write(tmp_path, "vkr/vkr.tex", "v2\n")
    svc.commit(project, message="Правка", kind=VcsCommitKind.edit)

    assert svc.build_inputs_changed(project, SETTINGS, head) is True


def test__changed__commit_not_in_history_or_not_a_commit_id__true(tmp_path: Path) -> None:
    svc, project, _head = _built(tmp_path)

    assert svc.build_inputs_changed(project, SETTINGS, "f" * 40) is True
    assert svc.build_inputs_changed(project, SETTINGS, "--output=/tmp/x") is True
    assert svc.build_inputs_changed(project, SETTINGS, "HEAD") is True
