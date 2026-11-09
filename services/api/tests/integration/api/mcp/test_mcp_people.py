"""set_project_people локально: люди проекта доходят до common/meta.tex, проект «только для чтения» не пишется."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import httpx2
import pytest_asyncio
from dishka import AsyncContainer
from fastapi import FastAPI
from hse_doc_studio.api.mcp_server import install_mcp
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.template_materializer import ITemplateMaterializer
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from httpx import ASGITransport, AsyncClient
from mcp.client.client import Client
from mcp.client.streamable_http import streamable_http_client

from tests.factories import project_api_payload
from tests.fixtures.app import create_test_app, create_test_container

_BASE = "http://127.0.0.1"


@dataclass
class Studio:
    app: FastAPI
    container: AsyncContainer
    rest: AsyncClient
    project_id: str
    folder: Path


@pytest_asyncio.fixture
async def studio(tmp_path: Path) -> AsyncIterator[Studio]:
    """Курсовая магистратуры СПИ: её meta.tex печатает плейсхолдеры, пока руководитель и группа не заданы."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    container = create_test_container(data_dir)
    app = create_test_app(container)
    install_mcp(app, mode=StudioMode.local)
    folder = tmp_path / "kp"
    payload = {
        **project_api_payload(str(folder)),
        "name": "Курсовая",
        "pack_id": "hse-cs-sse",
        "template_id": "coursework",
        "kind": "project",
        "authors": [{"name": "Иван Иванов"}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url=_BASE) as rest:
        created = await rest.post("/api/v1/projects", json=payload)
        assert created.status_code == 201, created.text
        enabled = await rest.put("/api/v1/mcp/settings", json={"enabled": True})
        assert enabled.status_code == 200, enabled.text
        yield Studio(app=app, container=container, rest=rest, project_id=created.json()["id"], folder=folder)
    await container.close()


def _client(studio: Studio) -> Client:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=studio.app), base_url=_BASE)
    return Client(streamable_http_client(f"{_BASE}/mcp", http_client=http), mode="legacy")


async def _rendered_meta(studio: Studio) -> str:
    """common/meta.tex так, как его перегенерирует сборка перед xelatex (TriggerCompileUC)."""
    async with studio.container() as request:
        project = (
            await (await request.get(GetProjectUC)).execute(GetProjectInput(project_id=UUID(studio.project_id)))
        ).project
        templates = await request.get(ITemplateRepository)  # type: ignore[type-abstract]
        materializer = await request.get(ITemplateMaterializer)  # type: ignore[type-abstract]
        version = templates.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        assert version is not None
        materializer.regenerate_dynamic_includes(project, version)
    return (studio.folder / "common" / "meta.tex").read_text(encoding="utf-8")


async def test__set_project_people__values_reach_meta_tex_instead_of_placeholders(studio: Studio) -> None:
    before = await _rendered_meta(studio)
    assert "\\hseFill{ФИО научного руководителя}" in before
    assert "\\hseFill{группа}" in before

    async with _client(studio) as client:
        result = await client.call_tool(
            "set_project_people",
            {
                "project_id": studio.project_id,
                "supervisor": {"name": "С. А. Шершаков", "degree": "канд. техн. наук", "title": "доцент"},
                "co_supervisor": {"name": "П. П. Петров", "role": "company", "title": "ведущий инженер"},
                "author": {"group": "МПИ251", "email": "ivanov@edu.hse.ru"},
            },
        )

    assert result.is_error is False, result.content
    meta = await _rendered_meta(studio)
    assert "\\hseFill{ФИО научного руководителя}" not in meta
    assert "\\hseFill{группа}" not in meta
    assert "С. А. Шершаков" in meta
    assert "\\hseSupervisorName, канд. техн. наук, доцент" in meta
    assert "МПИ251" in meta
    assert "ivanov@edu.hse.ru" in meta
    assert "\\hseHasCoSupervisortrue" in meta
    project = (await studio.rest.get(f"/api/v1/projects/{studio.project_id}")).json()
    (author,) = project["authors"]
    assert (author["name"], author["group"], author["email"]) == ("Иван Иванов", "МПИ251", "ivanov@edu.hse.ru")


async def test__set_project_people__empty_values__clear_fields_and_placeholders_return(studio: Studio) -> None:
    async with _client(studio) as client:
        await client.call_tool(
            "set_project_people",
            {"project_id": studio.project_id, "supervisor": {"name": "С. А. Шершаков"}, "author": {"group": "МПИ251"}},
        )
        result = await client.call_tool(
            "set_project_people",
            {"project_id": studio.project_id, "supervisor": {"name": ""}, "author": {"group": ""}},
        )

    assert result.is_error is False, result.content
    project = (await studio.rest.get(f"/api/v1/projects/{studio.project_id}")).json()
    assert project["supervisor"] is None
    assert project["authors"][0]["group"] is None
    meta = await _rendered_meta(studio)
    assert "\\hseFill{ФИО научного руководителя}" in meta
    assert "\\hseFill{группа}" in meta


async def test__set_project_people__read_only_project__refused_and_nothing_written(studio: Studio) -> None:
    # Проект записан более новой Студией, которая запрещает старым писать: так же отказывает и PATCH в вебе.
    state = studio.folder / ".hse-studio" / "project.json"
    data = json.loads(state.read_text(encoding="utf-8"))
    data["schema"] = {"version": 9, "read_compat": 1, "write_compat": 9, "written_by": "9.0.0"}
    state.write_text(json.dumps(data), encoding="utf-8")

    async with _client(studio) as client:
        result = await client.call_tool(
            "set_project_people", {"project_id": studio.project_id, "supervisor": {"name": "С. А. Шершаков"}}
        )

    assert result.is_error is True
    assert result.meta is not None
    assert result.meta["code"] == "read_only"
    assert json.loads(state.read_text(encoding="utf-8")).get("supervisor") is None
