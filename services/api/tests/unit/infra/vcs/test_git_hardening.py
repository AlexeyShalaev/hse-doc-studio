from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from hse_doc_studio.core.enums import VcsChange, VcsCommitKind
from hse_doc_studio.core.vcs.constants import DEFAULT_VCS_EXCLUDE
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.core.vcs.errors import VcsInvalidRefError
from hse_doc_studio.infra.vcs.git_env import base_git_env, hardened_git_config
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService

from tests.factories import make_project

_GIT_AVAILABLE = shutil.which("git") is not None
pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(not _GIT_AVAILABLE, reason="git binary not available"),
]

_posix_only = pytest.mark.skipif(os.name != "posix", reason="canary scripts are shell scripts")


def _service() -> GitVcsService:
    return GitVcsService(author_name="Test Bot", author_email="bot@test.local")


def _init(tmp_path: Path) -> tuple[GitVcsService, object]:
    project = make_project(folder=tmp_path)
    svc = _service()
    (tmp_path / "vkr").mkdir()
    (tmp_path / "vkr" / "vkr.tex").write_text("v1\n", encoding="utf-8")
    svc.init(project, list(DEFAULT_VCS_EXCLUDE))
    return svc, project


# ── окружение ────────────────────────────────────────────────────────────────
def test__base_git_env__drops_secrets_and_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HSE_STUDIO__SECRETS__KEY", "topsecret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agent.sock")
    monkeypatch.setenv("GIT_TRACE", "1")
    monkeypatch.setenv("GIT_SSH_COMMAND", "evil")
    monkeypatch.setenv("GIT_EXEC_PATH", "/evil")
    monkeypatch.setenv("HOME", "/home/evil")

    env = base_git_env()

    assert "topsecret" not in env.values()
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "SSH_AUTH_SOCK",
        "GIT_TRACE",
        "GIT_SSH_COMMAND",
        "GIT_EXEC_PATH",
    ):
        assert name not in env
    assert not any(key.startswith("HSE_STUDIO__") for key in env)
    assert env.get("HOME") != "/home/evil"


def test__base_git_env__keeps_path_proxy_and_ca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.local:3128")
    monkeypatch.setenv("NO_PROXY", "localhost")
    monkeypatch.setenv("SSL_CERT_FILE", "/etc/ssl/corp.pem")
    monkeypatch.setenv("TZ", "Europe/Moscow")

    env = base_git_env()

    assert env["PATH"] == os.environ["PATH"]
    assert env["HTTPS_PROXY"] == "http://proxy.local:3128"
    assert env["NO_PROXY"] == "localhost"
    assert env["SSL_CERT_FILE"] == "/etc/ssl/corp.pem"
    assert env["TZ"] == "Europe/Moscow"


def test__base_git_env__fixes_git_behaviour() -> None:
    env = base_git_env()

    assert env["LC_ALL"] == "C"
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GCM_INTERACTIVE"] == "never"
    assert env["GIT_OPTIONAL_LOCKS"] == "0"
    config = Path(env["GIT_CONFIG_GLOBAL"])
    assert config.exists() is (env["GIT_CONFIG_GLOBAL"] != os.devnull)
    if config.is_file():
        assert config.read_text(encoding="utf-8") == ""


def test__hardened_git_config__is_pairs_of_dash_c() -> None:
    args = hardened_git_config()
    assert args[::2] == ["-c"] * (len(args) // 2)
    settings = dict(item.split("=", 1) for item in args[1::2])
    assert settings["core.fsmonitor"] == "false"
    assert settings["core.sshCommand"] == ""
    assert settings["credential.helper"] == ""
    assert settings["protocol.ext.allow"] == "never"
    hooks = Path(settings["core.hooksPath"])
    assert hooks.is_dir()
    assert not any(hooks.iterdir())


def test__service__passes_clean_env_to_git(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    svc, project = _init(tmp_path)
    monkeypatch.setenv("HSE_STUDIO__SECRETS__KEY", "topsecret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen: list[dict[str, str]] = []
    real_run = subprocess.run

    def spy(cmd, **kwargs):  # noqa: ANN001, ANN003, ANN202
        seen.append(dict(kwargs["env"]))
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    svc.status(project, VcsSettings())
    svc.run_bytes(project, ["rev-parse", "HEAD"])

    assert len(seen) >= 2
    for env in seen:
        assert "HSE_STUDIO__SECRETS__KEY" not in env
        assert "OPENAI_API_KEY" not in env


# ── чужое хранилище не исполняет код ─────────────────────────────────────────
def _plant_canaries(tmp_path: Path, git_dir: Path) -> Path:
    canary = tmp_path.parent / f"{tmp_path.name}-canary"
    script = (
        '#!/bin/sh\nprintf "%s " "$(basename "$0")" >> ' + f'"{canary}"\n'  # noqa: ISC003
    )
    hooks = git_dir / "hooks"
    hooks.mkdir(exist_ok=True)
    for name in ("pre-commit", "post-commit", "commit-msg", "post-checkout", "reference-transaction"):
        hook = hooks / name
        hook.write_text(script, encoding="utf-8")
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    fsmonitor = tmp_path / "fsmonitor-canary.sh"
    fsmonitor.write_text(script + "printf '\\0'\n", encoding="utf-8")
    fsmonitor.chmod(fsmonitor.stat().st_mode | stat.S_IXUSR)
    elsewhere = tmp_path / "elsewhere-hooks"
    elsewhere.mkdir()
    (elsewhere / "pre-commit").write_text(script, encoding="utf-8")
    (elsewhere / "pre-commit").chmod(0o755)
    with (git_dir / "config").open("a", encoding="utf-8") as fh:
        fh.write(
            f"[core]\n\tfsmonitor = {fsmonitor}\n\thooksPath = {elsewhere}\n\tsshCommand = {fsmonitor}\n"
            f"[credential]\n\thelper = !{fsmonitor}\n"
        )
    return canary


@_posix_only
def test__hostile_store_config__does_not_execute_canary(tmp_path: Path) -> None:
    svc, project = _init(tmp_path)
    canary = _plant_canaries(tmp_path, tmp_path / ".hse-studio" / "git")
    (tmp_path / "vkr" / "vkr.tex").write_text("v2\n", encoding="utf-8")

    svc.status(project, VcsSettings())
    commit = svc.commit(project, message="edit", kind=VcsCommitKind.manual)
    assert commit is not None
    svc.create_branch(project, VcsSettings(), name="draft", switch=True)
    svc.switch_branch(project, VcsSettings(), name="master")
    svc.diff(project, to_id=commit.id)
    svc.commit_detail(project, commit.id)

    assert not canary.exists(), canary.read_text(encoding="utf-8") if canary.exists() else ""


@_posix_only
def test__hostile_store_config__canary_runs_without_hardening(tmp_path: Path) -> None:
    """Контроль для теста выше: те же приманки срабатывают в голом git, значит тест что-то проверяет."""
    svc, project = _init(tmp_path)
    git_dir = tmp_path / ".hse-studio" / "git"
    canary = _plant_canaries(tmp_path, git_dir)
    (tmp_path / "vkr" / "vkr.tex").write_text("v2\n", encoding="utf-8")
    env = {
        "PATH": os.environ["PATH"],
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(tmp_path),
    }
    base = ["git", "--git-dir", str(git_dir), "--work-tree", str(tmp_path), "-c", "user.name=a", "-c", "user.email=a@b"]
    subprocess.run([*base, "add", "-A"], env=env, check=True, capture_output=True)
    subprocess.run([*base, "commit", "-m", "x"], env=env, check=True, capture_output=True)

    assert canary.exists()
    assert svc.is_initialized(project)


# ── имена веток, тегов и ревизий ─────────────────────────────────────────────
@pytest.mark.parametrize("name", ["-x", "--orphan", "a b", "a..b", "x.lock", "a~1", ""])
def test__branch_and_tag_names__are_validated_before_git(tmp_path: Path, name: str) -> None:
    svc, project = _init(tmp_path)
    with pytest.raises(VcsInvalidRefError):
        svc.create_branch(project, VcsSettings(), name=name)
    with pytest.raises(VcsInvalidRefError):
        svc.switch_branch(project, VcsSettings(), name=name)
    with pytest.raises(VcsInvalidRefError):
        svc.delete_branch(project, name=name)
    with pytest.raises(VcsInvalidRefError):
        svc.create_tag(project, name=name)
    with pytest.raises(VcsInvalidRefError):
        svc.delete_tag(project, name=name)
    assert [b.name for b in svc.list_branches(project)] == ["master"]
    assert svc.list_tags(project) == []


def test__revisions__cannot_smuggle_options(tmp_path: Path) -> None:
    svc, project = _init(tmp_path)
    marker = tmp_path / "pwned"
    bad = f"--output={marker}"
    with pytest.raises(VcsInvalidRefError):
        svc.create_branch(project, VcsSettings(), name="ok", from_commit=bad)
    with pytest.raises(VcsInvalidRefError):
        svc.create_tag(project, name="ok", commit_id=bad)
    with pytest.raises(VcsInvalidRefError):
        svc.commit_detail(project, bad)
    with pytest.raises(VcsInvalidRefError):
        svc.diff(project, from_id=bad, to_id="HEAD")
    assert not marker.exists()


def test__branch_named_like_a_file__switches_to_the_branch(tmp_path: Path) -> None:
    svc, project = _init(tmp_path)
    svc.create_branch(project, VcsSettings(), name="vkr", switch=False)
    svc.switch_branch(project, VcsSettings(), name="vkr")
    assert svc.status(project, VcsSettings()).current_branch == "vkr"
    assert (tmp_path / "vkr" / "vkr.tex").read_text(encoding="utf-8") == "v1\n"


def test__tag_and_branch_names__with_slash_and_unicode_still_work(tmp_path: Path) -> None:
    svc, project = _init(tmp_path)
    svc.create_branch(project, VcsSettings(), name="feature/введение", switch=False)
    svc.create_tag(project, name="v1.0-финал")
    assert {b.name for b in svc.list_branches(project)} == {"master", "feature/введение"}
    assert [t.name for t in svc.list_tags(project)] == ["v1.0-финал"]
    svc.delete_branch(project, name="feature/введение")
    svc.delete_tag(project, name="v1.0-финал")


# ── детали слияния ───────────────────────────────────────────────────────────
def test__commit_detail__merge_commit_lists_files_against_first_parent(tmp_path: Path) -> None:
    svc, project = _init(tmp_path)
    settings = VcsSettings()
    svc.create_branch(project, settings, name="side", switch=True)
    (tmp_path / "vkr" / "side.tex").write_text("from side\n", encoding="utf-8")
    (tmp_path / "vkr" / "vkr.tex").write_text("v1\nside line\n", encoding="utf-8")
    svc.commit(project, message="side edit", kind=VcsCommitKind.manual)
    svc.switch_branch(project, settings, name="master")
    (tmp_path / "vkr" / "main.tex").write_text("from master\n", encoding="utf-8")
    svc.commit(project, message="master edit", kind=VcsCommitKind.manual)
    svc._run(project, ["merge", "--no-ff", "-m", "merge side", "side"], check=True)  # noqa: SLF001

    head = svc.log(project, limit=1)[0]
    assert len(head.parents) == 2
    detail = svc.commit_detail(project, head.id)

    changes = {f.path: f.change for f in detail.files}
    assert changes == {"vkr/side.tex": VcsChange.added, "vkr/vkr.tex": VcsChange.modified}
    assert detail.commit.stats is not None
    assert detail.commit.stats.files == 2
    assert detail.commit.stats.insertions == 2
    assert detail.commit.stats.deletions == 0


def test__commit_detail__root_and_regular_commits_unchanged(tmp_path: Path) -> None:
    svc, project = _init(tmp_path)
    root = svc.log(project)[0]
    assert [(f.path, f.change) for f in svc.commit_detail(project, root.id).files] == [("vkr/vkr.tex", VcsChange.added)]

    (tmp_path / "vkr" / "vkr.tex").write_text("v2\n", encoding="utf-8")
    commit = svc.commit(project, message="edit", kind=VcsCommitKind.manual)
    assert commit is not None
    detail = svc.commit_detail(project, commit.id)
    assert [(f.path, f.change) for f in detail.files] == [("vkr/vkr.tex", VcsChange.modified)]
    assert (detail.commit.stats.insertions, detail.commit.stats.deletions) == (1, 1)


# ── force_paths ──────────────────────────────────────────────────────────────
def test__commit__force_paths_adds_ignored_pdf_only_when_asked(tmp_path: Path) -> None:
    svc, project = _init(tmp_path)
    frozen = tmp_path / ".hse-studio" / "frozen"
    frozen.mkdir(parents=True)
    (frozen / "doc.pdf").write_bytes(b"%PDF frozen")

    assert svc.commit(project, message="plain", kind=VcsCommitKind.manual) is None

    commit = svc.commit(
        project,
        message="sync",
        kind=VcsCommitKind.manual,
        force_paths=[".hse-studio/frozen", ".hse-studio/missing"],
    )
    assert commit is not None
    assert [f.path for f in svc.commit_detail(project, commit.id).files] == [".hse-studio/frozen/doc.pdf"]
