"""База обновлений на настоящих паках репозитория: запись при создании полна и точна."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.factories import project_api_payload

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available")


@pytest.mark.parametrize(("template_id", "lang"), [("vkr", "ru"), ("coursework", "ru"), ("pp", "en")])
async def test__real_template__fresh_project_matches_its_recorded_base(
    test_app: AsyncClient, tmp_path: Path, template_id: str, lang: str
) -> None:
    folder = tmp_path / template_id
    folder.mkdir()
    # Скрытый файл пользователя, лежавший в папке до создания, — не часть шаблона.
    (folder / ".vscode").mkdir()
    (folder / ".vscode" / "settings.json").write_text("{}", encoding="utf-8", newline="\n")
    payload = {**project_api_payload(str(folder)), "template_id": template_id, "lang": lang}
    project = (await test_app.post("/api/v1/projects", json=payload)).json()

    compare = await test_app.get(f"/api/v1/projects/{project['id']}/template/compare")

    assert compare.status_code == 200, compare.text
    body = compare.json()
    assert body["provenance"] == "recorded"
    assert body["files"] == []
    git_dir = folder / ".hse-studio" / "git"
    base_files = subprocess.run(
        ["git", "--git-dir", str(git_dir), "ls-tree", "-r", "--name-only", "refs/hse/template/2026.1"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.split()
    assert base_files
    assert not any(p.startswith((".vscode/", ".hse-studio/")) for p in base_files)
    assert "common/meta.tex" not in base_files
    # Рендер шаблона не дописал в базу ничего «приблизительного»: запись при создании полна.
    message = subprocess.run(
        ["git", "--git-dir", str(git_dir), "log", "-1", "--format=%B", "refs/hse/template/2026.1"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    assert "Hse-Base-Approximate" not in message


async def test__real_coursework__existing_project_is_offered_the_patch_2026_1_1(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    """Проект на 2026.1 получает исправление как patch: затронуты только заявление и Beamer-презентация."""
    folder = tmp_path / "sse"
    folder.mkdir()
    payload = {
        **project_api_payload(str(folder)),
        "pack_id": "hse-cs-sse",
        "template_id": "coursework",
        "version": "2026.1",
        "lang": "ru",
    }
    created = await test_app.post("/api/v1/projects", json=payload)
    assert created.status_code == 201, created.text
    project = created.json()
    base = f"/api/v1/projects/{project['id']}/template-update"

    status = (await test_app.get(base)).json()
    assert status["current_version"] == "2026.1"
    assert status["recommended"]["version"]["version"] == "2026.1.6"
    assert status["recommended"]["update_class"] == "patch"

    plan = (await test_app.post(f"{base}/plan", json={"to_version": "2026.1.1"})).json()
    changed = {f["path"] for f in plan["files"] if f["action"] != "unchanged"}
    assert changed == {"topic_application/topic_application.tex", "presentation/beamer/presentation.tex"}


async def test__real_coursework__2026_1_1_project_is_offered_the_patch_2026_1_2(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    """Сверка заявления с бланком СПИ 2026 — patch: из файлов проекта меняется только заявление."""
    folder = tmp_path / "sse"
    folder.mkdir()
    payload = {
        **project_api_payload(str(folder)),
        "pack_id": "hse-cs-sse",
        "template_id": "coursework",
        "version": "2026.1.1",
        "lang": "ru",
    }
    created = await test_app.post("/api/v1/projects", json=payload)
    assert created.status_code == 201, created.text
    project = created.json()
    base = f"/api/v1/projects/{project['id']}/template-update"

    status = (await test_app.get(base)).json()
    assert status["current_version"] == "2026.1.1"
    assert status["recommended"]["version"]["version"] == "2026.1.6"
    assert status["recommended"]["update_class"] == "patch"

    plan = (await test_app.post(f"{base}/plan", json={"to_version": "2026.1.2"})).json()
    changed = {f["path"] for f in plan["files"] if f["action"] != "unchanged"}
    assert changed == {"topic_application/topic_application.tex"}


async def test__real_coursework__2026_1_2_project_gets_sign_methods_in_patch_2026_1_3(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    """2026.1.3 меняет только профили сдачи: файлы проекта не трогаются, PAdES-слот потом ждёт смены способа."""
    folder = tmp_path / "sse"
    folder.mkdir()
    payload = {
        **project_api_payload(str(folder)),
        "pack_id": "hse-cs-sse",
        "template_id": "coursework",
        "version": "2026.1.2",
        "lang": "ru",
    }
    created = await test_app.post("/api/v1/projects", json=payload)
    assert created.status_code == 201, created.text
    project = created.json()
    base = f"/api/v1/projects/{project['id']}/template-update"
    config = f"/api/v1/projects/{project['id']}/signatures/slots/author/config"
    signature_plan = f"/api/v1/projects/{project['id']}/signature-plan"

    # На 2026.1.2 ограничений нет: автор подписывает встроенной ЭП.
    resp = await test_app.patch(config, json={"sign_mode": "image_crypto"})
    assert resp.status_code == 200, resp.text

    status = (await test_app.get(base)).json()
    assert status["current_version"] == "2026.1.2"
    assert status["recommended"]["version"]["version"] == "2026.1.6"
    assert status["recommended"]["update_class"] == "patch"

    plan = (await test_app.post(f"{base}/plan", json={"to_version": "2026.1.3"})).json()
    assert {f["path"] for f in plan["files"] if f["action"] != "unchanged"} == set()
    applied = await test_app.post(
        f"{base}/apply", json={"to_version": "2026.1.3", "fingerprint": plan["fingerprint"], "resolutions": {}}
    )
    assert applied.status_code == 200, applied.text

    # Настройка слота сохранилась, но точка её не принимает и объясняет почему.
    resp = await test_app.get(signature_plan, params={"profile_id": "topic-approval"})
    assert resp.status_code == 200, resp.text
    doc = next(d for d in resp.json()["docs"] if d["doc_id"] == "topic_application")
    author = next(s for s in doc["slots"] if s["slot_id"] == "author")
    assert (author["status"], author["reason"]) == ("pending", "method_not_allowed")
    assert author["allowed_methods"] == ["image", "detached"]

    # Снова выбрать PAdES нельзя: его не принимает ни одна точка с этим слотом. Открепленную ЭП можно.
    resp = await test_app.patch(config, json={"sign_mode": "image_crypto"})
    assert resp.status_code == 400, resp.text
    assert "не принимает ни одна контрольная точка" in resp.text
    resp = await test_app.patch(config, json={"sign_mode": "detached_text"})
    assert resp.status_code == 200, resp.text


async def test__real_coursework__2026_1_3_project_gets_form_fixes_in_patch_2026_1_4(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    """2026.1.4 исправляет формы: город и год из проекта, заявление на языке проекта, строки по условию."""
    folder = tmp_path / "sse"
    folder.mkdir()
    payload = {
        **project_api_payload(str(folder)),
        "pack_id": "hse-cs-sse",
        "template_id": "coursework",
        "version": "2026.1.3",
        "lang": "ru",
    }
    created = await test_app.post("/api/v1/projects", json=payload)
    assert created.status_code == 201, created.text
    project = created.json()
    base = f"/api/v1/projects/{project['id']}/template-update"

    status = (await test_app.get(base)).json()
    assert status["current_version"] == "2026.1.3"
    assert status["recommended"]["version"]["version"] == "2026.1.6"
    assert status["recommended"]["update_class"] == "patch"

    plan = (await test_app.post(f"{base}/plan", json={"to_version": "2026.1.4"})).json()
    changed = {f["path"] for f in plan["files"] if f["action"] != "unchanged"}
    assert changed == {
        "topic_application/topic_application.tex",
        "report/title.tex",
        "presentation/beamer/presentation.tex",
    }
    applied = await test_app.post(
        f"{base}/apply", json={"to_version": "2026.1.4", "fingerprint": plan["fingerprint"], "resolutions": {}}
    )
    assert applied.status_code == 200, applied.text
    application = (folder / "topic_application" / "topic_application.tex").read_text(encoding="utf-8")
    assert "\\ifhseLangEn" in application
    assert "\\clearpage" not in application


async def test__real_coursework__2026_1_4_project_gets_anchors_and_presets_in_patch_2026_1_5(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    """2026.1.5 добавляет якоря мест в шаблон и пресеты маршрутов: файлы меняются только якорями."""
    folder = tmp_path / "sse"
    folder.mkdir()
    payload = {
        **project_api_payload(str(folder)),
        "pack_id": "hse-cs-sse",
        "template_id": "coursework",
        "version": "2026.1.4",
        "lang": "ru",
    }
    created = await test_app.post("/api/v1/projects", json=payload)
    assert created.status_code == 201, created.text
    project = created.json()
    base = f"/api/v1/projects/{project['id']}/template-update"

    status = (await test_app.get(base)).json()
    assert status["current_version"] == "2026.1.4"
    assert status["recommended"]["version"]["version"] == "2026.1.6"
    assert status["recommended"]["update_class"] == "patch"

    plan = (await test_app.post(f"{base}/plan", json={"to_version": "2026.1.5"})).json()
    changed = {f["path"] for f in plan["files"] if f["action"] != "unchanged"}
    assert changed == {
        "common/anchors.tex",
        "topic_application/topic_application.tex",
        "project_proposal/preamble.tex",
        "project_proposal/project_proposal.tex",
        "report/preamble.tex",
        "report/title.tex",
    }
    applied = await test_app.post(
        f"{base}/apply", json={"to_version": "2026.1.5", "fingerprint": plan["fingerprint"], "resolutions": {}}
    )
    assert applied.status_code == 200, applied.text
    application = (folder / "topic_application" / "topic_application.tex").read_text(encoding="utf-8")
    assert "\\hseSignField[supervisor]" in application
    assert (folder / "common" / "anchors.tex").is_file()


@pytest.mark.parametrize(
    ("pack_id", "template_id", "current", "patched", "lang"),
    [
        ("hse-cs-sse", "coursework", "2026.1.5", "2026.1.6", "ru"),
        ("hse-cs-se", "coursework", "2026.1.1", "2026.1.2", "ru"),
        ("hse-cs-se", "vkr", "2026.1.1", "2026.1.2", "ru"),
        ("hse-cs-se", "pp", "2026.1", "2026.1.1", "en"),
    ],
)
async def test__real_template__quoted_texts_patch_changes_no_project_files(
    test_app: AsyncClient, tmp_path: Path, pack_id: str, template_id: str, current: str, patched: str, lang: str
) -> None:
    """Кавычки у текстов `{ ru, en }` (запятая резала подписи полей и названия проверок): patch без правок файлов."""
    folder = tmp_path / template_id
    folder.mkdir()
    payload = {
        **project_api_payload(str(folder)),
        "pack_id": pack_id,
        "template_id": template_id,
        "version": current,
        "lang": lang,
    }
    created = await test_app.post("/api/v1/projects", json=payload)
    assert created.status_code == 201, created.text
    base = f"/api/v1/projects/{created.json()['id']}/template-update"

    status = (await test_app.get(base)).json()
    assert status["recommended"]["version"]["version"] == patched
    assert status["recommended"]["update_class"] == "patch"

    plan = (await test_app.post(f"{base}/plan", json={"to_version": patched})).json()
    assert {f["path"] for f in plan["files"] if f["action"] != "unchanged"} == set()
    applied = await test_app.post(
        f"{base}/apply", json={"to_version": patched, "fingerprint": plan["fingerprint"], "resolutions": {}}
    )
    assert applied.status_code == 200, applied.text
