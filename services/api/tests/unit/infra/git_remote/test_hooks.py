"""Хуки приёма на настоящем git: локальный push в стор вида `<папка>/.hse-studio/git` с нашими `-c` и хуками."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from hse_doc_studio.core.access.entities import Grant, ProjectAcl, Role
from hse_doc_studio.core.git_remote.entities import PushViolation, PushViolationCode
from hse_doc_studio.core.git_remote.push_policy import push_policy_for
from hse_doc_studio.infra.git_remote.pre_receive import MAX_LINES, render
from hse_doc_studio.infra.git_remote.push_runtime import GitPushRuntime, hooks_dir

_ENV = {
    "PATH": os.environ.get("PATH", ""),
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "LC_ALL": "C",
    "GIT_AUTHOR_NAME": "T",
    "GIT_AUTHOR_EMAIL": "t@example.org",
    "GIT_COMMITTER_NAME": "T",
    "GIT_COMMITTER_EMAIL": "t@example.org",
}


def _git(
    *args: str, cwd: Path, env: dict[str, str] | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        env={**_ENV, "HOME": str(cwd), **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


@pytest.fixture
def store(tmp_path: Path) -> tuple[Path, Path]:
    folder = tmp_path / "project"
    git_dir = folder / ".hse-studio" / "git"
    git_dir.parent.mkdir(parents=True)
    store_args = ["--git-dir", str(git_dir), "--work-tree", str(folder)]
    _git(*store_args, "init", "-q", "-b", "master", cwd=tmp_path)
    (git_dir / "info").mkdir(exist_ok=True)
    (git_dir / "info" / "exclude").write_text(".hse-studio/git/\n", encoding="utf-8")
    for path in ("ivanov/main.tex", "petrov/main.tex", "shared/intro.tex"):
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_text(path, encoding="utf-8")
    _git(*store_args, "add", "-A", cwd=tmp_path)
    _git(*store_args, "commit", "-q", "-m", "init", cwd=tmp_path)
    _git("clone", "-q", str(git_dir), "work", cwd=tmp_path)
    return folder, tmp_path / "work"


def _push(
    folder: Path, work: Path, grant: Grant, *args: str, team: bool = True, python: str | None = None
) -> subprocess.CompletedProcess[str]:
    runtime = GitPushRuntime()
    git_dir = folder / ".hse-studio" / "git"
    policy = push_policy_for(
        ProjectAcl(project_id="p", team=team), grant, branch="master", max_blob_bytes=1000, compat=(1, 1)
    )
    session = runtime.prepare(
        policy, git_dir=git_dir, work_tree=folder, actor_id="u1", lang="en", max_input_bytes=10_000_000
    )
    try:
        receive = " ".join(["git", *session.extra_config, "receive-pack"])
        env = dict(session.extra_env)
        if python is not None:
            env["HSE_PYTHON"] = python
        return _git("push", f"--receive-pack={receive}", "origin", *args, cwd=work, env=env, check=False)
    finally:
        runtime.cleanup(session)
        assert not session.policy_file.exists()


def _commit(work: Path, path: str, content: str = "x") -> None:
    (work / path).parent.mkdir(parents=True, exist_ok=True)
    (work / path).write_text(content, encoding="utf-8")
    _git("add", "-A", cwd=work)
    _git("commit", "-q", "-m", path, cwd=work)


def test__push__own_folder__accepted_and_checked_out(store: tuple[Path, Path]) -> None:
    folder, work = store
    _commit(work, "ivanov/chapter.tex", "глава")

    result = _push(folder, work, Grant(Role.editor, persona_slug="ivanov"), "HEAD:master")

    assert result.returncode == 0, result.stderr
    assert (folder / "ivanov" / "chapter.tex").read_text(encoding="utf-8") == "глава"


def test__push__several_violations__listed_and_nothing_applied(store: tuple[Path, Path]) -> None:
    folder, work = store
    _commit(work, "petrov/a.tex")
    _commit(work, "big.bin", "x" * 2000)
    os.symlink("/etc/passwd", work / "ivanov" / "link")
    _commit(work, "ivanov/x.tex")

    result = _push(folder, work, Grant(Role.editor, persona_slug="ivanov"), "HEAD:master")

    assert result.returncode != 0
    assert "HSE Doc Studio: push rejected (3 problems)" in result.stderr
    assert "petrov/a.tex" in result.stderr
    assert "[path_outside_scope]" in result.stderr
    assert "[symlink]" in result.stderr
    assert not (folder / "petrov" / "a.tex").exists()


def test__push__interpreter_without_package_on_sys_path__hooks_still_run(store: tuple[Path, Path]) -> None:
    """Как в образе: пакет виден интерпретатору только через PYTHONPATH=/app, а хук запускает python с -I."""
    folder, work = store
    bare = getattr(sys, "_base_executable", None) or sys.executable
    probe = subprocess.run(  # noqa: S603
        [bare, "-I", "-c", "import hse_doc_studio"], capture_output=True, check=False
    )
    if probe.returncode == 0:
        pytest.skip("базовый интерпретатор видит пакет сам: условие образа не воспроизвести")
    _commit(work, "ivanov/chapter.tex", "глава")
    _commit(work, "petrov/a.tex")

    refused = _push(folder, work, Grant(Role.editor, persona_slug="ivanov"), "HEAD:master", python=bare)

    assert "No module named" not in refused.stderr
    assert "[path_outside_scope]" in refused.stderr

    _git("reset", "-q", "--hard", "HEAD~1", cwd=work)
    accepted = _push(folder, work, Grant(Role.editor, persona_slug="ivanov"), "HEAD:master", python=bare)

    assert accepted.returncode == 0, accepted.stderr
    assert (folder / "ivanov" / "chapter.tex").read_text(encoding="utf-8") == "глава"


def test__push__hooks_dir_wiped_by_tmp_cleaner__recreated_and_policy_still_enforced(
    store: tuple[Path, Path],
) -> None:
    """Каталог хуков во временной папке чистят (tmpfiles): без проверки git принял бы push вовсе без pre-receive."""
    folder, work = store
    shutil.rmtree(hooks_dir())
    _commit(work, "petrov/a.tex")

    result = _push(folder, work, Grant(Role.editor, persona_slug="ivanov"), "HEAD:master")

    assert result.returncode != 0
    assert "[path_outside_scope]" in result.stderr
    assert not (folder / "petrov" / "a.tex").exists()


def test__push__owner_large_file_and_new_branch_refused(store: tuple[Path, Path]) -> None:
    folder, work = store
    _commit(work, "big.bin", "x" * 2000)

    large = _push(folder, work, Grant(Role.owner), "HEAD:master")
    branch = _push(folder, work, Grant(Role.owner), "HEAD:refs/heads/other")
    two = _push(folder, work, Grant(Role.owner), "HEAD:master", "HEAD:refs/heads/other")

    assert "[large_file]" in large.stderr
    assert "[ref_forbidden]" in branch.stderr
    assert "[ref_forbidden]" in two.stderr


def test__push__dirty_folder_conflict__rejected_by_checkout_hook(store: tuple[Path, Path]) -> None:
    folder, work = store
    (folder / "ivanov" / "main.tex").write_text("правка в браузере", encoding="utf-8")
    _commit(work, "ivanov/main.tex", "правка из git")

    result = _push(folder, work, Grant(Role.owner), "HEAD:master")

    assert result.returncode != 0
    assert (folder / "ivanov" / "main.tex").read_text(encoding="utf-8") == "правка в браузере"


def test__render__caps_lines_and_localizes() -> None:
    many = [PushViolation(PushViolationCode.unsafe_path, f"p{i}") for i in range(MAX_LINES + 5)]

    lines = render(many, "ru")

    assert lines[0] == f"HSE Doc Studio: отправка отклонена ({MAX_LINES + 5})"
    assert lines[-1] == "… и ещё 5"
    assert len(lines) == MAX_LINES + 2
