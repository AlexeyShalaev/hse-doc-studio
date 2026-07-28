from __future__ import annotations

import pytest
from hse_doc_studio.core.ai_catalog import ModelCatalog
from hse_doc_studio.core.entities import CatalogModel, PullJob
from hse_doc_studio.use_cases.ai_runtime.start_pull import StartPullInput, StartPullUC


class _FakeJobs:
    def __init__(self) -> None:
        self.started: str | None = None

    async def start(self, name: str) -> PullJob:
        self.started = name
        return PullJob(name=name, state="running", message="…", error=None)

    def list_jobs(self) -> list[PullJob]:
        return []

    def dismiss(self, name: str) -> None:
        pass


def _catalog() -> ModelCatalog:
    return ModelCatalog(models=[CatalogModel("qwen2.5:7b", "Qwen2.5 7B", "Qwen2.5", 7.0, 4.7, 6.0, 16.0, [], "")])


@pytest.mark.unit
async def test__start_pull__catalog_name_always_allowed() -> None:
    jobs = _FakeJobs()
    uc = StartPullUC(jobs=jobs, catalog=_catalog(), allow_custom=False)

    job = await uc.execute(StartPullInput(name="qwen2.5:7b"))

    assert jobs.started == "qwen2.5:7b"
    assert job.state == "running"


@pytest.mark.unit
async def test__start_pull__custom_valid_name_allowed_when_enabled() -> None:
    jobs = _FakeJobs()
    uc = StartPullUC(jobs=jobs, catalog=_catalog(), allow_custom=True)

    await uc.execute(StartPullInput(name="mistral:7b-instruct"))

    assert jobs.started == "mistral:7b-instruct"


@pytest.mark.unit
async def test__start_pull__custom_rejected_when_disabled() -> None:
    jobs = _FakeJobs()
    uc = StartPullUC(jobs=jobs, catalog=_catalog(), allow_custom=False)

    with pytest.raises(ValueError, match="нет в каталоге"):
        await uc.execute(StartPullInput(name="mistral:7b"))
    assert jobs.started is None


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["bad name!", "evil; rm -rf", "  ", "a" * 200])
async def test__start_pull__malformed_name_rejected_even_when_custom_enabled(bad: str) -> None:
    jobs = _FakeJobs()
    uc = StartPullUC(jobs=jobs, catalog=_catalog(), allow_custom=True)

    with pytest.raises(ValueError, match="некорректное название модели|укажите название модели"):
        await uc.execute(StartPullInput(name=bad))

    assert jobs.started is None
