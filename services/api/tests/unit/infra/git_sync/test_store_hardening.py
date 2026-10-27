from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.enums import VcsCommitKind
from hse_doc_studio.core.git_sync.entities import StoreFindingKind, StoreRemoteConfig
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.infra.git_sync.store_hardening import GitStoreGuard

from tests.unit.infra.git_sync.conftest import Repo

pytestmark = pytest.mark.unit

_posix_only = pytest.mark.skipif(os.name != "posix", reason="приманки — shell-скрипты")
_SECRET_URL = "https://oauth2:ghp_SECRETSECRETSECRETSECRET1234@evil.example/o/r.git"


def _config(repo: Repo) -> Path:
    return repo.folder / ".hse-studio" / "git" / "config"


def _append(repo: Repo, text: str) -> None:
    with _config(repo).open("a", encoding="utf-8") as fh:
        fh.write(text)


def _subjects(repo: Repo) -> set[tuple[StoreFindingKind, str]]:
    return {(f.kind, f.subject) for f in GitStoreGuard().audit(repo.folder).findings}


def _canary_script(canary: Path) -> str:
    return f'#!/bin/sh\nprintf "%s " "$(basename "$0")" >> "{canary}"\n'


def _plant_hook(repo: Repo, name: str, canary: Path) -> Path:
    hooks = repo.folder / ".hse-studio" / "git" / "hooks"
    hooks.mkdir(exist_ok=True)
    hook = hooks / name
    hook.write_text(_canary_script(canary), encoding="utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    return hook


# ── чистое хранилище ─────────────────────────────────────────────────────────
def test__audit__fresh_store__is_trusted(repo: Repo) -> None:
    audit = GitStoreGuard().audit(repo.folder)
    assert audit.trusted
    assert audit.findings == ()


def test__audit__store_with_our_remote_config__is_trusted(repo: Repo) -> None:
    repo.svc.write_remote_config(
        repo.project,
        StoreRemoteConfig(
            url="https://github.com/owner/repo.git", credential_id=uuid4(), local_branch="master", remote_branch="main"
        ),
    )
    _append(repo, '[remote "origin"]\n\tfetch = +refs/heads/main:refs/remotes/origin/main\n')
    _append(repo, '[branch "master"]\n\tremote = origin\n\tmerge = refs/heads/main\n')
    assert GitStoreGuard().audit(repo.folder).trusted


def test__audit__no_store_at_all__is_trusted(tmp_path: Path) -> None:
    assert GitStoreGuard().audit(tmp_path).trusted
    GitStoreGuard().ensure_trusted(tmp_path)
    assert GitStoreGuard().harden(tmp_path) == ()


def test__audit__stock_sample_hooks__are_fine(repo: Repo) -> None:
    hooks = repo.folder / ".hse-studio" / "git" / "hooks"
    assert list(hooks.glob("*.sample"))
    assert GitStoreGuard().audit(repo.folder).trusted


# ── недоверенный config ──────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("section", "label"),
    [
        ("[core]\n\tfsmonitor = /tmp/pwn.sh\n", "core.fsmonitor"),
        ("[core]\n\thooksPath = /tmp/hooks\n", "core.hookspath"),
        ("[core]\n\tsshCommand = /tmp/pwn.sh\n", "core.sshcommand"),
        ("[core]\n\tpager = /tmp/pwn.sh\n", "core.pager"),
        ("[credential]\n\thelper = !/tmp/pwn.sh\n", "credential.helper"),
        ("[alias]\n\tstatus = !/tmp/pwn.sh\n", "alias.status"),
        ('[url "ext::sh -c evil"]\n\tinsteadOf = https://github.com/\n', "url.*.insteadof"),
        ("[include]\n\tpath = /tmp/other.config\n", "include.path"),
        ('[includeIf "gitdir:/"]\n\tpath = /tmp/other.config\n', "includeif.*.path"),
        ('[filter "x"]\n\tclean = /tmp/pwn.sh\n', "filter.*.clean"),
        ('[diff "x"]\n\ttextconv = /tmp/pwn.sh\n', "diff.*.textconv"),
        ('[merge "x"]\n\tdriver = /tmp/pwn.sh\n', "merge.*.driver"),
        ('[remote "evil"]\n\turl = https://evil.example/x.git\n', "remote.*.url"),
        ('[remote "origin"]\n\tpushurl = https://evil.example/x.git\n', "remote.*.pushurl"),
        ('[remote "origin"]\n\tproxy = http://evil.example\n', "remote.*.proxy"),
        ("[http]\n\tproxy = http://evil.example\n", "http.proxy"),
        ("[extensions]\n\tworktreeConfig = true\n", "extensions.worktreeconfig"),
        ("[core]\n\taskPass = /tmp/pwn.sh\n", "core.askpass"),
    ],
)
def test__audit__hostile_config_key__is_flagged(repo: Repo, section: str, label: str) -> None:
    _append(repo, section)
    assert (StoreFindingKind.config_key, label) in _subjects(repo)


def test__audit__finding_subjects_never_carry_values(repo: Repo) -> None:
    _append(repo, f'[url "{_SECRET_URL}"]\n\tinsteadOf = https://github.com/\n')
    _append(repo, "[core]\n\tpager = secret-value-xyz\n")
    audit = GitStoreGuard().audit(repo.folder)
    blob = repr(audit)
    assert "ghp_" not in blob
    assert "secret-value-xyz" not in blob
    assert "evil.example" not in blob


@pytest.mark.parametrize(
    "url",
    [
        "ext::sh -c touch /tmp/pwn",
        "fd::17/foo",
        "-oProxyCommand=evil",
        _SECRET_URL,
        "https://github.com/a b/c.git",
        "javascript://x",
    ],
)
def test__audit__bad_remote_url__is_flagged_as_value(repo: Repo, url: str) -> None:
    _append(repo, f'[remote "origin"]\n\turl = {url}\n')
    assert (StoreFindingKind.config_value, "remote.origin.url") in _subjects(repo)
    assert url not in repr(GitStoreGuard().audit(repo.folder))


@pytest.mark.parametrize(
    "url", ["https://github.com/o/r.git", "ssh://git@github.com/o/r.git", "git@github.com:o/r.git"]
)
def test__audit__ordinary_remote_urls__are_fine(repo: Repo, url: str) -> None:
    _append(repo, f'[remote "origin"]\n\turl = {url}\n')
    assert GitStoreGuard().audit(repo.folder).trusted


@pytest.mark.parametrize("url", ["file:///srv/x.git", "/srv/x.git"])
def test__audit__local_remote__trusted_only_when_local_mode_allows_it(repo: Repo, url: str) -> None:
    _append(repo, f'[remote "origin"]\n\turl = {url}\n')
    assert (StoreFindingKind.config_value, "remote.origin.url") in _subjects(repo)
    assert GitStoreGuard(allow_local=True).audit(repo.folder).trusted


def test__audit__http_remote__trusted_only_when_insecure_http_is_allowed(repo: Repo) -> None:
    _append(repo, '[remote "origin"]\n\turl = http://git.example/o/r.git\n')
    assert (StoreFindingKind.config_value, "remote.origin.url") in _subjects(repo)
    assert GitStoreGuard(allow_http=True).audit(repo.folder).trusted


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("hse.credential", "not-a-uuid"),
        ("hse.localbranch", "--bad"),
        ("hse.remotebranch", "a..b"),
        ("remote.origin.fetch", "+refs/heads/*:refs/evil/*"),
    ],
)
def test__audit__invalid_values_of_allowed_keys__are_flagged(repo: Repo, key: str, value: str) -> None:
    section, _, rest = key.partition(".")
    sub, dot, var = rest.rpartition(".")
    header = f'[{section} "{sub}"]' if dot else f"[{section}]"
    _append(repo, f"{header}\n\t{var if dot else rest} = {value}\n")
    assert (StoreFindingKind.config_value, key) in _subjects(repo)


def test__audit__garbage_config__is_unreadable(repo: Repo) -> None:
    _config(repo).write_text("[core\nthis is not = a config\n\x00\n", encoding="utf-8")
    assert (StoreFindingKind.config_unreadable, "config") in _subjects(repo)


# ── хуки ─────────────────────────────────────────────────────────────────────
@_posix_only
def test__audit__real_hook__is_flagged_by_name(repo: Repo, tmp_path: Path) -> None:
    _plant_hook(repo, "pre-commit", tmp_path / "canary")
    assert (StoreFindingKind.hook, "pre-commit") in _subjects(repo)


def test__audit__hooks_dir_replaced_by_symlink__is_flagged(repo: Repo, tmp_path: Path) -> None:
    hooks = repo.folder / ".hse-studio" / "git" / "hooks"
    target = tmp_path / "elsewhere"
    target.mkdir()
    for child in hooks.iterdir():
        child.unlink()
    hooks.rmdir()
    hooks.symlink_to(target, target_is_directory=True)
    assert (StoreFindingKind.hook, "hooks") in _subjects(repo)


# ── ensure_trusted ───────────────────────────────────────────────────────────
def test__ensure_trusted__hostile_store__raises_store_untrusted(repo: Repo) -> None:
    _append(repo, "[core]\n\tfsmonitor = /tmp/pwn.sh\n")
    with pytest.raises(GitSyncError) as raised:
        GitStoreGuard().ensure_trusted(repo.folder)
    assert raised.value.code is GitErrorCode.store_untrusted


def test__ensure_trusted__clean_store__passes(repo: Repo) -> None:
    GitStoreGuard().ensure_trusted(repo.folder)


# ── harden ───────────────────────────────────────────────────────────────────
def test__harden__strips_everything_outside_the_allow_list(repo: Repo) -> None:
    _append(repo, "[core]\n\tfsmonitor = /tmp/pwn.sh\n\tpager = x\n")
    _append(repo, '[alias]\n\tst = !x\n[url "ext::x"]\n\tinsteadOf = https://a/\n[include]\n\tpath = /tmp/o\n')

    cleaned = GitStoreGuard().harden(repo.folder)

    assert {f.subject for f in cleaned} >= {
        "core.fsmonitor",
        "core.pager",
        "alias.st",
        "url.*.insteadof",
        "include.path",
    }
    assert GitStoreGuard().audit(repo.folder).trusted
    text = _config(repo).read_text(encoding="utf-8")
    assert "fsmonitor" not in text
    assert "ext::" not in text
    assert "include" not in text


def test__harden__keeps_our_remote_config(repo: Repo) -> None:
    credential = uuid4()
    original = StoreRemoteConfig(
        url="https://github.com/o/r.git", credential_id=credential, local_branch="master", remote_branch="main"
    )
    repo.svc.write_remote_config(repo.project, original)
    _append(repo, "[core]\n\tfsmonitor = /tmp/pwn.sh\n")

    GitStoreGuard().harden(repo.folder)

    assert repo.svc.read_remote_config(repo.project) == original
    assert repo.svc.is_initialized(repo.project)
    assert repo.svc.status(repo.project, VcsSettings()).current_branch == "master"


def test__harden__drops_a_remote_url_with_a_token(repo: Repo) -> None:
    _append(repo, f'[remote "origin"]\n\turl = {_SECRET_URL}\n')
    cleaned = GitStoreGuard().harden(repo.folder)
    assert (StoreFindingKind.config_value, "remote.origin.url") in {(f.kind, f.subject) for f in cleaned}
    assert "ghp_" not in _config(repo).read_text(encoding="utf-8")
    assert repo.svc.read_remote_config(repo.project) is None


def test__harden__keeps_the_last_value_of_a_single_valued_key(repo: Repo) -> None:
    repo.svc.write_remote_config(repo.project, StoreRemoteConfig(url="https://github.com/o/r.git"))
    _append(repo, '[remote "origin"]\n\turl = https://github.com/o/second.git\n\tpushurl = https://evil.example/x\n')
    GitStoreGuard().harden(repo.folder)
    remote = repo.svc.read_remote_config(repo.project)
    assert remote is not None
    assert remote.url == "https://github.com/o/second.git"


def test__harden__unreadable_config__is_replaced_by_a_working_one(repo: Repo) -> None:
    _config(repo).write_text("[core\nbroken\n", encoding="utf-8")
    cleaned = GitStoreGuard().harden(repo.folder)
    assert cleaned[0].kind is StoreFindingKind.config_unreadable
    assert GitStoreGuard().audit(repo.folder).trusted
    assert repo.svc.status(repo.project, VcsSettings()).initialized
    repo.snap("works", a="1\n")


@_posix_only
def test__harden__removes_hooks_and_keeps_samples(repo: Repo, tmp_path: Path) -> None:
    canary = tmp_path / "canary"
    hook = _plant_hook(repo, "post-commit", canary)
    _plant_hook(repo, "pre-push", canary)

    cleaned = GitStoreGuard().harden(repo.folder)

    assert {f.subject for f in cleaned} == {"post-commit", "pre-push"}
    assert not hook.exists()
    hooks = hook.parent
    assert hooks.is_dir()
    assert list(hooks.glob("*.sample"))
    assert GitStoreGuard().audit(repo.folder).trusted


def test__harden__replaces_a_hooks_symlink_with_an_empty_directory(repo: Repo, tmp_path: Path) -> None:
    hooks = repo.folder / ".hse-studio" / "git" / "hooks"
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    for child in hooks.iterdir():
        child.unlink()
    hooks.rmdir()
    hooks.symlink_to(target, target_is_directory=True)

    GitStoreGuard().harden(repo.folder)

    assert hooks.is_dir()
    assert not hooks.is_symlink()
    assert (target / "pre-commit").exists()
    assert GitStoreGuard().audit(repo.folder).trusted


def test__harden__clean_store__changes_nothing(repo: Repo) -> None:
    before = _config(repo).read_text(encoding="utf-8")
    assert GitStoreGuard().harden(repo.folder) == ()
    assert _config(repo).read_text(encoding="utf-8") == before


# ── приманки не срабатывают ──────────────────────────────────────────────────
@_posix_only
def test__hostile_store__audit_and_harden_never_execute_the_canary(repo: Repo, tmp_path: Path) -> None:
    canary = tmp_path / "canary"
    fsmonitor = tmp_path / "fsmonitor.sh"
    fsmonitor.write_text(_canary_script(canary) + "printf '\\0'\n", encoding="utf-8")
    fsmonitor.chmod(0o755)
    for name in ("pre-commit", "post-commit", "reference-transaction"):
        _plant_hook(repo, name, canary)
    _append(repo, f"[core]\n\tfsmonitor = {fsmonitor}\n\tsshCommand = {fsmonitor}\n")
    _append(repo, f"[credential]\n\thelper = !{fsmonitor}\n[alias]\n\tstatus = !{fsmonitor}\n")
    _append(repo, f'[filter "x"]\n\tclean = {fsmonitor}\n')

    guard = GitStoreGuard()
    assert not guard.audit(repo.folder).trusted
    with pytest.raises(GitSyncError):
        guard.ensure_trusted(repo.folder)
    guard.harden(repo.folder)
    assert guard.audit(repo.folder).trusted

    repo.snap("after harden", a="1\n")
    repo.svc.status(repo.project, VcsSettings())
    repo.svc.commit(repo.project, message="x", kind=VcsCommitKind.manual, allow_empty=True)
    assert not canary.exists(), canary.read_text(encoding="utf-8") if canary.exists() else ""


# ── хранилище подменено указателем ───────────────────────────────────────────
def _foreign_repo_with_uploadpack(base: Path, canary: Path) -> Path:
    foreign = base / "foreign.git"
    subprocess.run(["git", "init", "--bare", "-q", str(foreign)], check=True)  # noqa: S603, S607
    script = base / "uploadpack.sh"
    script.write_text(_canary_script(canary), encoding="utf-8")
    script.chmod(0o755)
    with (foreign / "config").open("a", encoding="utf-8") as fh:
        fh.write(f'[remote "origin"]\n\tuploadpack = {script}\n')
    return foreign


def _replace_store(repo: Repo, replacement: Path, *, symlink: bool) -> Path:
    git_dir = repo.folder / ".hse-studio" / "git"
    shutil.rmtree(git_dir)
    if symlink:
        git_dir.symlink_to(replacement, target_is_directory=True)
    else:
        git_dir.write_text(f"gitdir: {replacement}\n", encoding="utf-8")
    return git_dir


@_posix_only
@pytest.mark.parametrize("symlink", [False, True], ids=["gitfile", "symlink"])
def test__audit__store_replaced_by_pointer__is_untrusted_and_nothing_runs(
    repo: Repo, tmp_path: Path, symlink: bool
) -> None:
    canary = tmp_path / "canary"
    foreign = _foreign_repo_with_uploadpack(tmp_path, canary)
    _replace_store(repo, foreign, symlink=symlink)

    guard = GitStoreGuard()
    assert (StoreFindingKind.config_unreadable, "git") in _subjects(repo)
    with pytest.raises(GitSyncError) as raised:
        guard.ensure_trusted(repo.folder)
    assert raised.value.code is GitErrorCode.store_untrusted
    assert not canary.exists()


@pytest.mark.parametrize("symlink", [False, True], ids=["gitfile", "symlink"])
def test__harden__store_replaced_by_pointer__drops_the_pointer_and_spares_the_target(
    repo: Repo, tmp_path: Path, symlink: bool
) -> None:
    foreign = _foreign_repo_with_uploadpack(tmp_path, tmp_path / "canary")
    before = (foreign / "config").read_text(encoding="utf-8")
    git_dir = _replace_store(repo, foreign, symlink=symlink)

    cleaned = GitStoreGuard().harden(repo.folder)

    assert [(f.kind, f.subject) for f in cleaned] == [(StoreFindingKind.config_unreadable, "git")]
    assert not git_dir.exists()
    assert not git_dir.is_symlink()
    assert (foreign / "config").read_text(encoding="utf-8") == before
    assert GitStoreGuard().audit(repo.folder).trusted


def test__audit__hse_studio_folder_is_a_symlink__is_untrusted(repo: Repo, tmp_path: Path) -> None:
    moved = tmp_path / "moved"
    (repo.folder / ".hse-studio").rename(moved)
    (repo.folder / ".hse-studio").symlink_to(moved, target_is_directory=True)
    assert (StoreFindingKind.config_unreadable, "git") in _subjects(repo)


def test__harden__symlinked_config_temp_name__does_not_write_outside_the_store(repo: Repo, tmp_path: Path) -> None:
    victim = tmp_path / "victim"
    victim.write_text("precious", encoding="utf-8")
    (repo.folder / ".hse-studio" / "git" / "config.hse-new").symlink_to(victim)
    _append(repo, "[core]\n\tfsmonitor = /tmp/pwn.sh\n")

    GitStoreGuard().harden(repo.folder)

    assert victim.read_text(encoding="utf-8") == "precious"
    assert GitStoreGuard().audit(repo.folder).trusted
