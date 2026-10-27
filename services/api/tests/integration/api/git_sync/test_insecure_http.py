"""Открытый http: проверка адреса и клонирование берут согласие у человека, а не подставляют его сами.

Политика сервера (`allow_insecure_http`) только разрешает такой адрес. Токен по сети открыто уйдёт, лишь если
человек согласился на это для данного адреса: поле `insecure_http` в запросе, как у подключения.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.api.schemas.git_sync import GitErrorBody, GitStatusResponse, ProbeResponse
from httpx import AsyncClient

from tests.fixtures.git_remote import GitHttpServer
from tests.integration.api.git_sync.studios import Studio

_TOKEN = "pat-token-0123456789"


@pytest.fixture
def server(http_git_server_factory: Callable[..., GitHttpServer], monkeypatch: pytest.MonkeyPatch) -> GitHttpServer:
    monkeypatch.setattr(app_settings.git, "allow_insecure_http", True)
    return http_git_server_factory(token=_TOKEN)


async def _credential(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/git/credentials", json={"kind": "pat", "label": "Токен", "host": "127.0.0.1", "token": _TOKEN}
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def test__probe__http_without_consent__refused_and_the_token_does_not_leave(
    test_app: AsyncClient, server: GitHttpServer
) -> None:
    server.create_repo("origin.git")
    credential_id = await _credential(test_app)

    resp = await test_app.post(
        "/api/v1/git/remote/probe", json={"url": server.url("origin.git"), "credential_id": credential_id}
    )

    assert resp.status_code == 422, resp.text
    assert GitErrorBody.model_validate(resp.json()).code == "url_scheme_forbidden"
    assert server.authorizations() == []


async def test__probe__http_with_consent__reaches_the_server_with_the_token(
    test_app: AsyncClient, server: GitHttpServer
) -> None:
    server.create_repo("origin.git")
    credential_id = await _credential(test_app)

    resp = await test_app.post(
        "/api/v1/git/remote/probe",
        json={"url": server.url("origin.git"), "credential_id": credential_id, "insecure_http": True},
    )

    assert resp.status_code == 200, resp.text
    assert ProbeResponse.model_validate(resp.json()).reachable is True
    assert server.authorizations()


async def test__clone__http_without_consent__refused_before_any_request(
    boris: Studio, server: GitHttpServer, tmp_path: Path
) -> None:
    server.create_repo("origin.git")
    credential_id = await _credential(boris.client)

    resp = await boris.client.post(
        "/api/v1/git/clone",
        json={"url": server.url("origin.git"), "credential_id": credential_id, "folder": str(tmp_path / "clone")},
    )

    assert resp.status_code == 422, resp.text
    assert GitErrorBody.model_validate(resp.json()).code == "url_scheme_forbidden"
    assert server.requests == []
    assert not (tmp_path / "clone").exists()


async def test__clone__http_with_consent__remembers_the_consent_on_the_remote(
    anna: Studio, boris: Studio, server: GitHttpServer, tmp_path: Path
) -> None:
    bare = server.create_repo("origin.git")
    await anna.create_project()
    anna.git("push", "--quiet", bare.url, "master:refs/heads/main")
    credential_id = await _credential(boris.client)

    resp = await boris.client.post(
        "/api/v1/git/clone",
        json={
            "url": server.url("origin.git"),
            "credential_id": credential_id,
            "folder": str(tmp_path / "clone"),
            "insecure_http": True,
        },
    )

    assert resp.status_code == 202, resp.text
    operation = await boris.wait(resp.json()["operation_id"])
    assert operation.status == "succeeded", operation.error
    assert operation.result is not None
    shown = await boris.client.get(f"/api/v1/projects/{operation.result.project_id}/git")  # type: ignore[union-attr]
    status = GitStatusResponse.model_validate(shown.json())
    assert status.remote is not None
    assert status.remote.insecure_http is True
