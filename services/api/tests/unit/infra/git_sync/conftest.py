from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from hse_doc_studio.core.enums import VcsCommitKind
from hse_doc_studio.core.vcs.constants import DEFAULT_VCS_EXCLUDE
from hse_doc_studio.core.vcs.entities import VcsAuthor, VcsSettings
from hse_doc_studio.infra.git_sync.store_git import StoreGit
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService

from tests.factories import make_project

_GIT_AVAILABLE = shutil.which("git") is not None


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    skip = pytest.mark.skip(reason="git binary not available")
    for item in items:
        if not _GIT_AVAILABLE and "git_sync" in str(item.fspath):
            item.add_marker(skip)


class _Author:
    def __init__(self) -> None:
        self.current = VcsAuthor("Test Bot", "bot@test.local")

    def author(self) -> VcsAuthor:
        return self.current


class Repo:
    """Хранилище проекта во временной папке и короткие способы нарастить в нём историю."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.authors = _Author()
        self.svc = GitVcsService(author_name="Test Bot", author_email="bot@test.local", author_provider=self.authors)
        self.project = make_project(folder=folder)
        self.git = StoreGit()

    def write(self, path: str, data: str | bytes) -> None:
        target = self.folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            target.write_bytes(data)
        else:
            target.write_text(data, encoding="utf-8")

    def remove(self, path: str) -> None:
        (self.folder / path).unlink()

    def snap(self, message: str = "snap", **files: str | bytes) -> str:
        """Записывает файлы (ключ с `__` вместо `/`), снимает версию и возвращает её sha."""
        for name, data in files.items():
            self.write(name.replace("__", "/"), data)
        commit = self.svc.commit(self.project, message=message, kind=VcsCommitKind.manual)
        assert commit is not None
        return commit.id

    def head(self) -> str:
        return self.git.text(self.folder, ["rev-parse", "HEAD"]).strip()

    def branch(self, name: str, *, switch: bool = True, from_commit: str | None = None) -> None:
        self.svc.create_branch(self.project, VcsSettings(), name=name, from_commit=from_commit, switch=switch)

    def switch(self, name: str) -> None:
        self.svc.switch_branch(self.project, VcsSettings(), name=name)

    def show(self, rev: str, path: str) -> bytes | None:
        proc = self.git.run(self.folder, ["cat-file", "blob", f"{rev}:{path}"], check=False)
        return proc.stdout if proc.returncode == 0 else None


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    folder = tmp_path / "proj"
    folder.mkdir()
    r = Repo(folder)
    r.write("vkr/vkr.tex", "base\n")
    r.svc.init(r.project, list(DEFAULT_VCS_EXCLUDE))
    return r
