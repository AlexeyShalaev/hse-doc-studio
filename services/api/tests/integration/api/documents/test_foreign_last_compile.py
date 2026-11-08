"""Ссылка на последнюю сборку, пришедшая git-синхронизацией с другой Студии, не должна висеть.

project.json общий с облаком: перемотка и клон приносят `documents[].last_compile_id` облачной сборки, которой в
журнале этой Студии нет. Студия отдаёт вместо неё свою последнюю сборку документа (или ничего), а файл не правит.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CompileStatus, EngineType
from hse_doc_studio.infra.persistence.compile import JsonCompileRepository
from httpx import AsyncClient

_FOREIGN = uuid.UUID("039ea6b1-7bee-48b4-9613-589f292f779e")


def _project_file(project: dict[str, Any]) -> Path:
    return Path(project["folder"]) / ".hse-studio" / "project.json"


def _point_to(project: dict[str, Any], doc_id: str, compile_id: uuid.UUID) -> None:
    """Как после перемотки на облачный коммит: в project.json ссылка, записанная облаком."""
    path = _project_file(project)
    data = json.loads(path.read_text(encoding="utf-8"))
    for doc in data["documents"]:
        if doc["id"] == doc_id:
            doc["last_compile_id"] = str(compile_id)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def _local_build(project: dict[str, Any], doc_id: str, *, age: timedelta) -> uuid.UUID:
    started = datetime.now(UTC) - age
    record = CompileRecord(
        id=uuid.uuid4(),
        project_folder=Path(project["folder"]),
        doc_id=doc_id,
        engine=EngineType.xelatex,
        status=CompileStatus.success,
        started_at=started,
        finished_at=started + timedelta(seconds=30),
        log="",
        output_path=None,
        check_results=[],
        pages=2,
    )
    await JsonCompileRepository().save(record)
    return record.id


async def _doc_id(client: AsyncClient, project: dict[str, Any]) -> str:
    docs = (await client.get(f"/api/v1/projects/{project['id']}/documents")).json()
    return str(docs[0]["id"])


async def _listed(client: AsyncClient, project: dict[str, Any], doc_id: str) -> Any:
    resp = await client.get(f"/api/v1/projects/{project['id']}/documents")
    assert resp.status_code == 200, resp.text
    return next(d for d in resp.json() if d["id"] == doc_id)["last_compile_id"]


async def test__foreign_pointer__points_to_the_latest_local_build_everywhere(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    doc_id = await _doc_id(test_app, project)
    await _local_build(project, doc_id, age=timedelta(days=2))
    latest = await _local_build(project, doc_id, age=timedelta(hours=1))
    _point_to(project, doc_id, _FOREIGN)
    before = _project_file(project).read_bytes()

    listed = await _listed(test_app, project, doc_id)
    detail = (await test_app.get(f"/api/v1/projects/{project['id']}/documents/{doc_id}")).json()
    checks = (await test_app.get(f"/api/v1/projects/{project['id']}/documents/{doc_id}/checks")).json()
    compile_resp = await test_app.get(f"/api/v1/projects/{project['id']}/documents/{doc_id}/compiles/{listed}")

    assert listed == detail["last_compile_id"] == checks["compile_id"] == str(latest)
    assert compile_resp.status_code == 200, compile_resp.text
    # Файл общий с облаком: правка ушла бы туда следующей синхронизацией.
    assert _project_file(project).read_bytes() == before


async def test__foreign_pointer__no_local_builds__is_empty(test_app: AsyncClient, project: dict[str, Any]) -> None:
    doc_id = await _doc_id(test_app, project)
    _point_to(project, doc_id, _FOREIGN)

    assert await _listed(test_app, project, doc_id) is None
    checks = (await test_app.get(f"/api/v1/projects/{project['id']}/documents/{doc_id}/checks")).json()
    assert checks["compile_id"] is None


async def test__foreign_pointer__cloud_pdf_fetched_later__the_same_id_comes_alive(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    """Получение облачного PDF пишет запись под облачным id: ссылка из project.json снова верна и остаётся."""
    doc_id = await _doc_id(test_app, project)
    await _local_build(project, doc_id, age=timedelta(days=2))
    _point_to(project, doc_id, _FOREIGN)
    old = JsonCompileRepository()
    record = await old.get_for_project(Path(project["folder"]), await _any_record(project, doc_id))
    assert record is not None
    await old.save(
        CompileRecord(
            id=_FOREIGN,
            project_folder=record.project_folder,
            doc_id=doc_id,
            engine=record.engine,
            status=CompileStatus.success,
            started_at=record.started_at - timedelta(days=1),  # даже более старая по времени
            finished_at=record.finished_at,
            log="# fetched-from-cloud\n",
            output_path=None,
            check_results=[],
            pages=2,
        )
    )

    assert await _listed(test_app, project, doc_id) == str(_FOREIGN)


async def _any_record(project: dict[str, Any], doc_id: str) -> uuid.UUID:
    records = await JsonCompileRepository().list_for_document(Path(project["folder"]), doc_id)
    return records[0].id
