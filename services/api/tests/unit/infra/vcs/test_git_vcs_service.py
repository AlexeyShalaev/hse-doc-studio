from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from hse_doc_studio.core.enums import VcsChange, VcsCommitKind, VcsRestoreMode, VcsTagKind
from hse_doc_studio.core.vcs.constants import DEFAULT_VCS_EXCLUDE
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.core.vcs.errors import VcsCommandError, VcsNotInitializedError
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService

from tests.factories import make_project

_GIT_AVAILABLE = shutil.which("git") is not None
pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(not _GIT_AVAILABLE, reason="git binary not available"),
]


def _service() -> GitVcsService:
    return GitVcsService(author_name="Test Bot", author_email="bot@test.local")


def _init_with_files(tmp_path: Path) -> tuple[GitVcsService, object]:
    project = make_project(folder=tmp_path)
    svc = _service()
    (tmp_path / "vkr").mkdir()
    (tmp_path / "vkr" / "vkr.tex").write_text("v1\n", encoding="utf-8")
    svc.init(project, list(DEFAULT_VCS_EXCLUDE))
    return svc, project


def test__init__creates_isolated_store_not_raw_git(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    assert svc.is_initialized(project)
    assert (tmp_path / ".hse-studio" / "git" / "HEAD").exists()
    # No raw .git is created in the project root by us.
    assert not (tmp_path / ".git").exists()


def test__init__root_commit_tracks_sources_and_excludes_junk(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path)
    svc = _service()
    (tmp_path / "vkr").mkdir()
    (tmp_path / "vkr" / "vkr.tex").write_text("hi\n", encoding="utf-8")
    (tmp_path / "vkr" / "vkr.aux").write_text("junk\n", encoding="utf-8")
    (tmp_path / "vkr" / "vkr.pdf").write_bytes(b"%PDF fake")
    (tmp_path / ".build").mkdir()
    (tmp_path / ".build" / "x.log").write_text("log\n", encoding="utf-8")

    svc.init(project, list(DEFAULT_VCS_EXCLUDE))
    commits = svc.log(project)
    assert len(commits) == 1
    assert commits[0].kind == VcsCommitKind.init

    tracked = {f.path for f in svc.commit_detail(project, commits[0].id).files}
    assert tracked == {"vkr/vkr.tex"}  # .aux / .pdf / .build excluded


def test__init__coexists_with_a_user_git(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path)
    svc = _service()
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[user]\n", encoding="utf-8")
    (tmp_path / "doc.tex").write_text("x\n", encoding="utf-8")

    svc.init(project, list(DEFAULT_VCS_EXCLUDE))
    tracked = {f.path for f in svc.commit_detail(project, svc.log(project)[0].id).files}
    assert tracked == {"doc.tex"}  # the user's .git is never tracked


def test__commit__none_when_nothing_changed(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    assert svc.commit(project, message="noop", kind=VcsCommitKind.manual) is None


def test__commit__none_when_only_untracked_pdf_present(tmp_path: Path) -> None:
    # Regression: with a clean tree whose only "change" is an untracked compiled
    # PDF (excluded from `add`), git exits non-zero with "nothing added to commit
    # but untracked files present". That's a no-op, not an error — the snapshot
    # call must return None instead of bubbling up as a 400.
    svc, project = _init_with_files(tmp_path)
    (Path(project.folder) / "vkr" / "vkr.pdf").write_bytes(b"%PDF fresh build")
    assert svc.commit(project, message="noop", kind=VcsCommitKind.manual) is None


def test__commit_and_log__manual_snapshot_appends_history(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    (Path(project.folder) / "vkr" / "vkr.tex").write_text("v2\n", encoding="utf-8")
    commit = svc.commit(project, message="manual edit", kind=VcsCommitKind.manual)
    assert commit is not None
    assert commit.kind == VcsCommitKind.manual
    history = svc.log(project)
    assert [c.kind for c in history] == [VcsCommitKind.manual, VcsCommitKind.init]


def test__status__reflects_dirty_then_clean(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    settings = VcsSettings()
    assert svc.status(project, settings).dirty is False
    (Path(project.folder) / "vkr" / "vkr.tex").write_text("dirty\n", encoding="utf-8")
    dirty = svc.status(project, settings)
    assert dirty.dirty is True
    assert dirty.modified == 1
    assert dirty.current_branch == "master"


def test__status__pdf_changes_ignored_unless_track_pdf(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    (Path(project.folder) / "vkr" / "vkr.pdf").write_bytes(b"new pdf")
    assert svc.status(project, VcsSettings(track_pdf=False)).dirty is False
    assert svc.status(project, VcsSettings(track_pdf=True)).dirty is True


def test__diff__shows_modified_file(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    (Path(project.folder) / "vkr" / "vkr.tex").write_text("v2 changed\n", encoding="utf-8")
    commit = svc.commit(project, message="edit", kind=VcsCommitKind.manual)
    assert commit is not None
    diff = svc.diff(project, to_id=commit.id)
    assert len(diff.files) == 1
    assert diff.files[0].path == "vkr/vkr.tex"
    assert diff.files[0].change == VcsChange.modified
    assert "v2 changed" in diff.files[0].patch


def test__restore__snapshot_mode_reverts_and_keeps_history(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    init_commit = svc.log(project)[0]
    tex = Path(project.folder) / "vkr" / "vkr.tex"
    tex.write_text("v2\n", encoding="utf-8")
    svc.commit(project, message="edit", kind=VcsCommitKind.manual)

    result = svc.restore(project, commit_id=init_commit.id, mode=VcsRestoreMode.snapshot)
    assert result.new_snapshot_id is not None
    assert tex.read_text(encoding="utf-8").strip() == "v1"
    kinds = [c.kind for c in svc.log(project)]
    assert kinds[0] == VcsCommitKind.restore  # new restore commit on top
    assert VcsCommitKind.init in kinds  # original history preserved


def test__restore__autosnapshots_dirty_work_before_reverting(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    init_commit = svc.log(project)[0]
    tex = Path(project.folder) / "vkr" / "vkr.tex"
    tex.write_text("committed v2\n", encoding="utf-8")
    svc.commit(project, message="edit", kind=VcsCommitKind.manual)
    tex.write_text("UNCOMMITTED work\n", encoding="utf-8")  # dirty before restore

    result = svc.restore(project, commit_id=init_commit.id, mode=VcsRestoreMode.snapshot)
    assert result.pre_snapshot_id is not None  # work-in-progress was snapshotted
    assert tex.read_text(encoding="utf-8").strip() == "v1"


def test__commit__raises_when_not_initialized(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path)
    svc = _service()
    with pytest.raises(VcsNotInitializedError):
        svc.commit(project, message="x", kind=VcsCommitKind.manual)


def test__commit_detail__unknown_commit_raises(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    with pytest.raises(VcsCommandError):
        svc.commit_detail(project, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")


# ── branches ──────────────────────────────────────────────────────────────────
def test__list_branches__has_master_after_init(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    branches = svc.list_branches(project)
    assert len(branches) == 1
    assert branches[0].name == "master"
    assert branches[0].is_current is True


def test__create_branch__switches_and_isolates_content(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    tex = Path(project.folder) / "vkr" / "vkr.tex"
    branch = svc.create_branch(project, VcsSettings(), name="draft-2", switch=True)
    assert branch.name == "draft-2"
    assert branch.is_current is True

    tex.write_text("draft-2 work\n", encoding="utf-8")
    svc.commit(project, message="work", kind=VcsCommitKind.manual)
    svc.switch_branch(project, VcsSettings(), name="master")
    assert tex.read_text(encoding="utf-8").strip() == "v1"  # master is untouched


def test__switch_branch__autosnapshots_dirty(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    svc.create_branch(project, VcsSettings(), name="b2", switch=False)
    tex = Path(project.folder) / "vkr" / "vkr.tex"
    tex.write_text("dirty\n", encoding="utf-8")
    svc.switch_branch(project, VcsSettings(), name="b2")
    # the dirty work was committed on master before switching → master's HEAD is the autosnapshot
    svc.switch_branch(project, VcsSettings(), name="master")
    assert tex.read_text(encoding="utf-8").strip() == "dirty"


def test__delete_current_branch_raises(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    with pytest.raises(VcsCommandError):
        svc.delete_branch(project, name="master")


def test__default_branch_is_protected(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    svc.create_branch(project, VcsSettings(), name="feat", switch=True)
    by_name = {b.name: b for b in svc.list_branches(project)}
    assert by_name["master"].is_protected is True
    assert by_name["feat"].is_protected is False


# ── tags ──────────────────────────────────────────────────────────────────────
def test__create_and_list_tags__lightweight_and_release(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    svc.create_tag(project, name="v0.1", kind=VcsTagKind.tag)
    svc.create_tag(project, name="rel-1", kind=VcsTagKind.release, message="первый релиз")
    tags = {t.name: t for t in svc.list_tags(project)}
    assert tags["v0.1"].kind == VcsTagKind.tag
    assert tags["v0.1"].message is None
    assert tags["rel-1"].kind == VcsTagKind.release
    assert tags["rel-1"].message == "первый релиз"


def test__delete_tag__removes_it(tmp_path: Path) -> None:
    svc, project = _init_with_files(tmp_path)
    svc.create_tag(project, name="v0.1", kind=VcsTagKind.tag)
    svc.delete_tag(project, name="v0.1")
    assert svc.list_tags(project) == []
