"""Обновление проекта на новую версию шаблона — сквозь HTTP, с настоящим git."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from tests.fixtures.template_pack import (
    APPENDIX_TEX,
    LOGO_V2,
    PREAMBLE_V2,
    V1,
    V2,
)
from tests.integration.api.template_update.conftest import create_project

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available")

USER_INTRO = "Текст введения, написанный студентом."


def _base(project: dict[str, Any]) -> str:
    return f"/api/v1/projects/{project['id']}"


def _folder(project: dict[str, Any]) -> Path:
    return Path(project["folder"])


def _edit_intro(project: dict[str, Any]) -> None:
    report = _folder(project) / "report" / "report.tex"
    report.write_text(
        report.read_text(encoding="utf-8").replace("Текст введения из шаблона.", USER_INTRO), encoding="utf-8"
    )


async def _plan(client: AsyncClient, project: dict[str, Any], to: str = V2) -> dict[str, Any]:
    resp = await client.post(f"{_base(project)}/template-update/plan", json={"to_version": to})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _apply(
    client: AsyncClient, project: dict[str, Any], plan: dict[str, Any], resolutions: dict[str, str] | None = None
) -> dict[str, Any]:
    resp = await client.post(
        f"{_base(project)}/template-update/apply",
        json={"to_version": plan["to_version"], "fingerprint": plan["fingerprint"], "resolutions": resolutions or {}},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _actions(plan: dict[str, Any]) -> dict[str, str]:
    return {f["path"]: f["action"] for f in plan["files"]}


def _git(project: dict[str, Any], *args: str) -> str:
    folder = _folder(project)
    out = subprocess.run(
        ["git", "--git-dir", str(folder / ".hse-studio" / "git"), "--work-tree", str(folder), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout


def _tree(folder: Path) -> dict[str, bytes]:
    """Файлы проекта без служебных и сгенерированных сборкой."""
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in folder.rglob("*")
        if p.is_file() and ".hse-studio" not in p.parts and p.relative_to(folder).as_posix() != "common/meta.tex"
    }


async def test__status__offers_the_patch_with_its_notes(update_app: AsyncClient, project: dict[str, Any]) -> None:
    resp = await update_app.get(f"{_base(project)}/template-update")

    assert resp.status_code == 200, resp.text
    status = resp.json()
    assert status["current_version"] == V1
    assert status["current"]["released"] is True
    assert [u["version"]["version"] for u in status["available"]] == [V2]
    assert status["recommended"]["update_class"] == "patch"
    assert status["recommended"]["version"]["changes"]["ru"] == ["Чёрный акцент и раздел «Заключение»"]
    assert status["digest_mismatch"] is False
    assert status["last_update"] is None


async def test__new_project__records_the_base_and_lock_digest(update_app: AsyncClient, project: dict[str, Any]) -> None:
    refs = _git(project, "for-each-ref", "--format=%(refname)", "refs/hse/")
    assert refs.split() == [f"refs/hse/template/{V1}"]
    lock = json.loads((_folder(project) / ".hse-studio" / "project.json").read_text(encoding="utf-8"))["lock"]
    assert lock["digest"].startswith("sha256:")

    compare = (await update_app.get(f"{_base(project)}/template/compare")).json()
    assert compare["provenance"] == "recorded"
    assert compare["files"] == []


async def test__plan__classifies_every_changed_file(update_app: AsyncClient, project: dict[str, Any]) -> None:
    _edit_intro(project)

    plan = await _plan(update_app, project)

    assert plan["update_class"] == "patch"
    assert _actions(plan) == {
        "report/appendix.tex": "add",
        "report/logo.png": "update",
        "report/old.tex": "delete",
        "report/preamble.tex": "update",
        "report/report.tex": "merge",
    }
    assert plan["warnings"] == []
    # Предпросмотр ничего не пишет в проект.
    assert (_folder(project) / "report" / "old.tex").exists()
    assert not (_folder(project) / "report" / "appendix.tex").exists()


async def test__apply__updates_merges_and_keeps_user_edits(update_app: AsyncClient, project: dict[str, Any]) -> None:
    _edit_intro(project)
    plan = await _plan(update_app, project)

    result = await _apply(update_app, project, plan)

    folder = _folder(project)
    report = (folder / "report" / "report.tex").read_text(encoding="utf-8")
    assert USER_INTRO in report
    assert "\\section{Заключение}" in report
    assert (folder / "report" / "preamble.tex").read_text(encoding="utf-8") == PREAMBLE_V2
    assert (folder / "report" / "appendix.tex").read_text(encoding="utf-8") == APPENDIX_TEX
    assert (folder / "report" / "logo.png").read_bytes() == LOGO_V2
    assert not (folder / "report" / "old.tex").exists()
    assert result["markers"] == []

    detail = (await update_app.get(_base(project))).json()
    assert detail["lock"]["version"] == V2
    status = (await update_app.get(f"{_base(project)}/template-update")).json()
    assert status["available"] == []
    assert status["last_update"]["to_version"] == V2
    # В истории — коммит вида template_update, база новой версии записана.
    history = (await update_app.get(f"{_base(project)}/vcs/history")).json()
    assert history[0]["kind"] == "template_update"
    assert f"refs/hse/template/{V2}" in _git(project, "for-each-ref", "--format=%(refname)", "refs/hse/")
    assert not (folder / ".hse-studio" / "update").exists()


async def test__untouched_project__after_update_equals_a_fresh_one(
    update_app: AsyncClient, project: dict[str, Any], tmp_path: Path
) -> None:
    await _apply(update_app, project, await _plan(update_app, project))
    fresh = await create_project(update_app, tmp_path / "fresh", version=V2)

    assert _tree(_folder(project)) == _tree(_folder(fresh))


async def test__apply__refuses_an_outdated_plan(update_app: AsyncClient, project: dict[str, Any]) -> None:
    plan = await _plan(update_app, project)
    (_folder(project) / "report" / "preamble.tex").write_text("% моя преамбула\n", encoding="utf-8")

    resp = await update_app.post(
        f"{_base(project)}/template-update/apply",
        json={"to_version": V2, "fingerprint": plan["fingerprint"]},
    )

    assert resp.status_code == 409, resp.text
    assert (_folder(project) / "report" / "preamble.tex").read_text(encoding="utf-8") == "% моя преамбула\n"


async def test__conflict__default_keeps_mine_markers_on_request(
    update_app: AsyncClient, project: dict[str, Any]
) -> None:
    preamble = _folder(project) / "report" / "preamble.tex"
    mine = "\\usepackage{xcolor}\n\\definecolor{accent}{RGB}{255,0,0}\n"
    preamble.write_text(mine, encoding="utf-8")
    plan = await _plan(update_app, project)
    conflict = next(f for f in plan["files"] if f["path"] == "report/preamble.tex")
    assert conflict["action"] == "conflict"
    assert conflict["resolutions"] == ["mine", "theirs", "markers"]

    diff = await update_app.get(
        f"{_base(project)}/template-update/diff",
        params={"path": "report/preamble.tex", "view": "result", "to_version": V2, "resolution": "markers"},
    )
    assert diff.status_code == 200, diff.text
    assert "<<<<<<< ваш вариант" in diff.json()["patch"]

    result = await _apply(update_app, project, plan, {"report/preamble.tex": "markers"})

    content = preamble.read_text(encoding="utf-8")
    assert "<<<<<<< ваш вариант" in content
    assert ">>>>>>> шаблон: стало" in content
    assert result["markers"] == ["report/preamble.tex"]
    status = (await update_app.get(f"{_base(project)}/template-update")).json()
    assert status["unresolved_markers"] == ["report/preamble.tex"]


async def test__revert__restores_files_and_lock_but_keeps_later_edits(
    update_app: AsyncClient, project: dict[str, Any]
) -> None:
    folder = _folder(project)
    before = _tree(folder)
    await _apply(update_app, project, await _plan(update_app, project))
    # Правка после обновления в файле, который обновление тоже меняло.
    report = folder / "report" / "report.tex"
    report.write_text(report.read_text(encoding="utf-8").replace("Выводы.", "Мои выводы."), encoding="utf-8")

    dry = await update_app.post(f"{_base(project)}/template-update/revert", json={"dry_run": True})
    assert dry.status_code == 200, dry.text
    assert dry.json()["applied"] is False
    assert (folder / "report" / "appendix.tex").exists()

    resp = await update_app.post(f"{_base(project)}/template-update/revert", json={})
    assert resp.status_code == 200, resp.text

    assert (await update_app.get(_base(project))).json()["lock"]["version"] == V1
    after = _tree(folder)
    for path in ("report/preamble.tex", "report/logo.png", "report/old.tex"):
        assert after[path] == before[path]
    assert "report/appendix.tex" not in after
    # Отмена убрала бы раздел «Заключение», но пользователь его уже правил: конфликт,
    # по умолчанию файл остаётся как есть и попадает в список «оставлено».
    assert "Мои выводы." in report.read_text(encoding="utf-8")
    assert resp.json()["kept"] == ["report/report.tex"]
    status = (await update_app.get(f"{_base(project)}/template-update")).json()
    assert [u["version"]["version"] for u in status["available"]] == [V2]
    assert status["last_update"] is None


async def test__revert__untouched_update_round_trips_exactly(update_app: AsyncClient, project: dict[str, Any]) -> None:
    folder = _folder(project)
    before = _tree(folder)
    await _apply(update_app, project, await _plan(update_app, project))

    resp = await update_app.post(f"{_base(project)}/template-update/revert", json={})

    assert resp.status_code == 200, resp.text
    assert _tree(folder) == before
    assert resp.json()["kept"] == []


async def test__old_project_without_base__reconstructed_from_the_root_commit(
    update_app: AsyncClient, project: dict[str, Any]
) -> None:
    # Проект, созданный до механизма баз: ссылки нет, есть только история.
    _git(project, "update-ref", "-d", f"refs/hse/template/{V1}")
    _edit_intro(project)

    plan = await _plan(update_app, project)

    assert plan["provenance"] == "root"
    assert _actions(plan)["report/report.tex"] == "merge"
    assert plan["warnings"] == []


async def test__project_without_history__base_is_approximate(update_app: AsyncClient, project: dict[str, Any]) -> None:
    shutil.rmtree(_folder(project) / ".hse-studio" / "git")
    _edit_intro(project)

    plan = await _plan(update_app, project)

    assert plan["provenance"] == "approximate"
    assert {w["code"] for w in plan["warnings"]} == {"approximate_base"}
    # Даже без истории правки не теряются: нетронутое обновляется, правленое сливается.
    assert _actions(plan)["report/report.tex"] == "merge"
    await _apply(update_app, project, plan)
    assert USER_INTRO in (_folder(project) / "report" / "report.tex").read_text(encoding="utf-8")


async def test__ignored_file__is_left_alone(update_app: AsyncClient, project: dict[str, Any]) -> None:
    preamble = _folder(project) / "report" / "preamble.tex"
    preamble.write_text("% полностью своя преамбула\n", encoding="utf-8")
    resp = await update_app.put(
        f"{_base(project)}/template/tracking", json={"path": "report/preamble.tex", "tracked": False}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ignored"] == ["report/preamble.tex"]

    plan = await _plan(update_app, project)
    assert _actions(plan)["report/preamble.tex"] == "ignored"
    await _apply(update_app, project, plan)

    assert preamble.read_text(encoding="utf-8") == "% полностью своя преамбула\n"


async def test__compare_with_template__lists_my_edits_with_a_diff(
    update_app: AsyncClient, project: dict[str, Any]
) -> None:
    _edit_intro(project)
    (_folder(project) / "report" / "old.tex").unlink()

    compare = (await update_app.get(f"{_base(project)}/template/compare")).json()

    assert {f["path"]: f["status"] for f in compare["files"]} == {
        "report/old.tex": "deleted",
        "report/report.tex": "modified",
    }
    assert compare["files"][1]["doc_id"] == "report"
    diff = (await update_app.get(f"{_base(project)}/template-update/diff", params={"path": "report/report.tex"})).json()
    assert f"+{USER_INTRO}" in diff["patch"]
    assert "-Текст введения из шаблона." in diff["patch"]


async def test__project_written_by_a_newer_studio__is_read_only(
    update_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_json = _folder(project) / ".hse-studio" / "project.json"
    data = json.loads(project_json.read_text(encoding="utf-8"))
    data["schema"] = {"version": 7, "read_compat": 1, "write_compat": 7, "written_by": "9.0.0"}
    project_json.write_text(json.dumps(data), encoding="utf-8")

    detail = (await update_app.get(_base(project))).json()
    assert detail["access"] == {"mode": "read_only", "reasons": ["schema_write"], "required_studio": "9.0.0"}

    resp = await update_app.patch(_base(project), json={"name": "Переименован"})
    assert resp.status_code == 423, resp.text
    assert resp.json()["detail"]["required_studio"] == "9.0.0"
    assert (await update_app.post(f"{_base(project)}/template-update/plan", json={"to_version": V2})).status_code == 423
    assert json.loads(project_json.read_text(encoding="utf-8"))["name"] == data["name"]


async def test__project_on_a_template_version_this_studio_lacks__is_read_only(
    update_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_json = _folder(project) / ".hse-studio" / "project.json"
    data = json.loads(project_json.read_text(encoding="utf-8"))
    data["lock"]["version"] = "2027.0.0"
    data["lock"]["min_studio"] = "1.4.0"
    project_json.write_text(json.dumps(data), encoding="utf-8")

    detail = (await update_app.get(_base(project))).json()

    assert detail["access"]["mode"] == "read_only"
    assert detail["access"]["reasons"] == ["template_missing"]
    assert detail["access"]["required_studio"] == "1.4.0"


async def test__cli_plan__reports_without_writing(
    update_app: AsyncClient, project: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hse_doc_studio.infra.template_update.cli import main

    _git(project, "update-ref", "-d", f"refs/hse/template/{V1}")
    _edit_intro(project)
    before = _git(project, "for-each-ref")

    code = main(["plan", str(_folder(project)), "--to", V2, "--packs", str(tmp_path / "packs"), "--json"])

    assert code == 0
    report = json.loads(capsys.readouterr().out)[0]
    assert report["provenance"] == "root"
    assert report["files"]["report/report.tex"] == "merge"
    assert _git(project, "for-each-ref") == before

    assert main(["compare", str(_folder(project)), "--packs", str(tmp_path / "packs"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["edited"] == ["report/report.tex"]
