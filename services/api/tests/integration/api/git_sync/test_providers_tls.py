"""Провайдеры и TLS через настоящий API: свой CA, закреплённый сертификат, определение GitLab, проверка токена.

Сервер один и тот же: настоящий `git http-backend` за https на 127.0.0.1, который по тем же адресам отвечает как API
GitLab. Сертификаты создаются в тесте, сеть не нужна.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.schemas.git_sync import (
    GitCredentialCheckResponse,
    GitCredentialResponse,
    GitErrorBody,
    GitHostSettingsResponse,
    ProbeResponse,
)
from httpx import AsyncClient

from tests.fixtures.git_remote import ApiReply, GitHttpServer, seed_remote
from tests.fixtures.tls import TlsMaterial, make_ca_signed, make_self_signed

_TOKEN = "pat-token-0123456789"
_PROJECT = '{"id": "6f1c9a0e-0000-4000-8000-000000000001", "name": "Course paper"}\n'


def _data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


class Gitlab:
    """Поведение API GitLab на сервере: что отвечает на проверку токена, меняется между обращениями."""

    def __init__(self) -> None:
        self.scopes: list[str] = ["read_repository", "write_repository"]
        self.expires_at: str | None = (datetime.now(timezone.utc) + timedelta(days=60)).date().isoformat()
        self.token_status = 200

    def api(self) -> dict[str, Callable[[Mapping[str, str]], ApiReply]]:
        return {
            "/api/v4/version": lambda _h: (200, {}, {"version": "17.3.1", "revision": "abc1234"}),
            "/api/v4/personal_access_tokens/self": self._token,
            "/api/v4/user": lambda h: (
                (200, {}, {"username": "anna.petrova"}) if h.get("private-token") == _TOKEN else (401, {}, {})
            ),
        }

    def _token(self, headers: Mapping[str, str]) -> ApiReply:
        if headers.get("private-token") != _TOKEN or self.token_status == 401:
            return 401, {}, {"error": "invalid_token", "error_description": "Token was revoked."}
        return (
            200,
            {},
            {"active": True, "revoked": False, "user_id": 7, "scopes": self.scopes, "expires_at": self.expires_at},
        )


@pytest.fixture
def gitlab() -> Gitlab:
    return Gitlab()


@pytest.fixture
def tls_server(http_git_server_factory: Callable[..., GitHttpServer], tmp_path: Path) -> GitHttpServer:
    """Открытый для чтения git-сервер с самоподписанным сертификатом."""
    server = http_git_server_factory(token=None, tls=make_self_signed(tmp_path / "tls"))
    seed_remote(server.create_repo("team/paper.git"), {"project.json": _PROJECT})
    return server


@pytest.fixture
def gitlab_server(
    http_git_server_factory: Callable[..., GitHttpServer], tmp_path: Path, gitlab: Gitlab
) -> GitHttpServer:
    """Тот же сервер за токеном, который заодно отвечает как API GitLab."""
    server = http_git_server_factory(tls=make_self_signed(tmp_path / "tls"))
    server.api.update(gitlab.api())
    seed_remote(server.create_repo("team/paper.git"), {"project.json": _PROJECT})
    return server


def _url(server: GitHttpServer, repo: str = "team/paper.git") -> str:
    return server.url(repo)


async def _probe(client: AsyncClient, url: str, credential_id: str | None = None) -> ProbeResponse:
    resp = await client.post("/api/v1/git/remote/probe", json={"url": url, "credential_id": credential_id})
    assert resp.status_code == 200, resp.text
    return ProbeResponse.model_validate(resp.json())


async def _put_settings(client: AsyncClient, **body: Any) -> Any:
    return await client.put("/api/v1/git/host-settings", json=body)


async def _credential(client: AsyncClient, host: str = "127.0.0.1") -> GitCredentialResponse:
    resp = await client.post(
        "/api/v1/git/credentials", json={"kind": "pat", "label": "GitLab ВШЭ", "host": host, "token": _TOKEN}
    )
    assert resp.status_code == 201, resp.text
    return GitCredentialResponse.model_validate(resp.json())


# --- настройки хостов ------------------------------------------------------------------------------------------


async def test__get_host_settings__fresh_install__is_empty(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/git/host-settings")

    assert resp.status_code == 200
    assert resp.json() == []


async def test__get_host_settings__lists_hosts_of_saved_credentials_with_their_provider(test_app: AsyncClient) -> None:
    await _credential(test_app, "github.com")

    body = (await test_app.get("/api/v1/git/host-settings")).json()

    parsed = [GitHostSettingsResponse.model_validate(item) for item in body]
    assert [(item.host, item.provider_info.id, item.provider_info.detected_by) for item in parsed] == [
        ("github.com", "github", "host")
    ]
    assert (parsed[0].ca_present, parsed[0].pinned_fingerprint, parsed[0].provider_override) == (False, None, None)


async def test__put_host_settings__override__is_listed_and_can_be_cleared(test_app: AsyncClient) -> None:
    resp = await _put_settings(test_app, host="Git.HSE.ru", provider_override="gitlab")

    assert resp.status_code == 200, resp.text
    body = GitHostSettingsResponse.model_validate(resp.json())
    assert (body.host, body.provider_override, body.provider_info.id, body.provider_info.detected_by) == (
        "git.hse.ru",
        "gitlab",
        "gitlab",
        "override",
    )
    assert len((await test_app.get("/api/v1/git/host-settings")).json()) == 1

    cleared = await _put_settings(test_app, host="git.hse.ru", provider_override=None)

    assert cleared.status_code == 200
    assert cleared.json()["provider_override"] is None
    assert (await test_app.get("/api/v1/git/host-settings")).json() == []


async def test__put_host_settings__unknown_provider__is_provider_unknown(test_app: AsyncClient) -> None:
    resp = await _put_settings(test_app, host="git.hse.ru", provider_override="svn")

    assert resp.status_code == 422
    assert GitErrorBody.model_validate(resp.json()).code == "provider_unknown"


async def test__put_host_settings__not_a_certificate__is_host_settings_invalid(test_app: AsyncClient) -> None:
    resp = await _put_settings(test_app, host="git.hse.ru", ca_pem="hello")

    assert resp.status_code == 422
    assert GitErrorBody.model_validate(resp.json()).code == "host_settings_invalid"


async def test__put_host_settings__private_key_in_the_pem__is_rejected_and_not_stored(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    material = make_self_signed(tmp_path / "k")
    pem = material.cert_pem + material.key_file.read_text(encoding="ascii")

    resp = await _put_settings(test_app, host="git.hse.ru", ca_pem=pem)

    assert resp.status_code == 422
    assert "PRIVATE KEY" not in resp.text
    assert b"PRIVATE KEY" not in b"".join(p.read_bytes() for p in _data_dir(tmp_path).rglob("*") if p.is_file())


async def test__put_host_settings__ca__marks_ca_present_and_keeps_files_private(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    material = make_ca_signed(tmp_path / "ca")

    resp = await _put_settings(test_app, host="git.hse.local", port=8443, ca_pem=material.ca_pem)

    assert resp.status_code == 200, resp.text
    body = GitHostSettingsResponse.model_validate(resp.json())
    assert (body.ca_present, body.port, body.pinned_fingerprint) == (True, 8443, None)
    assert "BEGIN CERTIFICATE" not in resp.text
    stored = json.loads((_data_dir(tmp_path) / "git" / "host_settings.json").read_text(encoding="utf-8"))
    assert stored["hosts"][0]["ca_pem"] == material.ca_pem


# --- TLS ------------------------------------------------------------------------------------------------------------


async def test__probe__self_signed_server__fails_with_untrusted_ca_and_the_presented_certificate(
    test_app: AsyncClient, tls_server: GitHttpServer
) -> None:
    probe = await _probe(test_app, _url(tls_server))

    assert probe.ok is False
    assert probe.error is not None
    assert probe.error.code == "tls_untrusted_ca"
    assert probe.error.certificate is not None
    assert probe.error.certificate.self_signed is True
    assert probe.error.certificate.fingerprint_sha256.startswith("SHA256:")
    assert (probe.reachable, probe.auth_ok) == (False, False)


async def test__probe__after_pinning_the_presented_fingerprint__server_is_reachable(
    test_app: AsyncClient, tls_server: GitHttpServer
) -> None:
    failed = await _probe(test_app, _url(tls_server))
    assert failed.error is not None
    assert failed.error.certificate is not None
    fingerprint = failed.error.certificate.fingerprint_sha256

    pinned = await _put_settings(test_app, host="127.0.0.1", port=tls_server.port, pinned_fingerprint=fingerprint)
    probe = await _probe(test_app, _url(tls_server))

    assert pinned.status_code == 200, pinned.text
    assert GitHostSettingsResponse.model_validate(pinned.json()).pinned_fingerprint == fingerprint
    assert (probe.ok, probe.reachable, probe.branches) == (True, True, ["main"])


async def test__put_host_settings__pin_with_a_wrong_fingerprint__is_pin_mismatch_with_both_values(
    test_app: AsyncClient, tls_server: GitHttpServer
) -> None:
    wrong = "SHA256:" + "A" * 43

    resp = await _put_settings(test_app, host="127.0.0.1", port=tls_server.port, pinned_fingerprint=wrong)

    assert resp.status_code == 409
    body = GitErrorBody.model_validate(resp.json())
    assert (body.code, body.expected) == ("tls_pin_mismatch", wrong)
    assert body.actual is not None
    assert body.actual != wrong
    assert (await test_app.get("/api/v1/git/host-settings")).json() == []


async def test__probe__server_certificate_changed_after_pinning__is_pin_mismatch_before_any_git_call(
    test_app: AsyncClient, tls_server: GitHttpServer, tmp_path: Path
) -> None:
    failed = await _probe(test_app, _url(tls_server))
    assert failed.error is not None
    assert failed.error.certificate is not None
    real = failed.error.certificate.fingerprint_sha256
    await _put_settings(test_app, host="127.0.0.1", port=tls_server.port, pinned_fingerprint=real)
    path = _data_dir(tmp_path) / "git" / "host_settings.json"
    other = "SHA256:" + "B" * 43
    path.write_text(path.read_text(encoding="utf-8").replace(real, other), encoding="utf-8")
    before = len([r for r in tls_server.requests if "paper.git" in r.path])

    probe = await _probe(test_app, _url(tls_server))

    assert probe.ok is False
    assert probe.error is not None
    assert probe.error.code == "tls_pin_mismatch"
    assert (probe.error.expected, probe.error.actual) == (other, real)
    assert len([r for r in tls_server.requests if "paper.git" in r.path]) == before


async def test__probe__server_with_certificate_of_an_internal_ca__works_once_the_ca_is_added(
    test_app: AsyncClient, http_git_server_factory: Callable[..., GitHttpServer], tmp_path: Path
) -> None:
    material: TlsMaterial = make_ca_signed(tmp_path / "ca")
    server = http_git_server_factory(token=None, tls=material)
    seed_remote(server.create_repo("team/paper.git"), {"project.json": _PROJECT})

    untrusted = await _probe(test_app, _url(server))
    await _put_settings(test_app, host="127.0.0.1", port=server.port, ca_pem=material.ca_pem)
    trusted = await _probe(test_app, _url(server))

    assert untrusted.error is not None
    assert untrusted.error.code == "tls_untrusted_ca"
    assert untrusted.error.certificate is not None
    assert untrusted.error.certificate.self_signed is False
    assert (trusted.ok, trusted.branches) == (True, ["main"])


async def test__probe__ca_of_one_server__does_not_open_another_one(
    test_app: AsyncClient, http_git_server_factory: Callable[..., GitHttpServer], tmp_path: Path
) -> None:
    material = make_ca_signed(tmp_path / "ca")
    trusted_server = http_git_server_factory(token=None, tls=material)
    other_server = http_git_server_factory(token=None, tls=material)
    seed_remote(other_server.create_repo("team/paper.git"), {"project.json": _PROJECT})
    await _put_settings(test_app, host="127.0.0.1", port=trusted_server.port, ca_pem=material.ca_pem)

    probe = await _probe(test_app, _url(other_server))

    assert probe.error is not None
    assert probe.error.code == "tls_untrusted_ca"


# --- провайдер и токен ------------------------------------------------------------------------------------------


async def _trusted(client: AsyncClient, server: GitHttpServer) -> None:
    failed = await _probe(client, _url(server))
    assert failed.error is not None
    assert failed.error.certificate is not None
    resp = await _put_settings(
        client,
        host="127.0.0.1",
        port=server.port,
        pinned_fingerprint=failed.error.certificate.fingerprint_sha256,
    )
    assert resp.status_code == 200, resp.text


async def test__probe__unknown_host_answering_like_gitlab__is_detected_with_version_and_token_is_assessed(
    test_app: AsyncClient, gitlab_server: GitHttpServer
) -> None:
    await _trusted(test_app, gitlab_server)
    credential = await _credential(test_app)

    probe = await _probe(test_app, _url(gitlab_server), str(credential.id))

    assert probe.ok is True
    assert (probe.provider_info.id, probe.provider_info.detected_by, probe.provider_info.version) == (
        "gitlab",
        "api",
        "17.3.1",
    )
    assert probe.url.provider == "gitlab"
    assert probe.token_info is not None
    assert (probe.token_info.login, probe.token_info.sufficiency, probe.token_info.missing) == (
        "anna.petrova",
        "sufficient",
        [],
    )
    assert probe.token_info.scopes == ["read_repository", "write_repository"]


async def test__probe__detection_sends_no_credentials_to_the_guessed_endpoints(
    test_app: AsyncClient, gitlab_server: GitHttpServer
) -> None:
    await _trusted(test_app, gitlab_server)
    credential = await _credential(test_app)

    await _probe(test_app, _url(gitlab_server), str(credential.id))

    version_requests = [request for request in gitlab_server.requests if request.path == "/api/v4/version"]
    assert version_requests
    assert all("authorization" not in r.headers and "private-token" not in r.headers for r in version_requests)


async def test__probe__token_expiry_is_stored_on_the_credential(
    test_app: AsyncClient, gitlab_server: GitHttpServer, gitlab: Gitlab
) -> None:
    await _trusted(test_app, gitlab_server)
    credential = await _credential(test_app)

    await _probe(test_app, _url(gitlab_server), str(credential.id))

    listed = [
        GitCredentialResponse.model_validate(item) for item in (await test_app.get("/api/v1/git/credentials")).json()
    ]
    assert listed[0].expires_at is not None
    assert listed[0].expires_at.date().isoformat() == gitlab.expires_at


async def test__patch_credential__new_token__forgets_the_expiry_of_the_old_one(
    test_app: AsyncClient, gitlab_server: GitHttpServer
) -> None:
    await _trusted(test_app, gitlab_server)
    credential = await _credential(test_app)
    await _probe(test_app, _url(gitlab_server), str(credential.id))
    assert (await test_app.get("/api/v1/git/credentials")).json()[0]["expires_at"] is not None

    resp = await test_app.patch(
        f"/api/v1/git/credentials/{credential.id}", json={"token": "glpat-newTokenValue1234567890"}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["expires_at"] is None


async def test__probe__token_without_write_scope__is_ok_but_too_narrow(
    test_app: AsyncClient, gitlab_server: GitHttpServer, gitlab: Gitlab
) -> None:
    gitlab.scopes = ["read_repository"]
    await _trusted(test_app, gitlab_server)
    credential = await _credential(test_app)

    probe = await _probe(test_app, _url(gitlab_server), str(credential.id))

    assert probe.ok is True
    assert probe.token_info is not None
    assert (probe.token_info.sufficiency, probe.token_info.missing) == ("too_narrow", ["write_repository"])


async def test__probe__token_with_api_scope__is_too_broad(
    test_app: AsyncClient, gitlab_server: GitHttpServer, gitlab: Gitlab
) -> None:
    gitlab.scopes = ["api"]
    await _trusted(test_app, gitlab_server)
    credential = await _credential(test_app)

    probe = await _probe(test_app, _url(gitlab_server), str(credential.id))

    assert probe.token_info is not None
    assert probe.token_info.sufficiency == "too_broad"


async def test__probe__expired_token__fails_with_token_expired_and_marks_the_credential(
    test_app: AsyncClient, gitlab_server: GitHttpServer, gitlab: Gitlab
) -> None:
    gitlab.expires_at = (datetime.now(timezone.utc) - timedelta(days=5)).date().isoformat()
    await _trusted(test_app, gitlab_server)
    credential = await _credential(test_app)

    probe = await _probe(test_app, _url(gitlab_server), str(credential.id))

    assert probe.ok is False
    assert probe.error is not None
    assert probe.error.code == "token_expired"
    assert (probe.reachable, probe.auth_ok) == (True, False)
    assert probe.token_info is not None
    assert probe.token_info.expires_at is not None
    listed = (await test_app.get("/api/v1/git/credentials")).json()
    assert listed[0]["status"] == "auth_failed"


async def test__probe__introspection_answers_401_for_a_token_git_accepts__the_git_check_decides(
    test_app: AsyncClient, gitlab_server: GitHttpServer, gitlab: Gitlab
) -> None:
    # Токены развёртывания и CI годятся для git, а этот адрес GitLab знает только личные токены.
    gitlab.token_status = 401
    await _trusted(test_app, gitlab_server)
    credential = await _credential(test_app)

    probe = await _probe(test_app, _url(gitlab_server), str(credential.id))

    assert probe.ok is True
    assert probe.token_info is not None
    assert probe.token_info.sufficiency == "unknown"
    listed = (await test_app.get("/api/v1/git/credentials")).json()
    assert listed[0]["status"] != "auth_failed"


async def test__probe__introspection_answers_401_and_git_rejects_the_token__fails_with_auth_failed(
    test_app: AsyncClient, gitlab_server: GitHttpServer
) -> None:
    await _trusted(test_app, gitlab_server)
    created = await test_app.post(
        "/api/v1/git/credentials",
        json={"kind": "pat", "label": "Чужой", "host": "127.0.0.1", "token": "wrong-token-0123456789"},
    )
    assert created.status_code == 201, created.text

    probe = await _probe(test_app, _url(gitlab_server), created.json()["id"])

    assert probe.ok is False
    assert probe.error is not None
    assert probe.error.code == "auth_failed"


async def test__probe__old_gitlab_without_token_endpoint__falls_back_to_the_git_check(
    test_app: AsyncClient, gitlab_server: GitHttpServer
) -> None:
    gitlab_server.api["/api/v4/personal_access_tokens/self"] = lambda _h: (404, {}, {"message": "404 Not Found"})
    await _trusted(test_app, gitlab_server)
    credential = await _credential(test_app)

    probe = await _probe(test_app, _url(gitlab_server), str(credential.id))

    assert probe.ok is True
    assert probe.token_info is not None
    assert (probe.token_info.sufficiency, probe.token_info.scopes, probe.token_info.login) == ("unknown", [], None)


async def test__probe__user_override__changes_the_provider_and_the_chip_survives(
    test_app: AsyncClient, gitlab_server: GitHttpServer
) -> None:
    await _trusted(test_app, gitlab_server)
    await _put_settings(test_app, host="127.0.0.1", port=gitlab_server.port, provider_override="gitea")

    probe = await _probe(test_app, _url(gitlab_server))

    assert (probe.provider_info.id, probe.provider_info.detected_by) == ("gitea", "override")
    assert probe.url.provider == "gitea"


async def test__probe__token_secret__never_reaches_responses_or_settings_files(
    test_app: AsyncClient, gitlab_server: GitHttpServer, tmp_path: Path
) -> None:
    await _trusted(test_app, gitlab_server)
    credential = await _credential(test_app)

    resp = await test_app.post(
        "/api/v1/git/remote/probe", json={"url": _url(gitlab_server), "credential_id": str(credential.id)}
    )

    assert _TOKEN not in resp.text
    for name in ("host_settings.json",):
        assert _TOKEN not in (_data_dir(tmp_path) / "git" / name).read_text(encoding="utf-8")


async def test__check_credential__after_detection__returns_provider_and_token_info(
    test_app: AsyncClient, gitlab_server: GitHttpServer
) -> None:
    await _trusted(test_app, gitlab_server)
    credential = await _credential(test_app)
    await _probe(test_app, _url(gitlab_server), str(credential.id))

    resp = await test_app.post(f"/api/v1/git/credentials/{credential.id}/check")

    assert resp.status_code == 200, resp.text
    body = GitCredentialCheckResponse.model_validate(resp.json())
    assert (body.provider_info.id, body.provider_info.version) == ("gitlab", "17.3.1")
    assert body.token_info is not None
    assert (body.token_info.login, body.token_info.sufficiency) == ("anna.petrova", "sufficient")
    assert body.credential.id == credential.id
    assert body.credential.expires_at is not None
    assert _TOKEN not in resp.text


async def test__check_credential__expired_token__is_token_expired(
    test_app: AsyncClient, gitlab_server: GitHttpServer, gitlab: Gitlab
) -> None:
    await _trusted(test_app, gitlab_server)
    credential = await _credential(test_app)
    await _probe(test_app, _url(gitlab_server), str(credential.id))
    gitlab.expires_at = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()

    resp = await test_app.post(f"/api/v1/git/credentials/{credential.id}/check")

    assert resp.status_code == 502
    assert GitErrorBody.model_validate(resp.json()).code == "token_expired"


async def test__check_credential__unknown_id__is_404(test_app: AsyncClient) -> None:
    resp = await test_app.post("/api/v1/git/credentials/6f1c9a0e-0000-4000-8000-0000000000ff/check")

    assert resp.status_code == 404


async def test__check_credential__ssh_key__is_422(test_app: AsyncClient) -> None:
    created = await test_app.post(
        "/api/v1/git/credentials", json={"kind": "ssh_key", "label": "Ключ", "host": "git.hse.ru"}
    )

    resp = await test_app.post(f"/api/v1/git/credentials/{created.json()['id']}/check")

    assert resp.status_code == 422
    assert GitErrorBody.model_validate(resp.json()).code == "credential_invalid"


async def test__check_credential__unreachable_server__is_offline(test_app: AsyncClient) -> None:
    credential = await _credential(test_app, "127.0.0.1")
    await _put_settings(test_app, host="127.0.0.1", port=1, provider_override="gitlab")

    resp = await test_app.post(f"/api/v1/git/credentials/{credential.id}/check")

    assert resp.status_code == 502
    assert GitErrorBody.model_validate(resp.json()).code in {"offline", "timeout"}
