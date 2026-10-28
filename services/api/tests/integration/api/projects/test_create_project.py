from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient

from tests.factories import project_api_payload


async def test__api__post_projects__creates_hse_studio_dir(test_app: AsyncClient, tmp_path: Path) -> None:
    project_folder = tmp_path / "my-vkr"
    project_folder.mkdir()
    payload = project_api_payload(str(project_folder))

    response = await test_app.post("/api/v1/projects", json=payload)

    assert response.status_code == 201, response.text
    studio_project_json = project_folder / ".hse-studio" / "project.json"
    assert studio_project_json.exists(), ".hse-studio/project.json should be created by CreateProjectUC"


async def test__api__post_projects__language_the_template_does_not_declare__rejected(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    # Project Proposal по регламенту ОП пишется только на английском (langs: [en]).
    payload = {**project_api_payload(str(tmp_path / "my-pp")), "template_id": "pp", "lang": "ru"}

    response = await test_app.post("/api/v1/projects", json=payload)

    assert response.status_code == 400, response.text


async def test__api__post_projects__rejected_create__leaves_no_folder_behind(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    # Отказ не должен оставлять пустой каталог: он потом мешает повторной попытке.
    project_folder = tmp_path / "my-pp"
    payload = {**project_api_payload(str(project_folder)), "template_id": "pp", "lang": "ru"}

    await test_app.post("/api/v1/projects", json=payload)

    assert not project_folder.exists()


async def test__api__post_projects__msc_sse_coursework__renders_proposal_and_application(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    # Пак магистратуры СПИ: заявка на проект и заявление о теме получают данные
    # проекта (русская и английская тема, руководитель) через common/meta.tex.
    project_folder = tmp_path / "my-kp"
    payload = {
        **project_api_payload(str(project_folder)),
        "name": "Контур согласования действий LLM-агента",
        "pack_id": "hse-cs-sse",
        "template_id": "coursework",
        "kind": "project",
        "supervisor": {"name": "И. И. Иванов", "role": "university", "title": "доцент", "degree": "к.т.н."},
        "meta": {"name_en": "An Approval Gate for LLM Agents", "proposal_stage": "Доработанная"},
    }

    response = await test_app.post("/api/v1/projects", json=payload)

    assert response.status_code == 201, response.text
    for source in (
        "project_proposal/project_proposal.tex",
        "topic_application/topic_application.tex",
        "report/report.tex",
        "presentation/beamer/presentation.tex",
    ):
        assert (project_folder / source).is_file(), source
    meta = (project_folder / "common" / "meta.tex").read_text(encoding="utf-8")
    assert "An Approval Gate for LLM Agents" in meta
    assert "И. И. Иванов" in meta
    assert "\\hseSupervisorName, к.т.н., доцент" in meta
    assert "\\hseExtendedProposaltrue" in meta


async def test__api__post_projects__local_without_folder__unprocessable(test_app: AsyncClient, tmp_path: Path) -> None:
    payload = project_api_payload(str(tmp_path / "no-folder"))
    del payload["folder"]

    response = await test_app.post("/api/v1/projects", json=payload)

    assert response.status_code == 422, response.text
    assert not (tmp_path / "no-folder").exists()
