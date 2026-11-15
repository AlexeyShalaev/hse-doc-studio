"""Стенд Студии шаблонов в локальном режиме: настоящий роутер и DI, свой data_dir и маленький пак на диске."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any

import pytest_asyncio
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.infra.template.releases import freeze
from httpx import ASGITransport, AsyncClient, Response

from tests.fixtures.app import create_test_app, create_test_container

API = "/api/v1/pack-studio"
TEMPLATE_DIR = "demo/templates/report"
RELEASED = "2026.1.0"
DRAFT = "2026.1.1"
RELEASED_DIR = f"{TEMPLATE_DIR}/versions/{RELEASED}"
DRAFT_DIR = f"{TEMPLATE_DIR}/versions/{DRAFT}"
REGISTRY = f"{TEMPLATE_DIR}/releases.yaml"

_VERSION_YAML = """\
# Демо-версия для тестов Студии шаблонов.
id: "{version}"
status: {status}
summary:     {{ ru: "Первая", en: "First" }}   # выровнено как в паках
langs: [ru]
"""

PACK_FILES: Mapping[str, str] = {
    "demo/pack.yaml": 'id: demo\nname: { ru: "Демо", en: "Demo" }\n',
    f"{TEMPLATE_DIR}/template.yaml": (
        f'id: report\nname: {{ ru: "Отчёт", en: "Report" }}\ndefault_version: "{RELEASED}"\n'
    ),
    f"{RELEASED_DIR}/version.yaml": _VERSION_YAML.format(version=RELEASED, status="stable"),
    f"{RELEASED_DIR}/files/report/main.tex": "\\documentclass{article}\n",
    f"{DRAFT_DIR}/version.yaml": _VERSION_YAML.format(version=DRAFT, status="beta"),
    f"{DRAFT_DIR}/files/report/main.tex": "\\documentclass{article}\n% draft\n",
    "README.md": "Паки для тестов\n",
}


def write_pack(root: Path, files: Mapping[str, str] = PACK_FILES, *, release: bool = True) -> Path:
    """Пак на диске; `release`: 2026.1.0 внесена в реестр выпусков настоящим `freeze`."""
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    if release:
        freeze(root / TEMPLATE_DIR, RELEASED)
    return root


class Stand:
    def __init__(self, client: AsyncClient, root: Path) -> None:
        self.client = client
        self.root = root

    async def enable(self) -> None:
        resp = await self.client.put(f"{API}/section", json={"enabled": True})
        assert resp.status_code == 200, resp.text

    async def folder_workspace(self, folder: Path, **extra: Any) -> dict[str, Any]:
        resp = await self.client.post(f"{API}/workspaces", json={"kind": "folder", "folder": str(folder), **extra})
        assert resp.status_code == 201, resp.text
        return dict(resp.json())

    async def settled(self, workspace_id: str, *, timeout_s: float = 60.0) -> dict[str, Any]:
        """Карточка пространства после конца фоновой операции."""
        deadline = asyncio.get_running_loop().time() + timeout_s
        while True:
            resp = await self.client.get(f"{API}/workspaces/{workspace_id}")
            assert resp.status_code == 200, resp.text
            body = dict(resp.json())
            if not body["busy"]:
                return body
            assert asyncio.get_running_loop().time() < deadline, body
            await asyncio.sleep(0.05)

    def file_url(self, workspace_id: str, path: str) -> str:
        return f"{API}/workspaces/{workspace_id}/files/{path}"

    async def read(self, workspace_id: str, path: str) -> Response:
        return await self.client.get(self.file_url(workspace_id, path))


@pytest_asyncio.fixture
async def stand(tmp_path: Path) -> AsyncIterator[Stand]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    saved = app_settings.pack_studio.model_copy()
    container = create_test_container(data_dir)
    client = AsyncClient(transport=ASGITransport(app=create_test_app(container)), base_url="http://test")
    try:
        yield Stand(client, tmp_path)
    finally:
        await client.aclose()
        await container.close()
        app_settings.pack_studio = saved
