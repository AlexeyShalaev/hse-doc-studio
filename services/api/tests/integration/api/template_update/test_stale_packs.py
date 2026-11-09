"""Каталог шаблонов подключён извне и отстаёт от Студии: проект говорит правду, а не «обновите Студию»."""

from __future__ import annotations

import json
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from hse_doc_studio.infra.template.packs_source import FilesystemPacksSource, write_manifest
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_app, create_test_container
from tests.fixtures.template_pack import PACK_ID, TEMPLATE_ID, V1, V2, build_update_pack
from tests.integration.api.template_update.conftest import create_project

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available")


@pytest_asyncio.fixture
async def stale_app(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """Студия, в образ которой вшиты обе версии, а подключённый каталог знает только первую."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    builtin = tmp_path / "builtin"
    build_update_pack(builtin)
    manifest = tmp_path / "packs-manifest.json"
    write_manifest(builtin, manifest)

    packs_dir = tmp_path / "mounted-packs"
    shutil.rmtree(build_update_pack(packs_dir) / "versions" / V2)
    repo = YamlTemplateRepository(packs_dir)
    repo.load()
    source = FilesystemPacksSource(packs_dir, repo, manifest, tmp_path / "no-mountinfo")

    container = create_test_container(data_dir, packs_dir=packs_dir, packs_source=source)
    app = create_test_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await container.close()


def _lock_project_on(project: dict[str, Any], version: str, min_studio: str) -> None:
    project_json = Path(project["folder"]) / ".hse-studio" / "project.json"
    data = json.loads(project_json.read_text(encoding="utf-8"))
    data["lock"]["version"] = version
    data["lock"]["min_studio"] = min_studio
    project_json.write_text(json.dumps(data), encoding="utf-8", newline="\n")


async def test__version_built_in_but_missing_from_mounted_dir__names_the_dir(
    stale_app: AsyncClient, tmp_path: Path
) -> None:
    project = await create_project(stale_app, tmp_path / "proj", version=V1)
    _lock_project_on(project, V2, min_studio="0.0.1")
    base = f"/api/v1/projects/{project['id']}"

    access = (await stale_app.get(base)).json()["access"]

    assert access["mode"] == "read_only"
    assert access["reasons"] == ["template_missing"]
    # Студия свежая: минимальную версию Студии не советуем.
    assert access["required_studio"] is None
    assert access["stale_packs"]["path"] == str(tmp_path / "mounted-packs")
    assert access["stale_packs"]["studio_version"]

    resp = await stale_app.patch(base, json={"name": "Переименован"})
    assert resp.status_code == 423, resp.text
    detail = resp.json()["detail"]
    assert detail["detail"].startswith(f"Версии шаблона {V2} нет в каталоге шаблонов {tmp_path / 'mounted-packs'}")
    assert "Обновите каталог или уберите подключение" in detail["detail"]


async def test__version_missing_everywhere__still_asks_for_a_newer_studio(
    stale_app: AsyncClient, tmp_path: Path
) -> None:
    project = await create_project(stale_app, tmp_path / "proj", version=V1)
    _lock_project_on(project, "2027.0.0", min_studio="1.4.0")
    base = f"/api/v1/projects/{project['id']}"

    access = (await stale_app.get(base)).json()["access"]

    assert access["stale_packs"] is None
    assert access["required_studio"] == "1.4.0"
    resp = await stale_app.patch(base, json={"name": "Переименован"})
    assert resp.status_code == 423, resp.text
    assert "более новой версией Студии (нужна 1.4.0)" in resp.json()["detail"]["detail"]


async def test__system_packs__shows_the_mounted_dir_and_what_it_lacks(stale_app: AsyncClient, tmp_path: Path) -> None:
    body = (await stale_app.get("/api/v1/system/packs")).json()

    assert body["kind"] == "external"
    assert body["path"] == str(tmp_path / "mounted-packs")
    assert body["lagging"] is True
    assert body["templates"] == [
        {"pack_id": PACK_ID, "template_id": TEMPLATE_ID, "versions": [V1], "builtin": [V1, V2], "missing": [V2]}
    ]
