"""Студия шаблонов, срез T6: ветка, коммит от профиля, «Предложить изменения», слияние базы, начать заново.

Репозиторий паков это голый репозиторий по file:// (провайдер `other`: push без PR). git настоящий, сеть не нужна.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.fixtures.git_remote import BareRemote, run_git, seed_remote
from tests.integration.api.pack_studio.conftest import API, DRAFT_DIR, RELEASED_DIR, TEMPLATE_DIR, Stand
from tests.integration.api.pack_studio.test_git_workspace import _git_workspace, _remote, _store

_PROFILE = {"name": "Анна Иванова", "email": "anna@example.org"}
_DRAFT_TEX = f"{DRAFT_DIR}/files/report/main.tex"


async def _ready(stand: Stand) -> tuple[BareRemote, str]:
    remote = _remote(stand.root)
    resp = await stand.client.put("/api/v1/profile", json=_PROFILE)
    assert resp.status_code == 200, resp.text
    ws = await _git_workspace(stand, remote)
    assert ws["state"] == "ready", ws
    return remote, str(ws["id"])


def _git_url(ws_id: str, tail: str = "") -> str:
    return f"{API}/workspaces/{ws_id}/git{tail}"


async def _git(stand: Stand, ws_id: str) -> dict[str, Any]:
    resp = await stand.client.get(_git_url(ws_id))
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


async def _put(stand: Stand, ws_id: str, path: str, content: bytes) -> None:
    resp = await stand.client.put(stand.file_url(ws_id, path), content=content)
    assert resp.status_code == 200, resp.text


async def test__git_view__fresh_clone__detached_and_clean(stand: Stand) -> None:
    remote, ws_id = await _ready(stand)

    git = await _git(stand, ws_id)

    assert git["branch"] is None
    assert git["head_sha"] == remote.head("main")
    assert git["dirty"] is False
    assert git["changed"] == []
    assert (git["ahead"], git["behind"]) == (0, 0)
    assert git["provider"] == "other"
    assert git["workspace"]["service_access"] is False


async def test__commit__creates_work_branch_and_signs_with_the_profile(stand: Stand) -> None:
    _, ws_id = await _ready(stand)
    await _put(stand, ws_id, _DRAFT_TEX, b"\\documentclass{article}\n% edit\n")
    await _put(stand, ws_id, f"{DRAFT_DIR}/files/report/new.tex", b"new\n")

    before = await _git(stand, ws_id)
    done = await stand.client.post(_git_url(ws_id, "/commit"), json={})
    again = await stand.client.post(_git_url(ws_id, "/commit"), json={})

    assert {c["path"]: c["status"] for c in before["uncommitted"]} == {
        _DRAFT_TEX: "modified",
        f"{DRAFT_DIR}/files/report/new.tex": "added",
    }
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["committed"] is True
    assert body["git"]["branch"] == "pack-studio/anna/demo-report-2026.1.1"
    assert body["git"]["workspace"]["work_branch"] == body["git"]["branch"]
    assert body["git"]["dirty"] is False
    assert body["git"]["ahead"] == 1
    git_dir = _store(stand, ws_id) / "git"
    assert run_git("log", "-1", "--format=%an <%ae>|%cn <%ce>|%s", git_dir=git_dir) == (
        "Анна Иванова <anna@example.org>|Анна Иванова <anna@example.org>|fix(packs): demo/report 2026.1.1"
    )
    assert again.json()["committed"] is False
    assert again.json()["sha"] is None


async def test__propose__pushes_the_work_branch_without_a_pull_request_on_a_plain_remote(stand: Stand) -> None:
    remote, ws_id = await _ready(stand)
    await _put(stand, ws_id, _DRAFT_TEX, b"\\documentclass{article}\n% proposed\n")

    resp = await stand.client.post(_git_url(ws_id, "/propose"), json={"message": "fix(packs): правка черновика"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    branch = body["git"]["branch"]
    assert body["pull_request"] is None
    assert body["compare_url"] is None
    assert body["pr_error"] is None
    assert body["pushed_to"] == remote.url
    assert remote.head(branch) == body["pushed_sha"]
    assert remote.git("log", "-1", "--format=%an|%s", f"refs/heads/{branch}") == (
        "Анна Иванова|fix(packs): правка черновика"
    )
    assert body["checks"]["errors"] == 0
    assert [c["path"] for c in body["checks"]["classes"]] == [DRAFT_DIR]
    assert body["git"]["workspace"]["pushed_sha"] == body["pushed_sha"]
    checks = (await stand.client.get(_git_url(ws_id, "/checks"))).json()
    assert checks["available"] is False
    assert checks["reason"] == "ci_status_unavailable"


async def test__propose__nothing_changed__is_refused(stand: Stand) -> None:
    _, ws_id = await _ready(stand)

    resp = await stand.client.post(_git_url(ws_id, "/propose"), json={})

    assert resp.status_code == 409
    assert resp.json()["code"] == "nothing_to_propose"


async def test__propose__pack_check_fails__nothing_is_pushed(stand: Stand) -> None:
    remote, ws_id = await _ready(stand)
    await _put(stand, ws_id, f"{DRAFT_DIR}/version.yaml", b'id: "2026.1.1"\nstatus: beta\nlangs: [xx]\n')
    refs_before = remote.git("for-each-ref", "--format=%(refname)")

    resp = await stand.client.post(_git_url(ws_id, "/propose"), json={})

    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["code"] == "lint_failed"
    assert body["errors"] >= 1
    assert body["findings"]
    assert all(f["severity"] == "error" for f in body["findings"])
    assert remote.git("for-each-ref", "--format=%(refname)") == refs_before


async def test__propose__released_version_edited_on_disk__is_refused(stand: Stand) -> None:
    _, ws_id = await _ready(stand)
    # Правка мимо интерфейса (файлы API выпущенную версию не пишут): `releases check` перед push её ловит.
    tree = _store(stand, ws_id) / "tree" / "packs"
    (tree / RELEASED_DIR / "files/report/main.tex").write_text("tampered\n", encoding="utf-8")

    resp = await stand.client.post(_git_url(ws_id, "/propose"), json={})

    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "lint_failed"
    assert any(f["check"] == "releases" for f in resp.json()["findings"])


async def test__branch__named_then_switch_needs_a_clean_tree_and_fetches_remote_branches(stand: Stand) -> None:
    remote, ws_id = await _ready(stand)
    seed_remote(remote, {"packs/demo/notes.md": "из чужой ветки\n"}, branch="main", message="base move")
    run_git("push", "--quiet", remote.url, "refs/heads/main:refs/heads/someone/else", git_dir=remote.path)

    named = await stand.client.post(_git_url(ws_id, "/branch"), json={"name": "pack-studio/anna/presets"})
    await _put(stand, ws_id, _DRAFT_TEX, b"dirty\n")
    blocked = await stand.client.post(_git_url(ws_id, "/branch"), json={"name": "someone/else"})
    await stand.client.post(_git_url(ws_id, "/commit"), json={"message": "wip"})
    switched = await stand.client.post(_git_url(ws_id, "/branch"), json={"name": "someone/else"})
    bad = await stand.client.post(_git_url(ws_id, "/branch"), json={"name": "bad..name"})
    base = await stand.client.post(_git_url(ws_id, "/branch"), json={"name": "main"})

    assert named.status_code == 200, named.text
    assert named.json()["branch"] == "pack-studio/anna/presets"
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "workspace_dirty"
    assert switched.status_code == 200, switched.text
    assert switched.json()["branch"] == "someone/else"
    assert switched.json()["head_sha"] == remote.head("someone/else")
    assert (_store(stand, ws_id) / "tree" / "packs" / "demo" / "notes.md").is_file()
    assert bad.status_code == 400
    assert bad.json()["code"] == "branch_name_invalid"
    assert base.json()["code"] == "branch_name_invalid"


async def test__merge_base__brings_new_base_commits_into_the_work_branch(stand: Stand) -> None:
    remote, ws_id = await _ready(stand)
    await _put(stand, ws_id, _DRAFT_TEX, b"\\documentclass{article}\n% mine\n")
    await stand.client.post(_git_url(ws_id, "/commit"), json={})
    seed_remote(remote, {"packs/demo/notes.md": "новое в базе\n"}, message="base moved")

    merged = await stand.client.post(_git_url(ws_id, "/merge-base"))

    assert merged.status_code == 200, merged.text
    body = merged.json()
    assert body["behind"] == 0
    assert body["ahead"] == 2  # noqa: PLR2004 — свой коммит и слияние
    assert body["workspace"]["base_sha"] == remote.head("main")
    tree = _store(stand, ws_id) / "tree" / "packs"
    assert (tree / "demo" / "notes.md").read_text(encoding="utf-8") == "новое в базе\n"
    assert (tree / _DRAFT_TEX).read_bytes() == b"\\documentclass{article}\n% mine\n"


async def test__merge_base__conflict__is_cancelled_and_names_the_file(stand: Stand) -> None:
    remote, ws_id = await _ready(stand)
    await _put(stand, ws_id, _DRAFT_TEX, b"\\documentclass{article}\n% mine\n")
    commit = (await stand.client.post(_git_url(ws_id, "/commit"), json={})).json()
    seed_remote(remote, {f"packs/{_DRAFT_TEX}": "\\documentclass{article}\n% theirs\n"}, message="conflict")

    resp = await stand.client.post(_git_url(ws_id, "/merge-base"))
    after = await _git(stand, ws_id)

    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "merge_conflict"
    assert resp.json()["files"] == [_DRAFT_TEX]
    assert after["head_sha"] == commit["sha"]
    assert after["dirty"] is False
    assert (_store(stand, ws_id) / "tree" / "packs" / _DRAFT_TEX).read_bytes() == b"\\documentclass{article}\n% mine\n"


async def test__merge_base__dirty_tree__asks_to_commit_first(stand: Stand) -> None:
    _, ws_id = await _ready(stand)
    await _put(stand, ws_id, _DRAFT_TEX, b"dirty\n")

    resp = await stand.client.post(_git_url(ws_id, "/merge-base"))

    assert resp.status_code == 409
    assert resp.json()["code"] == "workspace_dirty"


async def test__start_over__needs_discard_for_edits_and_returns_to_the_base(stand: Stand) -> None:
    remote, ws_id = await _ready(stand)
    await _put(stand, ws_id, _DRAFT_TEX, b"\\documentclass{article}\n% proposed\n")
    await stand.client.post(_git_url(ws_id, "/propose"), json={})
    await _put(stand, ws_id, f"{DRAFT_DIR}/files/report/extra.tex", b"extra\n")

    kept = await stand.client.post(_git_url(ws_id, "/start-over"), json={})
    reset = await stand.client.post(_git_url(ws_id, "/start-over"), json={"discard": True})

    assert kept.status_code == 409
    assert kept.json()["code"] == "workspace_dirty"
    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert body["branch"] is None
    assert body["head_sha"] == remote.head("main")
    assert body["dirty"] is False
    assert body["workspace"]["work_branch"] is None
    assert body["workspace"]["pushed_sha"] is None
    tree = _store(stand, ws_id) / "tree" / "packs"
    assert not (tree / DRAFT_DIR / "files/report/extra.tex").exists()
    assert (tree / _DRAFT_TEX).read_bytes() == b"\\documentclass{article}\n% draft\n"


async def test__diff__shows_commits_and_new_files_against_the_base(stand: Stand) -> None:
    _, ws_id = await _ready(stand)
    await _put(stand, ws_id, _DRAFT_TEX, b"\\documentclass{article}\n% changed line\n")
    await stand.client.post(_git_url(ws_id, "/commit"), json={})
    await _put(stand, ws_id, f"{TEMPLATE_DIR}/notes.md", b"brand new\n")

    resp = await stand.client.get(_git_url(ws_id, "/diff"))

    assert resp.status_code == 200, resp.text
    diff = resp.json()["diff"]
    assert "+% changed line" in diff
    assert "+brand new" in diff
    assert resp.json()["truncated"] is False


async def test__checks__before_any_push__report_none(stand: Stand) -> None:
    _, ws_id = await _ready(stand)

    resp = await stand.client.get(_git_url(ws_id, "/checks"))

    assert resp.status_code == 200
    assert resp.json() == {
        "state": "none",
        "sha": None,
        "checks": [],
        "available": True,
        "reason": None,
        "web_url": None,
    }


async def test__git_routes__folder_workspace__is_not_a_git_workspace(stand: Stand, tmp_path: Path) -> None:
    from tests.integration.api.pack_studio.conftest import write_pack  # noqa: PLC0415

    await stand.enable()
    ws = await stand.folder_workspace(write_pack(tmp_path / "folder"))

    resp = await stand.client.get(_git_url(str(ws["id"])))

    assert resp.status_code == 409
    assert resp.json()["code"] == "not_a_git_workspace"
