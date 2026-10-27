from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from hse_doc_studio.api.schemas.git_sync import CiPreviewResponse, CiWriteResponse
from httpx import AsyncClient

from tests.integration.api.git.conftest import FAKE_PROJECT_ID

_GITHUB_PATH = ".github/workflows/hse-studio-build.yml"
_BODY: dict[str, Any] = {"provider": "github", "docs": "all", "publish": "artifacts", "triggers": ["push", "tag"]}


def _url(project: dict[str, Any], tail: str) -> str:
    return f"/api/v1/projects/{project['id']}/git/ci/{tail}"


def _tree(folder: Path) -> set[str]:
    return {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() and ".hse-studio" not in p.parts}


async def _doc_ids(client: AsyncClient, project: dict[str, Any]) -> list[str]:
    resp = await client.get(f"/api/v1/projects/{project['id']}/documents")
    assert resp.status_code == 200, resp.text
    return [doc["id"] for doc in resp.json()]


async def test__api__preview_ci__fresh_project__returns_contract_shape_and_writes_nothing(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    before = _tree(Path(project["folder"]))

    resp = await test_app.post(_url(project, "preview"), json=_BODY)

    assert resp.status_code == 200, resp.text
    data = CiPreviewResponse.model_validate(resp.json())
    [file] = data.files
    assert (file.path, file.exists, file.same) == (_GITHUB_PATH, False, False)
    assert yaml.safe_load(file.content)["jobs"]["build"]
    assert data.command == "hse-doc-studio build . --all --out build"
    assert _tree(Path(project["folder"])) == before


async def test__api__preview_ci__gitlab_with_listed_docs__points_at_gitlab_file(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    doc = (await _doc_ids(test_app, project))[0]
    body = {"provider": "gitlab", "docs": [doc], "publish": "release", "triggers": ["tag", "manual"]}

    resp = await test_app.post(_url(project, "preview"), json=body)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["files"][0]["path"] == ".gitlab-ci.yml"
    assert data["command"] == f"hse-doc-studio build . --docs {doc} --out build"
    assert "release-documents" in yaml.safe_load(data["files"][0]["content"])


async def test__api__write_ci__then_preview__reports_file_as_same(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    folder = Path(project["folder"])

    write = await test_app.post(_url(project, "write"), json={**_BODY, "overwrite": False})
    preview = await test_app.post(_url(project, "preview"), json=_BODY)

    assert write.status_code == 200, write.text
    assert CiWriteResponse.model_validate(write.json()).written == [_GITHUB_PATH]
    assert (folder / _GITHUB_PATH).read_text(encoding="utf-8") == preview.json()["files"][0]["content"]
    assert (preview.json()["files"][0]["exists"], preview.json()["files"][0]["same"]) == (True, True)


async def test__api__write_ci__only_the_ci_file_appears(test_app: AsyncClient, project: dict[str, Any]) -> None:
    folder = Path(project["folder"])
    before = _tree(folder)

    await test_app.post(_url(project, "write"), json={**_BODY, "overwrite": True})

    assert _tree(folder) - before == {_GITHUB_PATH}
    assert before <= _tree(folder)


async def test__api__write_ci__edited_file__needs_overwrite_to_be_replaced(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    target = Path(project["folder"]) / _GITHUB_PATH
    target.parent.mkdir(parents=True)
    target.write_text("name: mine\n", encoding="utf-8")

    preview = await test_app.post(_url(project, "preview"), json=_BODY)
    kept = await test_app.post(_url(project, "write"), json={**_BODY, "overwrite": False})
    kept_text = target.read_text(encoding="utf-8")
    replaced = await test_app.post(_url(project, "write"), json={**_BODY, "overwrite": True})

    assert (preview.json()["files"][0]["exists"], preview.json()["files"][0]["same"]) == (True, False)
    assert kept.json() == {"written": []}
    assert kept_text == "name: mine\n"
    assert replaced.json() == {"written": [_GITHUB_PATH]}
    assert target.read_text(encoding="utf-8") != "name: mine\n"


async def test__api__ci__invalid_options__return_422(test_app: AsyncClient, project: dict[str, Any]) -> None:
    bad_bodies = [
        {**_BODY, "provider": "bitbucket"},
        {**_BODY, "triggers": []},
        {**_BODY, "publish": "release", "triggers": ["push"]},
        {**_BODY, "docs": ["ghost"]},
        {**_BODY, "docs": ["a; rm -rf /"]},
        {**_BODY, "image": "bad image"},
    ]

    for body in bad_bodies:
        resp = await test_app.post(_url(project, "preview"), json=body)
        assert resp.status_code == 422, (body, resp.text)
        assert "detail" in resp.json()


async def test__api__ci__unknown_project__returns_404(test_app: AsyncClient) -> None:
    preview = await test_app.post(f"/api/v1/projects/{FAKE_PROJECT_ID}/git/ci/preview", json=_BODY)
    write = await test_app.post(f"/api/v1/projects/{FAKE_PROJECT_ID}/git/ci/write", json={**_BODY, "overwrite": True})

    assert preview.status_code == 404
    assert write.status_code == 404
