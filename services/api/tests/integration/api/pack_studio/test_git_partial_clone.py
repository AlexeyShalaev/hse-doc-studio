"""Студия шаблонов: состояние git в частичном клоне, когда база ушла вперёд.

Выборка базы (`--filter=blob:none`) приносит коммиты и деревья, но не содержимое файлов. Раньше `GET .../git`
сравнивал рабочее дерево с базой через `git diff`, который для правленого файла читает блоб базы. Локальный git
ходить в сеть не может (`GIT_ALLOW_PROTOCOL=none`), и страница получала 502 «transport 'https' not allowed ... could
not fetch ... from promisor remote». Теперь «Обновить» догружает блобы базы под папкой паков, а состояние ветки их и
не читает: хранилище, где блоба базы нет (пространство, обновлённое до этой правки), отвечает так же.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from tests.fixtures.git_remote import BareRemote, GitHttpServer, run_git, seed_remote
from tests.fixtures.tls import make_ca_signed
from tests.integration.api.pack_studio.conftest import API, DRAFT_DIR, TEMPLATE_DIR, Stand
from tests.integration.api.pack_studio.test_git_studio_layout import _drop_pack_with
from tests.integration.api.pack_studio.test_git_workspace import _git_workspace, _remote, _store

_DRAFT_TEX = f"{DRAFT_DIR}/files/report/main.tex"
_NOTES = f"{TEMPLATE_DIR}/notes.md"
_THEIRS = b"\\documentclass{article}\n% theirs in base\n"


def _missing_in_base(stand: Stand, ws_id: str, path: str) -> bool:
    """Блоба файла базы нет в хранилище; `--missing=print` ничего не подгружает."""
    out = run_git(
        "rev-list",
        "--objects",
        "--missing=print",
        "refs/remotes/origin/main",
        "--",
        f"packs/{path}",
        git_dir=_store(stand, ws_id) / "git",
    )
    base_blob = run_git("rev-parse", f"refs/remotes/origin/main:packs/{path}", git_dir=_store(stand, ws_id) / "git")
    return f"?{base_blob}" in out.splitlines()


async def _put(stand: Stand, ws_id: str, path: str, content: bytes) -> None:
    resp = await stand.client.put(stand.file_url(ws_id, path), content=content)
    assert resp.status_code == 200, resp.text


async def _refresh(stand: Stand, ws_id: str) -> dict[str, Any]:
    started = await stand.client.post(f"{API}/workspaces/{ws_id}/refresh")
    assert started.status_code == 202, started.text
    return await stand.settled(ws_id)


async def _base_moved_under_local_edits(stand: Stand, remote: BareRemote, ws_id: str) -> None:
    """База правит черновик и заметки, человек правит тот же черновик у себя; потом «Обновить» тянет базу."""
    seed_remote(remote, {f"packs/{_DRAFT_TEX}": _THEIRS, f"packs/{_NOTES}": "новое в базе\n"}, message="base moved")
    await _put(stand, ws_id, _DRAFT_TEX, b"\\documentclass{article}\n% mine\n")
    refreshed = await _refresh(stand, ws_id)
    assert refreshed["base_sha"] == remote.head("main")
    assert refreshed["error"] is None, refreshed
    # «Обновить» догрузила блобы базы под папкой паков.
    assert not _missing_in_base(stand, ws_id, _DRAFT_TEX)


def _forget_base_blob(stand: Stand, ws_id: str) -> None:
    """Блоба черновика из базы снова нет: так выглядит хранилище, обновлённое до догрузки блобов базы."""
    _drop_pack_with(stand, ws_id, f"refs/remotes/origin/main:packs/{_DRAFT_TEX}")
    assert _missing_in_base(stand, ws_id, _DRAFT_TEX)


async def test__git_view__base_moved_and_its_blobs_are_missing__answers_without_network(stand: Stand) -> None:
    remote = _remote(stand.root)
    ws = await _git_workspace(stand, remote)
    ws_id = str(ws["id"])
    await _base_moved_under_local_edits(stand, remote, ws_id)
    _forget_base_blob(stand, ws_id)

    resp = await stand.client.get(f"{API}/workspaces/{ws_id}/git")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {c["path"]: c["status"] for c in body["uncommitted"]} == {_DRAFT_TEX: "modified"}
    changed = {c["path"]: c["status"] for c in body["changed"]}
    assert changed[_DRAFT_TEX] == "modified"
    assert (body["ahead"], body["behind"]) == (0, 1)
    # Состояние считалось по деревьям: блоб базы так и не понадобился.
    assert _missing_in_base(stand, ws_id, _DRAFT_TEX)


async def test__git_view__file_equal_to_the_new_base__is_not_changed(stand: Stand) -> None:
    remote = _remote(stand.root)
    ws = await _git_workspace(stand, remote)
    ws_id = str(ws["id"])
    await _base_moved_under_local_edits(stand, remote, ws_id)
    _forget_base_blob(stand, ws_id)
    # Человек вручную привёл файл к тексту базы: от базы он не отличается, хотя от своего коммита отличается.
    await _put(stand, ws_id, _DRAFT_TEX, _THEIRS)

    resp = await stand.client.get(f"{API}/workspaces/{ws_id}/git")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {c["path"]: c["status"] for c in body["uncommitted"]} == {_DRAFT_TEX: "modified"}
    assert _DRAFT_TEX not in {c["path"] for c in body["changed"]}


async def test__commit_and_diff__base_blobs_missing__work_and_diff_fetches_them(stand: Stand) -> None:
    remote = _remote(stand.root)
    assert (await stand.client.put("/api/v1/profile", json={"name": "Анна", "email": "anna@example.org"})).is_success
    ws = await _git_workspace(stand, remote)
    ws_id = str(ws["id"])
    await _base_moved_under_local_edits(stand, remote, ws_id)
    _forget_base_blob(stand, ws_id)

    committed = await stand.client.post(f"{API}/workspaces/{ws_id}/git/commit", json={})
    diff = await stand.client.get(f"{API}/workspaces/{ws_id}/git/diff")

    assert committed.status_code == 200, committed.text
    assert committed.json()["git"]["ahead"] == 1
    assert diff.status_code == 200, diff.text
    # Полный diff нужен текст базы: блоб подгружается с доступом пространства.
    assert "-% theirs in base" in diff.json()["diff"]
    assert "+% mine" in diff.json()["diff"]


async def test__https_workspace_with_token__git_view_and_diff_after_base_moved(
    stand: Stand, http_git_server_factory: Callable[..., GitHttpServer], tmp_path: Path
) -> None:
    """То же через https с токеном (как у GitHub): локальный git в сеть не ходит, diff ходит с токеном."""
    tls = make_ca_signed(tmp_path / "tls")
    server = http_git_server_factory(tls=tls)
    bare = server.create_repo("acme/packs.git")
    bare.git("config", "uploadpack.allowFilter", "true")
    seed = _remote(stand.root / "seed")
    run_git("push", "--quiet", bare.url, "refs/heads/main:refs/heads/main", git_dir=seed.path)
    await stand.enable()
    trust = await stand.client.put(
        "/api/v1/git/host-settings", json={"host": "127.0.0.1", "port": server.port, "ca_pem": tls.ca_pem}
    )
    assert trust.status_code == 200, trust.text
    credential = await stand.client.post(
        "/api/v1/git/credentials", json={"kind": "pat", "label": "Токен", "host": "127.0.0.1", "token": server.token}
    )
    assert credential.status_code == 201, credential.text
    created = await stand.client.post(
        f"{API}/workspaces",
        json={"kind": "git", "url": server.url("acme/packs.git"), "credential_id": credential.json()["id"]},
    )
    assert created.status_code == 202, created.text
    ws = await stand.settled(created.json()["id"])
    assert ws["state"] == "ready", ws
    ws_id = str(ws["id"])
    await _base_moved_under_local_edits(stand, bare, ws_id)
    _forget_base_blob(stand, ws_id)

    view = await stand.client.get(f"{API}/workspaces/{ws_id}/git")
    diff = await stand.client.get(f"{API}/workspaces/{ws_id}/git/diff")

    assert view.status_code == 200, view.text
    assert {c["path"]: c["status"] for c in view.json()["changed"]}[_DRAFT_TEX] == "modified"
    assert diff.status_code == 200, diff.text
    assert "-% theirs in base" in diff.json()["diff"]
    token = str(server.token)
    assert token not in view.text
    assert token not in diff.text
    store = _store(stand, ws_id)
    assert [p for p in store.rglob("*") if p.is_file() and token.encode() in p.read_bytes()] == []
