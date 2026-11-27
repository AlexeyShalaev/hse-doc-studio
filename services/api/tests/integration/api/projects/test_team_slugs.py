"""Слаг автора команды: в новом проекте из фамилии на языке проекта, в созданном проекте не меняется.

Слаг это имя папки автора, часть id его документов и слотов подписей. Раньше в английском проекте он брался из
первого слова ФИО («Ivan Ivanov» -> `ivan`), теперь из фамилии. Проекты, созданные по прежнему правилу, изображены
явными слагами `ivan` и `petr`: после любого изменения они должны остаться теми же.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from httpx import AsyncClient

from tests.factories import project_api_payload

_OLD = [
    {"name": "Ivan Ivanov", "slug": "ivan", "topic": "Server"},
    {"name": "Petr I. Petrov", "slug": "petr", "topic": "Client"},
]


async def _create(client: AsyncClient, folder: Path, authors: list[dict[str, Any]], lang: str = "en") -> dict[str, Any]:
    folder.mkdir(exist_ok=True)
    payload = {**project_api_payload(str(folder)), "kind": "project", "staffing": "team", "lang": lang}
    resp = await client.post("/api/v1/projects", json={**payload, "authors": authors})
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


async def _patch(client: AsyncClient, project: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    resp = await client.patch(f"/api/v1/projects/{project['id']}", json=body)
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


async def _owners(client: AsyncClient, project: dict[str, Any]) -> set[str]:
    resp = await client.get(f"/api/v1/projects/{project['id']}/documents")
    assert resp.status_code == 200, resp.text
    return {doc["owner"] for doc in resp.json() if doc.get("owner")}


def _slugs(project: dict[str, Any]) -> list[str | None]:
    return [author["slug"] for author in project["authors"]]


def _unnamed(authors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Авторы без слага, как их может прислать клиент API."""
    return [{key: value for key, value in author.items() if key != "slug"} for author in authors]


async def test__new_english_team_project__folders_are_named_after_surnames(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    folder = tmp_path / "proj"

    project = await _create(test_app, folder, _unnamed(_OLD))

    assert _slugs(project) == ["ivanov", "petrov"]
    assert (folder / "ivanov").is_dir()
    assert (folder / "petrov").is_dir()
    assert await _owners(test_app, project) == {"ivanov", "petrov"}


async def test__new_russian_team_project__first_word_as_before(test_app: AsyncClient, tmp_path: Path) -> None:
    authors = [{"name": "Иванов Иван", "topic": "A"}, {"name": "Петров Пётр", "topic": "B"}]

    project = await _create(test_app, tmp_path / "proj", authors, lang="ru")

    assert _slugs(project) == ["ivanov", "petrov"]


async def test__existing_project__saved_slugs_survive_every_change(test_app: AsyncClient, tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    project = await _create(test_app, folder, _OLD)
    authors = project["authors"]

    renamed_project = await _patch(test_app, project, {"name": "Other title"})
    from_settings = await _patch(test_app, project, {"authors": authors})
    without_slugs = await _patch(test_app, project, {"authors": _unnamed(authors)})
    reordered = await _patch(test_app, project, {"authors": _unnamed(authors)[::-1]})
    middle_name = [{**_unnamed(authors)[0], "name": "Ivan A. Ivanov"}, _unnamed(authors)[1]]
    renamed_author = await _patch(test_app, project, {"authors": middle_name})
    languages = [_slugs(await _patch(test_app, project, {"lang": lang})) for lang in ("ru", "en")]
    toggled = []
    for enabled in (False, True):
        resp = await test_app.post(
            f"/api/v1/projects/{project['id']}/team/sets", json={"author_slug": "ivan", "enabled": enabled}
        )
        assert resp.status_code == 200, resp.text
        toggled.append(_slugs(resp.json()))
    added = await _patch(
        test_app,
        project,
        {"authors": [*_unnamed(renamed_author["authors"]), {"name": "Ivan Sidorov", "managed": False}]},
    )

    for state in (renamed_project, from_settings, without_slugs, renamed_author):
        assert _slugs(state) == ["ivan", "petr"]
    assert _slugs(reordered) == ["petr", "ivan"]
    assert languages == [["ivan", "petr"]] * 2
    assert toggled == [["ivan", "petr"]] * 2
    assert _slugs(added) == ["ivan", "petr", "sidorov"]
    assert await _owners(test_app, project) == {"ivan", "petr"}
    assert (folder / "ivan").is_dir()
    assert not (folder / "ivanov").exists()


async def test__existing_project__connected_again_from_disk__keeps_slugs(test_app: AsyncClient, tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    project = await _create(test_app, folder, _OLD)
    resp = await test_app.delete(f"/api/v1/projects/{project['id']}")
    assert resp.status_code == 204, resp.text

    resp = await test_app.post("/api/v1/projects/connect", json={"folder": str(folder)})

    assert resp.status_code == 201, resp.text
    assert _slugs(resp.json()) == ["ivan", "petr"]
    assert await _owners(test_app, resp.json()) == {"ivan", "petr"}
