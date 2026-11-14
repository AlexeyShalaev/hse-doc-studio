"""Студия шаблонов локально: раздел, пространство над папкой, дерево, файлы с ETag, защита выпущенных версий."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from hse_doc_studio.core.file_version import file_etag

from tests.integration.api.pack_studio.conftest import (
    API,
    DRAFT,
    DRAFT_DIR,
    REGISTRY,
    RELEASED,
    RELEASED_DIR,
    TEMPLATE_DIR,
    Stand,
    write_pack,
)

pytestmark = pytest.mark.usefixtures("stand")


async def _workspace(stand: Stand) -> tuple[str, Path]:
    folder = write_pack(stand.root / "packs-folder")
    await stand.enable()
    ws = await stand.folder_workspace(folder)
    return ws["id"], folder


async def test__section__off_by_default__routes_are_404_and_capability_is_false(stand: Stand) -> None:
    section = await stand.client.get(f"{API}/section")
    listed = await stand.client.get(f"{API}/workspaces")
    boot = await stand.client.get("/api/v1/session/bootstrap")

    assert section.json() == {
        "enabled": False,
        "locked": False,
        "allowed": False,
        "has_right": True,
        "standalone": False,
    }
    assert listed.status_code == 404
    assert listed.json()["code"] == "pack_studio_disabled"
    assert boot.json()["capabilities"]["pack_studio"] is False


async def test__section__turned_on_in_settings__opens_routes_and_capability(stand: Stand) -> None:
    await stand.enable()

    listed = await stand.client.get(f"{API}/workspaces")
    boot = await stand.client.get("/api/v1/session/bootstrap")

    assert listed.status_code == 200
    assert listed.json() == []
    assert boot.json()["capabilities"]["pack_studio"] is True


async def test__folder_workspace__is_ready_with_packs_path_detected(stand: Stand) -> None:
    root = stand.root / "repo"
    write_pack(root / "packs")
    await stand.enable()

    ws = await stand.folder_workspace(root, label="Мои паки")

    assert ws["kind"] == "folder"
    assert ws["state"] == "ready"
    assert ws["packs_path"] == "packs"
    assert ws["label"] == "Мои паки"
    assert ws["folder"] == str(root.resolve())


async def test__folder_workspace__folder_without_packs__is_refused(stand: Stand) -> None:
    folder = stand.root / "not-packs"
    folder.mkdir()
    (folder / "notes.txt").write_text("x", encoding="utf-8")
    await stand.enable()

    resp = await stand.client.post(f"{API}/workspaces", json={"kind": "folder", "folder": str(folder)})

    assert resp.status_code == 400
    assert resp.json()["code"] == "not_a_pack_repo"


async def test__tree__marks_released_versions_and_read_only_files(stand: Stand) -> None:
    ws_id, _ = await _workspace(stand)

    tree = (await stand.client.get(f"{API}/workspaces/{ws_id}/tree")).json()

    (pack,) = tree["packs"]
    (template,) = pack["templates"]
    versions = {v["version"]: v for v in template["versions"]}
    files = {f["path"]: f for f in tree["files"]}
    assert pack["name"] == {"ru": "Демо", "en": "Demo"}
    assert template["default_version"] == RELEASED
    assert versions[RELEASED]["released"] is True
    assert versions[RELEASED]["modified"] is False
    assert versions[DRAFT]["released"] is False
    assert files[f"{RELEASED_DIR}/version.yaml"]["read_only"] == "version_released"
    assert files[REGISTRY]["read_only"] == "releases_read_only"
    assert files[f"{DRAFT_DIR}/version.yaml"]["read_only"] is None


async def test__tree__released_dir_edited_outside__is_marked_modified(stand: Stand) -> None:
    ws_id, folder = await _workspace(stand)
    (folder / RELEASED_DIR / "files" / "report" / "main.tex").write_text("changed\n", encoding="utf-8")

    tree = (await stand.client.get(f"{API}/workspaces/{ws_id}/tree")).json()

    versions = {v["version"]: v for v in tree["packs"][0]["templates"][0]["versions"]}
    assert versions[RELEASED]["modified"] is True


async def test__read__returns_content_etag_and_read_only_header(stand: Stand) -> None:
    ws_id, folder = await _workspace(stand)

    draft = await stand.read(ws_id, f"{DRAFT_DIR}/version.yaml")
    released = await stand.read(ws_id, f"{RELEASED_DIR}/version.yaml")

    assert draft.status_code == 200
    assert draft.content == (folder / DRAFT_DIR / "version.yaml").read_bytes()
    assert draft.headers["etag"] == file_etag(draft.content)
    assert "x-pack-read-only" not in draft.headers
    assert released.headers["x-pack-read-only"] == "version_released"


async def test__write__draft_with_matching_etag__replaces_file(stand: Stand) -> None:
    ws_id, folder = await _workspace(stand)
    path = f"{DRAFT_DIR}/files/report/main.tex"
    etag = (await stand.read(ws_id, path)).headers["etag"]

    resp = await stand.client.put(stand.file_url(ws_id, path), content=b"new\n", headers={"If-Match": etag})

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"path": path, "etag": file_etag(b"new\n"), "size": 4}
    assert (folder / path).read_bytes() == b"new\n"


async def test__write__new_file_in_new_folder__is_created(stand: Stand) -> None:
    ws_id, folder = await _workspace(stand)
    path = f"{DRAFT_DIR}/files/appendix/a.tex"

    resp = await stand.client.put(stand.file_url(ws_id, path), content=b"A")

    assert resp.status_code == 200
    assert (folder / path).read_bytes() == b"A"


async def test__write__stale_etag__is_409_with_current_version(stand: Stand) -> None:
    ws_id, folder = await _workspace(stand)
    path = f"{DRAFT_DIR}/files/report/main.tex"

    resp = await stand.client.put(stand.file_url(ws_id, path), content=b"mine", headers={"If-Match": '"old"'})

    body = resp.json()
    current = (folder / path).read_bytes()
    assert resp.status_code == 409
    assert body["code"] == "stale_file"
    assert body["etag"] == file_etag(current)
    assert body["content"] == current.decode()


@pytest.mark.parametrize(
    "path",
    [
        f"{RELEASED_DIR}/version.yaml",
        f"{RELEASED_DIR}/files/report/new.tex",
        # Регистр не обходит запрет: на macOS и Windows это та же папка.
        f"demo/Templates/report/Versions/{RELEASED}/version.yaml",
    ],
)
async def test__write__released_version__is_409_version_released(stand: Stand, path: str) -> None:
    ws_id, folder = await _workspace(stand)
    before = (folder / RELEASED_DIR / "version.yaml").read_bytes()

    resp = await stand.client.put(stand.file_url(ws_id, path), content=b"x")

    assert resp.status_code == 409
    assert resp.json()["code"] == "version_released"
    assert resp.json()["path"].lower() == RELEASED_DIR.lower()
    assert (folder / RELEASED_DIR / "version.yaml").read_bytes() == before


async def test__write__release_registry__is_409_releases_read_only(stand: Stand) -> None:
    ws_id, _ = await _workspace(stand)

    resp = await stand.client.put(stand.file_url(ws_id, REGISTRY), content=b"releases: {}\n")

    assert resp.status_code == 409
    assert resp.json()["code"] == "releases_read_only"


@pytest.mark.parametrize("path", ["%2E%2E/escape.txt", "demo/%2E%2E/%2E%2E/escape.txt", ".git/config", "demo/.GIT/x"])
async def test__write__path_outside_or_into_git__is_refused(stand: Stand, path: str) -> None:
    ws_id, folder = await _workspace(stand)

    resp = await stand.client.put(f"{API}/workspaces/{ws_id}/files/{path}", content=b"x")

    assert resp.status_code in {400, 404}
    if resp.status_code == 400:
        assert resp.json()["code"] == "path_not_allowed"
    assert not (folder.parent / "escape.txt").exists()


@pytest.mark.skipif(os.name != "posix", reason="символьные ссылки")
async def test__files__symlink_on_path__is_refused(stand: Stand) -> None:
    ws_id, folder = await _workspace(stand)
    outside = stand.root / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    (folder / DRAFT_DIR / "link").symlink_to(outside, target_is_directory=True)
    (folder / DRAFT_DIR / "file-link").symlink_to(outside / "secret.txt")

    through_dir = await stand.client.put(stand.file_url(ws_id, f"{DRAFT_DIR}/link/x.txt"), content=b"x")
    read_link = await stand.read(ws_id, f"{DRAFT_DIR}/file-link")

    assert through_dir.status_code == 400
    assert through_dir.json()["code"] == "path_not_allowed"
    assert read_link.status_code == 400
    assert not (outside / "x.txt").exists()


async def test__write__over_size_limit__is_413(stand: Stand) -> None:
    ws_id, _ = await _workspace(stand)
    big = b"x" * (2 * 1024 * 1024 + 1)

    resp = await stand.client.put(stand.file_url(ws_id, f"{DRAFT_DIR}/big.bin"), content=big)

    assert resp.status_code == 413
    assert resp.json()["code"] == "file_too_large"


async def test__patch_yaml__point_edit_keeps_comments_and_alignment(stand: Stand) -> None:
    ws_id, folder = await _workspace(stand)
    path = f"{DRAFT_DIR}/version.yaml"
    before = (folder / path).read_text(encoding="utf-8")
    etag = (await stand.read(ws_id, path)).headers["etag"]

    resp = await stand.client.patch(
        stand.file_url(ws_id, path),
        json={
            "ops": [
                {"op": "set", "path": ["summary", "ru"], "value": "Вторая"},
                {"op": "set", "path": ["engine"], "value": "xelatex"},
            ]
        },
        headers={"If-Match": etag},
    )

    body = resp.json()
    after = (folder / path).read_text(encoding="utf-8")
    assert resp.status_code == 200, resp.text
    assert body["content"] == after
    assert body["etag"] == file_etag(after.encode())
    assert after.splitlines()[0] == before.splitlines()[0]
    assert '{ ru: "Вторая", en: "First" }   # выровнено как в паках' in after
    assert yaml.safe_load(after)["engine"] == "xelatex"


async def test__patch_yaml__path_missing_in_document__is_409_and_file_untouched(stand: Stand) -> None:
    ws_id, folder = await _workspace(stand)
    path = f"{DRAFT_DIR}/version.yaml"
    before = (folder / path).read_bytes()

    resp = await stand.client.patch(
        stand.file_url(ws_id, path),
        json={"ops": [{"op": "set", "path": ["summary", "ru"], "value": "ok"}, {"op": "delete", "path": ["nope", 0]}]},
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "yaml_patch_conflict"
    assert resp.json()["op"] == 1
    assert (folder / path).read_bytes() == before


async def test__patch_yaml__released_version_and_non_yaml__are_refused(stand: Stand) -> None:
    ws_id, _ = await _workspace(stand)
    ops = {"ops": [{"op": "set", "path": ["status"], "value": "deprecated"}]}

    released = await stand.client.patch(stand.file_url(ws_id, f"{RELEASED_DIR}/version.yaml"), json=ops)
    tex = await stand.client.patch(stand.file_url(ws_id, f"{DRAFT_DIR}/files/report/main.tex"), json=ops)

    assert released.status_code == 409
    assert released.json()["code"] == "version_released"
    assert tex.status_code == 400
    assert tex.json()["code"] == "not_yaml"


async def test__delete__draft_file_and_folder__are_removed(stand: Stand) -> None:
    ws_id, folder = await _workspace(stand)

    file_resp = await stand.client.delete(stand.file_url(ws_id, f"{DRAFT_DIR}/files/report/main.tex"))
    dir_resp = await stand.client.delete(stand.file_url(ws_id, DRAFT_DIR))

    assert file_resp.status_code == 204
    assert dir_resp.status_code == 204
    assert not (folder / DRAFT_DIR).exists()


@pytest.mark.parametrize(
    ("path", "code"),
    [
        (RELEASED_DIR, "version_released"),
        (f"{RELEASED_DIR}/files", "version_released"),
        (TEMPLATE_DIR, "version_released"),
        ("demo", "version_released"),
        (REGISTRY, "releases_read_only"),
    ],
)
async def test__delete__released_version_registry_or_their_parents__is_refused(
    stand: Stand, path: str, code: str
) -> None:
    ws_id, folder = await _workspace(stand)

    resp = await stand.client.delete(stand.file_url(ws_id, path))

    assert resp.status_code == 409
    assert resp.json()["code"] == code
    assert (folder / RELEASED_DIR / "version.yaml").exists()
    assert (folder / REGISTRY).exists()


async def test__delete_workspace__forgets_record_but_keeps_folder(stand: Stand) -> None:
    ws_id, folder = await _workspace(stand)

    resp = await stand.client.delete(f"{API}/workspaces/{ws_id}")
    missing = await stand.client.get(f"{API}/workspaces/{ws_id}")

    assert resp.status_code == 204
    assert missing.status_code == 404
    assert missing.json()["code"] == "workspace_not_found"
    assert (folder / TEMPLATE_DIR / "template.yaml").exists()


async def test__refresh__folder_workspace__is_not_a_git_workspace(stand: Stand) -> None:
    ws_id, _ = await _workspace(stand)

    resp = await stand.client.post(f"{API}/workspaces/{ws_id}/refresh")

    assert resp.status_code == 409
    assert resp.json()["code"] == "not_a_git_workspace"


async def test__draft_file_written_then_read__round_trips_with_version(stand: Stand) -> None:
    ws_id, _ = await _workspace(stand)
    path = f"{TEMPLATE_DIR}/examples/default.yaml"

    put = await stand.client.put(stand.file_url(ws_id, path), content="name: { ru: Пример }\n".encode())
    got = await stand.read(ws_id, path)

    assert put.status_code == 200
    assert got.headers["etag"] == put.headers["etag"]
    assert got.content.decode() == "name: { ru: Пример }\n"


async def test__workspace_limit__refuses_one_more(stand: Stand) -> None:
    from hse_doc_studio.api.config import settings  # noqa: PLC0415

    folder = write_pack(stand.root / "packs-folder")
    await stand.enable()
    limit = settings.pack_studio.max_workspaces_per_user
    for _ in range(limit):
        await stand.folder_workspace(folder)

    resp = await stand.client.post(f"{API}/workspaces", json={"kind": "folder", "folder": str(folder)})

    assert resp.status_code == 409
    assert resp.json()["code"] == "workspace_limit"


async def test__unknown_released_version_name_case__in_tree_reads_from_disk(stand: Stand) -> None:
    """Реестр на диске у папки: версия, внесённая в реестр, сразу защищена."""
    ws_id, folder = await _workspace(stand)
    (folder / DRAFT_DIR / "version.yaml").write_text(
        (folder / DRAFT_DIR / "version.yaml").read_text(encoding="utf-8").replace("status: beta", "status: stable"),
        encoding="utf-8",
    )
    from hse_doc_studio.infra.template.releases import freeze  # noqa: PLC0415

    freeze(folder / TEMPLATE_DIR, DRAFT)

    resp = await stand.client.put(stand.file_url(ws_id, f"{DRAFT_DIR}/files/report/main.tex"), content=b"x")

    assert resp.status_code == 409
    assert resp.json()["code"] == "version_released"
