from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from hse_doc_studio.infra.persistence.files import LocalFileRepository
from hse_doc_studio.use_cases.files._template_guard import is_protected_path
from hse_doc_studio.use_cases.files.delete_file import DeleteFileInput, DeleteFileUC
from hse_doc_studio.use_cases.files.move_file import MoveFileInput, MoveFileUC

# ── pure helper ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test__is_protected_path__exact_file() -> None:
    protected = {"vkr/vkr.tex", "common/meta.tex"}
    assert is_protected_path("vkr/vkr.tex", protected) is True
    assert is_protected_path("vkr/mine.png", protected) is False


@pytest.mark.unit
def test__is_protected_path__folder_with_protected_child() -> None:
    protected = {"vkr/vkr.tex"}
    assert is_protected_path("vkr", protected) is True  # folder holds a template file
    assert is_protected_path("assets", protected) is False


@pytest.mark.unit
def test__is_protected_path__empty() -> None:
    assert is_protected_path("", {"vkr/vkr.tex"}) is False


# ── UC integration (real template files/ dir + project on disk) ──────────


def _setup(tmp_path: Path) -> tuple[MagicMock, SimpleNamespace]:
    packs = tmp_path / "packs"
    files_dir = packs / "p" / "templates" / "t" / "versions" / "1" / "files" / "vkr"
    files_dir.mkdir(parents=True)
    (files_dir / "vkr.tex").write_text("tmpl", encoding="utf-8")

    project_folder = tmp_path / "project"
    (project_folder / "vkr").mkdir(parents=True)
    (project_folder / "vkr" / "vkr.tex").write_text("edited", encoding="utf-8")
    (project_folder / "vkr" / "diagram.png").write_text("user", encoding="utf-8")

    template_repo = MagicMock()
    template_repo._packs_dir = str(packs)
    template_repo.get_version.return_value = SimpleNamespace(
        pack_id="p", template_id="t", version="1", dynamic_includes=[]
    )
    project = SimpleNamespace(
        folder=project_folder,
        lock=SimpleNamespace(pack_id="p", template_id="t", version="1"),
        meta={},
        staffing="solo",
        authors=[],
        shared_enabled=True,
    )
    return template_repo, project


def _vcs_off() -> MagicMock:
    vcs = MagicMock()
    vcs.is_available.return_value = False  # short-circuit maybe_edit_commit
    return vcs


def _delete_uc(template_repo: MagicMock, project: SimpleNamespace) -> DeleteFileUC:
    uc = DeleteFileUC(
        project_repo=MagicMock(),
        project_index_repo=MagicMock(),
        file_repo=LocalFileRepository(),
        template_repo=template_repo,
        vcs_service=_vcs_off(),
        vcs_locks=MagicMock(),
        vcs_throttle=MagicMock(),
    )
    uc._get_uc = AsyncMock()
    uc._get_uc.execute.return_value = SimpleNamespace(project=project)
    return uc


def _move_uc(template_repo: MagicMock, project: SimpleNamespace) -> MoveFileUC:
    uc = MoveFileUC(
        project_repo=MagicMock(),
        project_index_repo=MagicMock(),
        file_repo=LocalFileRepository(),
        template_repo=template_repo,
        vcs_service=_vcs_off(),
        vcs_locks=MagicMock(),
        vcs_throttle=MagicMock(),
    )
    uc._get_uc = AsyncMock()
    uc._get_uc.execute.return_value = SimpleNamespace(project=project)
    return uc


@pytest.mark.unit
async def test__delete__template_file_refused(tmp_path: Path) -> None:
    template_repo, project = _setup(tmp_path)
    uc = _delete_uc(template_repo, project)
    with pytest.raises(PermissionError, match="шаблон"):
        await uc.execute(DeleteFileInput(project_id=uuid4(), path="vkr/vkr.tex"))
    assert (project.folder / "vkr" / "vkr.tex").exists()  # not deleted


@pytest.mark.unit
async def test__delete__user_file_allowed(tmp_path: Path) -> None:
    template_repo, project = _setup(tmp_path)
    uc = _delete_uc(template_repo, project)
    await uc.execute(DeleteFileInput(project_id=uuid4(), path="vkr/diagram.png"))
    assert not (project.folder / "vkr" / "diagram.png").exists()


@pytest.mark.unit
async def test__move__template_file_refused(tmp_path: Path) -> None:
    template_repo, project = _setup(tmp_path)
    uc = _move_uc(template_repo, project)
    with pytest.raises(PermissionError, match="шаблон"):
        await uc.execute(MoveFileInput(project_id=uuid4(), src="vkr/vkr.tex", dst="vkr/renamed.tex"))


@pytest.mark.unit
async def test__move__user_file_allowed(tmp_path: Path) -> None:
    template_repo, project = _setup(tmp_path)
    uc = _move_uc(template_repo, project)
    await uc.execute(MoveFileInput(project_id=uuid4(), src="vkr/diagram.png", dst="assets/diagram.png"))
    assert (project.folder / "assets" / "diagram.png").exists()
