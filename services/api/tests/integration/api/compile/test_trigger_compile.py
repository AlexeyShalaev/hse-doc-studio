from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager, DockerStatus, ImageInfo
from httpx import AsyncClient
from pytest_mock import MockerFixture

from tests.factories import project_api_payload


async def test__api__post_compile__returns_compile_id(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture
) -> None:
    project_folder = tmp_path / "my-vkr-compile"
    project_folder.mkdir()
    create_resp = await test_app.post("/api/v1/projects", json=project_api_payload(str(project_folder)))
    assert create_resp.status_code == 201, create_resp.text
    project_id = create_resp.json()["id"]

    docs_resp = await test_app.get(f"/api/v1/projects/{project_id}/documents")
    assert docs_resp.status_code == 200, docs_resp.text
    docs = docs_resp.json()
    assert len(docs) >= 1, "Template should define at least one document"
    doc_id = docs[0]["id"]

    # Докер-префлайт (демон отвечает, образ установлен) фейкуем на шве
    # DockerImageManager: тест проверяет контракт API (202 + compile_id),
    # а не наличие Docker и многогигабайтного образа на машине с тестами.
    mocker.patch.object(
        DockerImageManager,
        "docker_status",
        return_value=DockerStatus(available=True, version="fake", detail=None),
    )
    mocker.patch.object(
        DockerImageManager,
        "inspect",
        return_value=ImageInfo(image="texlive/texlive:latest", id="sha256:fake", size_bytes=1, created="2026-01-01"),
    )

    # И сам исполнитель: иначе фоновая задача запустит настоящий `docker run`,
    # а на машине без образа это молчаливый многогигабайтный pull.
    async def _fake_logs() -> AsyncIterator[str]:
        yield "compile stubbed: no docker in tests"

    mocker.patch.object(DockerCompileExecutor, "run", return_value=_fake_logs())
    compile_resp = await test_app.post(f"/api/v1/projects/{project_id}/documents/{doc_id}/compile")

    assert compile_resp.status_code == 202, compile_resp.text
    body = compile_resp.json()
    assert "compile_id" in body
    assert isinstance(body["compile_id"], str)
    assert len(body["compile_id"]) == 36  # UUID string length
