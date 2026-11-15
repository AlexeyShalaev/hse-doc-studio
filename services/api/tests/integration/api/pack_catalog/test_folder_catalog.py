"""«Подключить к каталогу этой Студии» локально (template-studio.md, 10.3 и 10.4, срез T17).

Настоящий пак репозитория копируется в папку под другим id (`acme-se`), папка становится рабочим пространством
Студии шаблонов и источником каталога. Проверка показывает план, «Применить» кладёт версии в хранилище по дайджесту,
мастер проекта видит пак с источником, проект создаётся из подключённой версии, а все файлы шаблона лежат в его
папке: раннер (встроенный, k8s, личный) получает проект целиком по манифесту, паков в его образе не нужно.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.infra.template.releases import load_releases

from tests.factories import project_api_payload
from tests.integration.api.pack_studio.conftest import API, Stand

_REPO_PACKS = Path(__file__).resolve().parents[6] / "packs"
PACK = "acme-se"


def _source_folder(root: Path) -> Path:
    folder = root / "acme-packs"
    shutil.copytree(_REPO_PACKS / "hse-cs-se", folder / PACK)
    manifest = folder / PACK / "pack.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("id: hse-cs-se", f"id: {PACK}", 1), encoding="utf-8"
    )
    return folder


async def _connect(stand: Stand, folder: Path, **check: Any) -> tuple[str, dict[str, Any]]:
    await stand.enable()
    ws = await stand.folder_workspace(folder)
    resp = await stand.client.post(f"{API}/workspaces/{ws['id']}/catalog/check", json=check)
    assert resp.status_code == 200, resp.text
    return str(ws["id"]), dict(resp.json())


def _released(folder: Path, template: str) -> set[str]:
    return set(load_releases(folder / PACK / "templates" / template))


@pytest.mark.timeout(180)
async def test__folder__check_apply_wizard_and_project_from_subscribed_version(stand: Stand) -> None:
    folder = _source_folder(stand.root)
    ws_id, report = await _connect(stand, folder)

    versions = {(v["template"], v["version"]): v["verdict"] for p in report["packs"] for v in p["versions"]}
    assert report["ok"], report
    assert report["source"]["kind"] == "folder"
    assert {key for key, verdict in versions.items() if verdict == "new"} == {
        (t, v) for t in ("coursework", "pp", "vkr") for v in _released(folder, t)
    }
    assert report["new_count"] > 0

    applied = await stand.client.post(f"{API}/workspaces/{ws_id}/catalog/apply", json={"revision": report["revision"]})
    assert applied.status_code == 200, applied.text
    assert applied.json()["catalog_revision"] == 1
    assert len(applied.json()["added"]) == report["new_count"]

    packs = (await stand.client.get("/api/v1/catalog/packs")).json()
    acme = next(p for p in packs if p["id"] == PACK)
    builtin = next(p for p in packs if p["id"] == "hse-cs-se")
    assert acme["origin"]["kind"] == "subscribed"
    assert acme["origin"]["source_kind"] == "folder"
    assert builtin["origin"]["kind"] == "builtin"

    # Проект из подключённой версии: файлы шаблона копируются в папку проекта из хранилища.
    payload = {**project_api_payload(str(stand.root / "proj")), "pack_id": PACK}
    created = await stand.client.post("/api/v1/projects", json=payload)
    assert created.status_code in (200, 201), created.text
    project_dir = stand.root / "proj"
    assert (project_dir / "common" / "meta.tex").is_file()
    assert any(p.suffix == ".tex" and p.parent.name != "common" for p in project_dir.rglob("*.tex"))
    store = stand.root / "data" / "packs-store" / PACK / "vkr"
    assert any(d.name.startswith("2026.1@") for d in store.iterdir())


@pytest.mark.timeout(180)
async def test__folder__edited_release_is_refused_and_disable_hides_from_wizard(stand: Stand) -> None:
    folder = _source_folder(stand.root)
    ws_id, report = await _connect(stand, folder)
    await stand.client.post(f"{API}/workspaces/{ws_id}/catalog/apply", json={"revision": report["revision"]})

    # Выпущенный каталог правят на месте и переиздают тот же номер: «версия изменена в источнике».
    version_dir = folder / PACK / "templates" / "vkr" / "versions" / "2026.1"
    tex = next(version_dir.rglob("*.tex"))
    tex.write_text(tex.read_text(encoding="utf-8") + "% правка\n", encoding="utf-8")
    from hse_doc_studio.infra.template.releases import freeze  # noqa: PLC0415

    freeze(folder / PACK / "templates" / "vkr", "2026.1", replace=True)
    second = (await stand.client.post(f"{API}/workspaces/{ws_id}/catalog/check", json={})).json()
    changed = [v for p in second["packs"] for v in p["versions"] if v["verdict"] == "changed"]
    assert not second["ok"]
    assert second["blockers"] == ["version_changed"]
    assert [(v["template"], v["version"]) for v in changed] == [("vkr", "2026.1")]
    refused = await stand.client.post(f"{API}/workspaces/{ws_id}/catalog/apply", json={"revision": second["revision"]})
    assert refused.status_code == 409
    assert refused.json()["code"] == "plan_blocked"

    off = await stand.client.patch(f"{API}/workspaces/{ws_id}/catalog", json={"enabled": False})
    assert off.status_code == 200, off.text
    assert PACK not in {p["id"] for p in (await stand.client.get("/api/v1/catalog/packs")).json()}

    gone = await stand.client.delete(f"{API}/workspaces/{ws_id}/catalog")
    assert gone.status_code == 204
    assert (await stand.client.get(f"{API}/workspaces/{ws_id}/catalog")).json() == {"source": None}
    # Хранилище только дописывается: каталоги версий на месте для существующих проектов.
    assert any((stand.root / "data" / "packs-store" / PACK / "vkr").iterdir())


async def test__folder__builtin_id_needs_replace_builtin(stand: Stand) -> None:
    folder = stand.root / "copy"
    shutil.copytree(_REPO_PACKS / "hse-cs-sse", folder / "hse-cs-sse")

    ws_id, refused = await _connect(stand, folder)
    allowed = (
        await stand.client.post(f"{API}/workspaces/{ws_id}/catalog/check", json={"replace_builtin": True})
    ).json()

    assert refused["blockers"] == ["pack_conflict"]
    assert refused["packs"][0]["conflict"] == "builtin"
    assert allowed["ok"], allowed
    assert allowed["packs"][0]["replaces_builtin"]
    # Те же версии, что вшиты, байт в байт: уже есть в каталоге.
    assert {v["verdict"] for p in allowed["packs"] for v in p["versions"]} <= {"present", "unreleased"}


async def test__apply__only_the_checked_revision(stand: Stand) -> None:
    folder = _source_folder(stand.root)
    ws_id, report = await _connect(stand, folder)

    moved = await stand.client.post(f"{API}/workspaces/{ws_id}/catalog/apply", json={"revision": "0" * 64})

    assert moved.status_code == 409
    assert moved.json()["code"] == "revision_moved"
    assert report["ok"]


async def test__admin_catalog_routes__absent_locally(stand: Stand) -> None:
    resp = await stand.client.get("/api/admin/pack-catalog")

    assert resp.status_code == 404
