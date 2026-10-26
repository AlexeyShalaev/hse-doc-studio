from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from hse_doc_studio.api.schemas.git_sync import GitErrorBody, GitHostResponse
from hse_doc_studio.core.git_sync.entities import ScannedHostKey
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.host_keys import key_fingerprint
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_app, create_test_container
from tests.unit.core.git_sync.test_host_keys import GITHUB_ED25519, GITHUB_FINGERPRINT

_OTHER = "AAAAC3NzaC1lZDI1NTE5AAAAIGk1Zq6mYQdkYxjqU4tUq0h8Y1m7X6uQ0mHk2m9o3a4B"
_OTHER_FINGERPRINT = key_fingerprint(_OTHER)


class _Scanner:
    def __init__(self) -> None:
        self.keys: list[ScannedHostKey] | Exception = [
            ScannedHostKey("ssh-ed25519", GITHUB_ED25519, GITHUB_FINGERPRINT)
        ]
        self.calls: list[tuple[str, int | None]] = []

    async def scan(self, host: str, port: int | None) -> list[ScannedHostKey]:
        self.calls.append((host, port))
        if isinstance(self.keys, Exception):
            raise self.keys
        return self.keys


@pytest_asyncio.fixture
async def scanner() -> _Scanner:
    return _Scanner()


@pytest_asyncio.fixture
async def hosts_app(tmp_path: Path, scanner: _Scanner) -> AsyncIterator[AsyncClient]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    container = create_test_container(data_dir, host_key_scanner=scanner)
    app = create_test_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await container.close()


async def _trust(client: AsyncClient, **body: object) -> object:
    return await client.post(
        "/api/v1/git/hosts/trust", json={"host": "github.com", "fingerprint_sha256": GITHUB_FINGERPRINT, **body}
    )


async def test__get_hosts__empty_by_default(hosts_app: AsyncClient) -> None:
    resp = await hosts_app.get("/api/v1/git/hosts")

    assert resp.status_code == 200
    assert resp.json() == []


async def test__trust__then_list__returns_the_host_with_fingerprints(hosts_app: AsyncClient, tmp_path: Path) -> None:
    resp = await _trust(hosts_app)
    assert resp.status_code == 204, resp.text

    listed = await hosts_app.get("/api/v1/git/hosts")

    hosts = [GitHostResponse.model_validate(item) for item in listed.json()]
    assert [(h.host, h.port, h.key_types, h.fingerprints_sha256) for h in hosts] == [
        ("github.com", None, ["ssh-ed25519"], [GITHUB_FINGERPRINT])
    ]
    assert (tmp_path / "data" / "git" / "known_hosts").is_file()


async def test__trust__stale_fingerprint__409_host_key_changed_with_both(
    hosts_app: AsyncClient, scanner: _Scanner
) -> None:
    scanner.keys = [ScannedHostKey("ssh-ed25519", _OTHER, _OTHER_FINGERPRINT)]

    resp = await _trust(hosts_app)

    assert resp.status_code == 409
    body = GitErrorBody.model_validate(resp.json())
    assert body.code == GitErrorCode.host_key_changed.value
    assert (body.expected, body.actual) == (GITHUB_FINGERPRINT, _OTHER_FINGERPRINT)
    assert (await hosts_app.get("/api/v1/git/hosts")).json() == []


async def test__trust__replace_needs_the_typed_hostname(hosts_app: AsyncClient, scanner: _Scanner) -> None:
    await _trust(hosts_app)
    scanner.keys = [ScannedHostKey("ssh-ed25519", _OTHER, _OTHER_FINGERPRINT)]
    changed = {"fingerprint_sha256": _OTHER_FINGERPRINT}

    plain = await _trust(hosts_app, **changed)
    no_confirm = await _trust(hosts_app, replace=True, **changed)
    wrong = await _trust(hosts_app, replace=True, confirm_host="gitlab.com", **changed)
    done = await _trust(hosts_app, replace=True, confirm_host="github.com", **changed)

    assert [plain.status_code, no_confirm.status_code, wrong.status_code] == [409, 409, 409]
    assert done.status_code == 204
    listed = (await hosts_app.get("/api/v1/git/hosts")).json()
    assert listed[0]["fingerprints_sha256"] == [_OTHER_FINGERPRINT]


async def test__trust__unreachable_host__502_offline(hosts_app: AsyncClient, scanner: _Scanner) -> None:
    scanner.keys = GitSyncError(GitErrorCode.offline, "Нет связи")

    resp = await _trust(hosts_app)

    assert resp.status_code == 502
    assert resp.json()["code"] == "offline"


async def test__trust__hostile_host_or_fingerprint__422(hosts_app: AsyncClient, scanner: _Scanner) -> None:
    bad_host = await _trust(hosts_app, host="-oProxyCommand=touch pwned")
    bad_print = await _trust(hosts_app, fingerprint_sha256="nonsense")

    assert (bad_host.status_code, bad_print.status_code) == (422, 422)
    assert bad_host.json()["code"] == "credential_invalid"
    assert scanner.calls == []


async def test__delete_hosts__forgets_one_port_only(hosts_app: AsyncClient) -> None:
    await _trust(hosts_app)
    await _trust(hosts_app, port=443)

    resp = await hosts_app.delete("/api/v1/git/hosts", params={"host": "github.com", "port": 443})

    assert resp.status_code == 204
    listed = (await hosts_app.get("/api/v1/git/hosts")).json()
    assert [(h["host"], h["port"]) for h in listed] == [("github.com", None)]


async def test__delete_hosts__unknown_host_is_not_an_error(hosts_app: AsyncClient) -> None:
    resp = await hosts_app.delete("/api/v1/git/hosts", params={"host": "nowhere.example"})

    assert resp.status_code == 204
