"""`hse-doc-studio build`: настоящий конвейер сборки без HTTP-приложения, docker подменён скриптом-пустышкой."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio import cli
from hse_doc_studio.api.config import settings as app_settings
from httpx import AsyncClient

from tests.fixtures.fake_docker import FakeDocker


async def _main(*argv: str) -> int:
    # asyncio.run внутри main не живёт в потоке с работающим циклом теста.
    return await asyncio.to_thread(cli.main, list(argv))


async def _doc_ids(client: AsyncClient, project: dict[str, Any]) -> list[str]:
    resp = await client.get(f"/api/v1/projects/{project['id']}/documents")
    assert resp.status_code == 200, resp.text
    return [doc["id"] for doc in resp.json()]


async def test__build__all_documents__compiles_each_and_copies_pdfs_to_out(
    test_app: AsyncClient, project: dict[str, Any], fake_docker: FakeDocker, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = Path(project["folder"])
    docs = await _doc_ids(test_app, project)

    code = await _main("build", str(folder), "--all")

    assert code == 0, capsys.readouterr()
    out = folder / "build"
    for doc in docs:
        assert list(out.glob(f"{doc}.*")), doc
    assert (out / "annotation.pdf").read_bytes().startswith(b"%PDF")
    assert len(fake_docker.build_calls()) >= 1
    report = capsys.readouterr().out
    assert all(doc in report for doc in docs)


async def test__build__listed_documents__builds_only_them_into_custom_out(
    test_app: AsyncClient, project: dict[str, Any], fake_docker: FakeDocker, tmp_path: Path
) -> None:
    folder = Path(project["folder"])
    first = (await _doc_ids(test_app, project))[0]
    out = tmp_path / "artifacts"

    code = await _main("build", str(folder), "--docs", first, "--out", str(out))

    assert code == 0
    assert sorted(p.name for p in out.iterdir()) == [f"{first}.pdf"]
    assert len(fake_docker.build_calls()) == 1


async def test__build__relative_out__is_resolved_from_the_project_folder(
    test_app: AsyncClient, project: dict[str, Any], fake_docker: FakeDocker
) -> None:
    folder = Path(project["folder"])
    first = (await _doc_ids(test_app, project))[0]

    code = await _main("build", str(folder), "--docs", first, "--out", "dist/docs")

    assert code == 0
    assert (folder / "dist" / "docs" / f"{first}.pdf").is_file()


async def test__build__unknown_document__exits_2_without_building(
    test_app: AsyncClient, project: dict[str, Any], fake_docker: FakeDocker, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await _main("build", project["folder"], "--docs", "ghost")

    assert code == 2
    assert "ghost" in capsys.readouterr().err
    assert fake_docker.build_calls() == []


async def test__build__folder_is_not_a_project__exits_2(
    test_app: AsyncClient, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    code = await _main("build", str(empty))

    assert code == 2
    assert "project.json" in capsys.readouterr().err


async def test__build__latex_fails__exits_1_and_prints_the_log(
    test_app: AsyncClient,
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tests.fixtures.fake_docker import install_fake_docker  # noqa: PLC0415

    install_fake_docker(monkeypatch, tmp_path / "failing", exit_code=1)
    first = (await _doc_ids(test_app, project))[0]

    code = await _main("build", project["folder"], "--docs", first)

    assert code == 1
    assert not (Path(project["folder"]) / "build" / f"{first}.pdf").exists()
    assert "latexmk exited with code 1" in capsys.readouterr().err


async def test__build__image_missing__pulls_it_and_retries(
    test_app: AsyncClient,
    project: dict[str, Any],
    fake_docker: FakeDocker,
    mocker: Any,
) -> None:
    from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager, ImageInfo  # noqa: PLC0415

    present = ImageInfo(image="i", id="sha256:fake", size_bytes=1, created="2026-01-01")
    mocker.patch.object(DockerImageManager, "inspect", side_effect=[None, present, present, present])

    pulled: list[str] = []

    async def _pull(_self: Any, image: str) -> Any:
        pulled.append(image)

        async def _lines() -> Any:
            yield f"[pull] {image}"
            yield "__DONE__"

        return _lines()

    mocker.patch.object(DockerImageManager, "pull", _pull)
    first = (await _doc_ids(test_app, project))[0]

    code = await _main("build", project["folder"], "--docs", first)

    assert code == 0
    assert pulled == [app_settings.compile.image]
    assert (Path(project["folder"]) / "build" / f"{first}.pdf").is_file()


def test__build__without_arguments_for_a_command__argparse_exits_2() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main([])

    assert exc.value.code == 2


def test__build__all_and_docs_together__argparse_exits_2() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["build", ".", "--all", "--docs", "a"])

    assert exc.value.code == 2
