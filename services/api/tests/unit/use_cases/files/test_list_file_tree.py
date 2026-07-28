from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from hse_doc_studio.infra.persistence.files import LocalFileRepository
from hse_doc_studio.use_cases.files.list_file_tree import ListFileTreeInput, ListFileTreeUC


def _make_uc(tmp_path: Path) -> tuple[ListFileTreeUC, Path]:
    packs = tmp_path / "packs"
    files_dir = packs / "p" / "templates" / "t" / "versions" / "1" / "files"
    (files_dir / "vkr").mkdir(parents=True)
    (files_dir / "vkr" / "vkr.tex").write_text("template", encoding="utf-8")
    (files_dir / "common").mkdir(parents=True)
    (files_dir / "common" / "preamble.tex").write_text("pre", encoding="utf-8")
    (files_dir / "common" / "meta.tex.j2").write_text("{{ x }}", encoding="utf-8")

    project_folder = tmp_path / "project"
    (project_folder / "vkr").mkdir(parents=True)
    (project_folder / "vkr" / "vkr.tex").write_text("edited by user", encoding="utf-8")
    (project_folder / "vkr" / "diagram.png").write_text("user asset", encoding="utf-8")
    (project_folder / "common").mkdir(parents=True)
    (project_folder / "common" / "preamble.tex").write_text("pre", encoding="utf-8")
    (project_folder / "common" / "meta.tex").write_text("generated", encoding="utf-8")

    template_repo = MagicMock()
    template_repo._packs_dir = str(packs)
    template_repo.get_version.return_value = SimpleNamespace(
        pack_id="p",
        template_id="t",
        version="1",
        dynamic_includes=[SimpleNamespace(output="common/meta.tex")],
    )

    uc = ListFileTreeUC(
        project_repo=MagicMock(),
        project_index_repo=MagicMock(),
        file_repo=LocalFileRepository(),
        template_repo=template_repo,
    )
    project = SimpleNamespace(
        folder=project_folder,
        lock=SimpleNamespace(pack_id="p", template_id="t", version="1"),
        staffing="solo",
        authors=[],
        shared_enabled=True,
    )
    uc._get_uc = AsyncMock()
    uc._get_uc.execute.return_value = SimpleNamespace(project=project)
    return uc, project_folder


@pytest.mark.unit
async def test__list_file_tree__template_files_not_deletable(tmp_path: Path) -> None:
    uc, _ = _make_uc(tmp_path)
    result = await uc.execute(ListFileTreeInput(project_id=uuid4()))
    by_path = {item.path: item.deletable for item in result.items}

    assert by_path["vkr/vkr.tex"] is False  # template document
    assert by_path["common/preamble.tex"] is False  # template preamble
    assert by_path["common/meta.tex"] is False  # dynamic-include output


@pytest.mark.unit
async def test__list_file_tree__user_files_deletable(tmp_path: Path) -> None:
    uc, _ = _make_uc(tmp_path)
    result = await uc.execute(ListFileTreeInput(project_id=uuid4()))
    by_path = {item.path: item.deletable for item in result.items}

    assert by_path["vkr/diagram.png"] is True  # user-added asset


@pytest.mark.unit
async def test__list_file_tree__no_version__all_deletable(tmp_path: Path) -> None:
    uc, _ = _make_uc(tmp_path)
    uc._template_repo.get_version.return_value = None
    result = await uc.execute(ListFileTreeInput(project_id=uuid4()))
    assert all(item.deletable for item in result.items)
