"""История: отбор по виду, автору, тексту и датам, метки синхронизации, слияния и фасеты (живой git)."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import VcsCommitKind, VcsHistorySync, VcsSyncMarker
from hse_doc_studio.core.git_sync.entities import StoreRemoteConfig
from hse_doc_studio.core.vcs.constants import DEFAULT_VCS_EXCLUDE
from hse_doc_studio.core.vcs.entities import VcsCommit, VcsHistoryQuery
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService, store_git_dir

from tests.factories import make_project

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available"),
]

_ANNA = ("Anna Petrova", "a.petrova@edu.hse.ru")
_MARIA = ("Maria Ivanova", "m.ivanova@edu.hse.ru")
_BRANCH = "main"


def _service(author: tuple[str, str] = _ANNA) -> GitVcsService:
    return GitVcsService(author_name=author[0], author_email=author[1])


def _git(folder: Path, args: list[str], env: dict[str, str] | None = None) -> str:
    return subprocess.run(  # noqa: S603
        ["git", "--git-dir", str(store_git_dir(folder)), *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout.strip()


def _snap(svc: GitVcsService, project: Project, message: str, kind: VcsCommitKind = VcsCommitKind.edit) -> VcsCommit:
    commit = svc.commit(project, message=message, kind=kind, allow_empty=True)
    assert commit is not None
    return commit


def _raw_commit(folder: Path, message: str, author: tuple[str, str] = _ANNA, date: str | None = None) -> None:
    """Коммит без трейлера Hse-Kind, как делает чужая Студия или человек с git."""
    env = {
        "PATH": os.environ["PATH"],
        "GIT_AUTHOR_NAME": author[0],
        "GIT_AUTHOR_EMAIL": author[1],
        "GIT_COMMITTER_NAME": author[0],
        "GIT_COMMITTER_EMAIL": author[1],
    }
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    _git(folder, ["--work-tree", str(folder), "commit", "--allow-empty", "-m", message], env)


@pytest.fixture
def svc() -> GitVcsService:
    return _service()


@pytest.fixture
def project(tmp_path: Path, svc: GitVcsService) -> Project:
    folder = tmp_path / "proj"
    folder.mkdir()
    proj = make_project(folder=folder)
    svc.init(proj, list(DEFAULT_VCS_EXCLUDE))
    return proj


def _ids(commits: list[VcsCommit]) -> list[str]:
    return [c.message for c in commits]


def test__log__author_email_and_merge_flag_are_filled(svc: GitVcsService, project: Project) -> None:
    commit = _snap(svc, project, "Правка")

    [newest, root] = svc.log(project)

    assert newest.id == commit.id
    assert newest.author_email == _ANNA[1]
    assert not newest.is_merge
    assert root.sync is None
    assert newest.sync is None


def test__log__is_merge_follows_parent_count(svc: GitVcsService, project: Project, tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    base = _git(folder, ["rev-parse", "HEAD"])
    side = _snap(svc, project, "Ветка")
    tree = _git(folder, ["rev-parse", "HEAD^{tree}"])
    merge = _git(
        folder,
        ["-c", f"user.name={_ANNA[0]}", "-c", f"user.email={_ANNA[1]}", "commit-tree", tree]
        + ["-p", base, "-p", side.id, "-m", "Слияние\n\nHse-Kind: sync"],
    )
    _git(folder, ["update-ref", "HEAD", merge])

    top = svc.log(project, limit=1)[0]

    assert top.id == merge
    assert top.is_merge
    assert top.kind is VcsCommitKind.sync
    assert not svc.log(project)[1].is_merge


def test__log__filters_by_kind(svc: GitVcsService, project: Project) -> None:
    _snap(svc, project, "e1", VcsCommitKind.edit)
    _snap(svc, project, "c1", VcsCommitKind.compile)
    _snap(svc, project, "e2", VcsCommitKind.edit)
    _snap(svc, project, "r1", VcsCommitKind.restore)

    edits = svc.log(project, query=VcsHistoryQuery(kinds=("edit",)))
    mixed = svc.log(project, query=VcsHistoryQuery(kinds=("edit", "compile")))

    assert _ids(edits) == ["e2", "e1"]
    assert _ids(mixed) == ["e2", "c1", "e1"]


def test__log__manual_kind_includes_commits_without_trailer_and_unknown_kinds(
    svc: GitVcsService, project: Project, tmp_path: Path
) -> None:
    _snap(svc, project, "edit", VcsCommitKind.edit)
    _snap(svc, project, "manual", VcsCommitKind.manual)
    _raw_commit(tmp_path / "proj", "plain")
    _raw_commit(tmp_path / "proj", "future\n\nHse-Kind: from-the-future")

    manual = svc.log(project, query=VcsHistoryQuery(kinds=("manual",)))
    future = svc.log(project, query=VcsHistoryQuery(kinds=("from-the-future",)))
    mixed = svc.log(project, query=VcsHistoryQuery(kinds=("manual", "edit")))

    assert _ids(manual) == ["future", "plain", "manual"]
    assert _ids(future) == ["future"]
    assert _ids(mixed) == ["future", "plain", "manual", "edit"]
    assert svc.log(project, query=VcsHistoryQuery(kinds=("manual",)))[0].kind is VcsCommitKind.manual


@pytest.mark.parametrize("kinds", [("edit",), ("manual",)], ids=["git_path", "python_path"])
def test__log__paging_applies_after_the_filter(svc: GitVcsService, project: Project, kinds: tuple[str, ...]) -> None:
    kind = VcsCommitKind(kinds[0])
    for i in range(5):
        _snap(svc, project, f"{kind.value}{i}", kind)
        _snap(svc, project, f"other{i}", VcsCommitKind.compile)
    query = VcsHistoryQuery(kinds=kinds)

    page1 = svc.log(project, limit=2, offset=0, query=query)
    page2 = svc.log(project, limit=2, offset=2, query=query)
    tail = svc.log(project, limit=10, offset=4, query=query)

    assert all(c.kind is kind for c in [*page1, *page2, *tail])
    assert _ids(page1)[0].endswith("4")
    assert len({c.id for c in [*page1, *page2]}) == 4
    assert _ids(page1)[-1] != _ids(page2)[0]
    assert len(tail) == 1


def test__log__filters_by_author_email_exactly(svc: GitVcsService, project: Project, tmp_path: Path) -> None:
    _snap(svc, project, "anna")
    _raw_commit(tmp_path / "proj", "maria\n\nHse-Kind: edit", _MARIA)
    _raw_commit(tmp_path / "proj", "lookalike", ("Fake", "xm.ivanova@edu.hse.ru.evil"))

    by_maria = svc.log(project, query=VcsHistoryQuery(author_email="M.Ivanova@edu.hse.ru"))
    by_partial = svc.log(project, query=VcsHistoryQuery(author_email="ivanova"))

    assert _ids(by_maria) == ["maria"]
    assert by_partial == []


def test__log__text_is_a_literal_case_insensitive_substring(svc: GitVcsService, project: Project) -> None:
    _snap(svc, project, "Правки введения (черновик)")
    _snap(svc, project, "Сборка v1.2")
    _snap(svc, project, "Сборка v1x2")

    assert _ids(svc.log(project, query=VcsHistoryQuery(text="ВВЕДЕНИЯ"))) == ["Правки введения (черновик)"]
    assert _ids(svc.log(project, query=VcsHistoryQuery(text="(черновик)"))) == ["Правки введения (черновик)"]
    assert _ids(svc.log(project, query=VcsHistoryQuery(text="v1.2"))) == ["Сборка v1.2"]
    assert svc.log(project, query=VcsHistoryQuery(text=".*")) == []


def test__log__filters_by_date_range(svc: GitVcsService, project: Project, tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    _raw_commit(folder, "old\n\nHse-Kind: edit", date="2026-01-10T10:00:00+00:00")
    _raw_commit(folder, "mid\n\nHse-Kind: edit", date="2026-02-10T10:00:00+00:00")
    _raw_commit(folder, "new\n\nHse-Kind: edit", date="2026-03-10T10:00:00+00:00")
    utc = timezone.utc

    window = svc.log(
        project, query=VcsHistoryQuery(since=datetime(2026, 2, 1, tzinfo=utc), until=datetime(2026, 3, 1, tzinfo=utc))
    )
    naive = svc.log(project, query=VcsHistoryQuery(since=datetime(2026, 3, 1)))  # noqa: DTZ001
    shifted = svc.log(
        project,
        query=VcsHistoryQuery(
            since=datetime(2026, 2, 10, 13, 0, tzinfo=timezone(timedelta(hours=3))),
            until=datetime(2026, 2, 11, tzinfo=utc),
        ),
    )

    assert _ids(window) == ["mid"]
    assert _ids(naive) == ["new"]
    assert _ids(shifted) == ["mid"]


def test__log__combined_filters_all_apply(svc: GitVcsService, project: Project, tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    _raw_commit(folder, "Введение\n\nHse-Kind: edit", _ANNA)
    _raw_commit(folder, "Введение\n\nHse-Kind: edit", _MARIA)
    _raw_commit(folder, "Введение\n\nHse-Kind: compile", _MARIA)
    _raw_commit(folder, "Заключение\n\nHse-Kind: edit", _MARIA)

    found = svc.log(project, query=VcsHistoryQuery(kinds=("edit",), text="введение", author_email=_MARIA[1]))
    only_kind_and_text = svc.log(project, query=VcsHistoryQuery(kinds=("compile",), text="введение"))
    python_kinds = svc.log(
        project, query=VcsHistoryQuery(kinds=("manual", "edit"), text="введение", author_email=_ANNA[1])
    )

    assert [(c.author_email, c.kind) for c in found] == [(_MARIA[1], VcsCommitKind.edit)]
    assert [c.kind for c in only_kind_and_text] == [VcsCommitKind.compile]
    assert [c.author_email for c in python_kinds] == [_ANNA[1]]


def test__log__doc_pathspec_still_combines_with_filters(svc: GitVcsService, project: Project, tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    (folder / "thesis").mkdir()
    (folder / "thesis" / "t.tex").write_text("x\n", encoding="utf-8")
    svc.commit(project, message="doc", kind=VcsCommitKind.edit)
    _snap(svc, project, "elsewhere", VcsCommitKind.edit)

    found = svc.log(project, doc_id="thesis", query=VcsHistoryQuery(kinds=("edit",)))

    assert _ids(found) == ["doc"]


def test__history_facets__counts_kinds_and_authors(svc: GitVcsService, project: Project, tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    _snap(svc, project, "e1", VcsCommitKind.edit)
    _raw_commit(folder, "m1\n\nHse-Kind: edit", _MARIA)
    _raw_commit(folder, "m2\n\nHse-Kind: sync", ("M. Ivanova (new name)", _MARIA[1].upper()))
    _raw_commit(folder, "plain", ("Nobody", ""))
    _raw_commit(folder, "future\n\nHse-Kind: from-the-future", _ANNA)

    facets = svc.history_facets(project)

    assert facets.kinds == {"init": 1, "edit": 2, "sync": 1, "manual": 2}
    assert [(a.name, a.email, a.count) for a in facets.authors] == [
        (_ANNA[0], _ANNA[1], 3),
        ("M. Ivanova (new name)", _MARIA[1].upper(), 2),
        ("Nobody", None, 1),
    ]


def test__history_facets__empty_store_and_missing_store(svc: GitVcsService, tmp_path: Path) -> None:
    folder = tmp_path / "bare"
    folder.mkdir()
    proj = make_project(folder=folder)

    assert svc.history_facets(proj).kinds == {}
    svc.init_bare_store(folder, _BRANCH)
    facets = svc.history_facets(proj)
    assert facets.kinds == {}
    assert facets.authors == ()


# --- метки синхронизации ------------------------------------------------------


class _Remote:
    """Локальный bare-репозиторий как удалённый: общий для двух «пользователей»."""

    def __init__(self, root: Path) -> None:
        self.bare = root / "remote.git"
        subprocess.run(["git", "init", "--bare", "-b", _BRANCH, str(self.bare)], check=True, capture_output=True)  # noqa: S603, S607
        self.url = self.bare.as_uri()

    def push(self, folder: Path, ref: str = "HEAD") -> None:
        _git(folder, ["push", self.url, f"{ref}:refs/heads/{_BRANCH}"])

    def fetch(self, folder: Path) -> None:
        _git(folder, ["fetch", self.url, f"+refs/heads/{_BRANCH}:refs/remotes/origin/{_BRANCH}"])

    def connect(self, svc: GitVcsService, project: Project) -> None:
        svc.write_remote_config(
            project,
            StoreRemoteConfig(url=self.url, local_branch="master", remote_branch=_BRANCH),
        )

    def teammate_commit(self, root: Path, message: str) -> str:
        clone = root / "teammate"
        if not clone.exists():
            subprocess.run(["git", "clone", "-q", str(self.bare), str(clone)], check=True, capture_output=True)  # noqa: S603, S607
            subprocess.run(["git", "-C", str(clone), "checkout", "-q", "-B", _BRANCH], check=True, capture_output=True)  # noqa: S603, S607
        subprocess.run(  # noqa: S603
            [  # noqa: S607
                "git",
                "-C",
                str(clone),
                "-c",
                f"user.name={_MARIA[0]}",
                "-c",
                f"user.email={_MARIA[1]}",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                message,
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "-C", str(clone), "push", "-q", "origin", _BRANCH], check=True, capture_output=True)  # noqa: S603, S607
        return subprocess.run(  # noqa: S603
            ["git", "-C", str(clone), "rev-parse", "HEAD"],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()


@pytest.fixture
def remote(tmp_path: Path) -> _Remote:
    return _Remote(tmp_path)


def _markers(commits: list[VcsCommit]) -> dict[str, VcsSyncMarker | None]:
    return {c.message: c.sync for c in commits}


def test__sync_markers__are_none_without_remote_or_before_the_first_fetch(
    svc: GitVcsService, project: Project, remote: _Remote
) -> None:
    _snap(svc, project, "local")
    assert {c.sync for c in svc.log(project)} == {None}

    remote.connect(svc, project)

    assert {c.sync for c in svc.log(project)} == {None}
    assert svc.log(project, query=VcsHistoryQuery(sync=VcsHistorySync.unpushed)) == []
    assert svc.log(project, query=VcsHistoryQuery(sync=VcsHistorySync.incoming)) == []
    assert len(svc.log(project, query=VcsHistoryQuery(sync=VcsHistorySync.all))) == 2


def test__sync_markers__pushed_unpushed_and_incoming(
    svc: GitVcsService, project: Project, remote: _Remote, tmp_path: Path
) -> None:
    folder = tmp_path / "proj"
    remote.connect(svc, project)
    _snap(svc, project, "shared")
    remote.push(folder)
    remote.teammate_commit(tmp_path, "from maria")
    _snap(svc, project, "mine 1")
    _snap(svc, project, "mine 2")
    remote.fetch(folder)

    default = svc.log(project)
    everything = svc.log(project, query=VcsHistoryQuery(sync=VcsHistorySync.all))

    assert _markers(default) == {
        "mine 2": VcsSyncMarker.unpushed,
        "mine 1": VcsSyncMarker.unpushed,
        "shared": VcsSyncMarker.pushed,
        "Создание проекта": VcsSyncMarker.pushed,
    }
    assert "from maria" not in _markers(default)
    assert _markers(everything)["from maria"] is VcsSyncMarker.incoming
    assert _markers(everything)["mine 1"] is VcsSyncMarker.unpushed
    assert _markers(everything)["shared"] is VcsSyncMarker.pushed
    incoming = next(c for c in everything if c.message == "from maria")
    assert incoming.author_email == _MARIA[1]


def test__sync_filter__unpushed_and_incoming_return_only_their_commits(
    svc: GitVcsService, project: Project, remote: _Remote, tmp_path: Path
) -> None:
    folder = tmp_path / "proj"
    remote.connect(svc, project)
    remote.push(folder)
    remote.teammate_commit(tmp_path, "from maria")
    _snap(svc, project, "mine")
    remote.fetch(folder)

    unpushed = svc.log(project, query=VcsHistoryQuery(sync=VcsHistorySync.unpushed))
    incoming = svc.log(project, query=VcsHistoryQuery(sync=VcsHistorySync.incoming))
    both_filters = svc.log(
        project, query=VcsHistoryQuery(sync=VcsHistorySync.incoming, author_email=_MARIA[1], kinds=("manual",))
    )

    assert _ids(unpushed) == ["mine"]
    assert _markers(unpushed) == {"mine": VcsSyncMarker.unpushed}
    assert _ids(incoming) == ["from maria"]
    assert _markers(incoming) == {"from maria": VcsSyncMarker.incoming}
    assert _ids(both_filters) == ["from maria"]


def test__sync_markers__everything_is_pushed_after_the_remote_catches_up(
    svc: GitVcsService, project: Project, remote: _Remote, tmp_path: Path
) -> None:
    folder = tmp_path / "proj"
    remote.connect(svc, project)
    _snap(svc, project, "mine")
    remote.push(folder)
    remote.fetch(folder)

    assert {c.sync for c in svc.log(project)} == {VcsSyncMarker.pushed}
    assert svc.log(project, query=VcsHistoryQuery(sync=VcsHistorySync.unpushed)) == []


def test__sync_incoming__works_while_the_local_branch_is_unborn(
    svc: GitVcsService, remote: _Remote, tmp_path: Path
) -> None:
    folder = tmp_path / "cloned"
    folder.mkdir()
    proj = make_project(folder=folder)
    svc.init_bare_store(folder, "master")
    remote.teammate_commit(tmp_path, "first")
    remote.connect(svc, proj)
    remote.fetch(folder)

    incoming = svc.log(proj, query=VcsHistoryQuery(sync=VcsHistorySync.incoming))
    unpushed = svc.log(proj, query=VcsHistoryQuery(sync=VcsHistorySync.unpushed))

    assert _ids(incoming) == ["first"]
    assert unpushed == []
    assert svc.log(proj) == []


def test__history_facets__include_incoming_commits(
    svc: GitVcsService, project: Project, remote: _Remote, tmp_path: Path
) -> None:
    folder = tmp_path / "proj"
    remote.connect(svc, project)
    remote.push(folder)
    remote.teammate_commit(tmp_path, "from maria")
    remote.fetch(folder)

    facets = svc.history_facets(project)

    assert {a.email: a.count for a in facets.authors} == {_ANNA[1]: 1, _MARIA[1]: 1}
