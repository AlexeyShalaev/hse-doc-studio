"""Студия шаблонов, срез T15: пак и шаблон с нуля (template-studio.md, раздел 8).

Пространство над папкой: окно «Новый пак» (источники копии, занятые id), заготовка «Минимальный», копия версии
пространства и каталога Студии в новый шаблон, отказы по id. Каталог Студии в тестовом приложении это `packs/`
монорепы: `hse-cs-sse` в нём есть.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from hse_doc_studio.infra.template.releases import load_releases

from tests.integration.api.pack_studio.conftest import API, RELEASED, Stand, write_pack

_NAME = {"ru": "Мой пак", "en": "My pack"}
_TEMPLATE = {"id": "report", "name": {"ru": "Отчёт", "en": "Report"}}


async def _folder(stand: Stand) -> tuple[str, Path]:
    folder = write_pack(stand.root / "packs-folder")
    await stand.enable()
    ws = await stand.folder_workspace(folder)
    return str(ws["id"]), folder


def _yaml(path: Path) -> dict[str, Any]:
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")))


async def _lint(stand: Stand, ws_id: str, path: str) -> list[dict[str, Any]]:
    resp = await stand.client.post(f"{API}/workspaces/{ws_id}/lint", json={"path": path})
    assert resp.status_code == 200, resp.text
    return [f for f in resp.json()["findings"] if f["severity"] == "error"]


async def test__options__workspace_and_catalog_sources_and_taken_ids(stand: Stand) -> None:
    ws_id, _ = await _folder(stand)

    resp = await stand.client.get(f"{API}/workspaces/{ws_id}/scaffold")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    origins = {(p["origin"], p["pack"]) for p in body["sources"]}
    assert ("workspace", "demo") in origins
    assert ("catalog", "hse-cs-sse") in origins
    assert {"demo", "hse-cs-sse"} <= set(body["taken_packs"])
    demo = next(p for p in body["sources"] if p["pack"] == "demo")
    versions = demo["templates"][0]["versions"]
    assert [(v["version"], v["released"]) for v in versions] == [("2026.1.1", False), (RELEASED, True)]
    assert body["license"] == "Apache-2.0"
    assert body["version"].endswith(".1")


async def test__create_pack__minimal__lint_clean_and_shown_in_the_tree(stand: Stand) -> None:
    ws_id, folder = await _folder(stand)

    resp = await stand.client.post(
        f"{API}/workspaces/{ws_id}/packs",
        json={
            "id": "my-pack",
            "name": _NAME,
            "maintainer": {"name": "Автор Паков", "email": "author@example.org"},
            "template": _TEMPLATE,
            "version": "2026.1",
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["version"]["path"] == "my-pack/templates/report/versions/2026.1"
    assert body["pack_created"] is True
    assert body["main_file"] == "my-pack/templates/report/versions/2026.1/files/report/report.tex"
    pack = _yaml(folder / "my-pack" / "pack.yaml")
    assert pack["id"] == "my-pack"
    assert pack["maintainer"] == {"name": "Автор Паков", "email": "author@example.org"}
    assert pack["license"] == "Apache-2.0"
    template_dir = folder / "my-pack" / "templates" / "report"
    assert _yaml(template_dir / "template.yaml")["default_version"] == "2026.1"
    assert load_releases(template_dir) == {}
    manifest = _yaml(template_dir / "versions" / "2026.1" / "version.yaml")
    assert (manifest["id"], manifest["status"]) == ("2026.1", "beta")
    assert manifest["documents"] == ["report"]
    assert set(manifest["meta_fields"]) == {"year", "program"}
    assert manifest["meta_fields"]["year"]["auto"] == "academic_year"
    assert [s["id"] for s in manifest["signatures"]["slots"]] == ["author"]
    assert [p["id"] for p in manifest["pack_submission"]["profiles"]] == ["final"]
    assert await _lint(stand, ws_id, body["manifests"][-1]) == []
    tree = await stand.client.get(f"{API}/workspaces/{ws_id}/tree")
    packs = {p["id"]: p for p in tree.json()["packs"]}
    assert packs["my-pack"]["templates"][0]["versions"][0]["version"] == "2026.1"
    assert not [p for p in folder.iterdir() if p.name.startswith(".new-")]


async def test__create_pack__copy_from_the_catalog__new_ids_and_attribution(stand: Stand) -> None:
    ws_id, folder = await _folder(stand)

    resp = await stand.client.post(
        f"{API}/workspaces/{ws_id}/packs",
        json={
            "id": "sse-spb",
            "name": {"ru": "СПИ Петербург", "en": ""},
            "template": {"id": "kp", "name": {"ru": "КП", "en": "CP"}},
            "scaffold": {
                "kind": "copy",
                "source": {"origin": "catalog", "pack": "hse-cs-sse", "template": "coursework", "version": "2026.1.6"},
            },
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"] == {
        "origin": "catalog",
        "pack": "hse-cs-sse",
        "template": "coursework",
        "version": "2026.1.6",
    }
    text = (folder / "sse-spb" / "pack.yaml").read_text(encoding="utf-8")
    assert "# Основан на паке hse-cs-sse" in text
    assert "версия 2026.1.6" in text
    pack = yaml.safe_load(text)
    assert pack["name"] == {"ru": "СПИ Петербург", "en": "СПИ Петербург"}
    version_dir = folder / "sse-spb" / "templates" / "kp" / "versions" / body["version"]["version"]
    manifest = _yaml(version_dir / "version.yaml")
    assert manifest["id"] == body["version"]["version"]
    assert manifest["status"] == "beta"
    assert "release" not in manifest
    assert manifest["breaking_changes"] == {"ru": [], "en": []}
    assert len(manifest["changes"]["ru"]) == len(manifest["changes"]["en"]) == 1
    assert (version_dir / "files" / "report" / "report.ru.tex").is_file()
    assert _yaml(folder / "sse-spb" / "templates" / "kp" / "template.yaml")["icon"] == "NotebookPen"
    assert await _lint(stand, ws_id, f"{body['version']['path']}/version.yaml") == []


async def test__create_template__copy_of_a_workspace_version_in_the_same_pack(stand: Stand) -> None:
    ws_id, folder = await _folder(stand)

    resp = await stand.client.post(
        f"{API}/workspaces/{ws_id}/packs/demo/templates",
        json={
            "id": "practice",
            "name": {"ru": "Практика", "en": "Internship"},
            "scaffold": {
                "kind": "copy",
                "source": {"origin": "workspace", "pack": "demo", "template": "report", "version": RELEASED},
            },
            "version": "2027.1",
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["pack_created"] is False
    assert body["manifests"] == [
        "demo/templates/practice/template.yaml",
        "demo/templates/practice/versions/2027.1/version.yaml",
    ]
    template_text = (folder / "demo" / "templates" / "practice" / "template.yaml").read_text(encoding="utf-8")
    assert "# Основан на паке demo" in template_text
    copied = folder / "demo" / "templates" / "practice" / "versions" / "2027.1" / "files" / "report" / "main.tex"
    assert copied.read_text(encoding="utf-8") == "\\documentclass{article}\n"


async def test__create__refusals(stand: Stand) -> None:
    ws_id, _ = await _folder(stand)
    url = f"{API}/workspaces/{ws_id}/packs"

    taken = await stand.client.post(url, json={"id": "demo", "name": _NAME, "template": _TEMPLATE})
    builtin = await stand.client.post(url, json={"id": "hse-cs-sse", "name": _NAME, "template": _TEMPLATE})
    invalid = await stand.client.post(url, json={"id": "My_Pack", "name": _NAME, "template": _TEMPLATE})
    no_name = await stand.client.post(url, json={"id": "x", "name": {"ru": " "}, "template": _TEMPLATE})
    template_taken = await stand.client.post(f"{url}/demo/templates", json=_TEMPLATE)
    no_pack = await stand.client.post(f"{url}/nope/templates", json=_TEMPLATE)
    no_source = await stand.client.post(
        f"{url}/demo/templates",
        json={
            "id": "other",
            "name": _NAME,
            "scaffold": {
                "kind": "copy",
                "source": {"origin": "workspace", "pack": "demo", "template": "report", "version": "9.9"},
            },
        },
    )

    assert (taken.status_code, taken.json()["code"], taken.json()["where"]) == (409, "pack_id_taken", "workspace")
    assert (builtin.status_code, builtin.json()["where"]) == (409, "studio")
    assert (invalid.status_code, invalid.json()["code"], invalid.json()["field"]) == (400, "id_invalid", "pack")
    assert (no_name.status_code, no_name.json()["code"]) == (400, "name_required")
    assert (template_taken.status_code, template_taken.json()["code"]) == (409, "template_id_taken")
    assert (no_pack.status_code, no_pack.json()["code"]) == (404, "pack_not_found")
    assert (no_source.status_code, no_source.json()["code"]) == (404, "version_not_found")
