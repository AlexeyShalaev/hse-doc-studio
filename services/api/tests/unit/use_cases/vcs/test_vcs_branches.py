from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.vcs.entities import VcsBranch
from hse_doc_studio.use_cases.vcs.vcs_branches import DeleteVcsBranchInput, DeleteVcsBranchUC
from tests.factories import make_project


class _FakeProjectRepo:
    def __init__(self, project: Project) -> None:
        self._project = project

    def get(self, folder: Path) -> Project | None:  # noqa: ARG002
        return self._project

    def save(self, project: Project) -> None:  # noqa: ARG002, D102
        return None


class _FakeIndex:
    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def list_known(self) -> list[Path]:
        return [self._folder]

    def register(self, folder: Path) -> None:  # noqa: ARG002
        return None

    def unregister(self, folder: Path) -> None:  # noqa: ARG002
        return None


class _FakeVcs:
    def __init__(self, branches: list[VcsBranch]) -> None:
        self._branches = branches
        self.deleted: list[str] = []

    def is_available(self, project: Project) -> bool:  # noqa: ARG002
        return True

    def list_branches(self, project: Project) -> list[VcsBranch]:  # noqa: ARG002
        return self._branches

    def delete_branch(self, project: Project, *, name: str) -> None:  # noqa: ARG002
        self.deleted.append(name)


class _FakeLocks:
    def for_folder(self, folder: Path) -> asyncio.Lock:  # noqa: ARG002
        return asyncio.Lock()


def _uc(branches: list[VcsBranch]) -> tuple[DeleteVcsBranchUC, _FakeVcs, Project]:
    project = make_project(folder=Path("/tmp/proj"))
    vcs = _FakeVcs(branches)
    uc = DeleteVcsBranchUC(_FakeProjectRepo(project), _FakeIndex(project.folder), vcs, _FakeLocks())  # type: ignore[arg-type]
    return uc, vcs, project


@pytest.mark.parametrize(
    ("name", "match"),
    [
        pytest.param("master", "основную ветку", id="protected"),
        pytest.param("feat", "текущую ветку", id="current"),
    ],
)
async def test__execute__protected_or_current_branch__is_refused(name: str, match: str) -> None:
    branches = [
        VcsBranch(name="master", head="a", is_current=False, is_protected=True),
        VcsBranch(name="feat", head="b", is_current=True),
    ]
    uc, vcs, project = _uc(branches)

    with pytest.raises(ValueError, match=match):
        await uc.execute(DeleteVcsBranchInput(project_id=project.id, name=name))

    assert vcs.deleted == []  # never reached git


async def test__execute__normal_branch__succeeds() -> None:
    branches = [
        VcsBranch(name="master", head="a", is_current=True, is_protected=True),
        VcsBranch(name="feat", head="b", is_current=False),
    ]
    uc, vcs, project = _uc(branches)

    out = await uc.execute(DeleteVcsBranchInput(project_id=project.id, name="feat"))

    assert out.deleted is True
    assert vcs.deleted == ["feat"]
