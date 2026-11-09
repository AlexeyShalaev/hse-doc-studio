"""set_project_people в облаке: автор командного проекта по slug, e-mail, аудит и отказ без права на настройки."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

import pytest

from tests.integration.api.mcp.server.test_mcp_server_pg import _call, _enable, _token
from tests.integration.api.personal.conftest import Person, Stand

pytestmark = pytest.mark.pg


def _team_project(stand: Stand, owner: Person) -> str:
    """Командный проект через REST, как из мастера создания: двум авторам сценарий выводит slug из фамилии."""
    created = stand.client.post(
        "/api/v1/projects",
        json={
            "name": "Система",
            "pack_id": "hse-cs-se",
            "template_id": "vkr",
            "version": "2026.1",
            "engine": "xelatex",
            "kind": "project",
            "staffing": "team",
            "lang": "ru",
            "authors": [{"name": "Анна Смирнова"}, {"name": "Борис Петров"}],
            "meta": {},
        },
        headers=owner.headers,
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _authors(stand: Stand, headers: dict[str, str], project_id: str) -> list[dict[str, Any]]:
    card = json.loads(_call(stand, headers, "get_project", {"project_id": project_id})["content"][0]["text"])
    return list(card["authors"])


async def test__set_project_people__team_author_by_slug__changes_only_that_author(stand: Stand) -> None:
    _enable(stand)
    owner = await stand.person("tamara")
    headers = _token(stand, owner.email, ["mcp"])
    project_id = _team_project(stand, owner)
    anna, boris = _authors(stand, headers, project_id)

    result = _call(
        stand,
        headers,
        "set_project_people",
        {"project_id": project_id, "author": {"slug": boris["slug"], "group": "БПИ222", "email": "boris@edu.hse.ru"}},
    )
    no_slug = _call(stand, headers, "set_project_people", {"project_id": project_id, "author": {"group": "БПИ223"}})

    assert result["isError"] is False, result
    first, second = _authors(stand, headers, project_id)
    assert first == anna
    assert (second["slug"], second["group"], second["email"]) == (boris["slug"], "БПИ222", "boris@edu.hse.ru")
    assert no_slug["_meta"]["code"] == "invalid_arguments"
    events = stand.admin().get("/api/admin/audit", params={"action": "project.people_update"}).json()["items"]
    (event,) = [e for e in events if e["target"] == project_id]
    assert event["actor_id"] == owner.id
    assert event["details"]["after"]["authors"][1]["email"] == "boris@edu.hse.ru"


async def test__set_project_people__editor_without_settings_right__forbidden(stand: Stand) -> None:
    from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow  # noqa: PLC0415

    _enable(stand)
    owner = await stand.person("timur")
    editor = await stand.person("tina")
    project_id = _team_project(stand, owner)
    async with stand.sessions.use() as db:
        db.add(
            ProjectMemberRow(project_id=UUID(project_id), principal_kind="user", principal_id=editor.id, role="editor")
        )
    headers = _token(stand, editor.email, ["mcp"])

    result = _call(
        stand,
        headers,
        "set_project_people",
        {"project_id": project_id, "supervisor": {"name": ""}, "author": {"slug": "x", "group": "Г"}},
    )

    assert result["isError"] is True
    assert result["_meta"]["code"] == "forbidden"
    events = stand.admin().get("/api/admin/audit", params={"action": "project.people_update"}).json()["items"]
    assert not [e for e in events if e["target"] == project_id]


async def test__create_project__team_via_mcp__then_author_by_slug(stand: Stand) -> None:
    """Командный проект через MCP в облаке: папку выбирает сервер, slug авторов как у мастера создания."""
    _enable(stand)
    owner = await stand.person("tanya")
    headers = _token(stand, owner.email, ["mcp"])

    created = _call(
        stand,
        headers,
        "create_project",
        {
            "name": "Система",
            "pack_id": "hse-cs-se",
            "template_id": "vkr",
            "version": "2026.1",
            "kind": "project",
            "authors": [{"name": "Анна Смирнова", "topic": "Сервер"}, {"name": "Борис Петров", "topic": "Клиент"}],
            "supervisor": {"name": "Петров П. П."},
        },
    )
    assert created["isError"] is False, created
    match = re.search(r"id ([0-9a-f-]{36})", created["content"][0]["text"])
    assert match is not None, created
    project_id = match.group(1)
    card = json.loads(_call(stand, headers, "get_project", {"project_id": project_id})["content"][0]["text"])
    anna, boris = card["authors"]
    result = _call(
        stand,
        headers,
        "set_project_people",
        {"project_id": project_id, "author": {"slug": boris["slug"], "topic": "UI"}},
    )

    assert card["staffing"] == "team"
    assert (anna["slug"], anna["topic"], boris["slug"]) == ("anna", "Сервер", "boris")
    assert result["isError"] is False, result
    assert _authors(stand, headers, project_id)[1]["topic"] == "UI"
