from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager, DockerStatus, ImageInfo
from hse_doc_studio.infra.languagetool.container_manager import LanguageToolContainerManager
from hse_doc_studio.infra.office.convert_manager import OfficeConvertManager
from httpx import AsyncClient
from pytest_mock import MockerFixture

from tests.factories import project_api_payload
from tests.fixtures.fake_docker import FakeDocker, install_fake_docker


@pytest.fixture
def fake_docker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeDocker:
    return install_fake_docker(monkeypatch, tmp_path)


@pytest.fixture(autouse=True)
def docker_ready(mocker: MockerFixture) -> None:
    """Демон отвечает, образ установлен: ни Docker, ни сеть тесту не нужны."""
    mocker.patch.object(
        DockerImageManager, "docker_status", return_value=DockerStatus(available=True, version="fake", detail=None)
    )
    mocker.patch.object(
        DockerImageManager,
        "inspect",
        return_value=ImageInfo(image="texlive/texlive:latest", id="sha256:fake", size_bytes=1, created="2026-01-01"),
    )


@pytest.fixture(autouse=True)
def languagetool_start(mocker: MockerFixture) -> None:
    mocker.patch.object(LanguageToolContainerManager, "ensure_running", return_value=None)


@pytest.fixture(autouse=True)
def office_convert(mocker: MockerFixture) -> None:
    """Предпросмотр pptx без Gotenberg: конвертера нет, сборка всё равно успешна."""
    mocker.patch.object(OfficeConvertManager, "convert_to_pdf", return_value=None)


@pytest_asyncio.fixture
async def project(test_app: AsyncClient, tmp_path: Path) -> dict[str, Any]:
    folder = tmp_path / "proj"
    folder.mkdir()
    resp = await test_app.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()
