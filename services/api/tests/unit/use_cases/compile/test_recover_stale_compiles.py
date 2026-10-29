"""Восстановление сборок, застрявших в pending/running после сбоя."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hse_doc_studio.core.enums import CompileStatus, DocumentStatus
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.use_cases.compile.recover_stale_compiles import RecoverStaleCompilesUC

from tests.contract.test_compile_contract import make_record
from tests.factories import make_document, make_project
from tests.fakes.compile import InMemoryCompileRepository
from tests.fakes.project_locator import InMemoryProjectLocator


async def test__execute__stuck_records_fail_and_building_documents_are_unstuck(tmp_path: Path) -> None:
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
    assert recovered.status is CompileStatus.failure
    assert recovered.finished_at is not None
    assert recovered.log.startswith("шаг 1\n[stale]")
    assert await compiles.get_for_project(folder, done.id) == done
    reloaded = projects.get(folder)
    assert reloaded is not None
    assert reloaded.documents[0].status is DocumentStatus.err
