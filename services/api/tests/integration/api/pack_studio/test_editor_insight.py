"""Студия шаблонов, срез T8: проверки открытого файла (`/lint`) и подсказки автодополнения (`/hints`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.api.pack_studio.conftest import API, DRAFT_DIR, RELEASED_DIR, TEMPLATE_DIR, Stand, write_pack

pytestmark = pytest.mark.usefixtures("stand")

_META_J2 = """\
% Макросы полей проекта.
\\newcommand{\\hseYear}{{{ project.meta.year | texesc }}}
\\newcommand{\\hseTitle}{{{ project.name }}}
\\newcommand{\\hse@internal}{x}
"""


async def _workspace(stand: Stand) -> tuple[str, Path]:
    folder = write_pack(stand.root / "packs-folder")
    await stand.enable()
    ws = await stand.folder_workspace(folder)
    return ws["id"], folder


async def _lint(stand: Stand, workspace_id: str, path: str) -> dict:
    resp = await stand.client.post(f"{API}/workspaces/{workspace_id}/lint", json={"path": path})
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


async def test__lint__jinja_error_in_draft__points_to_file_and_line(stand: Stand) -> None:
    ws_id, folder = await _workspace(stand)
    tex = f"{DRAFT_DIR}/files/report/main.tex"
    (folder / tex).write_text("\\documentclass{article}\n((* if project.kind *))\n{{ project.name \n", encoding="utf-8")

    report = await _lint(stand, ws_id, tex)

    assert report["scope"] == "version"
    assert report["target"] == DRAFT_DIR
    assert report["released"] is False
    assert report["errors"] >= 1
    jinja = next(f for f in report["findings"] if "TemplateSyntaxError" in f["message"])
    assert jinja == {**jinja, "severity": "error", "check": "lint", "path": tex, "line": 3, "pointer": None}


async def test__lint__schema_error__has_line_and_pointer_and_is_error_in_draft(stand: Stand) -> None:
    ws_id, folder = await _workspace(stand)
    manifest = folder / DRAFT_DIR / "version.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace("status: beta", "status: nope"), encoding="utf-8")

    report = await _lint(stand, ws_id, f"{DRAFT_DIR}/version.yaml")

    schema = [f for f in report["findings"] if f["check"] == "schema"]
    assert schema, report
    status = next(f for f in schema if f["pointer"] == "/status")
    assert status["severity"] == "error"
    assert status["path"] == f"{DRAFT_DIR}/version.yaml"
    lines = manifest.read_text(encoding="utf-8").splitlines()
    assert lines[status["line"] - 1].startswith("status: nope")


async def test__lint__released_version__schema_findings_are_warnings(stand: Stand) -> None:
    ws_id, folder = await _workspace(stand)
    manifest = folder / RELEASED_DIR / "version.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace("status: stable", "status: nope"))

    report = await _lint(stand, ws_id, f"{RELEASED_DIR}/files/report/main.tex")

    assert report["released"] is True
    schema = [f for f in report["findings"] if f["check"] == "schema"]
    assert schema
    assert {f["severity"] for f in schema} == {"warning"}


async def test__lint__pack_manifest__schema_only__and_other_files__nothing(stand: Stand) -> None:
    ws_id, folder = await _workspace(stand)
    (folder / "demo/pack.yaml").write_text("id: 5\n", encoding="utf-8")

    pack = await _lint(stand, ws_id, "demo/pack.yaml")
    template = await _lint(stand, ws_id, f"{TEMPLATE_DIR}/template.yaml")
    readme = await _lint(stand, ws_id, "README.md")

    assert pack["scope"] == "file"
    assert pack["target"] == "demo/pack.yaml"
    assert pack["errors"] >= 1
    assert all(f["check"] == "schema" and f["path"] == "demo/pack.yaml" for f in pack["findings"])
    assert all(f["line"] == 1 for f in pack["findings"])
    assert template["scope"] == "file"
    assert readme == {"scope": "none", "target": None, "released": False, "errors": 0, "warnings": 0, "findings": []}


async def test__lint__bad_path__is_refused(stand: Stand) -> None:
    ws_id, _ = await _workspace(stand)

    resp = await stand.client.post(f"{API}/workspaces/{ws_id}/lint", json={"path": "../etc/passwd"})

    assert resp.status_code == 400
    assert resp.json()["code"] == "path_not_allowed"


async def test__lint__missing_version__is_file_not_found(stand: Stand) -> None:
    ws_id, _ = await _workspace(stand)

    resp = await stand.client.post(
        f"{API}/workspaces/{ws_id}/lint", json={"path": f"{TEMPLATE_DIR}/versions/2099.1.0/version.yaml"}
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == "file_not_found"


async def test__hints__meta_fields_and_include_macros__of_the_files_version(stand: Stand) -> None:
    ws_id, folder = await _workspace(stand)
    manifest = folder / DRAFT_DIR / "version.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + "dynamic_includes:\n  - template: common/meta.tex.j2\n    output: common/meta.tex\n"
        + "meta_fields:\n  year:\n    type: string\n    group: study\n    label: { ru: Год, en: Year }\n"
        + "  advisor_note: {}\n",
        encoding="utf-8",
    )
    include = folder / DRAFT_DIR / "files/common/meta.tex.j2"
    include.parent.mkdir(parents=True)
    include.write_text(_META_J2, encoding="utf-8")

    resp = await stand.client.get(
        f"{API}/workspaces/{ws_id}/hints", params={"path": f"{DRAFT_DIR}/files/report/main.tex"}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["version"] == DRAFT_DIR
    assert body["meta_fields"] == [
        {"key": "year", "type": "string", "label": {"ru": "Год", "en": "Year"}, "group": "study"},
        {"key": "advisor_note", "type": None, "label": None, "group": None},
    ]
    source = f"{DRAFT_DIR}/files/common/meta.tex.j2"
    assert body["macros"] == [
        {"name": "hseYear", "keys": ["year"], "source": source},
        {"name": "hseTitle", "keys": [], "source": source},
    ]


async def test__hints__outside_a_version__are_empty(stand: Stand) -> None:
    ws_id, _ = await _workspace(stand)

    resp = await stand.client.get(f"{API}/workspaces/{ws_id}/hints", params={"path": "demo/pack.yaml"})

    assert resp.status_code == 200
    assert resp.json() == {"version": None, "meta_fields": [], "macros": []}


async def test__insight__section_off__is_404(stand: Stand) -> None:
    resp = await stand.client.post(f"{API}/workspaces/00000000-0000-4000-8000-000000000000/lint", json={"path": "a"})

    assert resp.status_code == 404
    assert resp.json()["code"] == "pack_studio_disabled"
