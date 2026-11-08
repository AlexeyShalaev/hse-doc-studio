"""Восстановление сборок, застрявших в pending/running после перезапуска."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.compile.failure import INTERRUPTED
from hse_doc_studio.core.enums import CompileStatus, DocumentStatus
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.use_cases.compile.recover_stale_compiles import RecoverStaleCompilesUC

from tests.contract.test_compile_contract import make_record
from tests.factories import make_document, make_project
from tests.fakes.compile import InMemoryCompileRepository
from tests.fakes.project_locator import InMemoryProjectLocator


class ActiveDispatcher:
    """Диспетчер нового процесса, подхвативший задачи очереди: `is_active` по их id."""

    def __init__(self, *active: UUID) -> None:
        self._active = set(active)

    def is_active(self, job_id: UUID) -> bool:
        return job_id in self._active


async def test__execute__stuck_records_interrupted_and_building_documents_are_unstuck(tmp_path: Path) -> None:
    folder = tmp_path / "p"
    folder.mkdir()
    document = replace(make_document(), status=DocumentStatus.building)
    project = make_project(folder=folder, documents=[document])
    projects = JsonProjectRepository()
    projects.save(project)
    locator = InMemoryProjectLocator()
    locator.add(project)
    compiles = InMemoryCompileRepository()
    stuck = make_record(folder, status=CompileStatus.running, finished_at=None, log="шаг 1")
    done = make_record(folder, minutes=5)
    await compiles.save(stuck)
    await compiles.save(done)

    result = await RecoverStaleCompilesUC(projects, locator, compiles).execute()

    assert (result.recovered_compiles, result.unstuck_documents) == (1, 1)
    recovered = await compiles.get_for_project(folder, stuck.id)
    assert recovered is not None
    # Не failure: документ ни при чём, сборку оборвал перезапуск.
    assert recovered.status is CompileStatus.cancelled
    assert recovered.error_code == INTERRUPTED
    assert recovered.finished_at is not None
    assert recovered.log.startswith("шаг 1\n[stale]")
    assert await compiles.get_for_project(folder, done.id) == done
    reloaded = projects.get(folder)
    assert reloaded is not None
    assert reloaded.documents[0].status is DocumentStatus.err


async def test__execute__build_continued_by_the_dispatcher__record_and_document_left_running(tmp_path: Path) -> None:
    folder = tmp_path / "p"
    folder.mkdir()
    building = [
        replace(make_document("tz"), status=DocumentStatus.building),
        replace(make_document("vkr"), status=DocumentStatus.building),
    ]
    project = make_project(folder=folder, documents=building)
    projects = JsonProjectRepository()
    projects.save(project)
    locator = InMemoryProjectLocator()
    locator.add(project)
    compiles = InMemoryCompileRepository()
    continued = make_record(folder, doc_id="tz", status=CompileStatus.running, finished_at=None, log="")
    lost = make_record(folder, doc_id="vkr", status=CompileStatus.pending, finished_at=None, log="")
    await compiles.save(continued)
    await compiles.save(lost)

    result = await RecoverStaleCompilesUC(projects, locator, compiles, ActiveDispatcher(continued.id)).execute()

    assert (result.recovered_compiles, result.continued_compiles, result.unstuck_documents) == (1, 1, 1)
    assert await compiles.get_for_project(folder, continued.id) == continued
    interrupted = await compiles.get_for_project(folder, lost.id)
    assert interrupted is not None
    assert (interrupted.status, interrupted.error_code) == (CompileStatus.cancelled, INTERRUPTED)
    reloaded = projects.get(folder)
    assert reloaded is not None
    assert {d.id: d.status for d in reloaded.documents} == {"tz": DocumentStatus.building, "vkr": DocumentStatus.err}
