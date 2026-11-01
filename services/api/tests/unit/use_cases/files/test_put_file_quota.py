"""PutFileUC и предел проекта: запись сверх предела отказ и ничего не пишет, прирост учитывается, чтение живо."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from hse_doc_studio.core.projects.usage import IProjectQuota, ProjectQuotaExceededError
from hse_doc_studio.infra.persistence.files import LocalFileRepository
from hse_doc_studio.use_cases.files.put_file import PutFileInput, PutFileUC

pytestmark = pytest.mark.unit


class RecordingQuota:
    enabled = True

    def __init__(self, free: int) -> None:
        self.free = free
        self.recorded: list[int] = []

    async def check_write(self, project_id: object, delta_bytes: int) -> None:
        if delta_bytes > self.free:
            raise ProjectQuotaExceededError(uuid4(), 0, 0, delta_bytes)

    async def record_change(self, project_id: object, delta_bytes: int) -> None:
        self.recorded.append(delta_bytes)

    async def status(self, project_id: object) -> None:
        return None


def _uc(folder: Path, quota: IProjectQuota | None) -> PutFileUC:
    vcs = MagicMock()
    vcs.is_available.return_value = False
    uc = PutFileUC(
        project_repo=MagicMock(),
        project_index_repo=MagicMock(),
        file_repo=LocalFileRepository(),
        vcs_service=vcs,
        vcs_locks=MagicMock(),
        vcs_throttle=MagicMock(),
        quota=quota,
    )
    uc._get_uc = AsyncMock()
    uc._get_uc.execute.return_value = SimpleNamespace(project=SimpleNamespace(id=uuid4(), folder=folder))
    return uc


async def test__put_file__over_quota__refused_and_file_untouched(tmp_path: Path) -> None:
    (tmp_path / "a.tex").write_bytes(b"old")
    quota = RecordingQuota(free=5)

    with pytest.raises(ProjectQuotaExceededError):
        await _uc(tmp_path, quota).execute(PutFileInput(project_id=uuid4(), path="a.tex", content=b"x" * 100))

    assert (tmp_path / "a.tex").read_bytes() == b"old"
    assert quota.recorded == []


async def test__put_file__counts_growth_over_existing_file(tmp_path: Path) -> None:
    (tmp_path / "a.tex").write_bytes(b"12345")
    quota = RecordingQuota(free=100)

    await _uc(tmp_path, quota).execute(PutFileInput(project_id=uuid4(), path="a.tex", content=b"12345678"))
    await _uc(tmp_path, quota).execute(PutFileInput(project_id=uuid4(), path="new.tex", content=b"abc"))
    await _uc(tmp_path, quota).execute(PutFileInput(project_id=uuid4(), path="a.tex", content=b"1"))

    assert quota.recorded == [3, 3, -7]


async def test__put_file__without_quota__local_behaviour_unchanged(tmp_path: Path) -> None:
    await _uc(tmp_path, None).execute(PutFileInput(project_id=uuid4(), path="a.tex", content=b"x" * 10_000))

    assert (tmp_path / "a.tex").stat().st_size == 10_000
