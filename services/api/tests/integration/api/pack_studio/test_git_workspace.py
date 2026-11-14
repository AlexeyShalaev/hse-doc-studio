"""Студия шаблонов локально: пространство над git-репозиторием паков (file://, git настоящий, сеть не нужна).

Клон частичный (без блобов) и разреженный (только папка паков), хранилище вне дерева и закалённое. Выпущенные
версии берутся из реестров базовой ветки: версию, выпущенную в базе после клона, закрывает «Обновить».
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.infra.template.releases import freeze, version_digest

from tests.fixtures.git_remote import BareRemote, GitHttpServer, make_bare_remote, run_git, seed_remote
from tests.integration.api.pack_studio.conftest import (
    API,
    DRAFT,
    DRAFT_DIR,
    PACK_FILES,
    RELEASED,
    RELEASED_DIR,
    TEMPLATE_DIR,
    Stand,
    write_pack,
)


def _remote(root: Path) -> BareRemote:
    remote = make_bare_remote(root / "packs.git")
    remote.git("config", "uploadpack.allowFilter", "true")
    files = {f"packs/{rel}": text for rel, text in PACK_FILES.items() if rel != "README.md"}
    files["README.md"] = "Репозиторий паков\n"
    files["services/api/big.txt"] = "x" * 10_000
    staged = write_pack(
        root / "stage", {rel.removeprefix("packs/"): t for rel, t in files.items() if rel.startswith("packs/")}
    )
    payload: dict[str, str | bytes] = {
        f"packs/{path.relative_to(staged).as_posix()}": path.read_bytes()
        for path in staged.rglob("*")
        if path.is_file()
    }
    payload.update({rel: text for rel, text in files.items() if not rel.startswith("packs/")})
    seed_remote(remote, payload)
    return remote


async def _git_workspace(stand: Stand, remote: BareRemote, **extra: object) -> dict[str, object]:
    await stand.enable()
    resp = await stand.client.post(f"{API}/workspaces", json={"kind": "git", "url": remote.url, **extra})
    assert resp.status_code == 202, resp.text
    assert resp.json()["state"] == "cloning"
    return await stand.settled(resp.json()["id"])


def _store(stand: Stand, workspace_id: str) -> Path:
    return stand.root / "data" / "pack-studio" / "workspaces" / workspace_id


async def test__git_workspace__partial_sparse_clone_is_ready(stand: Stand) -> None:
    remote = _remote(stand.root)

    ws = await _git_workspace(stand, remote)

    store = _store(stand, str(ws["id"]))
    tree = store / "tree"
    assert ws["state"] == "ready", ws
    assert ws["base_branch"] == "main"
    assert ws["base_sha"] == remote.head("main")
    assert ws["label"] == "packs"
    assert (tree / "packs" / TEMPLATE_DIR / "template.yaml").is_file()
    # Разреженное дерево: ничего вне папки паков, хранилище вне дерева.
    assert sorted(p.name for p in tree.iterdir()) == ["packs"]
    assert not (tree / ".git").exists()
    # Блобы вне папки паков не скачаны: частичный клон.
    missing = run_git("rev-list", "--objects", "--missing=print", "refs/remotes/origin/main", git_dir=store / "git")
    assert any(line.startswith("?") for line in missing.splitlines())


async def test__git_workspace__store_is_hardened_and_holds_no_secret(stand: Stand) -> None:
    remote = _remote(stand.root)

    ws = await _git_workspace(stand, remote)

    config = (_store(stand, str(ws["id"])) / "git" / "config").read_text(encoding="utf-8")
    assert "symlinks = false" in config
    assert "protectNTFS = true" in config
    assert "promisor = true" in config
    assert "hooksPath" not in config
    assert "extraheader" not in config.lower()
    assert "helper" not in config


async def test__git_workspace__tree_and_files_work_like_a_folder(stand: Stand) -> None:
    remote = _remote(stand.root)
    ws = await _git_workspace(stand, remote)
    ws_id = str(ws["id"])

    tree = (await stand.client.get(f"{API}/workspaces/{ws_id}/tree")).json()
    put_draft = await stand.client.put(stand.file_url(ws_id, f"{DRAFT_DIR}/files/report/main.tex"), content=b"x")
    put_released = await stand.client.put(stand.file_url(ws_id, f"{RELEASED_DIR}/files/report/main.tex"), content=b"x")

    versions = {v["version"]: v for v in tree["packs"][0]["templates"][0]["versions"]}
    assert tree["base_sha"] == remote.head("main")
    assert versions[RELEASED]["released"] is True
    assert versions[DRAFT]["released"] is False
    assert put_draft.status_code == 200
    assert put_released.status_code == 409
    assert put_released.json()["code"] == "version_released"


async def test__refresh__version_released_in_base__becomes_read_only(stand: Stand) -> None:
    remote = _remote(stand.root)
    ws = await _git_workspace(stand, remote)
    ws_id = str(ws["id"])
    path = f"{DRAFT_DIR}/files/report/main.tex"
    assert (await stand.client.put(stand.file_url(ws_id, path), content=b"draft edit")).status_code == 200
    # Кто-то выпустил 2026.1.1 в базовой ветке: правка реестра и статуса в новом коммите.
    other = write_pack(stand.root / "other", release=True)
    version_yaml = other / DRAFT_DIR / "version.yaml"
    version_yaml.write_text(version_yaml.read_text(encoding="utf-8").replace("beta", "stable"), encoding="utf-8")
    freeze(other / TEMPLATE_DIR, DRAFT)
    seed_remote(
        remote,
        {
            f"packs/{DRAFT_DIR}/version.yaml": version_yaml.read_bytes(),
            f"packs/{TEMPLATE_DIR}/releases.yaml": (other / TEMPLATE_DIR / "releases.yaml").read_bytes(),
        },
        message="release 2026.1.1",
    )

    started = await stand.client.post(f"{API}/workspaces/{ws_id}/refresh")
    refreshed = await stand.settled(ws_id)
    after = await stand.client.put(stand.file_url(ws_id, path), content=b"again")

    assert started.status_code == 202
    assert refreshed["base_sha"] == remote.head("main")
    assert refreshed["error"] is None
    assert after.status_code == 409
    assert after.json()["code"] == "version_released"
    # Рабочее дерево выборка не трогает: правка человека на месте.
    assert (_store(stand, ws_id) / "tree" / "packs" / path).read_bytes() == b"draft edit"


async def test__git_workspace__missing_branch__is_refused_before_clone(stand: Stand) -> None:
    remote = _remote(stand.root)
    await stand.enable()

    resp = await stand.client.post(
        f"{API}/workspaces", json={"kind": "git", "url": remote.url, "base_branch": "no-such-branch"}
    )

    assert resp.status_code in {404, 409, 422}
    assert resp.json()["code"] == "branch_missing"
    assert (await stand.client.get(f"{API}/workspaces")).json() == []


async def test__git_workspace__unreachable_remote__is_refused(stand: Stand) -> None:
    await stand.enable()

    resp = await stand.client.post(
        f"{API}/workspaces", json={"kind": "git", "url": f"file://{stand.root / 'nothing.git'}"}
    )

    assert resp.status_code >= 400
    assert resp.json()["code"] != "pack_studio_disabled"


async def test__git_workspace__repository_without_packs__fails_with_not_a_pack_repo(stand: Stand) -> None:
    remote = make_bare_remote(stand.root / "plain.git")
    seed_remote(remote, {"packs/notes.txt": "not a pack"})

    ws = await _git_workspace(stand, remote)

    assert ws["state"] == "failed"
    assert ws["error"]["code"] == "not_a_pack_repo"  # type: ignore[index]
    tree = await stand.client.get(f"{API}/workspaces/{ws['id']}/tree")
    assert tree.status_code == 409
    assert tree.json()["code"] == "workspace_not_ready"


async def test__git_workspace__too_large__fails_and_refresh_clones_again(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = _remote(stand.root)
    # Пределы читаются при первой сборке сервиса: до первого запроса их можно сузить.
    monkeypatch.setattr(app_settings.pack_studio, "max_tree_files", 2)

    ws = await _git_workspace(stand, remote)
    again = await stand.client.post(f"{API}/workspaces/{ws['id']}/refresh")
    settled = await stand.settled(str(ws["id"]))

    assert ws["state"] == "failed"
    assert ws["error"]["code"] == "workspace_too_large"  # type: ignore[index]
    assert again.status_code == 202
    assert again.json()["state"] == "cloning"
    assert settled["state"] == "failed"


async def test__delete_git_workspace__removes_its_store(stand: Stand) -> None:
    remote = _remote(stand.root)
    ws = await _git_workspace(stand, remote)
    store = _store(stand, str(ws["id"]))
    assert store.is_dir()

    resp = await stand.client.delete(f"{API}/workspaces/{ws['id']}")

    assert resp.status_code == 204
    assert not store.exists()


async def test__released_digest_matches_registry_after_clone(stand: Stand) -> None:
    remote = _remote(stand.root)
    ws = await _git_workspace(stand, remote)

    tree = _store(stand, str(ws["id"])) / "tree" / "packs"
    registry = (tree / TEMPLATE_DIR / "releases.yaml").read_text(encoding="utf-8")

    assert version_digest(tree / RELEASED_DIR) in registry


async def test__https_like_remote_with_token__clones_and_token_never_lands_on_disk(
    stand: Stand, http_git_server_factory: Callable[..., GitHttpServer]
) -> None:
    server = http_git_server_factory()
    bare = server.create_repo("packs.git")
    bare.git("config", "uploadpack.allowFilter", "true")
    seed = _remote(stand.root / "seed")
    run_git("push", "--quiet", bare.url, "refs/heads/main:refs/heads/main", git_dir=seed.path)
    await stand.enable()
    created = await stand.client.post(
        "/api/v1/git/credentials",
        json={"kind": "pat", "label": "Токен", "host": "127.0.0.1", "token": server.token},
    )
    assert created.status_code == 201, created.text

    resp = await stand.client.post(
        f"{API}/workspaces",
        json={"kind": "git", "url": server.url("packs.git"), "credential_id": created.json()["id"]},
    )
    assert resp.status_code == 202, resp.text
    ws = await stand.settled(resp.json()["id"])

    assert ws["state"] == "ready", ws
    assert server.authorizations()
    assert all(header == server.basic() for header in server.authorizations())
    token = str(server.token).encode()
    store = _store(stand, str(ws["id"]))
    leaked = [p for p in store.rglob("*") if p.is_file() and token in p.read_bytes()]
    assert leaked == []
    assert token not in (stand.root / "data" / "pack-studio" / "workspaces.json").read_bytes()
