"""Список проектов для локальной Студии (/git/-/projects) и адрес клонирования в настройках проекта."""

from __future__ import annotations

import pytest

from tests.integration.api.git_remote.conftest import Live

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]


def test__git_projects__only_projects_with_sources_and_push_by_scope(live: Live) -> None:
    anna, boris = live.person("anna"), live.person("boris")
    own = live.create_project(anna, "ВКР: Анализ требований")
    reviewed = live.create_project(boris, "Курсовой проект")
    hidden = live.create_project(boris, "Скрытый от читателя")
    live.add_member(reviewed, anna, "reviewer")
    live.add_member(hidden, anna, "reader", show_sources=False)
    write = live.token(anna, ["git:read", "git:write"])
    read = live.token(anna, ["git:read"])

    body = live.call("GET", "/git/-/projects", headers={"Authorization": f"Bearer {write}"}).json()

    by_id = {item["id"]: item for item in body["items"]}
    assert set(by_id) == {own, reviewed}
    assert body["total"] == 2
    assert by_id[own]["role"] == "owner"
    assert by_id[own]["can_push"] is True
    assert by_id[own]["clone_url"] == f"{live.base}/git/{own}.git"
    assert by_id[reviewed]["can_push"] is False
    assert by_id[reviewed]["owner_name"] == "boris"
    readonly = live.call("GET", "/git/-/projects", headers={"Authorization": f"Bearer {read}"}).json()
    assert all(item["can_push"] is False for item in readonly["items"])
    searched = live.call("GET", "/git/-/projects?q=Курсовой&limit=1", headers={"Authorization": f"Bearer {write}"})
    assert [item["id"] for item in searched.json()["items"]] == [reviewed]
    assert live.call("GET", "/git/-/projects", anna).status_code == 403


def test__project_git_remote__clone_url_role_and_bootstrap_capability(live: Live) -> None:
    anna, vera = live.person("anna"), live.person("vera")
    project = live.create_project(anna)
    live.add_member(project, vera, "reader", show_sources=True)

    owner = live.call("GET", f"/api/v1/projects/{project}/git-remote", anna).json()
    reader = live.call("GET", f"/api/v1/projects/{project}/git-remote", vera).json()

    assert owner == {
        "enabled": True,
        "clone_url": f"{live.base}/git/{project}.git",
        "can_push": True,
        "branch": "master",
    }
    assert reader["can_push"] is False
    assert reader["enabled"] is True
    caps = live.call("GET", "/api/v1/session/bootstrap").json()["capabilities"]
    assert (caps["git_remote"], caps["git_server_login"]) == (True, False)
