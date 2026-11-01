"""Приём push сервером Студии: перемотка вперёд, правила путей в хуке, снимок веб-правок, права токена."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.integration.api.git_remote.conftest import Live, Person, git

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]


def _clone(live: Live, project: str, token: str, name: str = "work") -> Path:
    git("clone", live.repo_url(project, token), name, cwd=live.tmp)
    return live.tmp / name


def _commit(work: Path, path: str, content: str, message: str = "edit") -> None:
    target = work / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    git("add", "-A", cwd=work)
    git("commit", "-q", "-m", message, cwd=work)


def _server_file(live: Live, owner: Person, project: str, path: str) -> str:
    response = live.call("GET", f"/api/v1/projects/{project}/files/{path}", owner)
    assert response.status_code == 200, response.text
    return response.text


def test__push__owner_fast_forward__applied_to_working_folder_and_audited(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    work = _clone(live, project, live.token(anna, ["git:read", "git:write"]))

    _commit(work, "notes/from-git.txt", "из git\n")
    pushed = git("push", "origin", "HEAD", cwd=work)

    assert "-> master" in pushed.stderr
    assert _server_file(live, anna, project, "notes/from-git.txt") == "из git\n"
    rows = live.sql("SELECT action, details FROM audit_log WHERE action = 'git.push' AND target = :t", t=project)
    assert rows
    assert rows[-1][1]["result"] == "accepted"


def test__push__not_fast_forward_new_branch_tag_and_delete__rejected(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    token = live.token(anna, ["git:read", "git:write"])
    first, second = _clone(live, project, token, "a"), _clone(live, project, token, "b")
    _commit(first, "a.txt", "a")
    git("push", "origin", "HEAD", cwd=first)
    _commit(second, "b.txt", "b")

    stale = git("push", "origin", "HEAD", cwd=second, check=False)
    assert stale.returncode != 0
    branch = git("push", "origin", "HEAD:refs/heads/feature", cwd=first, check=False)
    assert branch.returncode != 0
    assert "ref_forbidden" in branch.stderr
    git("tag", "v1", cwd=first)
    assert git("push", "origin", "v1", cwd=first, check=False).returncode != 0
    assert git("push", "origin", ":master", cwd=first, check=False).returncode != 0


def test__push__symlink_service_dir_and_newer_schema__rejected_with_text(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    work = _clone(live, project, live.token(anna, ["git:read", "git:write"]))
    os.symlink("/etc/passwd", work / "link.tex")
    git("add", "-A", cwd=work)
    git("commit", "-q", "-m", "symlink", cwd=work)

    rejected = git("push", "origin", "HEAD", cwd=work, check=False)
    assert rejected.returncode != 0
    assert "HSE Doc Studio" in rejected.stderr
    assert "[symlink]" in rejected.stderr

    git("reset", "-q", "--hard", "HEAD~1", cwd=work)
    state = json.loads((work / ".hse-studio" / "project.json").read_text(encoding="utf-8"))
    state["schema"] = {"version": 9, "read_compat": 9, "write_compat": 9, "written_by": "9.0.0"}
    _commit(work, ".hse-studio/project.json", json.dumps(state))
    newer = git("push", "origin", "HEAD", cwd=work, check=False)
    assert newer.returncode != 0
    assert "[schema_newer]" in newer.stderr


def test__push__team_author_outside_folder_rejected_own_folder_accepted(live: Live) -> None:
    anna, boris = live.person("anna"), live.person("boris")
    project = live.create_team_project(anna)
    live.add_member(project, boris, "editor", persona="boris")
    work = _clone(live, project, live.token(boris, ["git:read", "git:write"]))

    _commit(work, "anna/notes.tex", "чужое")
    outside = git("push", "origin", "HEAD", cwd=work, check=False)
    assert outside.returncode != 0
    assert "anna/notes.tex" in outside.stderr
    assert "[path_outside_scope]" in outside.stderr

    git("reset", "-q", "--hard", "HEAD~1", cwd=work)
    _commit(work, "boris/notes.tex", "своё")
    git("push", "origin", "HEAD", cwd=work)
    assert _server_file(live, anna, project, "boris/notes.tex") == "своё"


def test__push__web_edits_are_snapshotted_first_then_client_merges(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    work = _clone(live, project, live.token(anna, ["git:read", "git:write"]))
    saved = live.call("PUT", f"/api/v1/projects/{project}/files/notes/web.txt", anna, content=b"web")
    assert saved.status_code in {200, 204}, saved.text
    # Правка, ещё не попавшая в историю (частые правки сворачиваются в один снимок позже): прямо в папке проекта.
    (folder,) = [p for p in (live.tmp / "data").rglob(project) if (p / ".hse-studio" / "git").is_dir()]
    (folder / "notes" / "draft.txt").write_text("draft", encoding="utf-8")

    _commit(work, "notes/git.txt", "git")
    stale = git("push", "origin", "HEAD", cwd=work, check=False)
    assert stale.returncode != 0
    git("pull", "-q", "--no-rebase", "--no-edit", "origin", "master", cwd=work)
    git("push", "origin", "HEAD", cwd=work)

    assert _server_file(live, anna, project, "notes/web.txt") == "web"
    assert _server_file(live, anna, project, "notes/git.txt") == "git"
    assert (work / "notes" / "draft.txt").read_text(encoding="utf-8") == "draft"
    log = git("log", "--format=%an %s", "-5", cwd=work).stdout
    assert "Правки в браузере перед приёмом push" in log


def test__push__read_only_token_and_reviewer__forbidden(live: Live) -> None:
    anna, petr = live.person("anna"), live.person("petr")
    project = live.create_project(anna)
    live.add_member(project, petr, "reviewer")
    reader_token = live.token(anna, ["git:read"])
    work = _clone(live, project, reader_token)
    _commit(work, "x.txt", "x")

    read_only = git("push", "origin", "HEAD", cwd=work, check=False)
    assert read_only.returncode != 0
    reviewer = git(
        "push", live.repo_url(project, live.token(petr, ["git:read", "git:write"])), "HEAD", cwd=work, check=False
    )
    assert reviewer.returncode != 0
