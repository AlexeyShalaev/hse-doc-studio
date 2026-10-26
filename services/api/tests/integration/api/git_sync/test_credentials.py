from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.api.schemas.git_sync import GitCredentialResponse, GitErrorBody, SecretsStatusResponse
from hse_doc_studio.infra.git_sync.credential_repository import JsonGitCredentialRepository
from hse_doc_studio.infra.git_sync.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.git_sync.key_store import KeyFileStore
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from tests.fixtures.app import create_test_app, create_test_container
from tests.integration.api.vcs.conftest import create_project

_CANARY = "ghp_CANARYtokenValue1234567890abcdefXYZ"
_PAT = {"kind": "pat", "label": "GitHub, рабочий токен", "host": "GitHub.com", "token": _CANARY}
_SSH = {"kind": "ssh_key", "label": "Ключ для GitLab ВШЭ", "host": "git.hse.ru"}


def _data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


def _key_file(tmp_path: Path) -> Path:
    return _data_dir(tmp_path) / "secrets" / "master.keys.json"


def _all_bytes(root: Path) -> bytes:
    return b"".join(p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file())


async def _create(client: AsyncClient, body: dict[str, Any] | None = None) -> dict[str, Any]:
    resp = await client.post("/api/v1/git/credentials", json=body or _PAT)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test__post_credentials__pat__returns_masked_credential(test_app: AsyncClient) -> None:
    resp = await test_app.post("/api/v1/git/credentials", json=_PAT)

    assert resp.status_code == 201, resp.text
    body = GitCredentialResponse.model_validate(resp.json())
    assert (body.kind, body.label, body.host) == ("pat", "GitHub, рабочий токен", "github.com")
    assert body.status == "unverified"
    assert body.token_family == "ghp"
    assert body.username is None
    assert (body.public_key, body.fingerprint_sha256, body.last_used_at) == (None, None, None)
    assert body.used_by == []
    assert _CANARY not in resp.text


async def test__post_credentials__pat__token_is_stored_only_encrypted(test_app: AsyncClient, tmp_path: Path) -> None:
    created = await _create(test_app)

    assert _CANARY.encode() not in _all_bytes(_data_dir(tmp_path))
    repo = JsonGitCredentialRepository(_data_dir(tmp_path), FernetSecretCipher(KeyFileStore(_key_file(tmp_path))))
    secret = repo.get_secret(UUID(created["id"]))
    assert secret.reveal() == _CANARY


async def test__post_credentials__ssh_key__returns_public_key_and_fingerprint_only(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    resp = await test_app.post("/api/v1/git/credentials", json={**_SSH, "port": 2222})

    assert resp.status_code == 201, resp.text
    body = GitCredentialResponse.model_validate(resp.json())
    assert body.kind == "ssh_key"
    assert body.username == "git"
    assert body.public_key is not None
    assert body.public_key.startswith("ssh-ed25519 ")
    assert body.public_key.endswith(" hse-doc-studio:gitlab")
    assert body.fingerprint_sha256 is not None
    assert body.fingerprint_sha256.startswith("SHA256:")
    assert "PRIVATE KEY" not in resp.text
    assert b"PRIVATE KEY" not in _all_bytes(_data_dir(tmp_path))


async def test__get_credentials__lists_created_ones_in_order(test_app: AsyncClient) -> None:
    first = await _create(test_app)
    second = await _create(test_app, _SSH)

    resp = await test_app.get("/api/v1/git/credentials")

    assert resp.status_code == 200
    assert [c["id"] for c in resp.json()] == [first["id"], second["id"]]
    assert all(GitCredentialResponse.model_validate(c) for c in resp.json())
    assert _CANARY not in resp.text


async def test__get_credentials__fresh_install__is_empty(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/git/credentials")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.parametrize(
    "body",
    [
        {**_PAT, "host": "bad host"},
        {**_PAT, "host": "-oProxyCommand=x"},
        {**_PAT, "label": "  "},
        {**_PAT, "token": "   "},
        {**_PAT, "token": "has space inside"},
        {**_PAT, "username": "a:b"},
        {**_SSH, "port": 70000},
    ],
)
async def test__post_credentials__invalid_input__is_422_credential_invalid(
    test_app: AsyncClient, body: dict[str, Any]
) -> None:
    resp = await test_app.post("/api/v1/git/credentials", json=body)

    assert resp.status_code == 422, resp.text
    error = GitErrorBody.model_validate(resp.json())
    assert error.code == "credential_invalid"
    assert error.detail
    assert (await test_app.get("/api/v1/git/credentials")).json() == []


async def test__post_credentials__invalid_input_in_english__detail_is_english(test_app: AsyncClient) -> None:
    resp = await test_app.post(
        "/api/v1/git/credentials", json={**_PAT, "host": "bad host"}, headers={"X-Interface-Language": "en"}
    )

    assert resp.json()["detail"] == "The server name is not valid"


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "pat", "host": "github.com", "token": _CANARY},
        {**_PAT, "unexpected": _CANARY},
        {"kind": "pat", "label": "x", "host": "github.com", "token": _CANARY, "port": _CANARY},
        {"kind": "oauth", "label": "x", "host": "github.com", "token": _CANARY},
    ],
)
async def test__post_credentials__schema_error__422_does_not_echo_the_token(
    test_app: AsyncClient, body: dict[str, Any]
) -> None:
    resp = await test_app.post("/api/v1/git/credentials", json=body)

    assert resp.status_code == 422
    assert _CANARY not in resp.text


async def test__patch_credentials__label_only__keeps_the_secret(test_app: AsyncClient, tmp_path: Path) -> None:
    created = await _create(test_app)

    resp = await test_app.patch(f"/api/v1/git/credentials/{created['id']}", json={"label": "Переименован"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["label"] == "Переименован"
    assert _CANARY not in resp.text
    repo = JsonGitCredentialRepository(_data_dir(tmp_path), FernetSecretCipher(KeyFileStore(_key_file(tmp_path))))
    assert repo.get_secret(UUID(created["id"])).reveal() == _CANARY


@pytest.mark.parametrize("blank", ["", "   ", None])
async def test__patch_credentials__blank_token__keeps_the_stored_secret(
    test_app: AsyncClient, tmp_path: Path, blank: str | None
) -> None:
    created = await _create(test_app)

    resp = await test_app.patch(f"/api/v1/git/credentials/{created['id']}", json={"token": blank, "username": "oauth2"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["username"] == "oauth2"
    assert resp.json()["token_family"] == "ghp"
    repo = JsonGitCredentialRepository(_data_dir(tmp_path), FernetSecretCipher(KeyFileStore(_key_file(tmp_path))))
    assert repo.get_secret(UUID(created["id"])).reveal() == _CANARY


async def test__patch_credentials__new_token__replaces_secret_resets_status_and_updates_family(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    created = await _create(test_app)
    new_token = "glpat-NEWCANARYtoken1234567890"

    resp = await test_app.patch(f"/api/v1/git/credentials/{created['id']}", json={"token": f" {new_token}\n"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["token_family"] == "glpat"
    assert resp.json()["status"] == "unverified"
    assert new_token not in resp.text
    assert new_token.encode() not in _all_bytes(_data_dir(tmp_path))
    assert _CANARY.encode() not in _all_bytes(_data_dir(tmp_path))
    repo = JsonGitCredentialRepository(_data_dir(tmp_path), FernetSecretCipher(KeyFileStore(_key_file(tmp_path))))
    assert repo.get_secret(UUID(created["id"])).reveal() == new_token


async def test__patch_credentials__empty_username__clears_it(test_app: AsyncClient) -> None:
    created = await _create(test_app, {**_PAT, "username": "oauth2"})
    assert created["username"] == "oauth2"

    resp = await test_app.patch(f"/api/v1/git/credentials/{created['id']}", json={"username": ""})

    assert resp.json()["username"] is None


async def test__patch_credentials__token_for_ssh_key__is_422(test_app: AsyncClient) -> None:
    created = await _create(test_app, _SSH)

    resp = await test_app.patch(f"/api/v1/git/credentials/{created['id']}", json={"token": _CANARY})

    assert resp.status_code == 422
    assert GitErrorBody.model_validate(resp.json()).code == "credential_invalid"
    assert _CANARY not in resp.text


async def test__patch_credentials__invalid_token__is_422_without_echo(test_app: AsyncClient) -> None:
    created = await _create(test_app)

    resp = await test_app.patch(f"/api/v1/git/credentials/{created['id']}", json={"token": "bad token\x01"})

    assert resp.status_code == 422
    assert "bad token" not in resp.text


async def test__patch_credentials__unknown__is_404(test_app: AsyncClient) -> None:
    resp = await test_app.patch("/api/v1/git/credentials/00000000-0000-0000-0000-000000000000", json={"label": "x"})

    assert resp.status_code == 404


async def test__delete_credentials__unknown__is_404(test_app: AsyncClient) -> None:
    resp = await test_app.delete("/api/v1/git/credentials/00000000-0000-0000-0000-000000000000")

    assert resp.status_code == 404


async def test__delete_credentials__unused__is_204_and_removes_it(test_app: AsyncClient, tmp_path: Path) -> None:
    created = await _create(test_app)

    resp = await test_app.delete(f"/api/v1/git/credentials/{created['id']}")

    assert resp.status_code == 204
    assert (await test_app.get("/api/v1/git/credentials")).json() == []
    assert _CANARY.encode() not in _all_bytes(_data_dir(tmp_path))


def _bind(project: dict[str, Any], credential_id: str) -> None:
    git_dir = Path(project["folder"]) / ".hse-studio" / "git"
    subprocess.run(  # noqa: S603 — тестовая подготовка: записываем привязку так же, как это делает подключение
        ["git", "--git-dir", str(git_dir), "config", "hse.credential", credential_id],  # noqa: S607
        check=True,
        capture_output=True,
    )


async def test__credentials__bound_to_a_project__list_shows_used_by(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await create_project(test_app, tmp_path / "proj")
    created = await _create(test_app)
    _bind(project, created["id"])

    listed = (await test_app.get("/api/v1/git/credentials")).json()

    assert listed[0]["used_by"] == [{"project_id": project["id"], "name": project["name"]}]
    assert GitCredentialResponse.model_validate(listed[0]).used_by[0].name == project["name"]


async def test__delete_credentials__in_use__is_409_with_projects_and_keeps_it(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await create_project(test_app, tmp_path / "proj")
    created = await _create(test_app)
    _bind(project, created["id"])

    resp = await test_app.delete(f"/api/v1/git/credentials/{created['id']}")

    assert resp.status_code == 409, resp.text
    error = GitErrorBody.model_validate(resp.json())
    assert error.code == "credential_in_use"
    assert error.projects is not None
    assert [(str(p.project_id), p.name) for p in error.projects] == [(project["id"], project["name"])]
    assert len((await test_app.get("/api/v1/git/credentials")).json()) == 1


async def test__delete_credentials__in_use_with_force__is_204(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await create_project(test_app, tmp_path / "proj")
    created = await _create(test_app)
    _bind(project, created["id"])

    resp = await test_app.delete(f"/api/v1/git/credentials/{created['id']}?force=true")

    assert resp.status_code == 204
    assert (await test_app.get("/api/v1/git/credentials")).json() == []


async def test__secrets_status__fresh_install__is_ok_with_file_source(test_app: AsyncClient, tmp_path: Path) -> None:
    resp = await test_app.get("/api/v1/git/secrets/status")

    assert resp.status_code == 200, resp.text
    body = SecretsStatusResponse.model_validate(resp.json())
    assert (body.ok, body.source, body.credentials_total, body.credentials_unreadable) == (True, "file", 0, 0)
    assert body.data_dir_shared_folder is None
    assert not _key_file(tmp_path).exists()


async def test__secrets_status__data_dir_in_synced_folder__is_reported(tmp_path: Path) -> None:
    (tmp_path / "Sync" / ".stfolder").mkdir(parents=True)
    data_dir = tmp_path / "Sync" / "data"
    data_dir.mkdir()
    container = create_test_container(data_dir)
    try:
        async with AsyncClient(transport=ASGITransport(app=create_test_app(container)), base_url="http://test") as api:
            resp = await api.get("/api/v1/git/secrets/status")
    finally:
        await container.close()

    body = SecretsStatusResponse.model_validate(resp.json())
    assert body.data_dir_shared_folder is not None
    assert (body.data_dir_shared_folder.provider, body.data_dir_shared_folder.root) == (
        "syncthing",
        str(tmp_path / "Sync"),
    )


async def test__secrets_status__counts_credentials(test_app: AsyncClient) -> None:
    await _create(test_app)
    await _create(test_app, _SSH)

    body = (await test_app.get("/api/v1/git/secrets/status")).json()

    assert (body["ok"], body["credentials_total"], body["credentials_unreadable"]) == (True, 2, 0)


async def test__secrets_status__key_file_lost__is_degraded_and_credentials_are_unreadable(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    created = await _create(test_app)
    _key_file(tmp_path).unlink()

    status = (await test_app.get("/api/v1/git/secrets/status")).json()
    listed = (await test_app.get("/api/v1/git/credentials")).json()

    assert (status["ok"], status["credentials_total"], status["credentials_unreadable"]) == (False, 1, 1)
    assert [(c["id"], c["status"]) for c in listed] == [(created["id"], "unreadable")]
    assert not _key_file(tmp_path).exists()


async def test__patch_credentials__unreadable_with_new_token__becomes_readable(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    created = await _create(test_app)
    _key_file(tmp_path).unlink()

    resp = await test_app.patch(f"/api/v1/git/credentials/{created['id']}", json={"token": "glpat-AGAINtoken123456"})

    assert resp.json()["status"] == "unverified"
    assert (await test_app.get("/api/v1/git/secrets/status")).json()["ok"] is True


async def test__post_credentials__env_key__is_used_and_no_key_file_is_written(
    monkeypatch: pytest.MonkeyPatch, test_app: AsyncClient, tmp_path: Path
) -> None:
    monkeypatch.setattr(app_settings.secrets, "key", SecretStr(Fernet.generate_key().decode()))

    await _create(test_app)
    status = (await test_app.get("/api/v1/git/secrets/status")).json()

    assert status["source"] == "env"
    assert status["ok"] is True
    assert not _key_file(tmp_path).exists()
    assert _CANARY.encode() not in _all_bytes(_data_dir(tmp_path))


async def test__post_credentials__invalid_env_key__is_409_secrets_unavailable_and_status_is_degraded(
    monkeypatch: pytest.MonkeyPatch, test_app: AsyncClient, tmp_path: Path
) -> None:
    monkeypatch.setattr(app_settings.secrets, "key", SecretStr("not-a-fernet-key"))

    resp = await test_app.post("/api/v1/git/credentials", json=_PAT)
    status = (await test_app.get("/api/v1/git/secrets/status")).json()

    assert resp.status_code == 409, resp.text
    assert GitErrorBody.model_validate(resp.json()).code == "secrets_unavailable"
    assert _CANARY not in resp.text
    assert (status["ok"], status["source"]) == (False, "env")
    assert not _key_file(tmp_path).exists()


async def test__every_credential_response__never_contains_the_token(test_app: AsyncClient) -> None:
    created = await _create(test_app)
    texts = [
        (await test_app.get("/api/v1/git/credentials")).text,
        (await test_app.patch(f"/api/v1/git/credentials/{created['id']}", json={"label": "x"})).text,
        (await test_app.get("/api/v1/git/secrets/status")).text,
        (await test_app.post("/api/v1/git/credentials", json={**_PAT, "host": "bad host"})).text,
        (await test_app.delete(f"/api/v1/git/credentials/{created['id']}")).text,
    ]

    assert all(_CANARY not in text for text in texts)


async def test__export__bundle_does_not_carry_git_access(test_app: AsyncClient, tmp_path: Path) -> None:
    await _create(test_app)
    await _create(test_app, _SSH)

    resp = await test_app.post("/api/v1/data/export", json={})

    assert resp.status_code == 200, resp.text
    assert _CANARY not in resp.text
    assert "credential" not in resp.text.lower()
    assert "github.com" not in resp.text
    assert "hs1:" not in resp.text
    encryption_key = json.loads(_key_file(tmp_path).read_text(encoding="utf-8"))["keys"][0]["fernet_key"]
    assert encryption_key not in resp.text
