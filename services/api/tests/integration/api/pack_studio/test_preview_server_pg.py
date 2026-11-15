"""Предпросмотр на сервере (template-studio.md, 6.3): задача `compile` в общей очереди Postgres.

Настоящий `create_app` на Postgres. Раннера, который возьмёт задачу, нет: проверяется постановка (вход задачи
загружен с тома предпросмотра, «проект» задачи это id сборки), отказ без раннеров и отмена в очереди.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.core.jobs.runners import IRunnerRepository, Runner
from hse_doc_studio.core.pack_studio.entities import PackWorkspace, WorkspaceKind, WorkspaceState
from hse_doc_studio.core.pack_studio.protocols import IPackWorkspaceRepository

from tests.integration.api.pack_studio.conftest import write_pack
from tests.integration.api.pack_studio.test_pack_studio_server_pg import (  # noqa: F401 — фикстура `server`
    API,
    _admin,
    _enable,
    _in_container,
    server,
)
from tests.integration.api.pack_studio.test_preview import PREVIEW_FILES, VERSION

pytestmark = pytest.mark.pg


def _ready_workspace(owner_id: str) -> str:
    """Пространство над git в состоянии `ready`, рабочее дерево с паком уже на диске (как после клона)."""
    now = datetime.now(UTC)
    ws = PackWorkspace(
        id=uuid.uuid4(),
        owner_id=owner_id,
        kind=WorkspaceKind.git,
        label="packs",
        packs_path="packs",
        created_at=now,
        updated_at=now,
        state=WorkspaceState.ready,
        remote_url="https://github.com/example/packs.git",
        base_branch="main",
        base_sha="0" * 40,
    )
    tree = Path(settings.data_dir) / "pack-studio" / "workspaces" / str(ws.id) / "tree" / "packs"
    write_pack(tree, PREVIEW_FILES)

    async def work(container: Any) -> None:
        await (await container.get(IPackWorkspaceRepository)).add(ws)

    asyncio.run(_in_container(work))
    return str(ws.id)


def _live_runner() -> None:
    runner = Runner(
        id=str(uuid.uuid4()),
        name="shared",
        token_hash="x" * 64,
        tags=frozenset({"tex"}),
        concurrency=1,
        resource_class="default",
        version="test",
        created_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )

    async def work(container: Any) -> None:
        await (await container.get(IRunnerRepository)).add(runner)

    asyncio.run(_in_container(work))


def _queued(job_id: str) -> Any:
    async def work(container: Any) -> Any:
        return await (await container.get(IJobQueue)).get(uuid.UUID(job_id))

    return asyncio.run(_in_container(work))


def _admin_id(admin: Any) -> str:
    return str(admin.get("/api/v1/session/bootstrap").json()["user"]["id"])


def _url(ws: str) -> str:
    return f"{API}/workspaces/{ws}/versions/demo/report/{VERSION}/preview"


def _wait(client: Any, ws: str, build_id: str, statuses: set[str]) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while True:
        body = client.get(f"{API}/workspaces/{ws}/previews/{build_id}").json()
        if body["status"] in statuses:
            return dict(body)
        assert time.monotonic() < deadline, body
        time.sleep(0.1)


def test__preview__no_live_runner__build_fails_with_no_runners(server: TestClient) -> None:  # noqa: F811
    admin = _admin(server)
    _enable(admin)
    ws = _ready_workspace(_admin_id(admin))

    resp = admin.post(_url(ws), json={"documents": ["report"], "example": "auto:normal"})

    assert resp.status_code == 202, resp.text
    (build,) = resp.json()["builds"]
    done = _wait(admin, ws, build["id"], {"failed", "succeeded", "cancelled"})
    assert done["status"] == "failed"
    assert done["error"]["code"] == "no_runners"


def test__preview__enqueued_from_the_preview_volume_then_cancelled(server: TestClient) -> None:  # noqa: F811
    admin = _admin(server)
    _enable(admin)
    ws = _ready_workspace(_admin_id(admin))
    _live_runner()

    resp = admin.post(_url(ws), json={"documents": ["report"], "example": "auto:normal"})
    assert resp.status_code == 202, resp.text
    (build,) = resp.json()["builds"]
    deadline = time.monotonic() + 30
    while (job := _queued(build["id"])) is None:
        assert time.monotonic() < deadline
        time.sleep(0.1)

    paths = {entry["path"] for entry in job.payload["manifest"]}
    assert job.project_id == uuid.UUID(build["id"])
    assert {"report/report.tex", "common/meta.tex"} <= paths
    assert job.payload["spec"]["payload"]["source_file"] == "report/report.tex"

    cancelled = admin.delete(f"{API}/workspaces/{ws}/previews/{build['id']}")
    assert cancelled.status_code == 200, cancelled.text
    done = _wait(admin, ws, build["id"], {"cancelled", "failed"})
    assert done["status"] == "cancelled"
