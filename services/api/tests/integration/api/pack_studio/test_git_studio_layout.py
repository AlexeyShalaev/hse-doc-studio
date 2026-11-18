"""Студия шаблонов: частичный клон репозитория с раскладкой самой Студии (официальные паки).

В корне репозитория лежат `.gitignore` и `.gitattributes` с `* text=auto eol=lf`, паки в `packs/`. Разреженное дерево
берёт только `packs/`, поэтому корневые файлы правил остаются skip-worktree, а их блобы выборка `blob:none` не
приносит. `git status --untracked-files=all`, `add -A`, `ls-files --others --exclude-standard` и `clean` читают
правила игнорирования для путей под `packs/` из блоба `.gitignore` в индексе. Локальный git (`GIT_ALLOW_PROTOCOL=none`)
подгрузить его не мог, и `GET .../git` свежего пространства отвечал `workspace_git_failed`.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tests.fixtures.git_remote import BareRemote, GitHttpServer, run_git, seed_remote
from tests.fixtures.tls import make_ca_signed
from tests.integration.api.pack_studio.conftest import API, DRAFT_DIR, TEMPLATE_DIR, Stand
from tests.integration.api.pack_studio.test_git_workspace import _git_workspace, _remote, _store

_PROFILE = {"name": "Анна Иванова", "email": "anna@example.org"}
_DRAFT_TEX = f"{DRAFT_DIR}/files/report/main.tex"
_NOTES = f"{TEMPLATE_DIR}/notes.md"
# Как в корне репозитория Студии: нормализация переносов и бинарные ресурсы паков.
_GITATTRIBUTES = "* text=auto eol=lf\n*.bat text eol=crlf\n*.pptx binary\n*.docx binary\n*.pdf binary\n"
_GITIGNORE = "__pycache__/\n*.pyc\n.venv/\nnode_modules/\n*.log\n"


def _studio_remote(root: Path) -> BareRemote:
    remote = _remote(root)
    seed_remote(
        remote,
        {".gitattributes": _GITATTRIBUTES, ".gitignore": _GITIGNORE, "docs/.gitignore": "site/\n"},
        message="studio layout",
    )
    return remote


async def _ready(stand: Stand, remote: BareRemote) -> str:
    resp = await stand.client.put("/api/v1/profile", json=_PROFILE)
    assert resp.status_code == 200, resp.text
    ws = await _git_workspace(stand, remote)
    assert ws["state"] == "ready", ws
    return str(ws["id"])


def _git_url(ws_id: str, tail: str = "") -> str:
    return f"{API}/workspaces/{ws_id}/git{tail}"


async def _git(stand: Stand, ws_id: str) -> dict[str, Any]:
    resp = await stand.client.get(_git_url(ws_id))
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


async def _put(stand: Stand, ws_id: str, path: str, content: bytes) -> None:
    resp = await stand.client.put(stand.file_url(ws_id, path), content=content)
    assert resp.status_code == 200, resp.text


async def _refresh(stand: Stand, ws_id: str) -> dict[str, Any]:
    started = await stand.client.post(f"{API}/workspaces/{ws_id}/refresh")
    assert started.status_code == 202, started.text
    return await stand.settled(ws_id)


def _has_blob(stand: Stand, ws_id: str, spec: str) -> bool:
    """Блоб есть в хранилище; `--missing=print` ничего не подгружает."""
    git_dir = _store(stand, ws_id) / "git"
    oid = run_git("rev-parse", spec, git_dir=git_dir)
    tip = spec.split(":", 1)[0]
    listed = run_git("rev-list", "--objects", "--missing=print", "--no-walk", tip, git_dir=git_dir)
    return f"?{oid}" not in listed.splitlines()


def _drop_pack_with(stand: Stand, ws_id: str, spec: str) -> None:
    """Хранилище как у пространства до правки: пачка догруженных блобов, в которой пришёл этот, убирается целиком.

    Пачки самих выборок (коммиты и деревья) не трогаются: убирается только пачка, где одни блобы."""
    git_dir = _store(stand, ws_id) / "git"
    oid = run_git("rev-parse", spec, git_dir=git_dir)
    dropped = 0
    for idx in (git_dir / "objects" / "pack").glob("*.idx"):
        rows = [line.split() for line in run_git("verify-pack", "-v", str(idx)).splitlines()]
        objects = {row[0]: row[1] for row in rows if len(row) >= 3 and len(row[0]) == len(oid)}  # noqa: PLR2004
        if oid in objects and set(objects.values()) == {"blob"}:
            for suffix in (".pack", ".idx", ".promisor", ".rev"):
                idx.with_suffix(suffix).unlink(missing_ok=True)
            dropped += 1
    assert dropped == 1, f"пачка догруженных блобов с {spec} не найдена"


async def test__fresh_clone_of_the_studio_layout__git_view_works(stand: Stand) -> None:
    remote = _studio_remote(stand.root)
    ws_id = await _ready(stand, remote)

    git = await _git(stand, ws_id)

    assert git["head_sha"] == remote.head("main")
    assert git["dirty"] is False
    assert git["changed"] == []
    # Корневые правила вне разреженного дерева, но их блобы догружены при клоне: локальному git они нужны.
    tree = _store(stand, ws_id) / "tree"
    assert sorted(p.name for p in tree.iterdir()) == ["packs"]
    assert _has_blob(stand, ws_id, "HEAD:.gitignore")
    assert _has_blob(stand, ws_id, "HEAD:.gitattributes")
    # Остальное вне папки паков по-прежнему не скачано.
    assert not _has_blob(stand, ws_id, "HEAD:services/api/big.txt")
    assert not _has_blob(stand, ws_id, "HEAD:docs/.gitignore")


async def test__touched_file_without_edits__is_not_a_change(stand: Stand) -> None:
    ws_id = await _ready(stand, _studio_remote(stand.root))
    path = _store(stand, ws_id) / "tree" / "packs" / _DRAFT_TEX
    later = path.stat().st_mtime + 120
    os.utime(path, (later, later))

    git = await _git(stand, ws_id)

    assert git["dirty"] is False
    assert git["changed"] == []


async def test__edit_refresh_commit_diff_merge__base_moved_its_rules(stand: Stand) -> None:
    remote = _studio_remote(stand.root)
    ws_id = await _ready(stand, remote)
    await _put(stand, ws_id, _DRAFT_TEX, b"\\documentclass{article}\r\n% mine\r\n")
    seed_remote(
        remote,
        {
            ".gitignore": _GITIGNORE + "*.tmp\n",
            ".gitattributes": _GITATTRIBUTES + "*.zip binary\n",
            f"packs/{_NOTES}": "новое в базе\n",
        },
        message="base moved its rules",
    )

    refreshed = await _refresh(stand, ws_id)
    view = await _git(stand, ws_id)
    committed = await stand.client.post(_git_url(ws_id, "/commit"), json={})
    diff = await stand.client.get(_git_url(ws_id, "/diff"))
    merged = await stand.client.post(_git_url(ws_id, "/merge-base"))
    after = await _git(stand, ws_id)

    assert refreshed["error"] is None, refreshed
    assert {c["path"]: c["status"] for c in view["uncommitted"]} == {_DRAFT_TEX: "modified"}
    assert (view["ahead"], view["behind"]) == (0, 1)
    # «Обновить» догружает и блобы базы под папкой паков: паки маленькие.
    assert _has_blob(stand, ws_id, f"refs/remotes/origin/main:packs/{_NOTES}")
    assert committed.status_code == 200, committed.text
    assert committed.json()["committed"] is True
    assert diff.status_code == 200, diff.text
    # text=auto eol=lf: в коммит файл ушёл с LF.
    assert "+% mine" in diff.json()["diff"]
    assert "\r" not in diff.json()["diff"]
    assert merged.status_code == 200, merged.text
    assert after["behind"] == 0
    assert after["dirty"] is False
    assert _has_blob(stand, ws_id, "HEAD:.gitignore")


async def test__switch_to_a_server_branch_that_moved_the_rules(stand: Stand) -> None:
    remote = _studio_remote(stand.root)
    ws_id = await _ready(stand, remote)
    base = remote.head("main")
    assert base is not None
    # Чужая ветка от базы правит корневые правила; сама база остаётся на месте.
    seed_remote(remote, {".gitignore": "*.bak\n", f"packs/{_NOTES}": "ветка\n"}, message="other branch")
    run_git("push", "--quiet", remote.url, "refs/heads/main:refs/heads/someone/else", git_dir=remote.path)
    remote.git("update-ref", "refs/heads/main", base)

    switched = await stand.client.post(_git_url(ws_id, "/branch"), json={"name": "someone/else"})
    await _put(stand, ws_id, f"{DRAFT_DIR}/files/report/new.tex", b"new\n")
    view = await _git(stand, ws_id)

    assert switched.status_code == 200, switched.text
    assert switched.json()["branch"] == "someone/else"
    assert {c["path"]: c["status"] for c in view["uncommitted"]} == {f"{DRAFT_DIR}/files/report/new.tex": "added"}


async def test__start_over__base_moved_the_rules__clean_reads_them(stand: Stand) -> None:
    remote = _studio_remote(stand.root)
    ws_id = await _ready(stand, remote)
    await _put(stand, ws_id, f"{DRAFT_DIR}/files/report/extra.tex", b"extra\n")
    seed_remote(remote, {".gitignore": _GITIGNORE + "*.tmp\n"}, message="rules moved")

    resp = await stand.client.post(_git_url(ws_id, "/start-over"), json={"discard": True})

    assert resp.status_code == 200, resp.text
    assert resp.json()["dirty"] is False
    assert resp.json()["head_sha"] == remote.head("main")
    assert not (_store(stand, ws_id) / "tree" / "packs" / DRAFT_DIR / "files" / "report" / "extra.tex").exists()


async def test__workspace_created_before_the_fix__heals_itself_on_the_git_view(stand: Stand) -> None:
    """Хранилище без блоба корневого `.gitignore`, как у пространств на 0.34.0: пересоздавать не нужно."""
    ws_id = await _ready(stand, _studio_remote(stand.root))
    _drop_pack_with(stand, ws_id, "HEAD:.gitignore")
    assert not _has_blob(stand, ws_id, "HEAD:.gitignore")

    git = await _git(stand, ws_id)

    assert git["dirty"] is False
    assert _has_blob(stand, ws_id, "HEAD:.gitignore")


async def test__broken_store__answers_with_a_safe_hint(stand: Stand) -> None:
    """Сбой, который догрузка не лечит: код пространства и подсказка без путей сервера."""
    ws_id = await _ready(stand, _studio_remote(stand.root))
    store = _store(stand, ws_id)
    (store / "git" / "HEAD").write_text("ref: refs/heads/../broken\n", encoding="utf-8")

    resp = await stand.client.get(_git_url(ws_id))

    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["code"] == "workspace_git_failed"
    assert body["hint"].startswith("git ")
    assert str(store) not in body["hint"]
    assert str(stand.root) not in resp.text


async def test__https_with_token__fresh_clone_and_refresh_of_the_studio_layout(
    stand: Stand, http_git_server_factory: Callable[..., GitHttpServer], tmp_path: Path
) -> None:
    """То же через https с токеном: догрузка идёт с доступом пространства, токен не оседает ни в ответах, ни в
    хранилище."""
    tls = make_ca_signed(tmp_path / "tls")
    server = http_git_server_factory(tls=tls)
    bare = server.create_repo("acme/packs.git")
    bare.git("config", "uploadpack.allowFilter", "true")
    seed = _studio_remote(stand.root / "seed")
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

    fresh = await stand.client.get(_git_url(ws_id))
    _drop_pack_with(stand, ws_id, "HEAD:.gitignore")
    healed = await stand.client.get(_git_url(ws_id))
    await _put(stand, ws_id, _DRAFT_TEX, b"\\documentclass{article}\n% mine\n")
    seed_remote(bare, {".gitignore": _GITIGNORE + "*.tmp\n", f"packs/{_NOTES}": "новое\n"}, message="moved")
    refreshed = await _refresh(stand, ws_id)
    moved = await stand.client.get(_git_url(ws_id))

    version = run_git("--version")  # при сбое видно, на какой версии git он случился (прод: 2.39)
    assert fresh.status_code == 200, f"{version}: {fresh.text}"
    assert healed.status_code == 200, f"{version}: {healed.text}"
    assert refreshed["error"] is None, f"{version}: {refreshed}"
    assert moved.status_code == 200, f"{version}: {moved.text}"
    assert moved.json()["behind"] == 1
    token = str(server.token)
    for resp in (fresh, healed, moved):
        assert token not in resp.text
    store = _store(stand, ws_id)
    assert [p for p in store.rglob("*") if p.is_file() and token.encode() in p.read_bytes()] == []
    config = (store / "git" / "config").read_text(encoding="utf-8")
    assert "extraheader" not in config
    assert "@" not in config
