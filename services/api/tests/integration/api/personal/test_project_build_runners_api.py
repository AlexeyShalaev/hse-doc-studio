"""Где идут сборки проекта: владелец выбирает политику, соавтор видит только имя и состояние раннера владельца."""

from __future__ import annotations

import pytest

from tests.integration.api.personal.conftest import Stand, seed_shared_project

pytestmark = pytest.mark.pg


async def test__build_runners__owner_edits_coauthor_reads_only_name_and_state(stand: Stand) -> None:
    anna, boris, vera = await stand.person("anna"), await stand.person("boris"), await stand.person("vera")
    stand.personal_runner(anna, "MacBook Анны")
    project = await seed_shared_project(stand, anna, (boris, "editor"), (vera, "reader"))
    path = f"/api/v1/projects/{project}/build-runners"

    owner_view = stand.client.get(path, headers=anna.headers)
    assert owner_view.status_code == 200, owner_view.text
    assert owner_view.json() == {
        "policy": "shared",
        "editable": True,
        "project_kind": "personal",
        "personal_runners_enabled": True,
        "my_builds": "personal_first",
        "wait_s": 5,
        "owner_runners": [{"name": "MacBook Анны", "state": "online"}],
    }
    coauthor = stand.client.get(path, headers=boris.headers).json()
    assert (coauthor["editable"], coauthor["my_builds"], coauthor["owner_runners"]) == (
        False,
        "shared",
        [{"name": "MacBook Анны", "state": "online"}],
    )

    refused = stand.client.put(path, json={"policy": "owner"}, headers=boris.headers)
    assert refused.status_code == 403
    assert refused.json().get("required_role") == "owner"

    changed = stand.client.put(path, json={"policy": "owner"}, headers=anna.headers)
    assert changed.json()["policy"] == "owner"
    assert stand.client.get(path, headers=boris.headers).json()["my_builds"] == "personal_first"
    assert stand.client.get(path, headers=vera.headers).status_code == 200


async def test__build_runners__stranger_does_not_see_the_project(stand: Stand) -> None:
    anna, stranger = await stand.person("anna"), await stand.person("eve")
    project = await seed_shared_project(stand, anna)
    response = stand.client.get(f"/api/v1/projects/{project}/build-runners", headers=stranger.headers)
    assert response.status_code in (403, 404)


async def test__build_runners__owner_without_runners_builds_on_shared(stand: Stand) -> None:
    anna = await stand.person("anna")
    project = await seed_shared_project(stand, anna)
    view = stand.client.get(f"/api/v1/projects/{project}/build-runners", headers=anna.headers).json()
    assert (view["owner_runners"], view["my_builds"]) == ([], "shared")
