"""Выключенная синхронизация (`HSE_STUDIO__GIT__ENABLED=false`): интерфейс видит «не поддерживается».

Доступы при этом не копятся. Раньше состояние проекта всё так же обещало подключение, токены сохранялись
(и создавался файл ключа), а каждое действие отвечало «Git не найден»: причину в настройке развёртывания
человек не видел.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.api.schemas.git_sync import GitErrorBody
from httpx import AsyncClient

from tests.integration.api.vcs.conftest import create_project


@pytest.fixture(autouse=True)
def _git_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings.git, "enabled", False)


def _code(resp: Any) -> str:
    return GitErrorBody.model_validate(resp.json()).code


async def test__status__git_disabled__is_not_found_so_the_client_hides_sync(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/git")

    assert resp.status_code == 404, resp.text
    assert _code(resp) == "git_disabled"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/v1/git/remote/probe", {"url": "https://github.com/o/r.git"}),
        ("POST", "/api/v1/git/clone", {"url": "https://github.com/o/r.git", "folder": "/tmp/x"}),
        (
            "POST",
            "/api/v1/git/credentials",
            {"kind": "pat", "label": "Токен", "host": "github.com", "token": "ghp_0123456789abcdef"},
        ),
        ("PUT", "/api/v1/git/host-settings", {"host": "git.hse.ru", "provider_override": "gitlab"}),
        ("POST", "/api/v1/git/hosts/trust", {"host": "git.hse.ru", "fingerprint_sha256": "SHA256:abc"}),
    ],
)
async def test__global_actions__git_disabled__refused_with_git_disabled(
    test_app: AsyncClient, method: str, path: str, body: dict[str, Any]
) -> None:
    resp = await test_app.request(method, path, json=body)

    assert resp.status_code == 404, resp.text
    assert _code(resp) == "git_disabled"


async def test__credentials__git_disabled__nothing_is_stored_and_no_key_file_appears(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    await test_app.post(
        "/api/v1/git/credentials",
        json={"kind": "pat", "label": "Токен", "host": "github.com", "token": "ghp_0123456789abcdef"},
    )

    assert not (app_settings.data_dir / "secrets" / "master.keys.json").exists()
    assert not (app_settings.data_dir / "git" / "credentials.json").exists()


async def test__project_actions__git_disabled__refused_with_git_disabled(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await create_project(test_app, tmp_path / "proj")
    base = f"/api/v1/projects/{project['id']}/git"

    connect = await test_app.put(f"{base}/remote", json={"url": "https://github.com/o/r.git", "credential_id": None})
    sync = await test_app.post(f"{base}/sync")

    assert _code(connect) == "git_disabled"
    assert _code(sync) == "git_disabled"
