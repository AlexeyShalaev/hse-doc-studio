"""Локальная Студия входит на сервер Студии кодом устройства, видит его проекты и клонирует проект токеном.

Локальная и серверная Студии делят один объект `settings`, поэтому серверная живёт настоящим HTTP-сервером, а
локальная сторона проверяется своим сценарием (`StudioServersService`) с настоящими клиентом и хранилищем доступов.
"""

from __future__ import annotations

import asyncio
import base64
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.git_remote.client import StudioServerError
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.infra.git_remote_client.studio_client import HttpStudioServerClient
from hse_doc_studio.infra.git_sync.credential_repository import JsonGitCredentialRepository
from hse_doc_studio.infra.git_sync.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.git_sync.key_store import KeyFileStore
from hse_doc_studio.use_cases.git_sync.studio_servers import LoginState, StudioServerLogins, StudioServersService

from tests.integration.api.git_remote.conftest import Live, git

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]


class _Hosts:
    async def get(self, _host: str, _port: int | None) -> None:
        return None

    async def materialize(self) -> None:
        return None

    def trust_file(self, _host: str, _port: int | None) -> Path | None:
        return None


def _service(tmp: Path) -> tuple[StudioServersService, JsonGitCredentialRepository]:
    data = tmp / "local"
    credentials = JsonGitCredentialRepository(data, FernetSecretCipher(KeyFileStore(data / "secrets" / "k.json")))
    service = StudioServersService(
        HttpStudioServerClient(timeout_s=10),
        credentials,
        _Hosts(),
        StudioServerLogins(),  # type: ignore[arg-type]
    )
    return service, credentials


def _approve(live: Live, person: Any, code: str) -> None:
    with live.client() as client:
        response = client.post(
            f"/api/v1/account/device/{code}",
            json={"decision": "approve", "scopes": ["git:read", "git:write"]},
            headers=person.session,
            cookies=person.cookies,
        )
    assert response.status_code == 200, response.text


def test__studio_login__device_flow_lists_projects_and_clones(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna, "ВКР: Анализ требований")
    service, credentials = _service(live.tmp)

    async def scenario() -> None:
        login = await service.start_login(live.base, "Студия на MacBook Анны")
        assert login.state == LoginState.pending
        assert login.verification_uri_complete == f"{live.base}/device?code={login.user_code}"
        await asyncio.to_thread(_approve, live, anna, str(login.user_code))
        for _ in range(60):
            current = service.get_login(login.login_id)
            if current.state != LoginState.pending:
                break
            await asyncio.sleep(0.5)
        assert current.state == LoginState.approved, current
        assert current.credential_id is not None

        (server,) = await service.list_servers()
        assert (server.state, server.account_name, server.scopes) == ("ok", "anna", ("git:read", "git:write"))
        page = await service.list_projects(current.credential_id, q=None, limit=50, offset=0)
        assert [p.id for p in page.items] == [project]
        assert page.items[0].can_push is True

        secret = (await credentials.get_secret(current.credential_id)).reveal()
        basic = base64.b64encode(f"hse:{secret}".encode()).decode()
        await asyncio.to_thread(
            git,
            "-c",
            f"http.extraHeader=Authorization: Basic {basic}",
            "clone",
            page.items[0].clone_url,
            "cloned",
            cwd=live.tmp,
        )
        assert (live.tmp / "cloned" / ".hse-studio" / "project.json").is_file()

        (token,) = [t for t in _tokens(live, anna) if t["origin"] == "device"]
        await asyncio.to_thread(_revoke, live, anna, token["id"])
        (revoked,) = await service.list_servers()
        assert revoked.state == "revoked"
        with pytest.raises(GitSyncError):
            await service.list_projects(current.credential_id, q=None, limit=50, offset=0)
        await service.forget(current.credential_id)
        assert await service.list_servers() == []

    asyncio.run(scenario())


def test__studio_login__not_a_studio_and_bad_url(live: Live) -> None:
    service, _ = _service(live.tmp)

    async def scenario() -> None:
        with pytest.raises(StudioServerError) as plain:
            await service.start_login("http://example.org", "x")
        assert plain.value.code == "git_server_url_invalid"
        with pytest.raises(StudioServerError) as gone:
            await service.start_login("http://127.0.0.1:9", "x")
        assert gone.value.code == "git_server_unreachable"
        with _foreign_server() as foreign, pytest.raises(StudioServerError) as other:
            await service.start_login(foreign, "x")
        assert other.value.code == "git_server_not_studio"

    asyncio.run(scenario())


@contextmanager
def _foreign_server() -> Iterator[str]:
    """Чужой HTTP-сервер на loopback: на `/git/-/info` он отвечает, но не как Студия."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — имя из http.server
            body = json.dumps({"server": "gitea"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def _tokens(live: Live, person: Any) -> list[dict[str, Any]]:
    with live.client() as client:
        return list(client.get("/api/v1/account/tokens", headers=person.session, cookies=person.cookies).json())


def _revoke(live: Live, person: Any, token_id: str) -> None:
    with live.client() as client:
        response = client.delete(f"/api/v1/account/tokens/{token_id}", headers=person.session, cookies=person.cookies)
    assert response.status_code == 204, response.text
